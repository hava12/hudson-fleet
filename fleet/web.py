"""HTTP API 와 대시보드 화면."""
import json
import mimetypes
import os
import re
import signal
import sqlite3
import subprocess
import sys
import threading
from collections import Counter
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .agents import find_session, graph, mcp_servers, reopen, session
from .card import card_svg, tokens_svg
from .config import CFG, CONFIG, PORT, VERSION, claude, installed, installed_version, ver
from .db import DB, EDIT, db, delete_session, metrics, my_title, saved_settings, set_setting, set_title
from .links import LinkError, check as check_link, github_prs, jira_issue, jira_issues
from .para import (agent_view, archive_project, delete_resource, has_project, make_project_flow, names, para, save_area, save_project,
                   save_resource, search_resources)
from .pushes import pushes
from .routines import make_map, maps, refresh as refresh_routines, saved as saved_routines, session_schedules
from .tasks import TASKS_SQL, add_task, move_task, norm_flow, saved_tasks, set_task, summarize
from .usage import usage, usage5h_all


def agent_task(body):
    """MCP 서버가 보낸 작업 기록 {op: start|update|list, sid, ...}. DB 는 이 서버만 쓴다."""
    sid, op = body.get("sid") or "", body.get("op")
    if not re.fullmatch(r"[0-9a-f-]{36}", sid):
        return {"error": "세션 ID 확인"}, 400
    pj = body.get("project")
    if pj and not has_project(pj):  # 0 은 task_update 에서 "프로젝트 빼기"
        return {"error": f"없는 프로젝트 id 입니다: {pj}. project_list 로 확인하세요"}, 400
    if op == "start" and isinstance(body.get("text"), str) and body["text"].strip():
        tid = add_task(sid, body["text"][:160], "agent", tag=body.get("tag"), details=body.get("details"), project=pj)
        # 프로젝트 없이 적었으면 진행 중인 프로젝트를 돌려준다 — 세션이 열린 뒤 만든 프로젝트도 에이전트가 알게
        ps = not pj and agent_view()["projects"]
        return ({"id": tid, "projects": ps, "hint": f'이 일이 이 중 한 프로젝트의 일이면 task_update(id={tid}, status="todo",'
                 ' project=번호) 로 적으세요. 없으면 그대로 둡니다'} if ps else {"id": tid}), 200
    if op == "update":
        try:  # 코드를 바꾼 일을 끝낼 때 남기는 흐름도 — 형식이 틀리면 에이전트가 고쳐 다시 보내게 알린다
            flow = norm_flow(body["flow"]) if body.get("flow") else None
        except ValueError as e:
            return {"error": f"{e}. flow 는 {{trigger, steps: [{{title, detail, branch?}}], outputs}} 모양입니다"}, 400
        ok = set_task(body.get("id"), "agent", body.get("status"), note=body.get("note"), details=body.get("details"),
                      project=pj, flow=flow)
        return ({"ok": True}, 200) if ok else ({"error": "없는 작업 id 이거나 분류가 잘못됐습니다"}, 400)
    if op == "list":
        return {"tasks": saved_tasks(sid)[0]}, 200
    if op == "projects":
        return agent_view(), 200
    if op == "project_archive":
        err = archive_project(body.get("id"))
        return ({"error": err}, 400) if err else ({"ok": True}, 200)
    if op == "resource_save":
        r = save_resource(body, sid)
        return ({"id": r}, 200) if isinstance(r, int) else ({"error": r}, 400)
    if op == "resource_search":
        return {"resources": search_resources(body.get("query"))}, 200
    return {"error": "op 확인 (start·update·list·projects·project_archive·resource_save·resource_search)"}, 400


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
# Host 가 다른 이름이면 거절한다 — DNS 리바인딩(악성 사이트가 자기 도메인을 127.0.0.1 로 바꿔치기)으로 화면·API 를 읽지 못하게
HOSTS = ("127.0.0.1", "localhost")
ORIGINS = {f"http://{h}:{PORT}" for h in HOSTS}


class H(BaseHTTPRequestHandler):
    def send(self, body, ctype="application/json", code=200):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self.safe(self.get)

    def do_POST(self):
        self.safe(self.post)

    def safe(self, fn):
        """요청 하나를 처리한다. 처리 중 예외에도 JSON 으로 답한다 — 연결만 끊으면 화면은 서버가 꺼진 줄 알고,
        에이전트(MCP)는 같은 기록을 다시 보낼 수 있다."""
        # 다른 웹사이트가 img·fetch 로 부르는 API(명령 실행·내 기록 읽기)도 막는다. 주소창·즐겨찾기로 여는 것은 된다
        if (self.headers.get("Host") or "").rsplit(":", 1)[0] not in HOSTS or (
                self.path.startswith("/api/") and self.headers.get("Sec-Fetch-Site") in ("cross-site", "same-site")):
            return self.send({"error": "bad host"}, code=403)
        try:
            fn()
        except Exception as e:
            print("요청 처리 실패:", self.command, self.path, repr(e))
            try:
                self.send({"error": f"서버 오류: {e}"}, code=500)
            except OSError:  # 브라우저가 이미 연결을 끊었다
                pass

    def get(self):
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
        if u.path == "/api/para":  # 프로젝트 페이지: 영역·프로젝트와 각 프로젝트에 적힌 작업
            return self.send(para())
        if u.path == "/api/projects":  # 작업 줄의 프로젝트 고르기 칸
            return self.send(names())
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
                "SELECT t.id, t.sid, t.status, t.text, t.source, t.tag, t.details, t.project_id, t.flow, coalesce(s.my_title, s.title) AS title, s.name,"
                " s.cwd, s.status AS sst"
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
        if u.path == "/api/schedules":  # 예약 작업 페이지: 루틴 저장본 {at, items} 과 살아 있는 세션의 예약
            return self.send({"routines": saved_routines(), "sessions": session_schedules(), "maps": maps()})
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

    def post(self):
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or "{}")
        except ValueError:
            body = None
        if not isinstance(body, dict):
            return self.send({"error": "본문은 JSON 객체여야 합니다"}, code=400)
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
        if self.headers.get("Origin") not in ORIGINS:
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
        if self.path in ("/api/area", "/api/project"):  # 영역·프로젝트 만들기·고치기·보관·지우기 (fleet/para.py)
            err = (save_area if self.path == "/api/area" else save_project)(body)
            return self.send({"error": err} if err else {"ok": True})
        if self.path == "/api/project-flow":  # {id} — 그 프로젝트의 Flow 를 AI 로 (다시) 만든다 (haiku 사용)
            return self.send(make_project_flow(body.get("id")))
        if self.path == "/api/resource":  # {id} — 자료 지우기 (자료는 에이전트가 MCP 로 남긴다)
            return self.send({"ok": True} if delete_resource(body.get("id")) else {"error": "자료를 찾지 못했습니다"})
        if self.path == "/api/upgrade":  # [새 버전으로 바꾸기] — 설치된 새 버전의 server.py 를 세션과 따로 띄우고 자리를 넘긴다
            row = installed()
            new = Path(row.get("installPath", "")) / "server.py"
            if ver(row.get("version")) <= ver(VERSION) or not new.is_file():
                return self.send({"error": "더 새 버전이 설치돼 있지 않습니다"})
            # 새 세션(setsid)이라 이 세션이 끝나도 산다. stdout 은 MCP 통신 줄이라 물려주지 않고 로그 파일로
            with open(DB.parent / "server.log", "ab") as log:
                subprocess.Popen([sys.executable, str(new)], cwd=new.parent, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                 start_new_session=True)
            self.send({"ok": True, "version": row["version"]})
            return threading.Thread(target=self.server.shutdown, daemon=True).start()  # /api/handover 와 같이 포트를 놓는다
        if self.path == "/api/config":  # {name, value} — EDIT 에 있는 설정만. 빈 값이면 환경 변수·기본값으로
            err = set_setting(body.get("name"), body.get("value"))
            return self.send({"error": err} if err else {"ok": True})
        if self.path == "/api/reopen":  # {sid, fork?} — 끝난 세션을 새 터미널 창에서 claude --resume 으로 연다
            out, code = reopen(body.get("sid", ""), bool(body.get("fork")))
            return self.send(out, code=code)
        if self.path == "/api/task" and "to" in body:  # {id, to} — 남은 일을 살아 있는 세션으로 옮긴다
            if not find_session(body["to"] or ""):
                return self.send({"error": "살아 있는 세션으로만 옮길 수 있습니다"})
            return self.send({"ok": True} if move_task(body.get("id"), body["to"]) else {"error": "남은 일만 옮길 수 있습니다"})
        if self.path == "/api/task":  # {id, status?, tag?, sort?, project?(0 이면 빼기), delete?} — 사람이 웹에서 고친다
            if body.get("project") and not has_project(body["project"]):
                return self.send({"error": "없는 프로젝트입니다"})
            ok = set_task(body.get("id"), "human", body.get("status"), sort=body.get("sort"), delete=bool(body.get("delete")),
                          tag=body.get("tag"), project=body.get("project"))
            return self.send({"ok": ok} if ok else {"error": "작업 또는 분류 확인"})
        if self.path == "/api/session/delete":  # {sid} — 끝난 세션을 세션 기록에서 지운다 (soft delete)
            return self.send({"ok": True} if delete_session(body.get("sid")) else {"error": "끝난 세션만 지울 수 있습니다"})
        if self.path == "/api/title":  # {sid, title} — 대시보드에서만 쓰는 제목. 빈 값이면 원래대로
            return self.send({"ok": True} if set_title(body.get("sid"), body.get("title")) else {"error": "세션 확인"})
        if self.path == "/api/routine-map":  # {id} — 그 루틴의 흐름도를 AI 로 (다시) 만든다 (haiku 사용)
            return self.send(make_map(body.get("id")))
        if self.path == "/api/schedules/refresh":  # 루틴을 claude.ai 에서 새로 받는다 — haiku 를 쓰므로 POST (출처 검사 대상)
            return self.send(refresh_routines())
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
