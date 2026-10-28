"""지금 살아 있는 세션: claude agents 목록, 프로세스, 그래프, MCP 상태, 다시 열기."""
import json
import os
import re
import shlex
import subprocess
import time
from pathlib import Path

from .config import CFG, INTERNAL, SESSIONS, claude
from .db import db
from .transcripts import model_of, overview, subagents, transcript


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


def agents():
    """claude agents 목록에서 대시보드 자신의 `claude -p` 호출(/usage·AI 요약, 이름 INTERNAL)을 뺀다.
    몇 초 떴다 사라지는 '유령 세션'이 되기 때문. 다른 도구가 띄운 claude -p(예: 하네스의 역할 호출)는 보인다."""
    def internal(s):
        if "pid" not in s:  # 백그라운드 작업은 pid 가 없다
            return False
        try:
            info = json.loads((SESSIONS / f"{s['pid']}.json").read_text())
            return info.get("entrypoint") == "sdk-cli" and info.get("name") == INTERNAL
        except OSError:  # 목록에는 남았는데 파일은 지워짐 = 막 끝난 프로세스
            return True
        except ValueError:
            return False
    return [s for s in agent_list() if not internal(s)]


_ag = {"at": 0, "data": []}


def agent_list():
    """claude agents --json --all. 부를 때마다 node 를 띄워 ~0.2초 걸리므로 5초 동안 재사용한다."""
    if time.time() - _ag["at"] >= 5:
        try:
            _ag.update(at=time.time(), data=json.loads(claude("agents", "--json", "--all")))
        except ValueError:  # 빈 출력·오류 문장은 지난 목록을 쓴다 — 빈 목록이면 1분 기록이 살아 있는 세션을 모두 끝남으로 마감한다
            pass
    return _ag["data"]


def find_session(sid):
    """현재 claude agents 목록에 있는 세션만 조작 대상으로 인정한다 (임의 pid 종료 차단)."""
    return next((s for s in agent_list()
                 if s["sessionId"] == sid), None)


def session(sid):
    """세션 개요 + 프로세스 경로 (오른쪽 패널)."""
    path = transcript(sid)
    s = find_session(sid) or {}
    return {"home": str(Path.home()), "proc": proc_chain(s["pid"]) if s.get("pid") else [],
            "overview": overview(path) if path else {}}


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
    for s in agents():
        sid, cwd = s["sessionId"], s["cwd"]
        if s.get("pid") and (app := host_app(s["pid"])):
            s["app"] = Path(app).stem
        nodes["p:" + cwd] = {"type": "project", "label": os.path.basename(cwd) or cwd}
        nodes["s:" + sid] = {"type": "session", "label": s.get("name") or s.get("id"),
                             "status": s.get("status") or s.get("state", ""), **s, **model_of(sid)}
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


def reopen(sid, fork):
    """끝난 세션을 그 작업 폴더에서 claude --resume 으로 다시 연다. fork 면 --fork-session (기록은 그대로 두고 새 ID).
    DB 에 closed 로 남은 세션만 연다 — 아무 ID 나 받아 명령을 만들지 않게."""
    c = db()
    row = c.execute("SELECT cwd FROM sessions WHERE sid = ? AND status = 'closed'", (sid,)).fetchone()
    c.close()
    if not re.fullmatch(r"[0-9a-f-]{36}", sid) or not row or not os.path.isdir(row[0] or ""):
        return {"error": "끝난 세션이 아니거나 작업 폴더가 없습니다"}, 404
    cmd = ["claude", "--resume", sid, *(["--fork-session"] if fork else [])]
    app = CFG["HUDSON_FLEET_TERMINAL"]
    if app == "Terminal":  # Terminal.app 은 명령을 AppleScript 문자열로만 받는다
        line = f"cd {shlex.quote(row[0])} && {' '.join(cmd)}"
        subprocess.Popen(["osascript", "-e", f'tell application "Terminal" to do script "{line.replace(chr(92), chr(92) * 2).replace(chr(34), chr(92) + chr(34))}"',
                          "-e", 'tell application "Terminal" to activate'])
    else:
        subprocess.Popen(["open", "-na", app, "--args", f"--working-directory={row[0]}", "-e", *cmd])
    return {"text": f"{app} 새 창에서 {'복사해' if fork else '이어서'} 엽니다"}, 200
