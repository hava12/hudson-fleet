"""HTTP API 와 대시보드 화면."""
import json
import os
import re
import signal
import sqlite3
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .agents import agents, find_session, graph, mcp_servers, reopen, session
from .card import card_svg
from .config import CFG, CONFIG, DEAD, ORIGIN, claude
from .db import db, metrics, my_title, set_title
from .pushes import pushes
from .tasks import TASKS_SQL, add_task, saved_tasks, set_task, summarize
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
        if u.path == "/":
            return self.send((Path(__file__).parent.parent / "index.html").read_bytes(), "text/html")
        if u.path == "/api/graph":
            return self.send(graph())
        if u.path == "/api/config":
            return self.send([{"name": k, "value": CFG[k], "default": d, "desc": desc, "set": k in os.environ}
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
        if self.path == "/api/run":
            cwd = os.path.expanduser(body.get("cwd", ""))
            if not os.path.isdir(cwd) or not body.get("prompt"):
                return self.send({"error": "cwd/prompt 확인"}, code=400)
            return self.send({"text": claude("--bg", body["prompt"], cwd=cwd)})
        if self.path == "/api/reopen":  # {sid, fork?} — 끝난 세션을 새 터미널 창에서 claude --resume 으로 연다
            out, code = reopen(body.get("sid", ""), bool(body.get("fork")))
            return self.send(out, code=code)
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
