"""PARA — 일과 자료를 실행 가능성 순서로 네 칸에 나눈다 (티아고 포르테).
  Projects  프로젝트: 완료 조건이 있는 일. 사람이 만든다 (Jira 와는 묶지 않는다 — 에픽이면 이름에 키를 적는다)
  Areas     영역: 끝나지 않는 책임. 사람이 만들고, 더는 책임지지 않으면 보관한다
  Resources 자료: 나중에 쓸 참고. 에이전트가 MCP 로 남긴다 (사용자가 남기라고 할 때 · 프로젝트를 보관할 때 정리 한 장)
  Archives  보관: 끝난 프로젝트와 보관한 영역. 따로 표가 없다 — 프로젝트 status=done, 영역 archived_at 이 곧 보관이다
에이전트는 작업을 기록할 때 프로젝트 번호를 적는다 (session_tasks.project_id). 사람은 작업 줄의 프로젝트 칸에서 고친다."""
import hashlib
import json
import sqlite3
import subprocess
from datetime import date

from .config import now_iso
from .db import db
from .tasks import ask_flow

STATUS = ("pending", "active", "done")  # 시작 전 · 진행 중 · 끝남(보관)


def _rows(c, sql, args=()):
    c.row_factory = sqlite3.Row
    return [dict(r) for r in c.execute(sql, args)]


def para():
    """화면용: 영역·프로젝트(각각에 기록된 작업, 세션 이름 포함)·자료 전부. 보관은 화면이 상태로 가른다."""
    c = db()
    areas = _rows(c, "SELECT * FROM areas ORDER BY name")
    projects = _rows(c, "SELECT * FROM projects ORDER BY start DESC, id DESC")
    for p in projects:
        p["tasks"] = _rows(c, "SELECT t.id, t.sid, t.status, t.text, t.source, t.tag, t.details, t.note, t.project_id, t.flow,"
                              " coalesce(s.my_title, s.title, s.name) AS session FROM session_tasks t LEFT JOIN sessions s USING (sid)"
                              " WHERE t.project_id = ? ORDER BY t.created_at", (p["id"],))
        row = c.execute("SELECT hash, at, data FROM project_maps WHERE id = ?", (p["id"],)).fetchone()
        p["flow"] = row and {"data": json.loads(row[2]), "at": row[1], "stale": row[0] != _hash(flow_input(p, p["tasks"])),
                             "making": p["id"] in _making}
    resources = _rows(c, "SELECT r.*, p.name AS project, a.name AS area, coalesce(s.my_title, s.title, s.name) AS session"
                         " FROM resources r LEFT JOIN projects p ON p.id = r.project_id LEFT JOIN areas a ON a.id = r.area_id"
                         " LEFT JOIN sessions s ON s.sid = r.sid ORDER BY r.id DESC")
    c.close()
    return {"areas": areas, "projects": projects, "resources": resources}


# ── 프로젝트 Flow: AI(haiku)가 프로젝트의 작업 기록을 "무엇을 만들고 어떻게 동작하나" 흐름도 한 장으로 정리한다.
# 한 번 만들면 저장본을 쓰고, 작업이 늘거나 바뀌면(넘길 기록의 hash 가 달라지면) 화면이 펼칠 때 다시 만든다 ──
PROJ_ASK = """다음은 한 소프트웨어 프로젝트와 그 작업 기록이다. 코드를 읽지 않는 사람이 이 프로젝트가 만드는 기능이 어떻게 동작하는지
한눈에 보도록 흐름도로 정리해 JSON 하나만 출력하라. 코드 블록·설명은 붙이지 않는다.
{"summary": "이 프로젝트가 만드는 것 한 문장", "trigger": "사용자가 무엇을 하면(또는 언제) 이 기능이 시작되는지 한 줄",
 "inputs": ["쓰는 데이터·설정"], "steps": [{"title": "단계 이름 12자 이내", "detail": "그 단계에서 일어나는 일 한 줄",
 "branch": "조건에 따라 달라지면 '조건 → 처리' 한 줄, 없으면 빈 문자열"}], "outputs": ["사용자가 보게 되는 결과"],
 "rules": ["완료 조건·꼭 지킬 것, 최대 3개"]}
steps 는 작업을 한 순서가 아니라 기능이 동작하는 순서로 3~8개. 아직 끝나지 않은 단계는 detail 끝에 '(남은 일)' 을 붙인다.
작업 기록에 흐름이 있으면 그것을 우선 쓴다. 모든 문장은 쉬운 한국어로 60자 이내. 기록에 없는 내용은 지어내지 않는다."""
_making = set()
KO = {"todo": "남은 일", "done": "완료", "stopped": "중단", "rejected": "반려"}


def _hash(s):
    return hashlib.sha1(s.encode()).hexdigest()


def flow_input(p, tasks):
    """AI 에 넘길 프로젝트 기록 (오래된 작업부터, 1만 2천 자 이내). 이 글의 hash 로 Flow 가 낡았는지 본다."""
    out = [f"프로젝트: {p['name']}", f"완료 조건: {p['done_when']}", "작업 기록 (오래된 것부터):"]
    for t in tasks:
        out.append(f"- [{KO.get(t['status'], t['status'])}·{t.get('tag') or ''}] {t['text']}" + (f" — {t['note']}" if t.get("note") else ""))
        out += [f"  · {x}" for x in json.loads(t.get("details") or "[]")]
        if t.get("flow"):
            f = json.loads(t["flow"])
            out.append("  흐름: " + " → ".join([f.get("trigger") or "시작", *(s["title"] for s in f["steps"]), *f.get("outputs", [])]))
    return "\n".join(out)[-12000:]  # ponytail: 뒤쪽(최근) 1만 2천 자만, 작업이 아주 많아지면 단계별 요약으로


def make_project_flow(pid):
    """프로젝트 하나의 Flow 를 (다시) 만들어 저장한다."""
    p = next((x for x in para()["projects"] if x["id"] == pid), None)
    if not p or not p["tasks"]:
        return {"error": "작업 기록이 있는 프로젝트가 아닙니다"}
    if pid in _making:
        return {"error": "이미 만드는 중입니다"}
    _making.add(pid)
    text = flow_input(p, p["tasks"])
    try:
        data = ask_flow(PROJ_ASK, text)
    except (ValueError, OSError, subprocess.TimeoutExpired) as e:
        return {"error": str(e) if isinstance(e, ValueError) else "AI 를 부르지 못했습니다: " + str(e)}
    finally:
        _making.discard(pid)
    c = db()
    c.execute("INSERT OR REPLACE INTO project_maps VALUES (?,?,?,?)", (pid, _hash(text), now_iso(), json.dumps(data, ensure_ascii=False)))
    c.commit()
    c.close()
    return {"ok": True}


def agent_view():
    """에이전트용 (MCP project_list): 끝나지 않은 프로젝트와 보관하지 않은 영역."""
    c = db()
    out = {"projects": _rows(c, "SELECT p.id, p.name, p.done_when, p.status, a.name AS area FROM projects p"
                                " LEFT JOIN areas a ON a.id = p.area_id WHERE p.status != 'done' ORDER BY p.start DESC"),
           "areas": _rows(c, "SELECT id, name, keep FROM areas WHERE archived_at IS NULL ORDER BY name")}
    c.close()
    return out


def names():
    """작업 줄의 프로젝트 고르기 칸용: 프로젝트 전부 (id, 이름, 상태) — 끝난 프로젝트는 이미 붙은 작업에만 보인다."""
    c = db()
    out = _rows(c, "SELECT id, name, status FROM projects ORDER BY id DESC")
    c.close()
    return out


def _one(sql, args):
    c = db()
    row = c.execute(sql, args).fetchone()
    c.close()
    return row


def has_project(pid):
    return bool(_one("SELECT 1 FROM projects WHERE id = ?", (pid,)))


def _area(v):
    """영역 칸 값 → 보관하지 않은 영역의 id, 아니면 None (빈 값·없는 영역·보관한 영역)."""
    row = _one("SELECT id FROM areas WHERE id = ? AND archived_at IS NULL", (v,)) if v else None
    return row[0] if row else None


def _close_todos(c, pid):
    """프로젝트를 끝내면 그 프로젝트의 남은 일을 반려로 정리한다 (비고: 프로젝트 끝남). 남길 일은 먼저 다른 프로젝트로 옮긴다."""
    c.execute("UPDATE session_tasks SET status = 'rejected', note = '프로젝트 끝남', updated_at = ? WHERE project_id = ? AND status = 'todo'",
              (now_iso(), pid))


def save_area(b):
    """{id?, name, keep, archive?, delete?} — 영역을 만들거나 고치거나 보관(archive: true·false)하거나 지운다.
    잘못되면 오류 문장, 되면 None. 지우면 그 영역의 프로젝트·자료는 영역 없음으로 남는다."""
    name, keep = str(b.get("name") or "").strip()[:60], str(b.get("keep") or "").strip()[:120]
    if "archive" not in b and not b.get("delete") and not name:
        return "영역 이름을 넣으세요"
    c = db()
    try:
        if b.get("delete"):
            c.execute("UPDATE projects SET area_id = NULL WHERE area_id = ?", (b.get("id"),))
            c.execute("UPDATE resources SET area_id = NULL WHERE area_id = ?", (b.get("id"),))
            n = c.execute("DELETE FROM areas WHERE id = ?", (b.get("id"),)).rowcount
        elif "archive" in b:
            n = c.execute("UPDATE areas SET archived_at = ? WHERE id = ?", (now_iso() if b["archive"] else None, b.get("id"))).rowcount
        elif b.get("id"):
            n = c.execute("UPDATE areas SET name = ?, keep = ? WHERE id = ?", (name, keep, b["id"])).rowcount
        else:
            n = c.execute("INSERT INTO areas (name, keep, created_at) VALUES (?,?,?)", (name, keep, now_iso())).rowcount
        c.commit()
    except sqlite3.IntegrityError:
        return "같은 이름의 영역이 있습니다"
    finally:
        c.close()
    return None if n else "영역을 찾지 못했습니다"


def save_project(b):
    """{id?, name, done_when, area_id, status, delete?} — 잘못되면 오류 문장, 되면 None.
    이름과 완료 조건이 있어야 만든다 (완료 조건을 못 적으면 프로젝트가 아니라 영역이다). status=done 이 곧 보관이고, 남은 일은 반려로 정리한다.
    지우면 그 프로젝트에 적힌 작업·자료는 프로젝트 없음으로 남는다."""
    today, area = date.today().isoformat(), _area(b.get("area_id"))
    name, done_when, st = (str(b.get(k) or "").strip() for k in ("name", "done_when", "status"))
    c = db()
    try:
        if b.get("delete"):
            c.execute("UPDATE session_tasks SET project_id = NULL WHERE project_id = ?", (b.get("id"),))
            c.execute("UPDATE resources SET project_id = NULL WHERE project_id = ?", (b.get("id"),))
            n = c.execute("DELETE FROM projects WHERE id = ?", (b.get("id"),)).rowcount
        elif b.get("id"):
            row = c.execute("SELECT status, area_id FROM projects WHERE id = ?", (b["id"],)).fetchone()
            if not row:
                return "프로젝트를 찾지 못했습니다"
            if not name or not done_when or st not in STATUS:
                return "이름·완료 조건·상태를 확인하세요"
            if b.get("area_id") and b["area_id"] == row[1]:  # 그대로 둔 영역은 보관한 영역이어도 남긴다 (끝난 프로젝트를 되살릴 때)
                area = row[1]
            n = c.execute("UPDATE projects SET name = ?, done_when = ?, area_id = ?, status = ?,"
                          " end = CASE WHEN ? = 'done' THEN coalesce(end, ?) END WHERE id = ?",
                          (name[:80], done_when[:120], area, st, st, today, b["id"])).rowcount
            if st == "done" and row[0] != "done":
                _close_todos(c, b["id"])
        else:
            if not name or not done_when:
                return "이름과 완료 조건을 넣으세요. 완료 조건을 한 줄로 못 적으면 프로젝트가 아니라 영역입니다"
            n = c.execute("INSERT INTO projects (name, area_id, done_when, status, start) VALUES (?,?,?,?,?)",
                          (name[:80], area, done_when[:120], "pending", today)).rowcount
        c.commit()
    finally:
        c.close()
    return None if n else "프로젝트를 찾지 못했습니다"


def archive_project(pid):
    """에이전트용 (MCP project_archive): 프로젝트를 끝남(보관)으로, 남은 일은 반려로. 사용자 동의는 에이전트가 대화에서 받는다.
    잘못되면 오류 문장, 되면 None."""
    row = _one("SELECT status FROM projects WHERE id = ?", (pid,))
    if not row:
        return f"없는 프로젝트 id 입니다: {pid}"
    if row[0] == "done":
        return "이미 보관한 프로젝트입니다"
    c = db()
    c.execute("UPDATE projects SET status = 'done', end = ? WHERE id = ?", (date.today().isoformat(), pid))
    _close_todos(c, pid)
    c.commit()
    c.close()


def save_resource(b, sid=None):
    """{title, summary, body, project?, area?} — 자료 한 건. 제목과 한 줄 요약(100자)은 꼭. 새 id, 또는 오류 문장."""
    title, summary, body = (str(b.get(k) or "").strip() for k in ("title", "summary", "body"))
    if not title or not summary:
        return "제목과 한 줄 요약(summary)을 넣으세요"
    if len(summary) > 100:
        return f"한 줄 요약은 100자 이내로 줄이세요 (지금 {len(summary)}자)"
    pid = b.get("project") or None
    if pid and not has_project(pid):
        return f"없는 프로젝트 id 입니다: {pid}"
    area = _area(b.get("area"))
    if b.get("area") and not area:
        return f"없거나 보관한 영역 id 입니다: {b.get('area')}"
    if pid and not area:  # 영역을 안 주면 프로젝트의 영역을 따른다
        area = _one("SELECT area_id FROM projects WHERE id = ?", (pid,))[0]
    c = db()
    rid = c.execute("INSERT INTO resources (title, summary, body, project_id, area_id, sid, created_at) VALUES (?,?,?,?,?,?,?)",
                    (title[:80], summary, body[:20000], pid, area, sid, now_iso())).lastrowid
    c.commit()
    c.close()
    return rid


def search_resources(q, limit=5):
    """낱말마다 제목·요약·본문 어딘가에 들어 있는 자료 (최근 것부터). 본문은 1500자까지.
    ponytail: LIKE 검색, 자료가 수천 건을 넘어 느려지면 SQLite FTS5"""
    words = str(q or "").split()[:5]
    where = " AND ".join(["(r.title || ' ' || r.summary || ' ' || coalesce(r.body, '')) LIKE ?"] * len(words))
    c = db()
    out = _rows(c, "SELECT r.id, r.title, r.summary, substr(r.body, 1, 1500) AS body, p.name AS project, a.name AS area, r.created_at"
                   " FROM resources r LEFT JOIN projects p ON p.id = r.project_id LEFT JOIN areas a ON a.id = r.area_id"
                   + (f" WHERE {where}" if words else "") + " ORDER BY r.id DESC LIMIT ?", (*(f"%{w}%" for w in words), limit))
    c.close()
    return out


def delete_resource(rid):
    c = db()
    n = c.execute("DELETE FROM resources WHERE id = ?", (rid,)).rowcount
    c.commit()
    c.close()
    return n == 1


if __name__ == "__main__":  # 확인: HUDSON_FLEET_DB=<임시 파일> python3 -m fleet.para
    from .tasks import add_task
    assert save_area({"name": ""}) and save_area({"name": "백엔드", "keep": "장애 0"}) is None
    assert save_area({"name": "백엔드"}) == "같은 이름의 영역이 있습니다"
    aid = para()["areas"][0]["id"]
    assert save_project({"kind": "own", "name": "출석 알림"}).startswith("이름과 완료 조건")  # 완료 조건 없으면 안 만든다
    assert save_project({"kind": "own", "name": "출석 알림", "done_when": "푸시 지연 1초 이내", "area_id": aid}) is None
    p = para()["projects"][0]
    assert p["status"] == "pending" and p["area_id"] == aid and p["end"] is None and agent_view()["projects"][0]["area"] == "백엔드"
    assert save_project({"id": p["id"], "name": "출석 알림", "done_when": "x", "status": "done"}) is None
    p = para()["projects"][0]
    assert p["end"] == date.today().isoformat() and p["area_id"] is None and not agent_view()["projects"]  # 끝나면 end, 영역 비움
    assert save_project({"id": p["id"], "name": "출석 알림", "done_when": "x", "status": "active", "area_id": aid}) is None
    assert para()["projects"][0]["end"] is None  # 다시 열면 end 를 비운다
    # 자료
    assert save_resource({"title": "x"}).startswith("제목과") and "100자" in save_resource({"title": "x", "summary": "가" * 101})
    assert save_resource({"title": "x", "summary": "y", "project": 99}).startswith("없는 프로젝트")
    r1 = save_resource({"title": "FCM 발송 제한", "summary": "초당 600건 넘으면 지연", "body": "토픽 발송은 큐에 쌓인다", "project": p["id"]}, "sid-1")
    r2 = save_resource({"title": "결제 장애 정리", "summary": "PG 응답 지연 때 재시도", "body": "타임아웃 30초"})
    assert isinstance(r1, int) and para()["resources"][1]["area_id"] == aid  # 영역을 안 주면 프로젝트의 영역
    assert [r["id"] for r in search_resources("발송 큐")] == [r1] and [r["id"] for r in search_resources("")] == [r2, r1]
    assert not search_resources("발송 결제")
    # 보관 — 남은 일은 반려로 정리하고, 끝난 일은 그대로 둔다
    t1, t2 = add_task("sid-1", "문구 고치기", "agent", project=p["id"]), add_task("sid-1", "배포", "agent", "done", project=p["id"])
    assert archive_project(p["id"]) is None and archive_project(p["id"]) == "이미 보관한 프로젝트입니다" and archive_project(99)
    ts = {t["id"]: t for t in para()["projects"][0]["tasks"]}
    assert ts[t1]["status"] == "rejected" and ts[t1]["note"] == "프로젝트 끝남" and ts[t2]["status"] == "done"
    assert save_project({"name": "결제 교체", "done_when": "PG 전환"}) is None
    q = para()["projects"][0]
    t3 = add_task("sid-1", "PG 계약", "agent", project=q["id"])
    assert save_project({**q, "status": "active"}) is None and para()["projects"][0]["tasks"][0]["status"] == "todo"  # 끝낼 때만
    assert save_project({**q, "status": "done"}) is None and para()["projects"][0]["tasks"][0]["status"] == "rejected"
    assert [x["name"] for x in names()] == ["결제 교체", "출석 알림"]
    assert save_area({"id": aid, "archive": True}) is None and not agent_view()["areas"] and para()["areas"][0]["archived_at"]
    assert save_resource({"title": "x", "summary": "y", "area": aid}).startswith("없거나 보관한")  # 보관한 영역엔 안 붙인다
    assert save_area({"id": aid, "archive": False}) is None and agent_view()["areas"][0]["id"] == aid
    assert delete_resource(r2) and not delete_resource(r2)
    assert save_area({"id": aid, "delete": True}) is None and para()["resources"][0]["area_id"] is None
    # 프로젝트 Flow — AI 답을 받아 저장하고, 작업이 늘면 낡음(stale)으로 본다
    import fleet.tasks as T
    T.ask_haiku = lambda *a: '{"summary": "s", "trigger": "t", "steps": [{"title": "a", "detail": "b"}], "outputs": ["o"]}'
    assert make_project_flow(99)["error"] and make_project_flow(q["id"]) == {"ok": True}
    f = para()["projects"][0]["flow"]
    assert f["data"]["steps"][0]["title"] == "a" and not f["stale"]
    add_task("sid-1", "정산 화면", "agent", project=q["id"])
    assert para()["projects"][0]["flow"]["stale"]
    print("ok")
