"""Hudson Fleet MCP — Claude Code 가 작업을 시작·완료·중단·반려할 때 직접 기록한다 (stdio, 표준 라이브러리만).

어느 세션의 호출인지는 부모 프로세스로 찾는다. claude 가 이 서버를 자식으로 띄우므로
조상 pid 중 하나의 ~/.claude/sessions/<pid>.json 에 sessionId 가 있다. /clear 로 세션이 바뀔 수 있어 호출마다 다시 읽는다.
"""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from server import SESSIONS, TAGS, add_task, saved_tasks, set_task  # noqa: E402

INSTRUCTIONS = """Hudson Fleet 작업 기록 — 사용자가 맡긴 일을 작업 단위로 기록한다. 대시보드와 세션 기록에 그대로 쓰인다.
규칙 (일의 크기와 관계없이 지킨다):
1. 사용자가 무언가를 만들거나, 고치거나, 실행·조사하라고 하면 첫 작업 전에 task_start(text, tag) 를 부른다.
   text 는 120자 이내, 동사로 끝나는 한 문장. tag 는 일의 종류 하나 (도구 설명의 정의를 보고 고른다).
2. 그 일이 끝나면 task_update(id, "done"). 끝내지 못하고 멈추면 "stopped", 사용자가 하지 않기로 하면 "rejected".
3. 이 도구들이 지연 로드(deferred) 상태면 먼저 ToolSearch 로
   "select:mcp__plugin_hudson-fleet_fleet__task_start,mcp__plugin_hudson-fleet_fleet__task_update,mcp__plugin_hudson-fleet_fleet__task_list" 를 불러온다.
4. 일하는 도중에 사용자가 덧붙인 요청도 규칙 1 을 따른다. 하던 일의 일부가 아니면 따로 task_start 한다
   (예: 노드 모양을 고치는 중에 "애니메이션도 넣어 줘" → 새 행). 바로 하지 않고 미루는 일도 task_start 만 해 두면 남은 일로 남는다.
   사용자에게 방법을 고르게 하거나 진행 여부를 묻는 제안을 했으면, 답을 기다리는 동안 그 제안도 task_start 로 남긴다
   (예: "제목 변경 방법 A·B 중 골라 구현한다"). 답을 받아 진행하면 그 행을 이어 쓰고, 하지 않기로 하면 "rejected".
5. 기록하지 않는 것: 질문에 답만 하는 경우, 확인·잡담. 같은 일을 두 번 시작하지 않는다.
6. 대화가 압축(compact)된 뒤에는 task_list 로 기록을 확인하고 이어서 쓴다."""

TOOLS = [
    {"name": "task_start", "description": "작업을 시작하며 기록한다. 새 작업 id 를 돌려준다.",
     "inputSchema": {"type": "object", "properties": {
         "text": {"type": "string", "description": "120자 이내 한 문장"},
         "tag": {"type": "string", "enum": list(TAGS),
                 "description": "일의 종류 — " + " · ".join(f"{k}: {v}" for k, v in TAGS.items())}},
                     "required": ["text", "tag"]}},
    {"name": "task_update", "description": "작업의 결과를 기록한다: done 완료 · stopped 중단 · rejected 반려 · todo 남은 일.",
     "inputSchema": {"type": "object", "properties": {
         "id": {"type": "integer"}, "status": {"type": "string", "enum": ["done", "stopped", "rejected", "todo"]},
         "note": {"type": "string", "description": "선택. 결과나 멈춘 이유 한 줄"}}, "required": ["id", "status"]}},
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


def call(name, args):
    sid = my_session()
    if not sid:
        return "Claude Code 세션을 찾지 못했습니다", True
    if name == "task_start":
        return json.dumps({"id": add_task(sid, args["text"][:160], "agent", tag=args.get("tag"))}), False
    if name == "task_update":
        ok = set_task(args["id"], "agent", args["status"], note=args.get("note"), sid=sid)
        return ("기록했습니다" if ok else "이 세션의 작업 id 가 아니거나 분류가 잘못됐습니다"), not ok
    if name == "task_list":
        return json.dumps(saved_tasks(sid)[0], ensure_ascii=False), False
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
