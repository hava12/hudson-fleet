"""SQLite 저장소: 표 만들기와 단순 조회."""
import re
import sqlite3
import threading
import time
from pathlib import Path

from .config import CFG, now_iso


# 지표 저장소. 대화 기록은 cleanupPeriodDays(기본 30일) 뒤 지워지지만 이 표는 남는다.
# ponytail: SQLite 고정, 공유 서버(Postgres 등)가 필요해지면 db()/record() 두 곳만 바꾸면 된다
DB = Path(CFG["HUDSON_FLEET_DB"]).expanduser()


_lock, _ready = threading.Lock(), False


def db():
    """DB 연결. 표 만들기·칸 추가는 프로세스마다 처음 한 번만 한다 — 연결마다 하면 새 버전 직후 동시 요청이 같은 칸을 두 번 추가하다 실패한다."""
    global _ready
    with _lock:
        if not _ready:
            DB.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            schema(sqlite3.connect(DB)).close()
            DB.chmod(0o600)  # 토큰(설정)·프롬프트가 들어 있다 — 같은 Mac 의 다른 계정이 못 읽게
            try:
                DB.parent.chmod(0o700)  # 옆의 .env·server.log 도. 남의 폴더(/tmp 등)에 둔 DB 면 못 바꾼다
            except OSError:
                pass
            _ready = True
    return sqlite3.connect(DB)


def schema(c):
    c.execute("CREATE TABLE IF NOT EXISTS samples (ts INTEGER PRIMARY KEY, work INT, wait INT, idle INT,"
              " agents INT, pct5h INT, pct1w INT)")
    c.execute("CREATE TABLE IF NOT EXISTS daily (day TEXT PRIMARY KEY, tokens INT)")
    # 세션 1 : 작업 N. 살아 있는 세션도 1분마다 상태를 남기고, 끝나면 status=closed 로 바뀐다
    c.execute("CREATE TABLE IF NOT EXISTS sessions (sid TEXT PRIMARY KEY, name TEXT, title TEXT, cwd TEXT, kind TEXT,"
              " app TEXT, status TEXT, status_since TEXT, started_at TEXT, last_seen TEXT, ended_at TEXT,"
              " end_reason TEXT, tokens INT, tasks_mtime REAL)")  # status: work · wait · idle · closed
    if "user" in {r[1] for r in c.execute("PRAGMA table_info(sessions)")}:  # 지운 "기록 주인"(공유 서버 준비)이 남긴 칸
        c.execute("ALTER TABLE sessions DROP COLUMN user")
    if "my_title" not in {r[1] for r in c.execute("PRAGMA table_info(sessions)")}:  # 대시보드에서 붙인 제목 (Claude Code 파일은 안 건드림)
        c.execute("ALTER TABLE sessions ADD COLUMN my_title TEXT")
    if "deleted_at" not in {r[1] for r in c.execute("PRAGMA table_info(sessions)")}:  # 세션 기록에서 지운 시각 (soft delete — 행·작업은 남는다)
        c.execute("ALTER TABLE sessions ADD COLUMN deleted_at TEXT")
    # status: todo 남은 일 · done 완료 · stopped 중단 · rejected 반려 / source: agent(MCP) · haiku · human
    c.execute("CREATE TABLE IF NOT EXISTS session_tasks (id INTEGER PRIMARY KEY, sid TEXT REFERENCES sessions(sid),"
              " sort REAL, status TEXT, text TEXT, source TEXT, created_at TEXT, updated_at TEXT)")
    if "tag" not in {r[1] for r in c.execute("PRAGMA table_info(session_tasks)")}:  # 일의 종류 (TAGS). 옛 행은 비어 있다
        c.execute("ALTER TABLE session_tasks ADD COLUMN tag TEXT")
    if "details" not in {r[1] for r in c.execute("PRAGMA table_info(session_tasks)")}:  # 3-Step-Desc 설명 줄 (JSON 배열)
        c.execute("ALTER TABLE session_tasks ADD COLUMN details TEXT")
    if "note" not in {r[1] for r in c.execute("PRAGMA table_info(session_tasks)")}:  # 완료·중단·반려 때의 비고 한 줄
        c.execute("ALTER TABLE session_tasks ADD COLUMN note TEXT")
    if "flow" not in {r[1] for r in c.execute("PRAGMA table_info(session_tasks)")}:  # 에이전트가 코드를 바꾼 일을 끝낼 때 남긴 흐름도 (JSON, tasks.norm_flow)
        c.execute("ALTER TABLE session_tasks ADD COLUMN flow TEXT")
    if "project_id" not in {r[1] for r in c.execute("PRAGMA table_info(session_tasks)")}:  # 에이전트가 기록할 때 적은 프로젝트
        c.execute("ALTER TABLE session_tasks ADD COLUMN project_id INT")
    # PARA (fleet/para.py): 영역 1 : 프로젝트 N 1 : 작업 N. 영역·프로젝트는 사람이 만든다
    c.execute("CREATE TABLE IF NOT EXISTS areas (id INTEGER PRIMARY KEY, name TEXT UNIQUE, keep TEXT, created_at TEXT)")
    # status: pending 시작 전 · active 진행 중 · done 끝남(보관)
    # 0.5.27 까지 만든 DB 에는 지운 Jira 에픽 연결의 kind·epic·jira_status 칸이 남아 있다 (쓰지 않음, epic 은 UNIQUE 라 못 지운다)
    c.execute("CREATE TABLE IF NOT EXISTS projects (id INTEGER PRIMARY KEY, name TEXT, area_id INT, done_when TEXT, status TEXT,"
              " start TEXT, end TEXT)")
    if "folder" not in {r[1] for r in c.execute("PRAGMA table_info(projects)")}:  # 기획명세서를 만드는 프로젝트 폴더 ([명세서 업데이트])
        c.execute("ALTER TABLE projects ADD COLUMN folder TEXT")
    if "archived_at" not in {r[1] for r in c.execute("PRAGMA table_info(areas)")}:  # 더는 책임지지 않는 영역 (보관 칸으로)
        c.execute("ALTER TABLE areas ADD COLUMN archived_at TEXT")
    # 자료: 에이전트가 MCP 로 남긴다 (사용자가 남기라고 할 때 · 프로젝트를 보관할 때 정리 한 장). sid 는 남긴 세션
    c.execute("CREATE TABLE IF NOT EXISTS resources (id INTEGER PRIMARY KEY, title TEXT, summary TEXT, body TEXT,"
              " project_id INT, area_id INT, sid TEXT, created_at TEXT)")
    c.execute("DROP TABLE IF EXISTS task_events")  # 쌓기만 하고 읽지 않던 작업 이력(시작·완료·옮김 등)
    c.execute("DROP TABLE IF EXISTS session_files")  # 지운 "바뀐 파일" 기능(44f3f93)이 남긴 표
    # 세션에서 한 git push (Claude 의 Bash · 사용자의 ! 명령). 대화 기록이 지워져도 남도록 커밋 메시지까지 저장한다
    c.execute("CREATE TABLE IF NOT EXISTS pushes (id TEXT PRIMARY KEY, ts TEXT, sid TEXT, cwd TEXT, remote TEXT,"
              " ref TEXT, old TEXT, new TEXT, commits TEXT)")  # id = tool_use id + ref, commits = JSON [[hash, 제목]]
    # Claude 예약 작업(루틴) 저장본 한 줄 (fleet/routines.py). at = 받은 시각, data = JSON 목록
    c.execute("CREATE TABLE IF NOT EXISTS routines (id INTEGER PRIMARY KEY CHECK (id = 1), at TEXT, data TEXT)")
    # 루틴마다 AI 가 지시문을 정리한 흐름도 (id = 루틴 id). [새로 만들기] 전까지 그대로 쓴다. hash = 그때 지시문 — 바뀌면 화면이 알린다
    c.execute("CREATE TABLE IF NOT EXISTS routine_maps (id TEXT PRIMARY KEY, hash TEXT, at TEXT, data TEXT)")
    # 프로젝트마다 AI 가 작업 기록을 정리한 Flow. hash = 그때 넘긴 작업 기록 — 작업이 늘거나 바뀌면 다시 만든다
    c.execute("CREATE TABLE IF NOT EXISTS project_maps (id INTEGER PRIMARY KEY, hash TEXT, at TEXT, data TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS settings (name TEXT PRIMARY KEY, value TEXT)")  # 화면에서 바꾼 설정 (EDIT 에 있는 것만)
    c.execute("DROP TABLE IF EXISTS users")  # 지운 로그인 계정·API 키 기능(개인용으로 되돌림)이 남긴 표
    c.execute("DROP TABLE IF EXISTS api_keys")
    c.commit()
    return c


def my_title(sid):
    """대시보드에서 붙인 제목. 없으면 None."""
    c = db()
    row = c.execute("SELECT my_title FROM sessions WHERE sid = ?", (sid,)).fetchone()
    c.close()
    return row[0] if row else None


def set_title(sid, title):
    """대시보드에서만 쓰는 제목을 붙인다. 빈 값이면 지워서 원래 제목으로 돌아간다."""
    if not re.fullmatch(r"[0-9a-f-]{36}", sid or ""):
        return False
    c = db()
    c.execute("INSERT INTO sessions (sid, my_title) VALUES (?, ?) ON CONFLICT(sid) DO UPDATE SET my_title = excluded.my_title",
              (sid, (title or "").strip()[:120] or None))
    c.commit()
    c.close()
    return True


def delete_session(sid):
    """끝난 세션을 세션 기록·남은 일에서 숨긴다 (soft delete: deleted_at 만 적는다). 지웠으면 True.
    --resume 으로 다시 살아나면 recorder.track 이 deleted_at 을 지워 되돌린다."""
    c = db()
    n = c.execute("UPDATE sessions SET deleted_at = ? WHERE sid = ? AND status = 'closed' AND deleted_at IS NULL",
                  (now_iso(), sid)).rowcount
    c.commit()
    c.close()
    return n == 1


def metrics(hours):
    c = db()
    cols = ("ts", "work", "wait", "idle", "agents", "pct5h", "pct1w")
    rows = c.execute(f"SELECT {','.join(cols)} FROM samples WHERE ts >= ? ORDER BY ts",
                     (int(time.time() - hours * 3600),)).fetchall()
    c.close()
    return [dict(zip(cols, r)) for r in rows]


# ── 화면에서 바꾸는 설정 (settings 표, 환경 변수보다 먼저). 쓸 때마다 CFG 를 읽는 값만 받는다 ──
# 포트·DB 경로는 서버가 켜질 때 정해지고 MCP 서버도 환경 변수로 읽으므로 화면에서 바꾸지 않는다
EDIT = {  # 이름 → 받을 값 형식
    "HUDSON_FLEET_AUTO_SUMMARY": r"[01]",
    "HUDSON_FLEET_SUMMARY_MODEL": r"[\w.\[\]-]{1,60}",
    "HUDSON_FLEET_RETENTION_DAYS": r"\d{1,5}",
    "HUDSON_FLEET_TERMINAL": r"Ghostty|Terminal",
    "HUDSON_FLEET_GIST": r"[0-9a-f]{1,40}",
    "HUDSON_FLEET_GIST_USER": r"[\w-]{1,39}",
    "HUDSON_FLEET_GITHUB_ON": r"[01]",
    "HUDSON_FLEET_JIRA_ON": r"[01]",
    "HUDSON_FLEET_GITHUB_TOKEN": r"\S{20,255}",
    "HUDSON_FLEET_JIRA_SITE": r"[\w.-]+\.atlassian\.net",
    "HUDSON_FLEET_JIRA_EMAIL": r"[^@\s]+@[^@\s]+",
    "HUDSON_FLEET_JIRA_TOKEN": r"\S{16,512}",
}
BASE = dict(CFG)  # 환경 변수·기본값. 화면 값을 지우면 이리로 돌아간다


def saved_settings():
    c = db()
    out = dict(c.execute("SELECT name, value FROM settings").fetchall())
    c.close()
    return {k: v for k, v in out.items() if k in EDIT}


def load_settings():
    """서버를 켤 때 화면에서 바꾼 값을 CFG 에 덮어쓴다."""
    CFG.update(saved_settings())


def set_setting(name, value):
    """화면에서 설정 하나를 바꾼다. 빈 값이면 환경 변수·기본값으로 되돌린다. 잘못되면 오류 문장, 되면 None."""
    if name not in EDIT:
        return "화면에서 바꿀 수 없는 설정입니다 (환경 변수로만)"
    v = str(value or "").strip()
    if name.endswith("_SITE"):  # https://…/ 를 붙여 넣어도 주소만 남긴다
        v = re.sub(r"^https?://|/.*$", "", v)
    if v and not re.fullmatch(EDIT[name], v):
        return f"{name} 값 형식을 확인하세요"
    c = db()
    if v:
        c.execute("INSERT INTO settings VALUES (?, ?) ON CONFLICT(name) DO UPDATE SET value = excluded.value", (name, v))
    else:
        c.execute("DELETE FROM settings WHERE name = ?", (name,))
    c.commit()
    c.close()
    CFG[name] = v or BASE[name]


if __name__ == "__main__":  # 확인: HUDSON_FLEET_DB=<임시 파일> python3 -m fleet.db
    assert set_setting("HUDSON_FLEET_PORT", "1") and set_setting("HUDSON_FLEET_RETENTION_DAYS", "abc")
    assert set_setting("HUDSON_FLEET_RETENTION_DAYS", "30") is None and CFG["HUDSON_FLEET_RETENTION_DAYS"] == "30"
    assert saved_settings() == {"HUDSON_FLEET_RETENTION_DAYS": "30"}
    assert set_setting("HUDSON_FLEET_RETENTION_DAYS", "") is None and CFG["HUDSON_FLEET_RETENTION_DAYS"] == BASE["HUDSON_FLEET_RETENTION_DAYS"]
    k = db()
    k.executemany("INSERT INTO sessions (sid, status) VALUES (?, ?)", [("s-closed", "closed"), ("s-live", "work")])
    k.commit()
    k.close()
    assert delete_session("s-closed") and not delete_session("s-closed")  # 두 번 지우지 않는다
    assert not delete_session("s-live")  # 살아 있는 세션은 못 지운다
    print("ok")
