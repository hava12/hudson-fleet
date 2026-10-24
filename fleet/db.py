"""SQLite 저장소: 표 만들기와 단순 조회."""
import re
import sqlite3
import time
from pathlib import Path

from .config import CFG


# 지표 저장소. 대화 기록은 cleanupPeriodDays(기본 30일) 뒤 지워지지만 이 표는 남는다.
# ponytail: SQLite 고정, 공유 서버(Postgres 등)가 필요해지면 db()/record() 두 곳만 바꾸면 된다
DB = Path(CFG["HUDSON_FLEET_DB"]).expanduser()


def db():
    DB.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB)
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
    # status: todo 남은 일 · done 완료 · stopped 중단 · rejected 반려 / source: agent(MCP) · haiku · human
    c.execute("CREATE TABLE IF NOT EXISTS session_tasks (id INTEGER PRIMARY KEY, sid TEXT REFERENCES sessions(sid),"
              " sort REAL, status TEXT, text TEXT, source TEXT, created_at TEXT, updated_at TEXT)")
    if "tag" not in {r[1] for r in c.execute("PRAGMA table_info(session_tasks)")}:  # 일의 종류 (TAGS). 옛 행은 비어 있다
        c.execute("ALTER TABLE session_tasks ADD COLUMN tag TEXT")
    if "details" not in {r[1] for r in c.execute("PRAGMA table_info(session_tasks)")}:  # 3-Step-Desc 설명 줄 (JSON 배열)
        c.execute("ALTER TABLE session_tasks ADD COLUMN details TEXT")
    if "note" not in {r[1] for r in c.execute("PRAGMA table_info(session_tasks)")}:  # 완료·중단·반려 때의 비고 한 줄
        c.execute("ALTER TABLE session_tasks ADD COLUMN note TEXT")
    c.execute("CREATE TABLE IF NOT EXISTS task_events (id INTEGER PRIMARY KEY, task_id INT, ts TEXT, status TEXT,"
              " note TEXT)")  # 시작·완료·중단·반려·순서 변경 이력 (추가만)
    c.execute("DROP TABLE IF EXISTS session_files")  # 지운 "바뀐 파일" 기능(44f3f93)이 남긴 표
    # 세션에서 한 git push (Claude 의 Bash · 사용자의 ! 명령). 대화 기록이 지워져도 남도록 커밋 메시지까지 저장한다
    c.execute("CREATE TABLE IF NOT EXISTS pushes (id TEXT PRIMARY KEY, ts TEXT, sid TEXT, cwd TEXT, remote TEXT,"
              " ref TEXT, old TEXT, new TEXT, commits TEXT)")  # id = tool_use id + ref, commits = JSON [[hash, 제목]]
    c.execute("CREATE TABLE IF NOT EXISTS settings (name TEXT PRIMARY KEY, value TEXT)")  # 화면에서 바꾼 설정 (EDIT 에 있는 것만)
    c.execute("DROP TABLE IF EXISTS users")  # 지운 로그인 계정·API 키 기능(개인용으로 되돌림)이 남긴 표
    c.execute("DROP TABLE IF EXISTS api_keys")
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
    print("ok")
