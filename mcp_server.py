"""Hudson Fleet MCP — Claude Code 가 작업을 시작·완료·중단·반려할 때 기록한다 (stdio, 표준 라이브러리만).

기록은 대시보드 서버의 /api/agent/task 로 보낸다 — DB 는 서버 하나만 쓴다 (서버를 따로 두고 함께 쓸 때를 대비).
서버가 없으면 한 번 띄워 보고(훅과 같은 start.sh), 그래도 없으면 오류로 돌려준다.
ponytail: 못 보낸 기록은 버린다 — 빠지면 안 되게 되면 파일에 쌓았다가 다시 보낸다

어느 세션의 호출인지는 부모 프로세스로 찾는다. claude 가 이 서버를 자식으로 띄우므로
조상 pid 중 하나의 ~/.claude/sessions/<pid>.json 에 sessionId 가 있다. /clear 로 세션이 바뀔 수 있어 호출마다 다시 읽는다.
"""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
from fleet.config import SESSIONS  # noqa: E402
from fleet.tasks import TAGS  # noqa: E402

LOCAL = f"http://127.0.0.1:{os.environ.get('HUDSON_FLEET_PORT') or 8765}"
URL = os.environ.get("HUDSON_FLEET_URL") or LOCAL  # 대시보드 서버 주소. 다른 PC 의 서버를 쓸 때만 바꾼다

INSTRUCTIONS = """Hudson Fleet 작업 기록 — 사용자가 맡긴 일을 작업 단위로 기록한다. 대시보드와 세션 기록에 그대로 쓰인다.
규칙 (일의 크기와 관계없이 지킨다):
1. 사용자가 무언가를 만들거나, 고치거나, 실행·조사하라고 하면 첫 작업 전에 task_start(text, tag) 를 부른다.
   text 는 120자 이내, 동사로 끝나는 한 문장. tag 는 일의 종류 하나 (도구 설명의 정의를 보고 고른다).
2. 그 일이 끝나면 task_update(id, "done"). 끝내지 못하고 멈추면 "stopped", 사용자가 하지 않기로 하면 "rejected".
   이 세 가지는 note 에 비고 한 줄을 꼭 남긴다 — 완료면 결과, 중단이면 멈춘 이유, 반려면 반려 이유.
   details 는 text 를 풀어 쓴 설명 1줄씩 최대 3개다. task_start 때는 할 일(계획)을, task_update 때는 실제로 한 일·결과를
   적어 바꾼다 (줄마다 60자 안팎, 동사로 끝냄). 한 줄로 충분한 작은 일은 비워 둔다.
3. 이 도구들이 지연 로드(deferred) 상태면 먼저 ToolSearch 로
   "select:mcp__plugin_hudson-fleet_fleet__task_start,mcp__plugin_hudson-fleet_fleet__task_update,mcp__plugin_hudson-fleet_fleet__task_list" 를 불러온다.
4. 일하는 도중에 사용자가 덧붙인 요청도 규칙 1 을 따른다. 하던 일의 일부가 아니면 따로 task_start 한다
   (예: 노드 모양을 고치는 중에 "애니메이션도 넣어 줘" → 새 행). 바로 하지 않고 미루는 일도 task_start 만 해 두면 남은 일로 남는다.
   사용자에게 방법을 고르게 하거나 진행 여부를 묻는 제안을 했으면, 답을 기다리는 동안 그 제안도 task_start 로 남긴다
   (예: "제목 변경 방법 A·B 중 골라 구현한다"). 답을 받아 진행하면 그 행을 이어 쓰고, 하지 않기로 하면 "rejected".
5. 기록하지 않는 것: 질문에 답만 하는 경우, 확인·잡담. 같은 일을 두 번 시작하지 않는다.
6. 대화가 압축(compact)된 뒤에는 task_list 로 기록을 확인하고 이어서 쓴다."""

DETAILS = {"type": "array", "items": {"type": "string"}, "maxItems": 3}  # 3-Step-Desc (fleet/tasks.py MAX_DETAILS)

TOOLS = [
    {"name": "task_start", "description": "작업을 시작하며 기록한다. 새 작업 id 를 돌려준다.",
     "inputSchema": {"type": "object", "properties": {
         "text": {"type": "string", "description": "120자 이내 한 문장"},
         "tag": {"type": "string", "enum": list(TAGS),
                 "description": "일의 종류 — " + " · ".join(f"{k}: {v}" for k, v in TAGS.items())},
         "details": {**DETAILS, "description": "선택. 할 일(계획)을 풀어 쓴 설명 1줄씩 최대 3개"}},
                     "required": ["text", "tag"]}},
    {"name": "task_update", "description": "작업의 결과를 기록한다: done 완료 · stopped 중단 · rejected 반려 · todo 남은 일.",
     "inputSchema": {"type": "object", "properties": {
         "id": {"type": "integer"}, "status": {"type": "string", "enum": ["done", "stopped", "rejected", "todo"]},
         "note": {"type": "string", "description": "비고 한 줄 (done·stopped·rejected 때 꼭): 완료면 결과, 중단이면 멈춘 이유, 반려면 반려 이유"},
         "details": {**DETAILS, "description": "선택. 실제로 한 일·결과 1줄씩 최대 3개. 주면 기존 설명을 바꾼다"}},
                     "required": ["id", "status"]}},
    {"name": "task_list", "description": "이 세션에 기록된 작업 목록 (순서대로).",
     "inputSchema": {"type": "object", "properties": {}}},
]


def my_session():
    """조상 프로세스를 거슬러 올라가며 Claude Code 세션 파일을 찾는다 (중간에 셸이 끼어도 된다)."""
    pid = os.getppid()
    while pid > 1:
        f = SESSIONS / f"{pid}.json"
        if f.exists():
            return json.loads(f.read_text())["sessionId"]
        out = subprocess.run(["ps", "-o", "ppid=", "-p", str(pid)], capture_output=True, text=True).stdout.strip()
        pid = int(out) if out else 0
    return None


def post(body):
    req = urllib.request.Request(URL + "/api/agent/task", json.dumps(body).encode(), {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:  # 서버는 있는데 거절 — 400 은 이유가 본문에 있다
        if e.code in (403, 404):  # 이 API 가 없던 서버: 경로가 없거나(404) Origin 검사가 먼저 막는다(403)
            return {"error": "대시보드 서버가 옛 버전입니다. 서버를 껐다 켜라고 사용자에게 알리세요 (lsof -ti :8765 | xargs kill)"}
        return json.loads(e.read() or "{}")


def api(body):
    """대시보드 서버로 보낸다. 내 PC 의 서버가 없으면 띄우고 5초까지 기다린다."""
    try:
        return post(body)
    except urllib.error.URLError:
        pass
    if URL == LOCAL:  # 다른 PC 의 서버는 여기서 띄울 수 없다
        subprocess.run([os.path.join(ROOT, "hooks", "start.sh")], env={**os.environ, "CLAUDE_PLUGIN_ROOT": ROOT}, timeout=10)
        for _ in range(10):
            time.sleep(0.5)
            try:
                return post(body)
            except urllib.error.URLError:
                continue
    return {"error": f"대시보드 서버({URL})에 연결하지 못해 기록하지 못했습니다. 사용자에게 서버 상태를 확인하라고 알리세요"
                     " (~/.local/share/hudson-fleet/server.log)"}


def call(name, args):
    sid = my_session()
    if not sid:
        return "Claude Code 세션을 찾지 못했습니다", True
    if name == "task_start":
        r = api({"op": "start", "sid": sid, "text": args.get("text"), "tag": args.get("tag"), "details": args.get("details")})
        return (r["error"], True) if "error" in r else (json.dumps({"id": r["id"]}), False)
    if name == "task_update":
        r = api({"op": "update", "sid": sid, "id": args.get("id"), "status": args.get("status"), "note": args.get("note"),
                 "details": args.get("details")})
        return (r["error"], True) if "error" in r else ("기록했습니다", False)
    if name == "task_list":
        r = api({"op": "list", "sid": sid})
        return (r["error"], True) if "error" in r else (json.dumps(r["tasks"], ensure_ascii=False), False)
    return f"없는 도구: {name}", True


def reply(mid, result=None, error=None):
    msg = {"jsonrpc": "2.0", "id": mid, **({"error": error} if error else {"result": result})}
    sys.stdout.write(json.dumps(msg, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main():
    for line in sys.stdin:  # stdio MCP: 한 줄에 JSON-RPC 메시지 하나
        try:
            m = json.loads(line)
        except ValueError:
            continue
        method, mid, params = m.get("method"), m.get("id"), m.get("params") or {}
        if mid is None:  # 알림(notifications/*)에는 답하지 않는다
            continue
        if method == "initialize":
            reply(mid, {"protocolVersion": params.get("protocolVersion", "2025-06-18"),
                        "capabilities": {"tools": {}}, "instructions": INSTRUCTIONS,
                        "serverInfo": {"name": "hudson-fleet", "version": "0.1.0"}})
        elif method == "tools/list":
            reply(mid, {"tools": TOOLS})
        elif method == "tools/call":
            try:
                text, err = call(params.get("name"), params.get("arguments") or {})
            except Exception as e:  # 잘못된 인자 등 — 세션이 멈추지 않게 오류로 돌려준다
                text, err = f"오류: {e}", True
            reply(mid, {"content": [{"type": "text", "text": text}], "isError": err})
        elif method == "ping":
            reply(mid, {})
        else:
            reply(mid, error={"code": -32601, "message": f"method not found: {method}"})


if __name__ == "__main__":
    main()
