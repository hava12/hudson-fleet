"""SQLite 저장소: 표 만들기와 단순 조회."""
import hashlib
import hmac
import os
import re
import secrets
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
    if "user" not in {r[1] for r in c.execute("PRAGMA table_info(sessions)")}:  # 기록의 주인 — 작업·push 는 세션을 따라간다
        c.execute("ALTER TABLE sessions ADD COLUMN user TEXT")  # NULL = 이 PC 에서 읽은 기록 (서버 PC 주인 OWNER 것)
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
    c.execute("CREATE TABLE IF NOT EXISTS settings (name TEXT PRIMARY KEY, value TEXT)")
    # PC(MCP·수집기)가 서버에 "누구인지" 알리는 키. 원문은 발급 때 한 번만 보여 주고 sha256 만 저장한다
    c.execute("CREATE TABLE IF NOT EXISTS api_keys (id INTEGER PRIMARY KEY, user TEXT, hash TEXT UNIQUE, hint TEXT,"
              " created_at TEXT, last_used TEXT)")  # 화면에서 바꾼 설정 (EDIT 에 있는 것만)
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
# .env 관리자도 화면에서 비밀번호를 바꾸면 users 표에 행이 생기고, 그때부터는 그 행이 .env 보다 먼저다
ENV_USER = CFG["HUDSON_FLEET_ADMIN_USER"]
OWNER = ENV_USER  # 서버 PC 주인: 이 PC 의 세션·사용량·토큰 기록(sessions.user 가 NULL 인 행)과 서버 설정·계정 관리가 이 사람 것


def mine(alias, me):
    """SQL 조건과 값: 이 세션 행(alias)의 주인이 me 인가. 주인이 비어 있으면 OWNER 것."""
    a = alias + "." if alias else ""
    return f"(coalesce({a}user, ?) = ?)", (OWNER, me)


def owner(sid):
    """세션의 주인. 아직 행이 없으면 None (막 시작한 이 PC 세션)."""
    c = db()
    row = c.execute("SELECT coalesce(user, ?) FROM sessions WHERE sid = ?", (OWNER, sid)).fetchone()
    c.close()
    return row and row[0]


def task_owner(tid):
    c = db()
    row = c.execute("SELECT coalesce(s.user, ?) FROM session_tasks t JOIN sessions s USING (sid) WHERE t.id = ?",
                    (OWNER, tid)).fetchone()
    c.close()
    return row and row[0]


def _hash(pw, salt):
    return hashlib.pbkdf2_hmac("sha256", str(pw).encode(), salt, 200_000).hex()


def _same(a, b):  # 맞춘 글자 수로 응답 시간이 달라지지 않게
    return hmac.compare_digest(str(a or "").encode(), str(b).encode())


def _bad_pw(pw):
    return None if len(str(pw or "")) >= 8 else "비밀번호는 8자 이상이어야 합니다"


def _save_pw(c, name, pw):
    salt = os.urandom(16)
    c.execute("INSERT INTO users VALUES (?, ?, ?, ?) ON CONFLICT(name) DO UPDATE SET salt = excluded.salt, hash = excluded.hash",
              (name, salt.hex(), _hash(pw, salt), now_iso()))


def check_login(name, pw):
    c = db()
    row = c.execute("SELECT salt, hash FROM users WHERE name = ?", (str(name or ""),)).fetchone()
    c.close()
    if row:
        return _same(_hash(pw or "", bytes.fromhex(row[0])), row[1])
    return _same(name, ENV_USER) & _same(pw, CFG["HUDSON_FLEET_ADMIN_PASSWORD"])


def users():
    c = db()
    rows = c.execute("SELECT name, created_at FROM users ORDER BY created_at").fetchall()
    c.close()
    return [{"name": ENV_USER, "env": True}] + [{"name": n, "created_at": t} for n, t in rows if n != ENV_USER]


def add_user(name, pw):
    """계정을 추가한다. 잘못되면 오류 문장, 되면 None."""
    if not re.fullmatch(r"[\w.@-]{1,40}", name or "") or name == ENV_USER:
        return "아이디를 확인하세요 (영문·숫자·._@- 40자 이내, 관리자와 다른 이름)"
    if err := _bad_pw(pw):
        return err
    c = db()
    try:
        if c.execute("SELECT 1 FROM users WHERE name = ?", (name,)).fetchone():
            return "이미 있는 아이디입니다"
        _save_pw(c, name, pw)
        c.commit()
    finally:
        c.close()


def set_password(name, old, new):
    """자기 비밀번호 바꾸기. 지금 비밀번호를 맞혀야 한다. 잘못되면 오류 문장, 되면 None."""
    if not check_login(name, old):
        return "지금 비밀번호가 틀렸습니다"
    if err := _bad_pw(new):
        return err
    c = db()
    _save_pw(c, name, new)
    c.commit()
    c.close()


def del_user(name):
    if name == ENV_USER:  # .env 관리자는 지우지 않는다 (지우면 화면에서 바꾼 비밀번호가 .env 값으로 돌아간다)
        return False
    c = db()
    n = c.execute("DELETE FROM users WHERE name = ?", (str(name or ""),)).rowcount
    c.commit()
    c.close()
    return n > 0


# ── 화면에서 바꾸는 설정 (settings 표, 환경 변수보다 먼저). 쓸 때마다 CFG 를 읽는 값만 받는다 ──
# 포트·DB 경로·관리자 아이디는 서버가 켜질 때 정해지고 훅·MCP 도 환경 변수로 읽으므로 화면에서 바꾸지 않는다
EDIT = {  # 이름 → 받을 값 형식
    "HUDSON_FLEET_AUTO_SUMMARY": r"[01]",
    "HUDSON_FLEET_SUMMARY_MODEL": r"[\w.\[\]-]{1,60}",
    "HUDSON_FLEET_RETENTION_DAYS": r"\d{1,5}",
    "HUDSON_FLEET_TERMINAL": r"Ghostty|Terminal",
    "HUDSON_FLEET_GIST": r"[0-9a-f]{1,40}",
    "HUDSON_FLEET_GIST_USER": r"[\w-]{1,39}",
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


# ── API 키: 사용자마다 여러 개. 키는 무작위 32바이트라 느린 해시(pbkdf2) 없이 sha256 으로 충분하다 ──
def _key_hash(key):
    return hashlib.sha256(str(key).encode()).hexdigest()


def new_key(user):
    """키를 만들어 원문을 돌려준다. 원문은 저장하지 않으므로 이때만 볼 수 있다."""
    key = "hf_" + secrets.token_urlsafe(32)
    c = db()
    c.execute("INSERT INTO api_keys (user, hash, hint, created_at) VALUES (?, ?, ?, ?)",
              (user, _key_hash(key), key[:7] + "…" + key[-4:], now_iso()))
    c.commit()
    c.close()
    return key


def keys(user):
    c = db()
    rows = c.execute("SELECT id, hint, created_at, last_used FROM api_keys WHERE user = ? ORDER BY id", (user,)).fetchall()
    c.close()
    return [dict(zip(("id", "hint", "created_at", "last_used"), r)) for r in rows]


def del_key(user, kid):
    c = db()
    n = c.execute("DELETE FROM api_keys WHERE id = ? AND user = ?", (kid, user)).rowcount  # 남의 키는 못 지운다
    c.commit()
    c.close()
    return n > 0


def key_user(key):
    """키의 주인. 없거나 틀리면 None. 쓸 때마다 last_used 를 남긴다."""
    if not str(key or "").startswith("hf_"):
        return None
    c = db()
    row = c.execute("SELECT id, user FROM api_keys WHERE hash = ?", (_key_hash(key),)).fetchone()
    if row:
        c.execute("UPDATE api_keys SET last_used = ? WHERE id = ?", (now_iso(), row[0]))
        c.commit()
    c.close()
    return row and row[1]


if __name__ == "__main__":  # 확인: HUDSON_FLEET_DB=<임시 파일> python3 -m fleet.db
    assert add_user("kim", "short") and add_user(ENV_USER, "12345678")
    assert add_user("kim", "pass1234") is None and add_user("kim", "pass1234") == "이미 있는 아이디입니다"
    assert check_login("kim", "pass1234") and not check_login("kim", "x") and not check_login("nobody", "pass1234")
    assert set_password("kim", "x", "newpass99") and set_password("kim", "pass1234", "newpass99") is None
    assert check_login("kim", "newpass99") and not check_login("kim", "pass1234")
    pw = CFG["HUDSON_FLEET_ADMIN_PASSWORD"]  # .env 관리자: 바꾸면 .env 값으로는 못 들어온다
    assert set_password(ENV_USER, pw, "adminpass1") is None and check_login(ENV_USER, "adminpass1") and not check_login(ENV_USER, pw)
    assert [u["name"] for u in users()] == [ENV_USER, "kim"] and not del_user(ENV_USER)
    assert del_user("kim") and not check_login("kim", "newpass99")
    assert set_setting("HUDSON_FLEET_PORT", "1") and set_setting("HUDSON_FLEET_RETENTION_DAYS", "abc")
    assert set_setting("HUDSON_FLEET_RETENTION_DAYS", "30") is None and CFG["HUDSON_FLEET_RETENTION_DAYS"] == "30"
    assert saved_settings() == {"HUDSON_FLEET_RETENTION_DAYS": "30"}
    assert set_setting("HUDSON_FLEET_RETENTION_DAYS", "") is None and CFG["HUDSON_FLEET_RETENTION_DAYS"] == BASE["HUDSON_FLEET_RETENTION_DAYS"]
    k = new_key("kim")
    assert key_user(k) == "kim" and key_user(k + "x") is None and key_user("nope") is None
    kid = keys("kim")[0]["id"]
    assert keys("kim")[0]["last_used"] and not del_key("lee", kid) and del_key("kim", kid) and key_user(k) is None
    c = db()
    c.execute("INSERT INTO sessions (sid) VALUES ('s-local')")
    c.execute("INSERT INTO sessions (sid, user) VALUES ('s-kim', 'kim')")
    c.commit()
    w, a = mine("", "kim")
    assert [r[0] for r in c.execute(f"SELECT sid FROM sessions WHERE {w}", a)] == ["s-kim"]
    w, a = mine("", OWNER)
    assert [r[0] for r in c.execute(f"SELECT sid FROM sessions WHERE {w}", a)] == ["s-local"]
    c.close()
    assert owner("s-local") == OWNER and owner("s-kim") == "kim" and owner("none") is None
    print("ok")
