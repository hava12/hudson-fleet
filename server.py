"""Hudson Fleet — Claude Code 세션 대시보드. 실행: python3 server.py → http://127.0.0.1:8765 (포트는 HUDSON_FLEET_PORT)"""
import difflib
import glob
import itertools
import json
import os
import re
import shlex
import signal
import sqlite3
import subprocess
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# 설정은 모두 환경 변수 — ~/.claude/settings.json 의 "env" 에 적으면 훅·MCP·서버가 함께 받는다. 바꾸면 서버 재시작.
CONFIG = [  # (이름, 기본값, 설명)
    ("HUDSON_FLEET_PORT", "8765", "대시보드 서버 포트"),
    ("HUDSON_FLEET_DB", str(Path.home() / ".local" / "share" / "hudson-fleet" / "metrics.db"), "SQLite 파일 경로"),
    ("HUDSON_FLEET_AUTO_SUMMARY", "1", "에이전트 기록이 없는 세션이 끝날 때 AI 로 작업 정리 (0 이면 끔 — 토큰 절약)"),
    ("HUDSON_FLEET_SUMMARY_MODEL", "haiku", "작업 정리에 쓰는 모델"),
    ("HUDSON_FLEET_RETENTION_DAYS", "0", "1분 지표(samples) 보관 일수. 0 이면 지우지 않음"),
    ("HUDSON_FLEET_TERMINAL", "Ghostty", "끝난 세션을 다시 열 터미널 앱: Ghostty 또는 Terminal"),
]
CFG = {k: os.environ.get(k) or d for k, d, _ in CONFIG}
PORT = int(CFG["HUDSON_FLEET_PORT"])
ORIGIN = f"http://127.0.0.1:{PORT}"
PROJECTS = Path.home() / ".claude" / "projects"
SESSIONS = Path.home() / ".claude" / "sessions"
EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
DEAD = {"stopped", "completed", "done", "failed"}


# 대시보드가 내부용으로 돌리는 claude -p 는 MCP 서버·훅을 띄우지 않는다.
# 안 그러면 호출마다 사용자의 MCP 서버(예: Java 서버)와 다른 플러그인의 SessionStart 훅이 전부 실행된다.
QUIET = ("--no-session-persistence", "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
         "--settings", '{"disableAllHooks":true}')


def claude(*args, cwd=None):
    r = subprocess.run(["claude", *args], cwd=cwd, capture_output=True, text=True, timeout=60)
    return (r.stdout or r.stderr).strip()


def transcript(sid):
    # ponytail: glob over all projects per request, index by sid if project count grows large
    hits = glob.glob(str(PROJECTS / "*" / f"{glob.escape(sid)}.jsonl"))
    return Path(hits[0]) if sid and hits else None


def diff_of(tool, inp):
    """편집 도구 입력 → unified diff 본문. Write 는 전체가 추가로 보인다."""
    if tool == "Edit":
        pairs = [(inp.get("old_string", ""), inp.get("new_string", ""))]
    elif tool == "MultiEdit":
        pairs = [(e.get("old_string", ""), e.get("new_string", "")) for e in inp.get("edits", [])]
    else:
        pairs = [("", inp.get("content") or inp.get("new_source", ""))]
    lines = []
    for old, new in pairs:
        lines += difflib.unified_diff(old.splitlines(), new.splitlines(), lineterm="", n=2)
    return "\n".join(l for l in lines if not l.startswith(("---", "+++")))


def git_diff(fp, result):
    """도구 결과의 structuredPatch(실제 파일 줄 번호) → git 형식 unified diff. 없으면 None."""
    patch = result.get("structuredPatch")
    if patch:
        hunks = [f"@@ -{h['oldStart']},{h['oldLines']} +{h['newStart']},{h['newLines']} @@\n" + "\n".join(h["lines"])
                 for h in patch]
        return f"--- a{fp}\n+++ b{fp}\n" + "\n".join(hunks)
    if result.get("type") == "create":  # 새 파일: 전체가 추가
        lines = result.get("content", "").splitlines()
        return f"--- /dev/null\n+++ b{fp}\n@@ -0,0 +1,{len(lines)} @@\n" + "\n".join("+" + l for l in lines)
    return None


def scan(path, by):
    """jsonl 하나 → (성공한 편집 이벤트 목록, 마지막 assistant 답변). 훅 등에 막힌 호출은 뺀다."""
    events, failed, patches, last = {}, set(), {}, ""
    for line in path.open(encoding="utf-8", errors="replace"):
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        content = rec.get("message", {}).get("content", [])
        if not isinstance(content, list):
            continue
        for c in content:
            if not isinstance(c, dict):
                continue
            if c.get("type") == "tool_result":
                if c.get("is_error"):
                    failed.add(c.get("tool_use_id"))
                elif isinstance(rec.get("toolUseResult"), dict) and rec["toolUseResult"].get("filePath"):
                    patches[c.get("tool_use_id")] = git_diff(rec["toolUseResult"]["filePath"], rec["toolUseResult"])
            elif rec.get("type") != "assistant":
                continue
            elif c.get("type") == "tool_use" and c.get("name") in EDIT_TOOLS:
                inp = c.get("input", {})
                fp = inp.get("file_path") or inp.get("notebook_path")
                if fp:
                    events[c.get("id")] = {"file": fp, "ts": rec.get("timestamp", ""), "tool": c["name"],
                                           "by": by, "diff": diff_of(c["name"], inp)}
            elif c.get("type") == "text" and c.get("text", "").strip():
                last = c["text"]
    for i, e in events.items():
        # 실제 줄 번호가 있는 patch 우선, 없으면(옛 기록) 입력 조각으로 만든 diff 에 헤더만 붙인다
        e["diff"] = patches.get(i) or f"--- a{e['file']}\n+++ b{e['file']}\n{e['diff']}"
    return [e for i, e in events.items() if i not in failed], last


def subagents(sid):
    """[(agentId, 설명, jsonl 경로)] — 기록 위치: <sid>/subagents/agent-<id>.jsonl"""
    path = transcript(sid)
    if not path:
        return []
    out = []
    for p in sorted((path.parent / sid / "subagents").glob("agent-*.jsonl")):
        meta = p.with_suffix(".meta.json")
        desc = json.loads(meta.read_text()).get("description", "") if meta.exists() else ""
        out.append((p.stem.removeprefix("agent-"), desc, p))
    return out


def prompt_text(rec):
    """사용자가 직접 입력한 메시지만 — 도구 결과·명령 출력·시스템 주입은 뺀다."""
    if rec.get("type") != "user" or rec.get("isMeta") or rec.get("isCompactSummary"):
        return ""
    c = rec.get("message", {}).get("content", "")
    if isinstance(c, list):
        c = " ".join(x.get("text", "") for x in c if isinstance(x, dict) and x.get("type") == "text")
    c = c.strip()
    return "" if c.startswith("<") else c


_memo = {}


def by_mtime(fn):
    """대화 기록을 읽는 함수의 결과를 그 파일(마지막 인자)이 바뀌기 전까지 재사용한다. 36MB 기록이면 ~0.2초 아낀다."""
    def wrap(*a):
        key, m = (fn.__name__, *map(str, a)), a[-1].stat().st_mtime
        hit = _memo.get(key)
        if not hit or hit[0] != m:
            hit = _memo[key] = (m, fn(*a))
        return hit[1]
    return wrap


@by_mtime
def overview(path):
    """토큰 없이 만드는 세션 개요: 제목(ai-title/custom-title), 시킨 일, 시작·마지막 시각."""
    title, prompts, first, last = "", [], "", ""
    for line in path.open(encoding="utf-8", errors="replace"):
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        title = rec.get("customTitle") or rec.get("aiTitle") or title
        ts = rec.get("timestamp", "")
        if ts:
            first, last = first or ts, ts
        if p := prompt_text(rec):
            prompts.append({"ts": ts, "text": p[:300]})
    return {"title": title, "prompts": prompts, "first": first, "last": last}


def session(sid):
    """세션 개요 + 프로세스 경로 + 본체·서브에이전트의 변경 이력(시간순)."""
    path = transcript(sid)
    s = find_session(sid) or {}
    base = {"home": str(Path.home()), "proc": proc_chain(s["pid"]) if s.get("pid") else []}
    if not path:
        return {**base, "changes": [], "overview": {}}
    changes, ov = changes_of(sid, path), overview(path)
    return {**base, "changes": changes, "status": file_status(changes, ov["first"]), "overview": ov}


def file_status(changes, started):
    """git 처럼 D(지금 없음) · A(세션 시작 때 없었음) · M(그 밖).
    A 는 첫 편집이 새 파일 만들기이거나, 파일이 처음 생긴 시각(macOS birthtime)이 세션 시작보다 뒤인 경우.
    셸 mv 로 옮긴 파일도 birthtime 이 유지돼 생성으로 잡힌다."""
    t0 = datetime.fromisoformat(started.replace("Z", "+00:00")).timestamp() if started else 0
    status = {}
    for e in changes:
        f = e["file"]
        if f in status:
            continue
        if not os.path.exists(f):
            status[f] = "D"
        elif e["diff"].startswith("--- /dev/null") or getattr(os.stat(f), "st_birthtime", 0) >= t0 > 0:
            status[f] = "A"
        else:
            status[f] = "M"
    return status


FILE_HISTORY = Path.home() / ".claude" / "file-history"


def net_diff(sid, fp, changes, created):
    """세션이 처음 손대기 전 → 지금 디스크 상태를 한 번에 비교한 diff.
    처음 상태는 Claude Code 의 되돌리기(/rewind)용 백업 중 가장 이른 판. 없으면 diff=None (옛 기록·정리됨)."""
    first = next(e for e in changes if e["file"] == fp)
    if created or first["diff"].startswith("--- /dev/null"):  # 세션 중에 생긴 파일(지운 것 포함) — 빈 파일에서 시작
        base, src = "", "new"
        base, src = "", "new"
    else:
        h = None
        for line in transcript(sid).open(encoding="utf-8", errors="replace"):
            if '"file-history-snapshot"' not in line:
                continue
            for rel, b in json.loads(line).get("snapshot", {}).get("trackedFileBackups", {}).items():
                if b.get("backupFileName") and os.path.join(b.get("realParentDir", ""), os.path.basename(rel)) == fp:
                    h = b["backupFileName"].split("@")[0]
            if h:
                break
        vs = sorted(FILE_HISTORY.glob(f"{sid}/{h}@v*"), key=lambda p: int(p.name.rsplit("@v", 1)[1])) if h else []
        if not vs:
            return {"diff": None}
        base, src = vs[0].read_text(errors="replace"), "backup"
    cur = Path(fp).read_text(errors="replace") if os.path.isfile(fp) else ""
    lines = difflib.unified_diff(base.splitlines(), cur.splitlines(), "/dev/null" if src == "new" else f"a{fp}",
                                 f"b{fp}", lineterm="", n=3)
    return {"diff": "\n".join(lines), "src": src, "deleted": not os.path.isfile(fp)}


@by_mtime
def changes_of(sid, path):
    changes, _ = scan(path, "main")
    for aid, desc, p in subagents(sid):
        changes += scan(p, desc or aid)[0]
    return sorted(changes, key=lambda e: e["ts"])


def feed():
    """세션별 작업 게시글: 개요 + 변경 수 + 저장해 둔 AI 요약. 새 요약은 만들지 않는다 (토큰 절약)."""
    posts = []
    for s in agents():
        sid = s["sessionId"]
        path = transcript(sid)
        if not path or (s.get("status") or s.get("state")) in DEAD:  # 끝난 세션은 게시글에서도 뺀다
            continue
        ov, ch = overview(path), changes_of(sid, path)
        tasks, tmt = saved_tasks(sid)
        ps = ov["prompts"]
        posts.append({"sid": sid, "name": s.get("name") or s.get("id"), "cwd": s["cwd"], "kind": s["kind"],
                      "status": s.get("status") or s.get("state", ""), "title": ov["title"],
                      "first": ov["first"], "last": ov["last"], "nprompts": len(ps),
                      "goal": ps[0]["text"] if ps else "", "recent": ps[-1]["text"] if len(ps) > 1 else "",
                      "files": len({e["file"] for e in ch}), "edits": len(ch),
                      "tasks": tasks, "stale": tmt is not None and tmt != path.stat().st_mtime})
    return sorted(posts, key=lambda p: p["last"], reverse=True)


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
    for st, t in items:
        add_task(sid, t, "haiku", st)
    return {"tasks": saved_tasks(sid)[0], "cached": False}


def add_task(sid, text, source, status="todo"):
    """작업 한 행을 맨 뒤(sort 최댓값 + 1)에 넣고 이력에 'start' 를 남긴다. 새 id 를 돌려준다."""
    t = now_iso()
    c = db()
    c.execute("INSERT INTO sessions (sid) VALUES (?) ON CONFLICT(sid) DO NOTHING", (sid,))
    sort = (c.execute("SELECT max(sort) FROM session_tasks WHERE sid = ?", (sid,)).fetchone()[0] or 0) + 1
    tid = c.execute("INSERT INTO session_tasks (sid, sort, status, text, source, created_at, updated_at)"
                    " VALUES (?,?,?,?,?,?,?)", (sid, sort, status, text, source, t, t)).lastrowid
    c.execute("INSERT INTO task_events (task_id, ts, status, note) VALUES (?,?,?,?)", (tid, t, "start", source))
    c.commit()
    c.close()
    return tid


def set_task(tid, by, status=None, note=None, sort=None, delete=False, sid=None):
    """작업 한 행의 분류·순서를 바꾸거나 지운다. sid 를 주면 그 세션의 작업만 건드린다 (MCP 용).
    사람이 haiku 행을 고치면 source 를 human 으로 바꿔 다음 haiku 정리 때 지워지지 않게 한다."""
    if status is not None and status not in TASK_STATUS.values():
        return False
    c = db()
    where, key = "id = ?" + (" AND sid = ?" if sid else ""), (tid, *([sid] if sid else []))
    if delete:
        n = c.execute(f"DELETE FROM session_tasks WHERE {where}", key).rowcount
    else:
        n = c.execute(f"UPDATE session_tasks SET status = coalesce(?, status), sort = coalesce(?, sort), updated_at = ?,"
                      f" source = CASE WHEN ? = 'human' AND source = 'haiku' THEN 'human' ELSE source END WHERE {where}",
                      (status, sort, now_iso(), by, *key)).rowcount
    if n:
        c.execute("INSERT INTO task_events (task_id, ts, status, note) VALUES (?,?,?,?)",
                  (tid, now_iso(), "deleted" if delete else status or "moved", note or by))
    c.commit()
    c.close()
    return n == 1


TASKS_SQL = "SELECT id, sort, status, text, source FROM session_tasks WHERE sid = ? ORDER BY sort, id"


def saved_tasks(sid):
    """DB 에 저장된 작업 목록과 그때의 대화 기록 수정 시각. 아직 없으면 ([], None)."""
    c = db()
    c.row_factory = sqlite3.Row
    row = c.execute("SELECT tasks_mtime FROM sessions WHERE sid = ?", (sid,)).fetchone()
    tasks = [dict(r) for r in c.execute(TASKS_SQL, (sid,))]
    c.close()
    return tasks, row["tasks_mtime"] if row else None


TASK_STATUS = {"완료": "done", "중단": "stopped", "남은일": "todo", "반려": "rejected"}


def work_items(sid):
    """기록할 가치가 있는 작업만 [(분류, 작업)] — 항목당 최대 2줄. 히스토리에 모든 걸 남기지 않는다."""
    path = transcript(sid)
    text = ask_haiku("다음은 Claude Code 세션 기록이다. 나중에 다시 찾아볼 가치가 있는 작업만 골라 한국어로 적어라.\n"
                     "형식: 한 줄에 '분류|작업' 하나. 분류는 완료·중단·남은일·반려 중 하나다.\n"
                     "  완료 = 끝까지 마친 작업, 중단 = 시작했지만 끝내지 못하고 멈춘 작업, 남은일 = 하기로 했지만 시작하지 않은 작업,\n"
                     "  반려 = 제안됐지만 사용자가 하지 않기로 한 작업\n"
                     "작업은 120자 이내 1~2문장, 동사로 끝낸다. 번호·기호·제목은 붙이지 않는다.\n"
                     "질문·확인·잡담·되돌린 시도는 뺀다. 기록할 작업이 없으면 아무것도 출력하지 않는다.",
                     digest(sid, path)) if path else ""
    out = []
    for line in text.splitlines():
        kind, _, task = line.partition("|")
        if not task:  # 형식을 어긴 줄은 버린다
            continue
        task = re.sub(r"^\s*(\d+[.)]|[-*•])\s*", "", task).strip()[:160]
        if task:
            out.append((TASK_STATUS.get(re.sub(r"[^가-힣]", "", kind), "done"), task))
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
    files = sorted({e["file"] for e in session(sid)["changes"]})
    # ponytail: 앞 1건 + 뒤쪽 위주로 4만 자 자르기, 긴 세션은 구간별 요약이 필요해지면 그때
    body = "\n".join(parts)
    if len(body) > 40_000:
        body = parts[0] + "\n...(중략)...\n" + body[-38_000:]
    return body + "\n\n[변경 파일]\n" + "\n".join(files)


_usage = {"at": 0, "data": {}}


def usage():
    """/usage 의 한도(Current session = 5시간, Current week = 1주일). 5분 동안 재사용 (호출마다 claude 를 띄운다)."""
    if time.time() - _usage["at"] >= 300:
        # 내장 명령이라 모델을 부르지 않는다 (~4초)
        text = claude("-p", "/usage", *QUIET, cwd=Path.home())
        _usage.update(at=time.time(), data={"limits": [
            {"label": m[1], "pct": int(m[2]), "resets": m[3]}
            for m in re.finditer(r"^(Current [^:]+): (\d+)% used · resets (.+)$", text, re.M)]})
    return _usage["data"]


# 지표 저장소. 대화 기록은 cleanupPeriodDays(기본 30일) 뒤 지워지지만 이 표는 남는다.
# ponytail: SQLite 고정, 공유 서버(Postgres 등)가 필요해지면 db()/record() 두 곳만 바꾸면 된다
DB = Path(CFG["HUDSON_FLEET_DB"]).expanduser()
STATE = {"busy": "work", "running": "work", "blocked": "wait", "waiting": "wait", "needs_input": "wait"}


def db():
    DB.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB)
    c.execute("CREATE TABLE IF NOT EXISTS samples (ts INTEGER PRIMARY KEY, work INT, wait INT, idle INT,"
              " agents INT, pct5h INT, pct1w INT)")
    c.execute("CREATE TABLE IF NOT EXISTS daily (day TEXT PRIMARY KEY, tokens INT)")
    # 세션 1 : 작업 N · 파일 N. 살아 있는 세션도 1분마다 상태를 남기고, 끝나면 status=closed 로 바뀐다
    c.execute("CREATE TABLE IF NOT EXISTS sessions (sid TEXT PRIMARY KEY, name TEXT, title TEXT, cwd TEXT, kind TEXT,"
              " app TEXT, status TEXT, status_since TEXT, started_at TEXT, last_seen TEXT, ended_at TEXT,"
              " end_reason TEXT, tokens INT, tasks_mtime REAL)")  # status: work · wait · idle · closed
    # status: todo 남은 일 · done 완료 · stopped 중단 · rejected 반려 / source: agent(MCP) · haiku · human
    c.execute("CREATE TABLE IF NOT EXISTS session_tasks (id INTEGER PRIMARY KEY, sid TEXT REFERENCES sessions(sid),"
              " sort REAL, status TEXT, text TEXT, source TEXT, created_at TEXT, updated_at TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS task_events (id INTEGER PRIMARY KEY, task_id INT, ts TEXT, status TEXT,"
              " note TEXT)")  # 시작·완료·중단·반려·순서 변경 이력 (추가만)
    c.execute("CREATE TABLE IF NOT EXISTS session_files (sid TEXT REFERENCES sessions(sid), path TEXT,"
              " status TEXT, edits INT, first_at TEXT, last_at TEXT, added INT, removed INT, PRIMARY KEY (sid, path))")
    return c


def token_rows(paths):
    """대화 기록들 → (timestamp, 토큰) 응답당 한 번. 입력+캐시 생성+출력, 캐시 읽기는 뺀다."""
    seen = set()
    for p in paths:
        for line in p.open(encoding="utf-8", errors="replace"):
            if '"usage"' not in line:  # 대부분의 줄은 json 해석 없이 건너뛴다
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            m = rec.get("message") or {}
            u, mid = m.get("usage"), m.get("id")
            if rec.get("type") != "assistant" or not u or not rec.get("timestamp") or mid in seen:
                continue
            seen.add(mid)  # 응답 하나가 내용 블록마다 기록돼 같은 usage 가 반복된다
            yield rec["timestamp"], u.get("input_tokens", 0) + u.get("cache_creation_input_tokens", 0) \
                + u.get("output_tokens", 0)


_u5 = {"at": 0, "data": {}}


def usage5h_all():
    """세션별(서브에이전트 포함) 5시간 한도 몫 (%) = /usage 의 % × 같은 창에서 그 세션 토큰 비율. 1분 동안 재사용.
    창은 /usage 의 리셋 시각 − 5시간. 읽지 못하면 지금부터 5시간 전."""
    if time.time() - _u5["at"] < 60:
        return _u5["data"]
    lim = next((x for x in usage()["limits"] if x["label"] == "Current session"), None)
    m = lim and re.match(r"(\w+ \d+) at (\d+)(?::(\d+))?(am|pm)", lim["resets"])
    since = time.time() - 5 * 3600
    if m:
        hh = int(m[2]) % 12 + (12 if m[4] == "pm" else 0)
        reset = datetime.strptime(f"{m[1]} {datetime.now().year} {hh}:{m[3] or 0}", "%b %d %Y %H:%M")
        since = reset.timestamp() - 5 * 3600
    cut = datetime.fromtimestamp(since, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")  # 기록의 timestamp 와 문자열 비교
    by = {}
    for p in PROJECTS.glob("*/*.jsonl"):
        if p.stat().st_mtime >= since:
            by[p.stem] = by.get(p.stem, 0) + sum(t for ts, t in token_rows([p]) if ts >= cut)
    for p in PROJECTS.glob("*/*/subagents/agent-*.jsonl"):
        if p.stat().st_mtime >= since:
            sid = p.parent.parent.name
            by[sid] = by.get(sid, 0) + sum(t for ts, t in token_rows([p]) if ts >= cut)
    total = sum(by.values())
    _u5.update(at=time.time(), data={sid: {"tokens": n, "pct": round(lim["pct"] * n / total, 1) if lim and total else None}
                                     for sid, n in by.items()})
    return _u5["data"]


def daily_tokens():
    """대화 기록 전체 → 날짜(로컬)별 토큰 합계 (283MB 기준 ~1초)."""
    days = {}
    for ts, n in token_rows([*PROJECTS.glob("*/*.jsonl"), *PROJECTS.glob("*/*/subagents/agent-*.jsonl")]):
        d = datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone().strftime("%Y-%m-%d")
        days[d] = days.get(d, 0) + n
    return days


def archive(n, status):
    """끝난 세션을 sessions 에 status=closed 로 마감하고 session_files(N) 를 남긴다.
    기록할 작업(session_tasks)은 summarize 로 채운다 — 저장본이 최신이면 haiku 를 다시 부르지 않는다."""
    sid = n["sessionId"]
    path = transcript(sid)
    if not path:
        return
    if n["kind"] == "background":
        reason = status
    else:
        try:
            os.kill(n["pid"], 0)
            reason = "switched"  # 프로세스는 살아 있고 세션만 바뀜 (/clear·/resume)
        except OSError:
            reason = "exited"  # 직접 종료·창 닫기·크래시 — 여기서는 구분 못 한다
    se, ov = session(sid), overview(path)
    files = {}
    for e in se["changes"]:
        files.setdefault(e["file"], []).append(e)
    rows = []
    for f, evs in files.items():
        d = (net_diff(sid, f, se["changes"], se["status"][f] == "A").get("diff") or "").splitlines()[2:]
        rows.append((sid, f, se["status"][f], len(evs), evs[0]["ts"], evs[-1]["ts"],
                     sum(x.startswith("+") for x in d), sum(x.startswith("-") for x in d)))
    tokens = sum(t for _, t in token_rows([path, *(p for *_, p in subagents(sid))]))
    if CFG["HUDSON_FLEET_AUTO_SUMMARY"] != "0":
        summarize(sid)
    c = db()
    # summarize 가 sid 만 있는 행을 먼저 만들 수 있다 — 비어 있는 칸만 채운다
    c.execute("INSERT INTO sessions (sid, name, cwd, kind, app, started_at) VALUES (?,?,?,?,?,?)"
              " ON CONFLICT(sid) DO UPDATE SET name=coalesce(sessions.name, excluded.name),"
              " cwd=coalesce(sessions.cwd, excluded.cwd), kind=coalesce(sessions.kind, excluded.kind),"
              " app=coalesce(sessions.app, excluded.app), started_at=coalesce(sessions.started_at, excluded.started_at)",
              (sid, n.get("label"), n["cwd"], n["kind"], n.get("app"), ov["first"]))
    c.execute("UPDATE sessions SET title=?, status='closed', status_since=?, ended_at=?, end_reason=?, tokens=?"
              " WHERE sid=?", (ov["title"], now_iso(), ov["last"], reason, tokens, sid))
    c.execute("DELETE FROM session_files WHERE sid = ?", (sid,))
    c.executemany("INSERT INTO session_files VALUES (?,?,?,?,?,?,?,?)", rows)
    c.commit()
    c.close()


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def track(alive):
    """살아 있는 세션의 상태를 sessions 에 남긴다. 상태가 바뀐 때만 status_since 를 새로 적는다."""
    t = now_iso()
    c = db()
    for sid, n in alive.items():
        started = datetime.fromtimestamp(n["startedAt"] / 1000, timezone.utc).isoformat(timespec="seconds") \
            if n.get("startedAt") else None
        c.execute("INSERT INTO sessions (sid, name, cwd, kind, app, status, status_since, started_at, last_seen)"
                  " VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(sid) DO UPDATE SET name=excluded.name, app=excluded.app,"
                  " last_seen=excluded.last_seen, ended_at=NULL, end_reason=NULL,"  # --resume 로 다시 살아난 세션
                  " status_since=CASE WHEN sessions.status IS excluded.status"
                  " THEN sessions.status_since ELSE excluded.status_since END, status=excluded.status",
                  (sid, n.get("label"), n["cwd"], n["kind"], n.get("app"), STATE.get(n["status"], "idle"), t, started, t))
    c.commit()
    c.close()


def reopen(sid, fork):
    """끝난 세션을 그 작업 폴더에서 claude --resume 으로 다시 연다. fork 면 --fork-session (기록은 그대로 두고 새 ID).
    DB 에 closed 로 남은 세션만 연다 — 아무 ID 나 받아 명령을 만들지 않게."""
    c = db()
    row = c.execute("SELECT cwd FROM sessions WHERE sid = ? AND status = 'closed'", (sid,)).fetchone()
    c.close()
    if not re.fullmatch(r"[0-9a-f-]{36}", sid) or not row or not os.path.isdir(row[0] or ""):
        return {"error": "끝난 세션이 아니거나 작업 폴더가 없습니다"}, 404
    cmd = ["claude", "--resume", sid, *(["--fork-session"] if fork else [])]
    app = CFG["HUDSON_FLEET_TERMINAL"]
    if app == "Terminal":  # Terminal.app 은 명령을 AppleScript 문자열로만 받는다
        line = f"cd {shlex.quote(row[0])} && {' '.join(cmd)}"
        subprocess.Popen(["osascript", "-e", f'tell application "Terminal" to do script "{line.replace(chr(92), chr(92) * 2).replace(chr(34), chr(92) + chr(34))}"',
                          "-e", 'tell application "Terminal" to activate'])
    else:
        subprocess.Popen(["open", "-na", app, "--args", f"--working-directory={row[0]}", "-e", *cmd])
    return {"text": f"{app} 새 창에서 {'복사해' if fork else '이어서'} 엽니다"}, 200


def archive_safe(n, status):
    try:
        archive(n, status)
    except Exception as e:  # 한 세션 정리에 실패해도 기록 스레드는 계속 돈다
        print("종료 세션 저장 실패:", n.get("sessionId"), e)


def prune():
    days = int(CFG["HUDSON_FLEET_RETENTION_DAYS"])
    if days > 0:
        c = db()
        c.execute("DELETE FROM samples WHERE ts < ?", (int(time.time()) - days * 86400,))
        c.commit()
        c.close()


def save_daily():
    # 기록 파일이 정리돼 합계가 줄어도 저장해 둔 큰 값을 지킨다 (잔디가 지워지지 않게)
    c = db()
    c.executemany("INSERT INTO daily VALUES (?,?) ON CONFLICT(day) DO UPDATE SET tokens=max(tokens, excluded.tokens)",
                  daily_tokens().items())
    c.commit()
    c.close()


def record():
    """1분마다 지표 한 줄: 상태별 살아 있는 세션 수, 실행 중 서브에이전트 수, 5시간·1주일 사용률.
    10분마다 날짜별 토큰 합계(잔디)도 갱신한다. 세션 상태는 sessions 에 남기고, 사라진 세션은 closed 로 마감한다."""
    prev = {}
    for i in itertools.count():
        try:
            if i % 10 == 0:
                save_daily()
            if i % 1440 == 0:  # 하루에 한 번
                prune()
            nodes = graph()["nodes"]
            alive = {n["sessionId"]: n for n in nodes if n["type"] == "session" and n["status"] not in DEAD}
            now = {n["sessionId"]: n["status"] for n in nodes if n["type"] == "session"}
            for sid, n in prev.items():
                if sid not in alive:  # 요약에 수십 초 걸릴 수 있어 따로 돌린다
                    threading.Thread(target=archive_safe, args=(n, now.get(sid, "gone")), daemon=True).start()
            prev = alive
            track(alive)
            live = {sid: STATE.get(n["status"], "idle") for sid, n in alive.items()}
            agents = sum(n["type"] == "agent" and n["status"] == "running" and n["sid"] in live for n in nodes)
            pct = {x["label"]: x["pct"] for x in usage()["limits"]}
            c = db()
            c.execute("INSERT OR REPLACE INTO samples VALUES (?,?,?,?,?,?,?)",
                      (int(time.time()), *(list(live.values()).count(g) for g in ("work", "wait", "idle")), agents,
                       pct.get("Current session"), pct.get("Current week (all models)")))
            c.commit()
            c.close()
        except Exception as e:  # 한 번 실패해도 다음 분에 다시 시도한다
            print("지표 기록 실패:", e)
        time.sleep(60)


def metrics(hours):
    c = db()
    cols = ("ts", "work", "wait", "idle", "agents", "pct5h", "pct1w")
    rows = c.execute(f"SELECT {','.join(cols)} FROM samples WHERE ts >= ? ORDER BY ts",
                     (int(time.time() - hours * 3600),)).fetchall()
    c.close()
    return [dict(zip(cols, r)) for r in rows]


_mcp = {"at": 0, "data": []}


def mcp_servers(refresh=False):
    """claude mcp list(연결 검사 포함, ~9초) → [{name, group, target, ok, state}]. 1분 동안 재사용."""
    if refresh or time.time() - _mcp["at"] > 60:
        out = []
        for line in re.sub(r"\x1b\][^\x07\x1b]*(\x07|\x1b\\)|\x1b\[[0-9;]*m", "", claude("mcp", "list", cwd=Path.home())).splitlines():
            if m := re.match(r"^(.+?): (.+) - ([✔✘!⏸]) (.+)$", line):
                name, target, mark, state = m.groups()
                group = "claude.ai 커넥터" if name.startswith("claude.ai ") else "플러그인" if name.startswith("plugin:") else "직접 설정"
                out.append({"name": name.removeprefix("claude.ai ").split(":")[-1], "group": group, "target": target,
                            "ok": {"✔": "ok", "✘": "fail", "!": "auth", "⏸": "pending"}[mark], "state": state})
        _mcp.update(at=time.time(), data=out)
    return _mcp["data"]


def agents():
    """claude agents 목록에서 1회성 `claude -p` 실행(entrypoint=sdk-cli)을 뺀다.
    대시보드 자신의 /usage·AI 요약 호출도 여기에 해당 — 몇 초 떴다 사라지는 '유령 세션'이 된다."""
    def headless(s):
        if "pid" not in s:  # 백그라운드 작업은 pid 가 없다
            return False
        try:
            return json.loads((SESSIONS / f"{s['pid']}.json").read_text()).get("entrypoint") == "sdk-cli"
        except OSError:  # 목록에는 남았는데 파일은 지워짐 = 막 끝난 프로세스
            return True
        except ValueError:
            return False
    return [s for s in agent_list() if not headless(s)]


_ag = {"at": 0, "data": []}


def agent_list():
    """claude agents --json --all. 부를 때마다 node 를 띄워 ~0.2초 걸리므로 5초 동안 재사용한다."""
    if time.time() - _ag["at"] >= 5:
        _ag.update(at=time.time(), data=json.loads(claude("agents", "--json", "--all") or "[]"))
    return _ag["data"]


def find_session(sid):
    """현재 claude agents 목록에 있는 세션만 조작 대상으로 인정한다 (임의 pid 종료 차단)."""
    return next((s for s in agent_list()
                 if s["sessionId"] == sid), None)


def proc_chain(pid):
    """세션 프로세스부터 부모를 거슬러 올라간 목록 [{pid, name, path}] — 어떤 앱 안에서 도는지."""
    out = []
    while pid > 1:
        r = subprocess.run(["ps", "-o", "ppid=,comm=", "-p", str(pid)], capture_output=True, text=True).stdout.strip()
        if not r:
            break
        ppid, comm = r.split(None, 1)
        name = Path(comm.split(".app/")[0]).stem if ".app/" in comm else Path(comm.lstrip("-")).name
        out.append({"pid": pid, "name": name, "path": comm})
        pid = int(ppid)
    return out


def host_app(pid):
    """세션을 띄운 터미널 앱(.app 번들)."""
    return next((p["path"].split(".app/")[0] + ".app" for p in proc_chain(pid) if ".app/" in p["path"]), None)


def graph():
    """프로젝트 → 세션 → 서브에이전트 DAG. 파일 변경은 그래프가 아니라 탐색기 패널(/api/session)로 본다."""
    nodes, edges = {}, set()
    for s in agents():
        sid, cwd = s["sessionId"], s["cwd"]
        if s.get("pid") and (app := host_app(s["pid"])):
            s["app"] = Path(app).stem
        nodes["p:" + cwd] = {"type": "project", "label": os.path.basename(cwd) or cwd}
        nodes["s:" + sid] = {"type": "session", "label": s.get("name") or s.get("id"),
                             "status": s.get("status") or s.get("state", ""), **s}
        edges.add(("p:" + cwd, "s:" + sid))
        for aid, desc, p in subagents(sid):
            meta = p.with_suffix(".meta.json")  # 서브에이전트가 끝나면 finished: true 가 기록된다
            done = meta.exists() and json.loads(meta.read_text()).get("finished")
            nodes["a:" + aid] = {"type": "agent", "label": desc or aid, "sid": sid,
                                 "status": "done" if done else "running"}
            edges.add(("s:" + sid, "a:" + aid))
    # 세션의 "id"(백그라운드 짧은 id)가 노드 id 를 덮지 않도록 bgId 로 옮긴다
    return {"home": str(Path.home()), "nodes": [{**v, "bgId": v.get("id"), "id": k} for k, v in nodes.items()],
            "edges": [{"source": a, "target": b} for a, b in edges]}


class H(BaseHTTPRequestHandler):
    def send(self, body, ctype="application/json", code=200):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        if u.path == "/":
            return self.send((Path(__file__).parent / "index.html").read_bytes(), "text/html")
        if u.path == "/api/graph":
            return self.send(graph())
        if u.path == "/api/config":
            return self.send([{"name": k, "value": CFG[k], "default": d, "desc": desc, "set": k in os.environ}
                              for k, d, desc in CONFIG])
        if u.path == "/api/sessions":  # ?status=closed|work|wait|idle (없으면 전체) &limit=
            c = db()
            c.row_factory = sqlite3.Row
            st = q.get("status")
            out = [dict(r) for r in c.execute(
                "SELECT * FROM sessions WHERE status IS NOT NULL" + (" AND status = ?" if st else "")
                + " ORDER BY coalesce(ended_at, last_seen) DESC LIMIT ?", (*([st] if st else []), int(q.get("limit", 50))))]
            for s in out:
                s["tasks"] = [dict(r) for r in c.execute(
                    TASKS_SQL, (s["sid"],))]
                s["files"] = [dict(r) for r in c.execute("SELECT * FROM session_files WHERE sid = ?", (s["sid"],))]
            c.close()
            return self.send(out)
        if u.path == "/api/todo":  # 남은 일 — 끝난 세션 것도 포함
            c = db()
            c.row_factory = sqlite3.Row
            out = [dict(r) for r in c.execute(
                "SELECT t.id, t.sid, t.status, t.text, t.source, s.title, s.name, s.cwd, s.status AS sst"
                " FROM session_tasks t JOIN sessions s USING (sid) WHERE t.status = 'todo'"
                " ORDER BY coalesce(s.ended_at, s.last_seen) DESC, t.sort, t.id")]
            c.close()
            return self.send(out)
        if u.path == "/api/daily":
            c = db()
            rows = c.execute("SELECT day, tokens FROM daily WHERE day >= date('now', '-371 days')").fetchall()
            c.close()
            return self.send(dict(rows))
        if u.path == "/api/metrics":
            return self.send(metrics(float(q.get("hours", 24))))
        if u.path == "/api/usage":
            return self.send(usage())
        if u.path == "/api/mcp":
            return self.send(mcp_servers(q.get("refresh") == "1"))
        if u.path == "/api/usage5h":
            return self.send(usage5h_all())
        if u.path == "/api/feed":
            return self.send(feed())
        if u.path == "/api/session":
            return self.send({**session(q.get("sid", "")), "tasks": saved_tasks(q.get("sid", ""))[0]})
        if u.path == "/api/netdiff":
            sid, p = q.get("sid", ""), q.get("path", "")
            se = session(sid)
            if p not in se["status"]:  # 세션이 편집한 파일만 (임의 파일 읽기 차단)
                return self.send({"error": "not allowed"}, code=404)
            return self.send(net_diff(sid, p, se["changes"], se["status"][p] == "A"))
        if u.path == "/api/file":
            # 세션(서브에이전트 포함)이 실제로 편집한 파일만 열람 허용 (임의 파일 읽기 차단)
            p = q.get("path", "")
            if p not in {e["file"] for e in session(q.get("sid", ""))["changes"]} or not os.path.isfile(p):
                return self.send({"error": "not allowed or missing"}, code=404)
            return self.send(Path(p).read_bytes()[:500_000], "text/plain")
        if u.path == "/api/logs":
            return self.send({"text": claude("logs", q.get("id", ""))})
        self.send({"error": "not found"}, code=404)

    def do_POST(self):
        # 다른 웹사이트가 localhost 로 실행 요청을 보내는 것(CSRF) 차단
        if self.headers.get("Origin") != ORIGIN:
            return self.send({"error": "bad origin"}, code=403)
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or "{}")
        if self.path == "/api/run":
            cwd = os.path.expanduser(body.get("cwd", ""))
            if not os.path.isdir(cwd) or not body.get("prompt"):
                return self.send({"error": "cwd/prompt 확인"}, code=400)
            return self.send({"text": claude("--bg", body["prompt"], cwd=cwd)})
        if self.path == "/api/reopen":  # {sid, fork?} — 끝난 세션을 새 터미널 창에서 claude --resume 으로 연다
            out, code = reopen(body.get("sid", ""), bool(body.get("fork")))
            return self.send(out, code=code)
        if self.path == "/api/task":  # {id, status?, sort?, delete?} — 사람이 웹에서 고친다
            ok = set_task(body.get("id"), "human", body.get("status"), sort=body.get("sort"), delete=bool(body.get("delete")))
            return self.send({"ok": ok} if ok else {"error": "작업 또는 분류 확인"})
        if self.path == "/api/summary":  # 토큰을 쓰므로 GET 이 아닌 POST (출처 검사 대상)
            return self.send(summarize(body.get("sid", "")))
        if self.path != "/api/stop":
            return self.send({"error": "not found"}, code=404)
        s = find_session(body.get("sid", ""))
        if not s:
            return self.send({"error": "실행 중인 세션이 아님"}, code=404)
        if s["kind"] == "background":
            return self.send({"text": claude("stop", s["id"])})
        os.kill(s["pid"], signal.SIGTERM)
        return self.send({"text": f"{s.get('name')} 종료 신호 보냄"})


if __name__ == "__main__":
    print(f"→ {ORIGIN} · 지표 DB: {DB}")
    threading.Thread(target=record, daemon=True).start()
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
