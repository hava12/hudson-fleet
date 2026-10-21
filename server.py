"""Hudson Fleet — Claude Code 세션 대시보드. 실행: python3 server.py → http://127.0.0.1:8765"""
import glob
import json
import os
import signal
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

PORT = 8765
ORIGIN = f"http://127.0.0.1:{PORT}"
PROJECTS = Path.home() / ".claude" / "projects"
EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}


def claude(*args, cwd=None):
    r = subprocess.run(["claude", *args], cwd=cwd, capture_output=True, text=True, timeout=60)
    return (r.stdout or r.stderr).strip()


def transcript(sid):
    # ponytail: glob over all projects per request, index by sid if project count grows large
    hits = glob.glob(str(PROJECTS / "*" / f"{glob.escape(sid)}.jsonl"))
    return Path(hits[0]) if sid and hits else None


def edits(path):
    """jsonl 하나에서 Edit/Write 한 파일 {경로: 횟수} + 마지막 assistant 답변."""
    files, last = {}, ""
    for line in path.open(encoding="utf-8", errors="replace"):
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if rec.get("type") != "assistant":
            continue
        for c in rec.get("message", {}).get("content", []):
            if not isinstance(c, dict):
                continue
            if c.get("type") == "tool_use" and c.get("name") in EDIT_TOOLS:
                inp = c.get("input", {})
                fp = inp.get("file_path") or inp.get("notebook_path")
                if fp:
                    files[fp] = files.get(fp, 0) + 1
            elif c.get("type") == "text" and c.get("text", "").strip():
                last = c["text"]
    return files, last


def subagents(sid):
    """[(agentId, 설명, jsonl 경로)] — 기록 위치: <sid>/subagents/agent-<id>.jsonl"""
    path = transcript(sid)
    if not path:
        return []
    out = []
    for p in sorted((path.parent / sid / "subagents").glob("agent-*.jsonl")):
        meta = p.with_suffix(".meta.json")
        desc = json.loads(meta.read_text()).get("description", "") if meta.exists() else ""
        out.append((p.stem.removeprefix("agent-"), desc, p))
    return out


def session_files(sid):
    """세션 본체 + 서브에이전트가 편집한 파일 전체 (열람 허용 목록)."""
    path = transcript(sid)
    files = set(edits(path)[0]) if path else set()
    for _, _, p in subagents(sid):
        files |= set(edits(p)[0])
    return files


def find_session(sid):
    """현재 claude agents 목록에 있는 세션만 조작 대상으로 인정한다 (임의 pid 종료 차단)."""
    return next((s for s in json.loads(claude("agents", "--json", "--all") or "[]")
                 if s["sessionId"] == sid), None)


def host_app(pid):
    """세션을 띄운 터미널 앱(.app 번들) — 부모 프로세스를 거슬러 올라가며 찾는다."""
    while pid > 1:
        comm = subprocess.run(["ps", "-o", "comm=", "-p", str(pid)], capture_output=True, text=True).stdout.strip()
        if ".app/" in comm:
            return comm.split(".app/")[0] + ".app"
        ppid = subprocess.run(["ps", "-o", "ppid=", "-p", str(pid)], capture_output=True, text=True).stdout.strip()
        pid = int(ppid or 1)
    return None


def graph():
    """프로젝트 → 세션 → 서브에이전트 → 파일 DAG. 같은 파일 노드를 여러 부모가 공유한다."""
    nodes, edges = {}, set()
    for s in json.loads(claude("agents", "--json", "--all") or "[]"):
        sid, cwd = s["sessionId"], s["cwd"]
        nodes["p:" + cwd] = {"type": "project", "label": os.path.basename(cwd) or cwd}
        nodes["s:" + sid] = {"type": "session", "label": s.get("name") or s.get("id"),
                             "status": s.get("status") or s.get("state", ""), **s}
        edges.add(("p:" + cwd, "s:" + sid))
        path = transcript(sid)
        children = [("s:" + sid, path)] if path else []
        for aid, desc, p in subagents(sid):
            nodes["a:" + aid] = {"type": "agent", "label": desc or aid, "sid": sid}
            edges.add(("s:" + sid, "a:" + aid))
            children.append(("a:" + aid, p))
        for parent, p in children:
            for fp in edits(p)[0]:
                nodes["f:" + fp] = {"type": "file", "label": os.path.basename(fp), "path": fp, "sid": sid}
                edges.add((parent, "f:" + fp))
    # 세션의 "id"(백그라운드 짧은 id)가 노드 id 를 덮지 않도록 bgId 로 옮긴다
    return {"nodes": [{**v, "bgId": v.get("id"), "id": k} for k, v in nodes.items()],
            "edges": [{"source": a, "target": b} for a, b in edges]}


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
            return self.send((Path(__file__).parent / "index.html").read_bytes(), "text/html")
        if u.path == "/api/graph":
            return self.send(graph())
        if u.path == "/api/last":
            path = transcript(q.get("sid", ""))
            return self.send({"text": edits(path)[1] if path else ""})
        if u.path == "/api/file":
            # 세션(서브에이전트 포함)이 실제로 편집한 파일만 열람 허용 (임의 파일 읽기 차단)
            p = q.get("path", "")
            if p not in session_files(q.get("sid", "")) or not os.path.isfile(p):
                return self.send({"error": "not allowed or missing"}, code=404)
            return self.send(Path(p).read_bytes()[:500_000], "text/plain")
        if u.path == "/api/logs":
            return self.send({"text": claude("logs", q.get("id", ""))})
        self.send({"error": "not found"}, code=404)

    def do_POST(self):
        # 다른 웹사이트가 localhost 로 실행 요청을 보내는 것(CSRF) 차단
        if self.headers.get("Origin") != ORIGIN:
            return self.send({"error": "bad origin"}, code=403)
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or "{}")
        if self.path == "/api/run":
            cwd = os.path.expanduser(body.get("cwd", ""))
            if not os.path.isdir(cwd) or not body.get("prompt"):
                return self.send({"error": "cwd/prompt 확인"}, code=400)
            return self.send({"text": claude("--bg", body["prompt"], cwd=cwd)})
        if self.path not in ("/api/stop", "/api/focus"):
            return self.send({"error": "not found"}, code=404)
        s = find_session(body.get("sid", ""))
        if not s:
            return self.send({"error": "실행 중인 세션이 아님"}, code=404)
        bg = s["kind"] == "background"
        if self.path == "/api/stop":
            if bg:
                return self.send({"text": claude("stop", s["id"])})
            os.kill(s["pid"], signal.SIGTERM)
            return self.send({"text": f"{s.get('name')} 종료 신호 보냄"})
        if bg:
            # ponytail: Ghostty 고정, 다른 터미널을 쓰게 되면 설정값으로
            subprocess.Popen(["open", "-na", "Ghostty", "--args", "-e", "claude", "attach", s["id"]])
            return self.send({"text": "Ghostty 새 창에서 attach"})
        app = host_app(s["pid"])
        if not app:
            return self.send({"error": "터미널 앱을 찾지 못함"}, code=404)
        # JetBrains IDE 는 폴더를 넘기면 그 프로젝트 창을 앞으로 가져온다. 탭 단위 이동은 불가
        subprocess.Popen(["open", "-a", app, *([s["cwd"]] if "IntelliJ" in app else [])])
        return self.send({"text": f"{Path(app).stem} 로 이동"})


if __name__ == "__main__":
    print(f"→ {ORIGIN}")
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
