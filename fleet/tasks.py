"""작업 기록: 추가·수정·조회와 haiku 정리."""
import json
import re
import sqlite3
import subprocess

from .config import CFG, QUIET, now_iso
from .db import db
from .transcripts import prompt_text, transcript


TASK_STATUS = {"완료": "done", "중단": "stopped", "남은일": "todo", "반려": "rejected"}
# 작업 태그(일의 종류) — MCP 도구 설명·haiku 프롬프트·웹 선택지가 모두 이 표를 쓴다. 모르는 값은 기타
TAGS = {
    "개발": "기능을 만들거나 고치는 코드 작업, 리팩터링 (원인을 알고 고치는 일 포함)",
    "디자인": "화면·UI·Figma 작업",
    "기획": "요구사항 정리, 계획 수립, 화면 흐름 설계",
    "테스트": "동작이 맞는지 확인하는 작업 (테스트 코드 작성·실행, 배포 전 검증)",
    "문서": "문서·안내문·노트 작성과 교정",
    "디버그": "원인을 모르는 문제의 원인 찾기",
    "데이터": "조회·집계·지표 뽑기, 결과 공유",
    "운영": "실제 운영 환경을 바꾸는 작업: 배포, DB 마이그레이션, 설정·인프라 변경, 체크리스트 실행",
    "기타": "위 어디에도 맞지 않는 일",
}
TAG_GUIDE = "\n".join(f"  {k} = {v}" for k, v in TAGS.items())


def norm_tag(tag):
    tag = re.sub(r"[^가-힣]", "", tag or "")
    return tag if tag in TAGS else "기타"


MAX_DETAILS = 3  # 3-Step-Desc: 지금은 2단계(작업 + 설명 3줄). 3단계는 항목을 {text, details} 로 늘려 받는다


def norm_details(d):
    """작업을 풀어 쓴 설명 줄 → JSON 배열 (줄당 120자, 최대 3줄). 안 주면 None (바꾸지 않음), 빈 목록이면 지운다."""
    if d is None:
        return None
    lines = [str(x).strip()[:120] for x in (d if isinstance(d, list) else [d]) if str(x).strip()]
    return json.dumps(lines[:MAX_DETAILS], ensure_ascii=False)


def norm_flow(d):
    """흐름도(Flow) 한 장 → 화면에 그릴 칸만 다듬는다 (작업·프로젝트·예약 작업이 같은 모양). 단계가 없으면 ValueError.
    {summary, trigger, inputs[], steps[{title, detail, branch}], outputs[], rules[]} — 시작 → 단계 → 결과, 조건 분기는 branch"""
    d = d if isinstance(d, dict) else {}
    lines = lambda v, n: [str(x).strip()[:120] for x in (v if isinstance(v, list) else []) if str(x).strip()][:n]
    steps = [{"title": str(s.get("title", "")).strip()[:40], "detail": str(s.get("detail", "")).strip()[:160],
              "branch": str(s.get("branch") or "").strip()[:160]} for s in d.get("steps") or [] if isinstance(s, dict)][:10]
    if not steps:
        raise ValueError("flow 에 steps(단계)가 없습니다")
    return {"summary": str(d.get("summary", "")).strip()[:200], "trigger": str(d.get("trigger", "")).strip()[:160],
            "inputs": lines(d.get("inputs"), 6), "steps": steps, "outputs": lines(d.get("outputs"), 6), "rules": lines(d.get("rules"), 3)}


def ask_flow(instr, body):
    """haiku 에게 흐름도 JSON 을 받아 다듬는다. 못 받으면 ValueError."""
    m = re.search(r"\{.*\}", ask_haiku(instr, body) or "", re.S)
    try:
        return norm_flow(json.loads(m[0]) if m else None)
    except ValueError:
        raise ValueError("AI 가 흐름을 정리하지 못했습니다. [새로 만들기] 를 다시 눌러 주세요") from None


def add_task(sid, text, source, status="todo", tag=None, details=None, project=None):
    """작업 한 행을 맨 뒤(sort 최댓값 + 1)에 넣는다. 새 id 를 돌려준다.
    project: 에이전트가 적은 프로젝트 id (fleet/para.py) — 있는 프로젝트인지는 부르는 쪽(web)이 확인한다."""
    t = now_iso()
    c = db()
    c.execute("INSERT INTO sessions (sid) VALUES (?) ON CONFLICT(sid) DO NOTHING", (sid,))
    sort = (c.execute("SELECT max(sort) FROM session_tasks WHERE sid = ?", (sid,)).fetchone()[0] or 0) + 1
    tid = c.execute("INSERT INTO session_tasks (sid, sort, status, text, source, created_at, updated_at, tag, details, project_id)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (sid, sort, status, text, source, t, t, norm_tag(tag), norm_details(details), project or None)).lastrowid
    c.commit()
    c.close()
    return tid


def set_task(tid, by, status=None, note=None, sort=None, delete=False, tag=None, details=None, project=None, flow=None):
    """작업 한 행의 분류·태그·순서·설명 줄·프로젝트(0 이면 뺀다)·흐름도(flow, norm_flow 로 다듬은 것)를 바꾸거나 지운다.
    어느 세션의 작업이든 id 로 고친다 — 다른 세션이 남긴 질문의 답을 이 세션에서 들었을 때 닫을 수 있게.
    사람이 haiku 행을 고치면 source 를 human 으로 바꿔 다음 haiku 정리 때 지워지지 않게 한다."""
    if (status is not None and status not in TASK_STATUS.values()) or (tag is not None and tag not in TAGS):
        return False
    c = db()
    where, key = "id = ?", (tid,)
    if delete:
        n = c.execute(f"DELETE FROM session_tasks WHERE {where}", key).rowcount
    else:
        n = c.execute(f"UPDATE session_tasks SET status = coalesce(?, status), sort = coalesce(?, sort),"
                      f" tag = coalesce(?, tag), details = coalesce(?, details), note = coalesce(?, note), flow = coalesce(?, flow), updated_at = ?,"
                      f" project_id = CASE WHEN ? IS NULL THEN project_id ELSE nullif(?, 0) END,"
                      f" source = CASE WHEN ? = 'human' AND source = 'haiku' THEN 'human' ELSE source END WHERE {where}",
                      (status, sort, tag, norm_details(details), note.strip()[:200] if isinstance(note, str) and note.strip()
                       else None, json.dumps(flow, ensure_ascii=False) if flow else None, now_iso(), project, project, by, *key)).rowcount
    c.commit()
    c.close()
    return n == 1


def move_task(tid, to_sid):
    """남은 일을 다른 세션으로 옮긴다 (끝난 세션의 남은 일 → 살아 있는 세션). 그 세션 목록의 맨 끝에 붙인다.
    살아 있는 세션인지는 부르는 쪽(web)이 확인한다. haiku 행이면 human 으로 바꾼다 — 받은 세션의 haiku 정리가 지우지 않게."""
    c = db()
    c.execute("INSERT OR IGNORE INTO sessions (sid) VALUES (?)", (to_sid,))  # 아직 1분 기록 전인 새 세션
    n = c.execute("UPDATE session_tasks SET sid = ?, updated_at = ?, source = replace(source, 'haiku', 'human'),"
                  " sort = (SELECT coalesce(max(sort), 0) + 1 FROM session_tasks WHERE sid = ?) WHERE id = ? AND status = 'todo'",
                  (to_sid, now_iso(), to_sid, tid)).rowcount
    c.commit()
    c.close()
    return n == 1


TASKS_SQL = "SELECT id, sort, status, text, source, tag, details, note, project_id, flow FROM session_tasks WHERE sid = ? ORDER BY sort, id"


def saved_tasks(sid):
    """DB 에 저장된 작업 목록과 그때의 대화 기록 수정 시각. 아직 없으면 ([], None)."""
    c = db()
    c.row_factory = sqlite3.Row
    row = c.execute("SELECT tasks_mtime FROM sessions WHERE sid = ?", (sid,)).fetchone()
    tasks = [dict(r) for r in c.execute(TASKS_SQL, (sid,))]
    c.close()
    return tasks, row["tasks_mtime"] if row else None


def summarize(sid):
    """에이전트가 MCP 로 직접 기록하지 않은 세션만 haiku 로 작업 목록을 만든다 (보조 수단).
    haiku 가 만든 행만 갈아 끼우고, 사람이 고친 행은 남긴다. 대화 기록이 그대로면 저장본을 쓴다."""
    path = transcript(sid)
    if not path:
        return {"error": "기록 없음"}
    mtime = path.stat().st_mtime
    tasks, tmt = saved_tasks(sid)
    if tmt == mtime or any(t["source"] == "agent" for t in tasks):
        return {"tasks": tasks, "cached": True}
    items = work_items(sid)  # 수십 초 — DB 연결은 그 뒤에 연다
    if not items:  # haiku 가 가끔 빈 답을 낸다 — 저장본으로 굳히지 않고 다음에 다시 시도
        return {"tasks": tasks, "cached": False}
    c = db()
    c.execute("INSERT INTO sessions (sid) VALUES (?) ON CONFLICT(sid) DO NOTHING", (sid,))
    c.execute("UPDATE sessions SET tasks_mtime = ? WHERE sid = ?", (mtime, sid))
    c.execute("DELETE FROM session_tasks WHERE sid = ? AND source = 'haiku'", (sid,))
    c.commit()
    c.close()
    for st, tag, t in items:
        add_task(sid, t, "haiku", st, tag)
    return {"tasks": saved_tasks(sid)[0], "cached": False}


def work_items(sid):
    """기록할 가치가 있는 작업만 [(분류, 태그, 작업)] — 항목당 최대 2줄. 히스토리에 모든 걸 남기지 않는다."""
    path = transcript(sid)
    text = ask_haiku("다음은 Claude Code 세션 기록이다. 나중에 다시 찾아볼 가치가 있는 작업만 골라 한국어로 적어라.\n"
                     "형식: 한 줄에 '분류|태그|작업' 하나. 분류는 완료·중단·남은일·반려 중 하나다.\n"
                     "  완료 = 끝까지 마친 작업, 중단 = 시작했지만 끝내지 못하고 멈춘 작업, 남은일 = 하기로 했지만 시작하지 않은 작업,\n"
                     "  반려 = 제안됐지만 사용자가 하지 않기로 한 작업\n"
                     "태그는 일의 종류로, 아래 중 가장 맞는 하나다.\n" + TAG_GUIDE + "\n"
                     "작업은 120자 이내 1~2문장, 동사로 끝낸다. 번호·기호·제목은 붙이지 않는다.\n"
                     "질문·확인·잡담·되돌린 시도는 뺀다. 기록할 작업이 없으면 아무것도 출력하지 않는다.",
                     digest(sid, path)) if path else ""
    out = []
    for line in text.splitlines():
        kind, *rest = line.split("|", 2)
        if not rest:  # 형식을 어긴 줄은 버린다
            continue
        tag, task = rest if len(rest) == 2 else ("", rest[0])  # 태그를 빼먹은 줄은 기타
        task = re.sub(r"^\s*(\d+[.)]|[-*•])\s*", "", task).strip()[:160]
        if task:
            out.append((TASK_STATUS.get(re.sub(r"[^가-힣]", "", kind), "done"), norm_tag(tag), task))
    return out[:20]


# AI 티 줄이기 — im-not-ai(github.com/epoko77-ai/im-not-ai, MIT)의 규칙 가운데 "쓰기 전에 넣어도 되는" 것만 골랐다
# (A-7·A-8·A-9·B-2·C-5·C-11·D-2·D-3·D-6·I-3). "~를 통해 한 문단 3회+" 같은 횟수 규칙은 쓰기 전에 넣으면 금지로 읽혀
# 글이 어색해진다고 원작자가 밝혀서 뺐다. 모든 haiku 정리(작업 정리·Flow·프로젝트·예약 작업 흐름도)가 이 함수를 거친다.
STYLE = """
한국어 문장을 쓸 때 지킬 것:
- 이중 피동(~되어진다, ~지게 된다)을 쓰지 않는다. "~에 의해 ~됐다" 대신 하는 쪽을 주어로 쓴다.
- "~을 가지고 있다" 같은 직역 대신 "~이 있다", "~하다"로 쓴다.
- "매우 중요하다, 주목할 만하다, 시사하는 바가 크다, 혁신적" 같은 과장을 쓰지 않고 실제로 한 일을 쓴다.
- "다음과 같다, 크게 세 가지로 나눌 수 있다" 같은 도입구 없이 바로 쓴다.
- "~다는 것이다", "~할 때입니다" 같은 맺음 공식을 쓰지 않는다.
- 연결어미(-고, -며, -지만) 바로 뒤에 쉼표를 찍지 않는다. 이모지를 쓰지 않는다.
- 광고 같은 영어(seamless, robust 등)는 우리말로 쓰고, API·DB·PR 같은 기술 용어는 그대로 둔다."""


def ask_haiku(instr, body):
    return subprocess.run(["claude", "-p", "--model", CFG["HUDSON_FLEET_SUMMARY_MODEL"], *QUIET, instr + STYLE],
                          input=body, capture_output=True, text=True, timeout=180).stdout.strip()


def digest(sid, path):
    """요약용 입력: 사용자 요청·Claude 답변(각각 잘라서) + 바뀐 파일 목록. 4만 자 이내."""
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
    # ponytail: 앞 1건 + 뒤쪽 위주로 4만 자 자르기, 긴 세션은 구간별 요약이 필요해지면 그때
    body = "\n".join(parts)
    if len(body) > 40_000:
        body = parts[0] + "\n...(중략)...\n" + body[-38_000:]
    return body
