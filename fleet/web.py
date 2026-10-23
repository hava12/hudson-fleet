"""HTTP API 와 대시보드 화면."""
import json
import mimetypes
import os
import re
import secrets
import signal
import sqlite3
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .agents import agents, find_session, graph, mcp_servers, reopen, session
from .card import card_svg, tokens_svg
from .config import CFG, CONFIG, DEAD, ORIGIN, claude
from .db import (EDIT, add_user, check_login, db, del_user, metrics, my_title, saved_settings, set_password,
                 set_setting, set_title, users)
from .pushes import pushes
from .tasks import TASKS_SQL, add_task, move_task, saved_tasks, set_task, summarize
from .transcripts import overview, transcript
from .usage import usage, usage5h_all


def feed():
    """세션별 작업 게시글: 개요 + 저장해 둔 AI 요약. 새 요약은 만들지 않는다 (토큰 절약)."""
    posts = []
    for s in agents():
        sid = s["sessionId"]
        path = transcript(sid)
        if not path or (s.get("status") or s.get("state")) in DEAD:  # 끝난 세션은 게시글에서도 뺀다
            continue
        ov = overview(path)
        tasks, tmt = saved_tasks(sid)
        ps = ov["prompts"]
        posts.append({"sid": sid, "name": s.get("name") or s.get("id"), "cwd": s["cwd"], "kind": s["kind"],
                      "status": s.get("status") or s.get("state", ""), "title": my_title(sid) or ov["title"],
                      "first": ov["first"], "last": ov["last"], "nprompts": len(ps),
                      "goal": ps[0]["text"] if ps else "", "recent": ps[-1]["text"] if len(ps) > 1 else "",
                      "tasks": tasks, "stale": tmt is not None and tmt != path.stat().st_mtime})
    return sorted(posts, key=lambda p: p["last"], reverse=True)


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


DIST = (Path(__file__).parent.parent / "dist").resolve()  # web/ 의 React 빌드 결과
TOKENS = {}  # 로그인 쿠키 값 → 아이디. ponytail: 메모리에만 — 서버를 다시 켜면 다시 로그인. 오래 유지하려면 DB 로
COOKIE = "hf"


class H(BaseHTTPRequestHandler):
    def send(self, body, ctype="application/json", code=200, cookie=None):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        if cookie is not None:  # HttpOnly: 화면 스크립트가 못 읽음 · SameSite=Strict: 다른 사이트에서 온 요청엔 안 붙음
            self.send_header("Set-Cookie", f"{COOKIE}={cookie}; HttpOnly; SameSite=Strict; Path=/" + ("" if cookie else "; Max-Age=0"))
        self.end_headers()
        self.wfile.write(data)

    def token(self):
        m = re.search(rf"(?:^|;\s*){COOKIE}=([\w-]+)", self.headers.get("Cookie", ""))
        return m and m[1]

    def user(self):
        return TOKENS.get(self.token())

    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        if u.path == "/" or u.path.startswith("/assets/"):  # 화면 파일은 누구나 — 로그인 창도 이 안에 있다
            f = (DIST / (u.path.lstrip("/") or "index.html")).resolve()
            if f.is_relative_to(DIST) and f.is_file():  # ../ 로 dist 밖을 읽지 못하게
                return self.send(f.read_bytes(), mimetypes.guess_type(f.name)[0] or "application/octet-stream")
        if not self.user():
            return self.send({"error": "로그인이 필요합니다"}, code=401)
        if u.path == "/api/me":
            return self.send({"user": self.user()})
        if u.path == "/api/users":
            return self.send(users())
        if u.path == "/api/graph":
            return self.send(graph())
        if u.path == "/api/config":
            hide = lambda k, v: "****" if k.endswith("PASSWORD") else v
            saved = saved_settings()  # src: screen 화면에서 바꿈 · env 환경 변수 · default 기본값
            return self.send([{"name": k, "value": hide(k, CFG[k]), "default": hide(k, d), "desc": desc, "edit": k in EDIT,
                               "src": "screen" if k in saved else "env" if k in os.environ else "default"}
                              for k, d, desc in CONFIG])
        if u.path == "/api/sessions":  # ?status=closed|work|wait|idle (없으면 전체) &limit=
            c = db()
            c.row_factory = sqlite3.Row
            st = q.get("status")
            out = [dict(r) for r in c.execute(
                "SELECT * FROM sessions WHERE status IS NOT NULL" + (" AND status = ?" if st else "")
                + " ORDER BY coalesce(ended_at, last_seen) DESC LIMIT ?", (*([st] if st else []), int(q.get("limit", 50))))]
            for s in out:
                s["title"] = s["my_title"] or s["title"]
                s["tasks"] = [dict(r) for r in c.execute(
                    TASKS_SQL, (s["sid"],))]
            c.close()
            return self.send(out)
        if u.path == "/api/todo":  # 남은 일 — 끝난 세션 것도 포함
            c = db()
            c.row_factory = sqlite3.Row
            out = [dict(r) for r in c.execute(
                "SELECT t.id, t.sid, t.status, t.text, t.source, t.tag, t.details, coalesce(s.my_title, s.title) AS title, s.name, s.cwd, s.status AS sst"
                " FROM session_tasks t JOIN sessions s USING (sid) WHERE t.status = 'todo'"
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
        if u.path == "/api/feed":
            return self.send(feed())
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
        if self.path == "/api/agent/task" and "Origin" not in self.headers:
            out, code = agent_task(body)
            return self.send(out, code=code)
        # 다른 웹사이트가 localhost 로 실행 요청을 보내는 것(CSRF) 차단
        if self.headers.get("Origin") != ORIGIN:
            return self.send({"error": "bad origin"}, code=403)
        if self.path == "/api/login":  # {user, password} — 관리자 하나 (.env 의 HUDSON_FLEET_ADMIN_*)
            if not check_login(body.get("user"), body.get("password")):
                return self.send({"error": "아이디 또는 비밀번호가 틀렸습니다"}, code=401)
            t = secrets.token_urlsafe(32)
            TOKENS[t] = body["user"]
            return self.send({"user": body["user"]}, cookie=t)
        if not self.user():
            return self.send({"error": "로그인이 필요합니다"}, code=401)
        if self.path == "/api/logout":
            TOKENS.pop(self.token(), None)
            return self.send({"ok": True}, cookie="")
        if self.path == "/api/users":  # {name, password} 추가 · {name, delete: true} 삭제 (그 계정의 로그인도 끊는다)
            if body.get("delete"):
                if not del_user(body.get("name")):
                    return self.send({"error": "지울 수 있는 계정이 아닙니다"})
                for t in [t for t, n in TOKENS.items() if n == body["name"]]:
                    TOKENS.pop(t)
                return self.send({"ok": True})
            err = add_user(body.get("name"), body.get("password"))
            return self.send({"error": err} if err else {"ok": True})
        if self.path == "/api/password":  # {old, new} — 로그인한 사람 자기 비밀번호
            err = set_password(self.user(), body.get("old"), body.get("new"))
            return self.send({"error": err} if err else {"ok": True})
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
