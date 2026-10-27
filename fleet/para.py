"""PARA — 일과 자료를 실행 가능성 순서로 네 칸에 나눈다 (티아고 포르테).
  Projects  프로젝트: 완료 조건이 있는 일. 사람이 만든다 — own 직접 만든 것(상태를 여기서 들고 있다) · jira 에픽(이름·상태는 에픽이 근거)
  Areas     영역: 끝나지 않는 책임. 사람이 만들고, 더는 책임지지 않으면 보관한다
  Resources 자료: 나중에 쓸 참고. 에이전트가 MCP 로 남긴다 (사용자가 남기라고 할 때 · 프로젝트를 보관할 때 정리 한 장)
  Archives  보관: 끝난 프로젝트와 보관한 영역. 따로 표가 없다 — 프로젝트 status=done, 영역 archived_at 이 곧 보관이다
에이전트는 작업을 기록할 때 프로젝트 번호를 적는다 (session_tasks.project_id)."""
import sqlite3
from datetime import date

from .config import CFG, now_iso
from .db import db
from .links import LinkError, jira_epic

STATUS = ("pending", "active", "done")  # 시작 전 · 진행 중 · 끝남(보관)
FROM_JIRA = {"new": "pending", "indeterminate": "active", "done": "done"}  # Jira 상태 분류 → 프로젝트 상태


def _rows(c, sql, args=()):
    c.row_factory = sqlite3.Row
    return [dict(r) for r in c.execute(sql, args)]


def para():
    """화면용: 영역·프로젝트(각각에 기록된 작업, 세션 이름 포함)·자료 전부. 보관은 화면이 상태로 가른다."""
    c = db()
    areas = _rows(c, "SELECT * FROM areas ORDER BY name")
    projects = _rows(c, "SELECT * FROM projects ORDER BY start DESC, id DESC")
    for p in projects:
        p["url"] = p["epic"] and f"https://{CFG['HUDSON_FLEET_JIRA_SITE']}/browse/{p['epic']}"
        p["tasks"] = _rows(c, "SELECT t.id, t.sid, t.status, t.text, t.source, t.tag, t.details, t.note,"
                              " coalesce(s.my_title, s.title, s.name) AS session FROM session_tasks t LEFT JOIN sessions s USING (sid)"
                              " WHERE t.project_id = ? ORDER BY t.created_at", (p["id"],))
    resources = _rows(c, "SELECT r.*, p.name AS project, a.name AS area, coalesce(s.my_title, s.title, s.name) AS session"
                         " FROM resources r LEFT JOIN projects p ON p.id = r.project_id LEFT JOIN areas a ON a.id = r.area_id"
                         " LEFT JOIN sessions s ON s.sid = r.sid ORDER BY r.id DESC")
    c.close()
    return {"areas": areas, "projects": projects, "resources": resources}


def agent_view():
    """에이전트용 (MCP project_list): 끝나지 않은 프로젝트와 보관하지 않은 영역."""
    c = db()
    out = {"projects": _rows(c, "SELECT p.id, p.name, p.kind, p.epic, p.done_when, p.status, a.name AS area FROM projects p"
                                " LEFT JOIN areas a ON a.id = p.area_id WHERE p.status != 'done' ORDER BY p.start DESC"),
           "areas": _rows(c, "SELECT id, name, keep FROM areas WHERE archived_at IS NULL ORDER BY name")}
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


def project_of_epic(epic):
    """맡기기: 이슈가 속한 에픽에 연결한 프로젝트 (id, 이름, 영역 id). 없으면 None."""
    return _one("SELECT id, name, area_id FROM projects WHERE epic = ?", (epic,)) if epic else None


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
    """{id?, kind, name, done_when, epic, area_id, status, delete?} — 잘못되면 오류 문장, 되면 None.
    own 은 이름과 완료 조건이 있어야 만든다 (완료 조건을 못 적으면 프로젝트가 아니라 영역이다). status=done 이 곧 보관이다.
    jira 는 에픽 키만 받고 이름·상태는 Jira 에서 받는다. 지우면 그 프로젝트에 적힌 작업·자료는 프로젝트 없음으로 남는다."""
    today, area = date.today().isoformat(), _area(b.get("area_id"))
    c = db()
    try:
        if b.get("delete"):
            c.execute("UPDATE session_tasks SET project_id = NULL WHERE project_id = ?", (b.get("id"),))
            c.execute("UPDATE resources SET project_id = NULL WHERE project_id = ?", (b.get("id"),))
            n = c.execute("DELETE FROM projects WHERE id = ?", (b.get("id"),)).rowcount
        elif b.get("id"):
            row = c.execute("SELECT kind, area_id FROM projects WHERE id = ?", (b["id"],)).fetchone()
            if not row:
                return "프로젝트를 찾지 못했습니다"
            if b.get("area_id") and b["area_id"] == row[1]:  # 그대로 둔 영역은 보관한 영역이어도 남긴다 (끝난 프로젝트를 되살릴 때)
                area = row[1]
            if row[0] == "jira":  # 이름·상태는 Jira 가 근거 — 영역만 바꾼다
                n = c.execute("UPDATE projects SET area_id = ? WHERE id = ?", (area, b["id"])).rowcount
            else:
                name, done_when, st = (str(b.get(k) or "").strip() for k in ("name", "done_when", "status"))
                if not name or not done_when or st not in STATUS:
                    return "이름·완료 조건·상태를 확인하세요"
                n = c.execute("UPDATE projects SET name = ?, done_when = ?, area_id = ?, status = ?,"
                              " end = CASE WHEN ? = 'done' THEN coalesce(end, ?) END WHERE id = ?",
                              (name[:80], done_when[:120], area, st, st, today, b["id"])).rowcount
        elif b.get("kind") == "jira":
            try:
                e = jira_epic(str(b.get("epic") or "").strip().upper())
            except LinkError as x:
                return str(x)
            st = FROM_JIRA.get(e["cat"], "active")
            c.execute("INSERT INTO projects (kind, name, epic, area_id, status, jira_status, start, end) VALUES (?,?,?,?,?,?,?,?)",
                      ("jira", e["title"], e["key"], area, st, e["status"], today, today if st == "done" else None))
            n = 1
        else:
            name, done_when = (str(b.get(k) or "").strip() for k in ("name", "done_when"))
            if not name or not done_when:
                return "이름과 완료 조건을 넣으세요. 완료 조건을 한 줄로 못 적으면 프로젝트가 아니라 영역입니다"
            c.execute("INSERT INTO projects (kind, name, area_id, done_when, status, start) VALUES (?,?,?,?,?,?)",
                      ("own", name[:80], area, done_when[:120], "pending", today))
            n = 1
        c.commit()
    except sqlite3.IntegrityError:
        return "이미 연결한 에픽입니다"
    finally:
        c.close()
    return None if n else "프로젝트를 찾지 못했습니다"


def archive_project(pid):
    """에이전트용 (MCP project_archive): 직접 만든 프로젝트를 끝남(보관)으로. 사용자 동의는 에이전트가 대화에서 받는다.
    Jira 에픽 프로젝트는 에픽 상태가 근거라 여기서 바꾸지 않는다. 잘못되면 오류 문장, 되면 None."""
    row = _one("SELECT kind, status FROM projects WHERE id = ?", (pid,))
    if not row:
        return f"없는 프로젝트 id 입니다: {pid}"
    if row[0] == "jira":
        return "Jira 에픽 프로젝트는 에픽이 Done 이 되면 저절로 보관됩니다. Jira 에서 에픽을 끝내라고 사용자에게 알리세요"
    if row[1] == "done":
        return "이미 보관한 프로젝트입니다"
    c = db()
    c.execute("UPDATE projects SET status = 'done', end = ? WHERE id = ?", (date.today().isoformat(), pid))
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


def resources_for(pid, area, limit=5):
    """맡기기 지시문에 붙일 자료: 같은 프로젝트 또는 같은 영역의 최근 자료 (제목·요약)."""
    c = db()
    out = c.execute("SELECT title, summary FROM resources WHERE project_id = ? OR (? IS NOT NULL AND area_id = ?)"
                    " ORDER BY id DESC LIMIT ?", (pid, area, area, limit)).fetchall()
    c.close()
    return out


def delete_resource(rid):
    c = db()
    n = c.execute("DELETE FROM resources WHERE id = ?", (rid,)).rowcount
    c.commit()
    c.close()
    return n == 1


def sync_jira():
    """jira 프로젝트의 이름·상태를 에픽에서 다시 받는다 (1분 기록이 10분마다). 에픽이 끝나면 end 를 채우고(보관), 다시 열리면 비운다.
    한 에픽을 못 받아도(지워짐·권한) 나머지는 받는다."""
    if CFG["HUDSON_FLEET_JIRA_ON"] != "1":
        return
    c = db()
    rows = c.execute("SELECT id, epic FROM projects WHERE kind = 'jira'").fetchall()
    c.close()
    today = date.today().isoformat()
    for pid, epic in rows:
        try:
            e = jira_epic(epic)
        except LinkError as x:
            print("에픽 동기화 실패:", epic, x)
            continue
        st = FROM_JIRA.get(e["cat"], "active")
        c = db()
        c.execute("UPDATE projects SET name = ?, jira_status = ?, status = ?, end = CASE WHEN ? = 'done' THEN coalesce(end, ?) END"
                  " WHERE id = ?", (e["title"], e["status"], st, st, today, pid))
        c.commit()
        c.close()


if __name__ == "__main__":  # 확인: HUDSON_FLEET_DB=<임시 파일> python3 -m fleet.para
    import sys
    m = sys.modules[__name__]
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
    assert not search_resources("발송 결제") and resources_for(p["id"], aid) == [("FCM 발송 제한", "초당 600건 넘으면 지연")]
    # 보관
    assert archive_project(p["id"]) is None and archive_project(p["id"]) == "이미 보관한 프로젝트입니다" and archive_project(99)
    assert save_area({"id": aid, "archive": True}) is None and not agent_view()["areas"] and para()["areas"][0]["archived_at"]
    assert save_resource({"title": "x", "summary": "y", "area": aid}).startswith("없거나 보관한")  # 보관한 영역엔 안 붙인다
    assert save_area({"id": aid, "archive": False}) is None and agent_view()["areas"][0]["id"] == aid
    m.jira_epic = lambda k: {"key": k, "title": "PG 변경", "status": "진행 중", "cat": "indeterminate"}  # 가짜 Jira
    assert save_project({"kind": "jira", "epic": "bvvb-1"}) is None and save_project({"kind": "jira", "epic": "BVVB-1"}) == "이미 연결한 에픽입니다"
    j = next(x for x in para()["projects"] if x["kind"] == "jira")
    assert j["epic"] == "BVVB-1" and j["status"] == "active" and project_of_epic("BVVB-1")[0] == j["id"]
    assert archive_project(j["id"]).startswith("Jira 에픽 프로젝트는")
    assert save_project({"id": j["id"], "name": "바꿈", "status": "done", "area_id": aid}) is None
    j = next(x for x in para()["projects"] if x["kind"] == "jira")
    assert j["name"] == "PG 변경" and j["status"] == "active" and j["area_id"] == aid  # jira 는 영역만 바뀐다
    CFG["HUDSON_FLEET_JIRA_ON"] = "1"
    m.jira_epic = lambda k: {"key": k, "title": "PG 변경 (끝)", "status": "완료", "cat": "done"}
    sync_jira()
    j = next(x for x in para()["projects"] if x["kind"] == "jira")
    assert j["status"] == "done" and j["end"] and j["name"] == "PG 변경 (끝)"
    assert delete_resource(r2) and not delete_resource(r2)
    assert save_area({"id": aid, "delete": True}) is None and para()["resources"][0]["area_id"] is None
    print("ok")
