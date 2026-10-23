"""SQLite 저장소: 표 만들기와 단순 조회."""
import hashlib
import hmac
import os
import re
import sqlite3
import time
from pathlib import Path

from .config import CFG, now_iso


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
    # 설정 화면에서 추가한 로그인 계정. .env 의 관리자는 여기 없다. hash = pbkdf2_hmac(sha256, salt)
    c.execute("CREATE TABLE IF NOT EXISTS users (name TEXT PRIMARY KEY, salt TEXT, hash TEXT, created_at TEXT)")
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


# ── 로그인 계정: .env 의 관리자 하나 + 설정 화면에서 추가한 계정(users 표). 모두 같은 권한 ──
ENV_USER = CFG["HUDSON_FLEET_ADMIN_USER"]


def _hash(pw, salt):
    return hashlib.pbkdf2_hmac("sha256", str(pw).encode(), salt, 200_000).hex()


def _same(a, b):  # 맞춘 글자 수로 응답 시간이 달라지지 않게
    return hmac.compare_digest(str(a or "").encode(), str(b).encode())


def check_login(name, pw):
    if _same(name, ENV_USER) & _same(pw, CFG["HUDSON_FLEET_ADMIN_PASSWORD"]):
        return True
    c = db()
    row = c.execute("SELECT salt, hash FROM users WHERE name = ?", (str(name or ""),)).fetchone()
    c.close()
    return bool(row) and _same(_hash(pw or "", bytes.fromhex(row[0])), row[1])


def users():
    c = db()
    rows = c.execute("SELECT name, created_at FROM users ORDER BY created_at").fetchall()
    c.close()
    return [{"name": ENV_USER, "env": True}] + [{"name": n, "created_at": t} for n, t in rows]


def add_user(name, pw):
    """계정을 추가한다. 잘못되면 오류 문장, 되면 None."""
    if not re.fullmatch(r"[\w.@-]{1,40}", name or "") or name == ENV_USER:
        return "아이디를 확인하세요 (영문·숫자·._@- 40자 이내, 관리자와 다른 이름)"
    if len(str(pw or "")) < 8:
        return "비밀번호는 8자 이상이어야 합니다"
    salt = os.urandom(16)
    c = db()
    try:
        c.execute("INSERT INTO users VALUES (?, ?, ?, ?)", (name, salt.hex(), _hash(pw, salt), now_iso()))
        c.commit()
    except sqlite3.IntegrityError:
        return "이미 있는 아이디입니다"
    finally:
        c.close()


def del_user(name):
    c = db()
    n = c.execute("DELETE FROM users WHERE name = ?", (str(name or ""),)).rowcount
    c.commit()
    c.close()
    return n > 0


if __name__ == "__main__":  # 계정 확인: HUDSON_FLEET_DB=<임시 파일> python3 -m fleet.db
    assert add_user("kim", "short") and add_user(ENV_USER, "12345678")
    assert add_user("kim", "pass1234") is None and add_user("kim", "pass1234") == "이미 있는 아이디입니다"
    assert check_login("kim", "pass1234") and not check_login("kim", "x") and not check_login("nobody", "pass1234")
    assert [u["name"] for u in users()] == [ENV_USER, "kim"]
    assert del_user("kim") and not check_login("kim", "pass1234")
    print("ok")
