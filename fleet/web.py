"""HTTP API 와 대시보드 화면."""
import json
import mimetypes
import os
import re
import signal
import sqlite3
import threading
from collections import Counter
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .agents import find_session, graph, mcp_servers, reopen, session
from .card import card_svg, tokens_svg
from .config import CFG, CONFIG, ORIGIN, VERSION, claude, installed_version, ver
from .db import EDIT, db, delete_session, metrics, my_title, saved_settings, set_setting, set_title
from .links import LinkError, check as check_link, github_prs, jira_issue, jira_issues
from .pushes import pushes
from .tasks import TASKS_SQL, add_task, move_task, saved_tasks, set_task, summarize
from .usage import usage, usage5h_all


def agent_task(body):
    """MCP 서버가 보낸 작업 기록 {op: start|update|list, sid, ...}. DB 는 이 서버만 쓴다."""
    sid, op = body.get("sid") or "", body.get("op")
    if not re.fullmatch(r"[0-9a-f-]{36}", sid):
        return {"error": "세션 ID 확인"}, 400
    if op == "start" and isinstance(body.get("text"), str) and body["text"].strip():
        return {"id": add_task(sid, body["text"][:160], "agent", tag=body.get("tag"), details=body.get("details"))}, 200
    if op == "update":
        ok = set_task(body.get("id"), "agent", body.get("status"), note=body.get("note"), sid=sid, details=body.get("details"))
        return ({"ok": True}, 200) if ok else ({"error": "이 세션의 작업 id 가 아니거나 분류가 잘못됐습니다"}, 400)
    if op == "list":
        return {"tasks": saved_tasks(sid)[0]}, 200
    return {"error": "op 확인 (start·update·list)"}, 400


JIRA_KEY = re.compile(r"[A-Z][A-Z0-9_]+-\d+")


def guess_cwd(key):
    """이슈를 맡길 폴더를 지난 세션 기록(이름·제목)으로 고른다: 같은 이슈 → 같은 프로젝트 키(QA-) 를 가장 많이 한 폴더 → 최근 폴더.
    맡길 때 세션 이름을 '키 제목' 으로 붙이므로, 맡길수록 잘 맞는다."""
    c = db()
    rows = [r for r in c.execute("SELECT name, coalesce(my_title, title), cwd FROM sessions WHERE cwd IS NOT NULL"
                                 " ORDER BY last_seen DESC") if os.path.isdir(r[2])]
    c.close()
    recent = list(dict.fromkeys(r[2] for r in rows))
    proj = key.split("-")[0]
    for why, pat in (("같은 이슈를 했던 폴더", rf"\b{key}\b"), (f"{proj} 이슈를 가장 많이 한 폴더", rf"\b{proj}-\d+")):
        hit = Counter(r[2] for r in rows if re.search(pat, f"{r[0]} {r[1]}"))
        if hit:
            cwd = hit.most_common(1)[0][0]
            return {"cwd": cwd, "why": why, "recent": [cwd] + [d for d in recent if d != cwd][:9]}
    return {"cwd": recent[0] if recent else "", "why": "기록이 없어 최근 폴더", "recent": recent[:10]}


def assign_prompt(i):
    body = i["body"][:4000] or "(본문 없음)"
    return (f"{i['key']} 「{i['title']}」 Jira 이슈를 맡아 처리해 줘. {i['url']}\n\n[이슈 본문]\n{body}\n\n"
            "먼저 코드를 살펴 무엇을 바꿀지 계획을 세우고 진행해. 커밋·push 는 하지 말고, 끝나면 바꾼 것과 확인한 것을 정리해 줘.")


DIST = (Path(__file__).parent.parent / "dist").resolve()  # web/ 의 React 빌드 결과


class H(BaseHTTPRequestHandler):
    def send(self, body, ctype="application/json", code=200):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        if u.path == "/" or u.path.startswith("/assets/"):
            f = (DIST / (u.path.lstrip("/") or "index.html")).resolve()
            if f.is_relative_to(DIST) and f.is_file():  # ../ 로 dist 밖을 읽지 못하게
                return self.send(f.read_bytes(), mimetypes.guess_type(f.name)[0] or "application/octet-stream")
        if u.path == "/api/version":  # 화면을 띄운 리더의 버전과 설치된 버전 — 다르면 화면이 알리고, 바뀌면 새로 고친다
            return self.send({"version": VERSION, "installed": installed_version()})
        if u.path in ("/api/jira", "/api/github"):  # 이슈·PR 페이지 — 둘을 따로 받아 한쪽이 실패해도 다른 쪽은 보인다
            try:
                return self.send({"items": jira_issues()} if u.path == "/api/jira" else github_prs())
            except LinkError as e:
                return self.send({"error": str(e)})
        if u.path == "/api/assign":  # ?key=QA-3001 — 맡길 폴더 추천과 고를 수 있는 최근 폴더
            return self.send(guess_cwd(q["key"]) if JIRA_KEY.fullmatch(q.get("key", "")) else {"error": "이슈 키 확인"})
        if u.path == "/api/graph":
            return self.send(graph())
        if u.path == "/api/config":
            saved = saved_settings()  # src: screen 화면에서 바꿈 · env 환경 변수 · default 기본값
            hide = lambda k, v: ("****" + v[-4:] if v else "") if k.endswith("_TOKEN") else v  # 토큰은 끝 4글자만
            return self.send([{"name": k, "value": hide(k, CFG[k]), "default": hide(k, d), "desc": desc, "edit": k in EDIT,
                               "secret": k.endswith("_TOKEN"),
                               "src": "screen" if k in saved else "env" if k in os.environ else "default"}
                              for k, d, desc in CONFIG])
        if u.path == "/api/sessions":  # ?status=closed|work|wait|idle (없으면 전체) &limit=
            c = db()
            c.row_factory = sqlite3.Row
            st = q.get("status")
            out = [dict(r) for r in c.execute(
                "SELECT * FROM sessions WHERE status IS NOT NULL AND deleted_at IS NULL" + (" AND status = ?" if st else "")
                + " ORDER BY coalesce(ended_at, last_seen) DESC LIMIT ?", (*([st] if st else []), int(q.get("limit", 50))))]
            for s in out:
                s["title"] = s["my_title"] or s["title"]
                s["tasks"] = [dict(r) for r in c.execute(
                    TASKS_SQL, (s["sid"],))]
            c.close()
            return self.send(out)
        if u.path == "/api/todo":  # 남은 일 — 끝난 세션 것도 포함 (지운 세션 것은 뺀다)
            c = db()
            c.row_factory = sqlite3.Row
            out = [dict(r) for r in c.execute(
                "SELECT t.id, t.sid, t.status, t.text, t.source, t.tag, t.details, coalesce(s.my_title, s.title) AS title, s.name, s.cwd, s.status AS sst"
                " FROM session_tasks t JOIN sessions s USING (sid) WHERE t.status = 'todo' AND s.deleted_at IS NULL"
                " ORDER BY coalesce(s.ended_at, s.last_seen) DESC, t.sort, t.id")]
            c.close()
            return self.send(out)
        if u.path == "/api/daily":
            c = db()
            rows = c.execute("SELECT day, tokens FROM daily WHERE day >= date('now', '-371 days')").fetchall()
            c.close()
            return self.send(dict(rows))
        if u.path == "/api/metrics":
            return self.send(metrics(float(q.get("hours", 24))))
        if u.path == "/api/usage":
            return self.send(usage())
        if u.path == "/api/mcp":
            return self.send(mcp_servers(q.get("refresh") == "1"))
        if u.path == "/api/pushes":  # Claude 가 한 git push 목록 (?limit= &sid= 그 세션 것만)
            return self.send(pushes(int(q.get("limit", 200)), q.get("sid")))
        if u.path == "/api/card.svg":  # Gist 에 올리는 프로필 카드 미리보기
            return self.send(card_svg().encode(), "image/svg+xml")
        if u.path == "/api/tokens.svg":  # 같은 Gist 에 올리는 1년 토큰 잔디 미리보기
            return self.send(tokens_svg().encode(), "image/svg+xml")
        if u.path == "/api/usage5h":
            return self.send(usage5h_all())
        if u.path == "/api/session":
            se = session(q.get("sid", ""))
            if t := my_title(q.get("sid", "")):
                se["overview"] = {**se.get("overview", {}), "title": t}
            return self.send({**se, "tasks": saved_tasks(q.get("sid", ""))[0]})
        if u.path == "/api/logs":
            return self.send({"text": claude("logs", q.get("id", ""))})
        self.send({"error": "not found"}, code=404)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or "{}")
        # MCP 서버의 작업 기록. 브라우저는 POST 에 Origin 을 꼭 붙이므로, Origin 이 없으면 브라우저(다른 웹사이트)가 아니다
        # 새 버전 대기자(다른 세션의 MCP 서버)가 자리를 넘겨 달라고 한다 {version}. 더 새 버전일 때만 물러난다
        if self.path == "/api/handover" and "Origin" not in self.headers:
            if ver(body.get("version")) <= ver(VERSION):
                return self.send({"error": "더 새 버전이 아닙니다"}, code=409)
            self.send({"ok": True})
            return threading.Thread(target=self.server.shutdown, daemon=True).start()  # serve_forever 가 끝나면 serve() 가 포트를 닫는다
        if self.path == "/api/agent/task" and "Origin" not in self.headers:
            out, code = agent_task(body)
            return self.send(out, code=code)
        # 다른 웹사이트가 localhost 로 실행 요청을 보내는 것(CSRF) 차단
        if self.headers.get("Origin") != ORIGIN:
            return self.send({"error": "bad origin"}, code=403)
        if self.path == "/api/connect":  # {service: github|jira} — 저장된 토큰으로 내 계정 이름을 받아 와 연결을 확인한다
            try:
                return self.send({"ok": True, "who": check_link(body.get("service"))})
            except LinkError as e:
                return self.send({"error": str(e)})
        if self.path == "/api/assign":  # {key, cwd} — Jira 이슈를 그 폴더의 새 백그라운드 에이전트에게. 세션 이름은 '키 제목'
            cwd = os.path.expanduser(body.get("cwd", ""))
            if not JIRA_KEY.fullmatch(body.get("key", "")) or not os.path.isdir(cwd):
                return self.send({"error": "이슈 키·폴더 확인"}, code=400)
            try:
                i = jira_issue(body["key"])
            except LinkError as e:
                return self.send({"error": str(e)})
            return self.send({"text": claude("--bg", "-n", f"{i['key']} {i['title']}"[:60], assign_prompt(i), cwd=cwd)})
        if self.path == "/api/config":  # {name, value} — EDIT 에 있는 설정만. 빈 값이면 환경 변수·기본값으로
            err = set_setting(body.get("name"), body.get("value"))
            return self.send({"error": err} if err else {"ok": True})
        if self.path == "/api/run":
            cwd = os.path.expanduser(body.get("cwd", ""))
            if not os.path.isdir(cwd) or not body.get("prompt"):
                return self.send({"error": "cwd/prompt 확인"}, code=400)
            return self.send({"text": claude("--bg", body["prompt"], cwd=cwd)})
        if self.path == "/api/reopen":  # {sid, fork?} — 끝난 세션을 새 터미널 창에서 claude --resume 으로 연다
            out, code = reopen(body.get("sid", ""), bool(body.get("fork")))
            return self.send(out, code=code)
        if self.path == "/api/task" and "to" in body:  # {id, to} — 남은 일을 살아 있는 세션으로 옮긴다
            if not find_session(body["to"] or ""):
                return self.send({"error": "살아 있는 세션으로만 옮길 수 있습니다"})
            return self.send({"ok": True} if move_task(body.get("id"), body["to"]) else {"error": "남은 일만 옮길 수 있습니다"})
        if self.path == "/api/task":  # {id, status?, tag?, sort?, delete?} — 사람이 웹에서 고친다
            ok = set_task(body.get("id"), "human", body.get("status"), sort=body.get("sort"), delete=bool(body.get("delete")),
                          tag=body.get("tag"))
            return self.send({"ok": ok} if ok else {"error": "작업 또는 분류 확인"})
        if self.path == "/api/session/delete":  # {sid} — 끝난 세션을 세션 기록에서 지운다 (soft delete)
            return self.send({"ok": True} if delete_session(body.get("sid")) else {"error": "끝난 세션만 지울 수 있습니다"})
        if self.path == "/api/title":  # {sid, title} — 대시보드에서만 쓰는 제목. 빈 값이면 원래대로
            return self.send({"ok": True} if set_title(body.get("sid"), body.get("title")) else {"error": "세션 확인"})
        if self.path == "/api/summary":  # 토큰을 쓰므로 GET 이 아닌 POST (출처 검사 대상)
            return self.send(summarize(body.get("sid", "")))
        if self.path != "/api/stop":
            return self.send({"error": "not found"}, code=404)
        s = find_session(body.get("sid", ""))
        if not s:
            return self.send({"error": "실행 중인 세션이 아님"}, code=404)
        if s["kind"] == "background":
            return self.send({"text": claude("stop", s["id"])})
        os.kill(s["pid"], signal.SIGTERM)
        return self.send({"text": f"{s.get('name')} 종료 신호 보냄"})
