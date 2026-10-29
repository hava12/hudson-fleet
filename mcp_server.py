"""Hudson Fleet MCP — Claude Code 가 작업을 시작·완료·중단·반려할 때 기록한다 (stdio, 표준 라이브러리만).

기록은 대시보드 서버의 /api/agent/task 로 보낸다 — DB 는 서버 하나만 쓴다.
대시보드 서버도 여기서 띄운다: 세션마다 뜨는 MCP 서버 중 포트를 먼저 연 하나가 맡는다 (server.lead, 리더 선출).
ponytail: 못 보낸 기록은 버린다 — 빠지면 안 되게 되면 파일에 쌓았다가 다시 보낸다

어느 세션의 호출인지는 부모 프로세스로 찾는다. claude 가 이 서버를 자식으로 띄우므로
조상 pid 중 하나의 ~/.claude/sessions/<pid>.json 에 sessionId 가 있다. /clear 로 세션이 바뀔 수 있어 호출마다 다시 읽는다.
"""
import json
import os
import subprocess
import sys
import threading
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
   코드를 바꾼 일(tag 개발·디버그)을 "done" 으로 끝낼 때는 flow 도 남긴다 — 코드를 읽지 않는 사용자가 바뀐 동작을 이해하는 흐름도다.
   trigger 는 그 동작을 무엇이 시작하나(사용자 동작·요청·일정), steps 는 실제로 도는 순서 2~6개(화면 → 서버 → DB 처럼,
   title 12자·detail 60자 안팎, 조건에 따라 갈리면 branch 에 "조건 → 처리"), outputs 는 사용자가 보게 되는 결과.
   쉬운 말로 쓰고, 코드 이름은 꼭 필요할 때만 괄호로 붙인다. 대시보드의 작업 줄을 펼치면 이 그림이 보인다.
3. 이 도구들이 지연 로드(deferred) 상태면 먼저 ToolSearch 로
   "select:mcp__plugin_hudson-fleet_fleet__task_start,mcp__plugin_hudson-fleet_fleet__task_update,mcp__plugin_hudson-fleet_fleet__task_list,mcp__plugin_hudson-fleet_fleet__project_list,mcp__plugin_hudson-fleet_fleet__project_archive,mcp__plugin_hudson-fleet_fleet__resource_save,mcp__plugin_hudson-fleet_fleet__resource_search" 를 불러온다.
4. 일하는 도중에 사용자가 덧붙인 요청도 규칙 1 을 따른다. 하던 일의 일부가 아니면 따로 task_start 한다
   (예: 노드 모양을 고치는 중에 "애니메이션도 넣어 줘" → 새 행). 바로 하지 않고 미루는 일도 task_start 만 해 두면 남은 일로 남는다.
   사용자에게 방법을 고르게 하거나 진행 여부를 묻는 제안을 했으면, 답을 기다리는 동안 그 제안도 task_start 로 남긴다
   (예: "제목 변경 방법 A·B 중 골라 구현한다"). 답을 받아 진행하면 그 행을 이어 쓰고, 하지 않기로 하면 "rejected".
5. 기록하지 않는 것: 질문에 답만 하는 경우, 확인·잡담. 같은 일을 두 번 시작하지 않는다.
6. 대화가 압축(compact)된 뒤에는 task_list 로 기록을 확인하고 이어서 쓴다.
7. 프로젝트: 세션에서 처음 task_start 하기 전에 project_list 를 한 번 불러, 이 일이 속한 프로젝트가 있으면 task_start 의
   project 에 그 id 를 넣는다 (이름·완료 조건으로 판단, 이름에 Jira 키가 있으면 그 이슈·에픽의 일인지로).
   맞는 것이 없거나 애매하면 비워 둔다 — 프로젝트는 사용자만 만든다. project 없이 기록하면 task_start 응답에
   진행 중인 프로젝트 목록이 오니, 그중 맞는 것이 있으면 task_update 의 project 로 적는다.
   사용자가 다른 프로젝트라고 알려 주면 task_update 의 project 로 바로잡는다.
8. 자료(Resources)·보관(Archives) — PARA 의 R·A. resource_save 는 두 경우에만 부른다: 사용자가 남기라고 했을 때,
   프로젝트를 보관할 때 남기는 정리 한 장(무엇을 정했고 왜, 다음에 알아야 할 것). 스스로 판단해 수시로 남기지 않는다.
   프로젝트의 완료 조건을 채운 것 같으면, 보관할지와 정리 한 장을 남길지 사용자에게 한 번에 묻고 동의하면
   project_archive 와 resource_save 를 부른다. 보관하면 그 프로젝트의 남은 일은 반려로 정리되므로, 남은 일이 있으면
   물을 때 함께 알린다.
   일을 시작할 때 같은 주제의 자료가 있을 법하면 resource_search 로 먼저 찾아본다."""

DETAILS = {"type": "array", "items": {"type": "string"}, "maxItems": 3}  # 3-Step-Desc (fleet/tasks.py MAX_DETAILS)
LINES = {"type": "array", "items": {"type": "string"}, "maxItems": 6}
FLOW = {"type": "object", "description": "선택. 코드를 바꾼 일을 done 으로 끝낼 때 — 바뀐 동작의 흐름도 (시작 → 단계 → 결과)",
        "properties": {"trigger": {"type": "string", "description": "무엇이 이 동작을 시작하나 (사용자 동작·요청·일정)"},
                       "inputs": {**LINES, "description": "선택. 쓰는 데이터·설정"},
                       "steps": {"type": "array", "minItems": 2, "maxItems": 6, "description": "실제로 도는 순서",
                                 "items": {"type": "object", "properties": {
                                     "title": {"type": "string", "description": "12자 안팎"},
                                     "detail": {"type": "string", "description": "60자 안팎 한 줄"},
                                     "branch": {"type": "string", "description": "선택. 조건에 따라 갈리면 '조건 → 처리'"}},
                                           "required": ["title", "detail"]}},
                       "outputs": {**LINES, "description": "사용자가 보게 되는 결과"},
                       "rules": {**LINES, "maxItems": 3, "description": "선택. 꼭 지키는 규칙"}},
        "required": ["trigger", "steps", "outputs"]}  # fleet/tasks.py norm_flow 가 다듬는다

TOOLS = [
    {"name": "task_start", "description": "작업을 시작하며 기록한다. 새 작업 id 를 돌려준다.",
     "inputSchema": {"type": "object", "properties": {
         "text": {"type": "string", "description": "120자 이내 한 문장"},
         "tag": {"type": "string", "enum": list(TAGS),
                 "description": "일의 종류 — " + " · ".join(f"{k}: {v}" for k, v in TAGS.items())},
         "details": {**DETAILS, "description": "선택. 할 일(계획)을 풀어 쓴 설명 1줄씩 최대 3개"},
         "project": {"type": "integer", "description": "선택. 이 일이 속한 프로젝트 id (project_list 에서 고른다). 맞는 것이 없으면 비운다"}},
                     "required": ["text", "tag"]}},
    {"name": "task_update", "description": "작업의 결과를 기록한다: done 완료 · stopped 중단 · rejected 반려 · todo 남은 일.",
     "inputSchema": {"type": "object", "properties": {
         "id": {"type": "integer"}, "status": {"type": "string", "enum": ["done", "stopped", "rejected", "todo"]},
         "note": {"type": "string", "description": "비고 한 줄 (done·stopped·rejected 때 꼭): 완료면 결과, 중단이면 멈춘 이유, 반려면 반려 이유"},
         "details": {**DETAILS, "description": "선택. 실제로 한 일·결과 1줄씩 최대 3개. 주면 기존 설명을 바꾼다"},
         "project": {"type": "integer", "description": "선택. 프로젝트를 바로잡을 때만. 0 이면 프로젝트에서 뺀다"},
         "flow": FLOW},
                     "required": ["id", "status"]}},
    {"name": "task_list", "description": "이 세션에 기록된 작업 목록 (순서대로).",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "project_list", "description": "끝나지 않은 프로젝트(id, 이름, 완료 조건, 상태, 영역)와"
                                            " 보관하지 않은 영역(id, 이름, 유지할 상태). task_start 의 project, resource_save 의 project·area 를 고를 때 쓴다.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "project_archive", "description": "프로젝트를 끝남으로 바꿔 보관한다. 그 프로젝트의 남은 일은 반려로 정리된다."
                                               " 사용자가 대화에서 동의했을 때만 부른다.",
     "inputSchema": {"type": "object", "properties": {"id": {"type": "integer"}}, "required": ["id"]}},
    {"name": "resource_save", "description": "자료(Resources) 한 건을 남긴다. 사용자가 남기라고 했을 때와, 프로젝트를 보관할 때 정리 한 장만.",
     "inputSchema": {"type": "object", "properties": {
         "title": {"type": "string", "description": "80자 이내 제목"},
         "summary": {"type": "string", "description": "100자 이내 한 줄 요약 — 목록에서 이것만 보고 쓸지 판단한다"},
         "body": {"type": "string", "description": "본문 (결정·근거·다음에 알아야 할 것, 2만 자 이내)"},
         "project": {"type": "integer", "description": "선택. 관련 프로젝트 id"},
         "area": {"type": "integer", "description": "선택. 관련 영역 id (안 주면 프로젝트의 영역)"}},
                     "required": ["title", "summary", "body"]}},
    {"name": "resource_search", "description": "자료를 낱말로 찾는다 (낱말마다 제목·요약·본문 어딘가에 든 것, 최근 5건, 본문 1500자까지).",
     "inputSchema": {"type": "object", "properties": {"query": {"type": "string", "description": "띄어 쓴 낱말들. 비우면 최근 자료"}}}},
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
        if e.code in (403, 404):  # 이 API 가 없는 프로그램이 포트를 잡고 있다: 경로가 없거나(404) Origin 검사가 먼저 막는다(403)
            # 대시보드는 리더 MCP 서버 안에서 돈다 — kill 하면 그 세션의 MCP 까지 꺼지므로 세션을 다시 시작하게 한다
            return {"error": "포트를 이 기록 API 가 없는 프로그램이 쓰고 있습니다. 사용자에게 lsof -i :8765 로 확인하고,"
                             " 옛 버전 Claude Code 세션이면 그 세션을 다시 시작(/exit 뒤 claude --resume)하라고 알리세요"}
        return json.loads(e.read() or "{}")


def api(body):
    """대시보드 서버로 보낸다. 리더가 바뀌는 중(1~2초)일 수 있어 5초까지 다시 시도한다."""
    for _ in range(10):
        try:
            return post(body)
        except urllib.error.URLError:
            time.sleep(0.5)
    return {"error": f"대시보드 서버({URL})에 연결하지 못해 기록하지 못했습니다. 사용자에게 다른 프로그램이 포트를 쓰고 있지 않은지"
                     " 확인하라고 알리세요 (lsof -i :8765)"}


def call(name, args):
    sid = my_session()
    if not sid:
        return "Claude Code 세션을 찾지 못했습니다", True
    if name == "task_start":
        r = api({"op": "start", "sid": sid, "text": args.get("text"), "tag": args.get("tag"), "details": args.get("details"),
                 "project": args.get("project")})
        return (r["error"], True) if "error" in r else (json.dumps(r, ensure_ascii=False), False)  # {id, projects?, hint?}
    if name == "task_update":
        r = api({"op": "update", "sid": sid, "id": args.get("id"), "status": args.get("status"), "note": args.get("note"),
                 "details": args.get("details"), "project": args.get("project"), "flow": args.get("flow")})
        return (r["error"], True) if "error" in r else ("기록했습니다", False)
    if name == "task_list":
        r = api({"op": "list", "sid": sid})
        return (r["error"], True) if "error" in r else (json.dumps(r["tasks"], ensure_ascii=False), False)
    if name == "project_list":
        r = api({"op": "projects", "sid": sid})
        return (r["error"], True) if "error" in r else (json.dumps(r, ensure_ascii=False), False)
    if name == "project_archive":
        r = api({"op": "project_archive", "sid": sid, "id": args.get("id")})
        return (r["error"], True) if "error" in r else ("보관했습니다", False)
    if name == "resource_save":
        r = api({"op": "resource_save", "sid": sid, **{k: args.get(k) for k in ("title", "summary", "body", "project", "area")}})
        return (r["error"], True) if "error" in r else (json.dumps({"id": r["id"]}), False)
    if name == "resource_search":
        r = api({"op": "resource_search", "sid": sid, "query": args.get("query")})
        return (r["error"], True) if "error" in r else (json.dumps(r["resources"], ensure_ascii=False), False)
    return f"없는 도구: {name}", True


def reply(mid, result=None, error=None):
    msg = {"jsonrpc": "2.0", "id": mid, **({"error": error} if error else {"result": result})}
    OUT.write(json.dumps(msg, ensure_ascii=False) + "\n")
    OUT.flush()


OUT = sys.stdout  # MCP 통신 전용. 대시보드 서버의 print·로그는 stderr 로 (stdout 에 섞이면 통신이 깨진다)


def main():
    sys.stdout = sys.stderr
    if URL == LOCAL:  # 다른 PC 의 서버를 쓰면 여기서 띄우지 않는다
        from server import lead
        threading.Thread(target=lead, daemon=True).start()
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
