"""Hudson Fleet — Claude Code 세션 대시보드. 실행: python3 server.py → http://127.0.0.1:8765"""
import difflib
import glob
import json
import os
import re
import signal
import subprocess
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

PORT = 8765
ORIGIN = f"http://127.0.0.1:{PORT}"
PROJECTS = Path.home() / ".claude" / "projects"
EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
DEAD = {"stopped", "completed", "done", "failed"}


def claude(*args, cwd=None):
    r = subprocess.run(["claude", *args], cwd=cwd, capture_output=True, text=True, timeout=60)
    return (r.stdout or r.stderr).strip()


def transcript(sid):
    # ponytail: glob over all projects per request, index by sid if project count grows large
    hits = glob.glob(str(PROJECTS / "*" / f"{glob.escape(sid)}.jsonl"))
    return Path(hits[0]) if sid and hits else None


def diff_of(tool, inp):
    """편집 도구 입력 → unified diff 본문. Write 는 전체가 추가로 보인다."""
    if tool == "Edit":
        pairs = [(inp.get("old_string", ""), inp.get("new_string", ""))]
    elif tool == "MultiEdit":
        pairs = [(e.get("old_string", ""), e.get("new_string", "")) for e in inp.get("edits", [])]
    else:
        pairs = [("", inp.get("content") or inp.get("new_source", ""))]
    lines = []
    for old, new in pairs:
        lines += difflib.unified_diff(old.splitlines(), new.splitlines(), lineterm="", n=2)
    return "\n".join(l for l in lines if not l.startswith(("---", "+++")))


def git_diff(fp, result):
    """도구 결과의 structuredPatch(실제 파일 줄 번호) → git 형식 unified diff. 없으면 None."""
    patch = result.get("structuredPatch")
    if patch:
        hunks = [f"@@ -{h['oldStart']},{h['oldLines']} +{h['newStart']},{h['newLines']} @@\n" + "\n".join(h["lines"])
                 for h in patch]
        return f"--- a{fp}\n+++ b{fp}\n" + "\n".join(hunks)
    if result.get("type") == "create":  # 새 파일: 전체가 추가
        lines = result.get("content", "").splitlines()
        return f"--- /dev/null\n+++ b{fp}\n@@ -0,0 +1,{len(lines)} @@\n" + "\n".join("+" + l for l in lines)
    return None


def scan(path, by):
    """jsonl 하나 → (성공한 편집 이벤트 목록, 마지막 assistant 답변). 훅 등에 막힌 호출은 뺀다."""
    events, failed, patches, last = {}, set(), {}, ""
    for line in path.open(encoding="utf-8", errors="replace"):
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        content = rec.get("message", {}).get("content", [])
        if not isinstance(content, list):
            continue
        for c in content:
            if not isinstance(c, dict):
                continue
            if c.get("type") == "tool_result":
                if c.get("is_error"):
                    failed.add(c.get("tool_use_id"))
                elif isinstance(rec.get("toolUseResult"), dict) and rec["toolUseResult"].get("filePath"):
                    patches[c.get("tool_use_id")] = git_diff(rec["toolUseResult"]["filePath"], rec["toolUseResult"])
            elif rec.get("type") != "assistant":
                continue
            elif c.get("type") == "tool_use" and c.get("name") in EDIT_TOOLS:
                inp = c.get("input", {})
                fp = inp.get("file_path") or inp.get("notebook_path")
                if fp:
                    events[c.get("id")] = {"file": fp, "ts": rec.get("timestamp", ""), "tool": c["name"],
                                           "by": by, "diff": diff_of(c["name"], inp)}
            elif c.get("type") == "text" and c.get("text", "").strip():
                last = c["text"]
    for i, e in events.items():
        # 실제 줄 번호가 있는 patch 우선, 없으면(옛 기록) 입력 조각으로 만든 diff 에 헤더만 붙인다
        e["diff"] = patches.get(i) or f"--- a{e['file']}\n+++ b{e['file']}\n{e['diff']}"
    return [e for i, e in events.items() if i not in failed], last


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


def prompt_text(rec):
    """사용자가 직접 입력한 메시지만 — 도구 결과·명령 출력·시스템 주입은 뺀다."""
    if rec.get("type") != "user" or rec.get("isMeta") or rec.get("isCompactSummary"):
        return ""
    c = rec.get("message", {}).get("content", "")
    if isinstance(c, list):
        c = " ".join(x.get("text", "") for x in c if isinstance(x, dict) and x.get("type") == "text")
    c = c.strip()
    return "" if c.startswith("<") else c


def overview(path):
    """토큰 없이 만드는 세션 개요: 제목(ai-title/custom-title), 시킨 일, 시작·마지막 시각."""
    title, prompts, first, last = "", [], "", ""
    for line in path.open(encoding="utf-8", errors="replace"):
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        title = rec.get("customTitle") or rec.get("aiTitle") or title
        ts = rec.get("timestamp", "")
        if ts:
            first, last = first or ts, ts
        if p := prompt_text(rec):
            prompts.append({"ts": ts, "text": p[:300]})
    return {"title": title, "prompts": prompts, "first": first, "last": last}


def session(sid):
    """세션 개요 + 프로세스 경로 + 본체·서브에이전트의 변경 이력(시간순)."""
    path = transcript(sid)
    s = find_session(sid) or {}
    base = {"home": str(Path.home()), "proc": proc_chain(s["pid"]) if s.get("pid") else []}
    if not path:
        return {**base, "changes": [], "overview": {}}
    return {**base, "changes": changes_of(sid, path), "overview": overview(path)}


def changes_of(sid, path):
    changes, _ = scan(path, "main")
    for aid, desc, p in subagents(sid):
        changes += scan(p, desc or aid)[0]
    return sorted(changes, key=lambda e: e["ts"])


def feed():
    """세션별 작업 게시글: 개요 + 변경 수 + 저장해 둔 AI 요약. 새 요약은 만들지 않는다 (토큰 절약)."""
    posts = []
    for s in json.loads(claude("agents", "--json", "--all") or "[]"):
        sid = s["sessionId"]
        path = transcript(sid)
        if not path or (s.get("status") or s.get("state")) in DEAD:  # 끝난 세션은 게시글에서도 뺀다
            continue
        ov, ch = overview(path), changes_of(sid, path)
        cache = CACHE / f"{sid}.json"
        c = json.loads(cache.read_text()) if cache.exists() else {}
        ps = ov["prompts"]
        posts.append({"sid": sid, "name": s.get("name") or s.get("id"), "cwd": s["cwd"], "kind": s["kind"],
                      "status": s.get("status") or s.get("state", ""), "title": ov["title"],
                      "first": ov["first"], "last": ov["last"], "nprompts": len(ps),
                      "goal": ps[0]["text"] if ps else "", "recent": ps[-1]["text"] if len(ps) > 1 else "",
                      "files": len({e["file"] for e in ch}), "edits": len(ch),
                      "summary": c.get("text", ""), "stale": bool(c) and c["mtime"] != path.stat().st_mtime})
    return sorted(posts, key=lambda p: p["last"], reverse=True)


CACHE = Path.home() / ".cache" / "hudson-fleet"  # 플러그인 폴더는 업데이트 때 덮이므로 밖에 둔다


def summarize(sid):
    """haiku 로 세션 요약. 기록이 바뀌지 않았으면 저장해 둔 요약을 다시 쓴다 (토큰 절약)."""
    path = transcript(sid)
    if not path:
        return {"error": "기록 없음"}
    cache = CACHE / f"{sid}.json"
    mtime = path.stat().st_mtime
    if cache.exists() and (c := json.loads(cache.read_text()))["mtime"] == mtime:
        return {**c, "cached": True}
    parts = []
    for line in path.open(encoding="utf-8", errors="replace"):
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if p := prompt_text(rec):
            parts.append("[사용자] " + p[:1000])
        elif rec.get("type") == "assistant":
            for c in rec.get("message", {}).get("content", []):
                if isinstance(c, dict) and c.get("type") == "text" and c["text"].strip():
                    parts.append("[Claude] " + c["text"][:600])
    files = sorted({e["file"] for e in session(sid)["changes"]})
    # ponytail: 앞 1건 + 뒤쪽 위주로 4만 자 자르기, 긴 세션은 구간별 요약이 필요해지면 그때
    body = "\n".join(parts)
    if len(body) > 40_000:
        body = parts[0] + "\n...(중략)...\n" + body[-38_000:]
    instr = ("다음은 Claude Code 세션 기록이다. 한국어로 아래 형식만 출력하라.\n"
             "목표: 한 줄\n한 일: 3개 이내 글머리표\n결과: 한 줄\n남은 일: 없으면 '없음'")
    text = subprocess.run(["claude", "-p", "--model", "haiku", "--no-session-persistence", instr],
                          input=body + "\n\n[변경 파일]\n" + "\n".join(files),
                          capture_output=True, text=True, timeout=180).stdout.strip()
    if not text:
        return {"error": "요약 실패"}
    CACHE.mkdir(parents=True, exist_ok=True)
    out = {"text": text, "mtime": mtime}
    cache.write_text(json.dumps(out, ensure_ascii=False))
    return {**out, "cached": False}


_mcp = {"at": 0, "data": []}


def mcp_servers(refresh=False):
    """claude mcp list(연결 검사 포함, ~9초) → [{name, group, target, ok, state}]. 1분 동안 재사용."""
    if refresh or time.time() - _mcp["at"] > 60:
        out = []
        for line in re.sub(r"\x1b\][^\x07\x1b]*(\x07|\x1b\\)|\x1b\[[0-9;]*m", "", claude("mcp", "list", cwd=Path.home())).splitlines():
            if m := re.match(r"^(.+?): (.+) - ([✔✘!⏸]) (.+)$", line):
                name, target, mark, state = m.groups()
                group = "claude.ai 커넥터" if name.startswith("claude.ai ") else "플러그인" if name.startswith("plugin:") else "직접 설정"
                out.append({"name": name.removeprefix("claude.ai ").split(":")[-1], "group": group, "target": target,
                            "ok": {"✔": "ok", "✘": "fail", "!": "auth", "⏸": "pending"}[mark], "state": state})
        _mcp.update(at=time.time(), data=out)
    return _mcp["data"]


def find_session(sid):
    """현재 claude agents 목록에 있는 세션만 조작 대상으로 인정한다 (임의 pid 종료 차단)."""
    return next((s for s in json.loads(claude("agents", "--json", "--all") or "[]")
                 if s["sessionId"] == sid), None)


def proc_chain(pid):
    """세션 프로세스부터 부모를 거슬러 올라간 목록 [{pid, name, path}] — 어떤 앱 안에서 도는지."""
    out = []
    while pid > 1:
        r = subprocess.run(["ps", "-o", "ppid=,comm=", "-p", str(pid)], capture_output=True, text=True).stdout.strip()
        if not r:
            break
        ppid, comm = r.split(None, 1)
        name = Path(comm.split(".app/")[0]).stem if ".app/" in comm else Path(comm.lstrip("-")).name
        out.append({"pid": pid, "name": name, "path": comm})
        pid = int(ppid)
    return out


def host_app(pid):
    """세션을 띄운 터미널 앱(.app 번들)."""
    return next((p["path"].split(".app/")[0] + ".app" for p in proc_chain(pid) if ".app/" in p["path"]), None)


def graph():
    """프로젝트 → 세션 → 서브에이전트 DAG. 파일 변경은 그래프가 아니라 탐색기 패널(/api/session)로 본다."""
    nodes, edges = {}, set()
    for s in json.loads(claude("agents", "--json", "--all") or "[]"):
        sid, cwd = s["sessionId"], s["cwd"]
        if s.get("pid") and (app := host_app(s["pid"])):
            s["app"] = Path(app).stem
        nodes["p:" + cwd] = {"type": "project", "label": os.path.basename(cwd) or cwd}
        nodes["s:" + sid] = {"type": "session", "label": s.get("name") or s.get("id"),
                             "status": s.get("status") or s.get("state", ""), **s}
        edges.add(("p:" + cwd, "s:" + sid))
        for aid, desc, p in subagents(sid):
            meta = p.with_suffix(".meta.json")  # 서브에이전트가 끝나면 finished: true 가 기록된다
            done = meta.exists() and json.loads(meta.read_text()).get("finished")
            nodes["a:" + aid] = {"type": "agent", "label": desc or aid, "sid": sid,
                                 "status": "done" if done else "running"}
            edges.add(("s:" + sid, "a:" + aid))
    # 세션의 "id"(백그라운드 짧은 id)가 노드 id 를 덮지 않도록 bgId 로 옮긴다
    return {"home": str(Path.home()), "nodes": [{**v, "bgId": v.get("id"), "id": k} for k, v in nodes.items()],
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
        if u.path == "/api/mcp":
            return self.send(mcp_servers(q.get("refresh") == "1"))
        if u.path == "/api/feed":
            return self.send(feed())
        if u.path == "/api/session":
            return self.send(session(q.get("sid", "")))
        if u.path == "/api/file":
            # 세션(서브에이전트 포함)이 실제로 편집한 파일만 열람 허용 (임의 파일 읽기 차단)
            p = q.get("path", "")
            if p not in {e["file"] for e in session(q.get("sid", ""))["changes"]} or not os.path.isfile(p):
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


if __name__ == "__main__":
    print(f"→ {ORIGIN}")
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
