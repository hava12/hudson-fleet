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


def add_task(sid, text, source, status="todo", tag=None):
    """작업 한 행을 맨 뒤(sort 최댓값 + 1)에 넣고 이력에 'start' 를 남긴다. 새 id 를 돌려준다."""
    t = now_iso()
    c = db()
    c.execute("INSERT INTO sessions (sid) VALUES (?) ON CONFLICT(sid) DO NOTHING", (sid,))
    sort = (c.execute("SELECT max(sort) FROM session_tasks WHERE sid = ?", (sid,)).fetchone()[0] or 0) + 1
    tid = c.execute("INSERT INTO session_tasks (sid, sort, status, text, source, created_at, updated_at, tag)"
                    " VALUES (?,?,?,?,?,?,?,?)", (sid, sort, status, text, source, t, t, norm_tag(tag))).lastrowid
    c.execute("INSERT INTO task_events (task_id, ts, status, note) VALUES (?,?,?,?)", (tid, t, "start", source))
    c.commit()
    c.close()
    return tid


def set_task(tid, by, status=None, note=None, sort=None, delete=False, sid=None, tag=None):
    """작업 한 행의 분류·태그·순서를 바꾸거나 지운다. sid 를 주면 그 세션의 작업만 건드린다 (MCP 용).
    사람이 haiku 행을 고치면 source 를 human 으로 바꿔 다음 haiku 정리 때 지워지지 않게 한다."""
    if (status is not None and status not in TASK_STATUS.values()) or (tag is not None and tag not in TAGS):
        return False
    c = db()
    where, key = "id = ?" + (" AND sid = ?" if sid else ""), (tid, *([sid] if sid else []))
    if delete:
        n = c.execute(f"DELETE FROM session_tasks WHERE {where}", key).rowcount
    else:
        n = c.execute(f"UPDATE session_tasks SET status = coalesce(?, status), sort = coalesce(?, sort),"
                      f" tag = coalesce(?, tag), updated_at = ?,"
                      f" source = CASE WHEN ? = 'human' AND source = 'haiku' THEN 'human' ELSE source END WHERE {where}",
                      (status, sort, tag, now_iso(), by, *key)).rowcount
    if n:
        c.execute("INSERT INTO task_events (task_id, ts, status, note) VALUES (?,?,?,?)",
                  (tid, now_iso(), "deleted" if delete else status or ("tag:" + tag if tag else "moved"), note or by))
    c.commit()
    c.close()
    return n == 1


TASKS_SQL = "SELECT id, sort, status, text, source, tag FROM session_tasks WHERE sid = ? ORDER BY sort, id"


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


def ask_haiku(instr, body):
    return subprocess.run(["claude", "-p", "--model", CFG["HUDSON_FLEET_SUMMARY_MODEL"], *QUIET, instr],
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
