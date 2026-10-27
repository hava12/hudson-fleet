"""PARA 의 영역(Area)·프로젝트(Project). 영역과 프로젝트는 사람이 화면에서 만들고, 에이전트는 작업을 기록할 때 프로젝트를 적는다.
프로젝트는 두 가지다 — own: 직접 만든 것, 상태를 여기서 들고 있다 · jira: 에픽에 연결한 것, 이름·상태는 에픽이 근거라 받아 적기만 한다."""
import sqlite3
from datetime import date

from .config import CFG, now_iso
from .db import db
from .links import LinkError, jira_epic

STATUS = ("pending", "active", "done")  # 시작 전 · 진행 중 · 끝남
FROM_JIRA = {"new": "pending", "indeterminate": "active", "done": "done"}  # Jira 상태 분류 → 프로젝트 상태


def para():
    """화면용: 영역 전부, 프로젝트 전부와 각 프로젝트에 적힌 작업 (어느 세션의 작업인지 함께)."""
    c = db()
    c.row_factory = sqlite3.Row
    areas = [dict(r) for r in c.execute("SELECT * FROM areas ORDER BY name")]
    projects = [dict(r) for r in c.execute("SELECT * FROM projects ORDER BY start DESC, id DESC")]
    for p in projects:
        p["url"] = p["epic"] and f"https://{CFG['HUDSON_FLEET_JIRA_SITE']}/browse/{p['epic']}"
        p["tasks"] = [dict(r) for r in c.execute(
            "SELECT t.id, t.sid, t.status, t.text, t.source, t.tag, t.details, t.note, coalesce(s.my_title, s.title, s.name) AS session"
            " FROM session_tasks t LEFT JOIN sessions s USING (sid) WHERE t.project_id = ? ORDER BY t.created_at", (p["id"],))]
    c.close()
    return {"areas": areas, "projects": projects}


def open_projects():
    """에이전트용 (MCP project_list): 끝나지 않은 프로젝트."""
    c = db()
    c.row_factory = sqlite3.Row
    out = [dict(r) for r in c.execute(
        "SELECT p.id, p.name, p.kind, p.epic, p.done_when, p.status, a.name AS area FROM projects p"
        " LEFT JOIN areas a ON a.id = p.area_id WHERE p.status != 'done' ORDER BY p.start DESC")]
    c.close()
    return out


def has_project(pid):
    c = db()
    row = c.execute("SELECT 1 FROM projects WHERE id = ?", (pid,)).fetchone()
    c.close()
    return bool(row)


def project_of_epic(epic):
    """맡기기: 이슈가 속한 에픽에 연결한 프로젝트 (id, 이름). 없으면 None."""
    c = db()
    row = c.execute("SELECT id, name FROM projects WHERE epic = ?", (epic,)).fetchone() if epic else None
    c.close()
    return row


def save_area(b):
    """{id?, name, keep, delete?} — 영역을 만들거나 고치거나 지운다. 잘못되면 오류 문장, 되면 None.
    지우면 그 영역의 프로젝트는 영역 없음으로 남는다."""
    name, keep = str(b.get("name") or "").strip()[:60], str(b.get("keep") or "").strip()[:120]
    if not b.get("delete") and not name:
        return "영역 이름을 넣으세요"
    c = db()
    try:
        if b.get("delete"):
            c.execute("UPDATE projects SET area_id = NULL WHERE area_id = ?", (b.get("id"),))
            n = c.execute("DELETE FROM areas WHERE id = ?", (b.get("id"),)).rowcount
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


def _area(v):
    """영역 칸 값 → id 또는 None (빈 값·없는 영역)."""
    c = db()
    row = c.execute("SELECT id FROM areas WHERE id = ?", (v,)).fetchone() if v else None
    c.close()
    return row[0] if row else None


def save_project(b):
    """{id?, kind, name, done_when, epic, area_id, status, delete?} — 잘못되면 오류 문장, 되면 None.
    own 은 이름과 완료 조건이 있어야 만든다 (완료 조건을 못 적으면 프로젝트가 아니라 영역이다).
    jira 는 에픽 키만 받고 이름·상태는 Jira 에서 받는다. 지우면 그 프로젝트에 적힌 작업은 프로젝트 없음으로 남는다."""
    today, area = date.today().isoformat(), _area(b.get("area_id"))
    c = db()
    try:
        if b.get("delete"):
            c.execute("UPDATE session_tasks SET project_id = NULL WHERE project_id = ?", (b.get("id"),))
            n = c.execute("DELETE FROM projects WHERE id = ?", (b.get("id"),)).rowcount
        elif b.get("id"):
            row = c.execute("SELECT kind FROM projects WHERE id = ?", (b["id"],)).fetchone()
            if not row:
                return "프로젝트를 찾지 못했습니다"
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


def sync_jira():
    """jira 프로젝트의 이름·상태를 에픽에서 다시 받는다 (1분 기록이 10분마다). 에픽이 끝나면 end 를 채우고, 다시 열리면 비운다.
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
    assert p["status"] == "pending" and p["area_id"] == aid and p["end"] is None and open_projects()[0]["area"] == "백엔드"
    assert save_project({"id": p["id"], "name": "출석 알림", "done_when": "x", "status": "done"}) is None
    p = para()["projects"][0]
    assert p["end"] == date.today().isoformat() and p["area_id"] is None and not open_projects()  # 끝나면 end, 영역 비움
    assert save_project({"id": p["id"], "name": "출석 알림", "done_when": "x", "status": "active"}) is None
    assert para()["projects"][0]["end"] is None  # 다시 열면 end 를 비운다
    m.jira_epic = lambda k: {"key": k, "title": "PG 변경", "status": "진행 중", "cat": "indeterminate"}  # 가짜 Jira
    assert save_project({"kind": "jira", "epic": "bvvb-1"}) is None and save_project({"kind": "jira", "epic": "BVVB-1"}) == "이미 연결한 에픽입니다"
    j = next(x for x in para()["projects"] if x["kind"] == "jira")
    assert j["epic"] == "BVVB-1" and j["status"] == "active" and project_of_epic("BVVB-1")[0] == j["id"]
    assert save_project({"id": j["id"], "name": "바꿈", "status": "done", "area_id": aid}) is None
    j = next(x for x in para()["projects"] if x["kind"] == "jira")
    assert j["name"] == "PG 변경" and j["status"] == "active" and j["area_id"] == aid  # jira 는 영역만 바뀐다
    CFG["HUDSON_FLEET_JIRA_ON"] = "1"
    m.jira_epic = lambda k: {"key": k, "title": "PG 변경 (끝)", "status": "완료", "cat": "done"}
    sync_jira()
    j = next(x for x in para()["projects"] if x["kind"] == "jira")
    assert j["status"] == "done" and j["end"] and j["name"] == "PG 변경 (끝)"
    assert save_area({"id": aid, "delete": True}) is None and para()["projects"][0]["area_id"] is None
    print("ok")
