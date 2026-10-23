"""1분 주기 기록 스레드: 지표·세션 상태·끝난 세션 마감."""
import itertools
import os
import threading
import time
from datetime import datetime, timezone

from .agents import graph
from .card import publish
from .config import CFG, DEAD, now_iso
from .db import db
from .tasks import summarize
from .transcripts import overview, subagents, token_rows, transcript
from .usage import daily_tokens, usage


STATE = {"busy": "work", "running": "work", "blocked": "wait", "waiting": "wait", "needs_input": "wait"}


def archive(n, status):
    """끝난 세션을 sessions 에 status=closed 로 마감한다.
    기록할 작업(session_tasks)은 summarize 로 채운다 — 저장본이 최신이면 haiku 를 다시 부르지 않는다."""
    sid = n["sessionId"]
    path = transcript(sid)
    if not path:
        return
    if n["kind"] == "background":
        reason = status
    elif not n.get("pid"):  # 리더가 바뀌는 사이에 끝나 DB 에서 찾은 세션 — 끝난 방식을 모른다
        reason = "gone"
    else:
        try:
            os.kill(n["pid"], 0)
            reason = "switched"  # 프로세스는 살아 있고 세션만 바뀜 (/clear·/resume)
        except OSError:
            reason = "exited"  # 직접 종료·창 닫기·크래시 — 여기서는 구분 못 한다
    ov = overview(path)
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
    c.commit()
    c.close()


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


def unclosed():
    """DB 에 아직 살아 있다고 남은 세션 — 리더가 바뀌면 메모리의 prev 가 없어지므로 여기서 이어받는다."""
    c = db()
    rows = c.execute("SELECT sid, name, cwd, kind, app FROM sessions WHERE status IN ('work', 'wait', 'idle')").fetchall()
    c.close()
    return {sid: {"sessionId": sid, "label": name, "cwd": cwd, "kind": kind, "app": app} for sid, name, cwd, kind, app in rows}


def record():
    """1분마다 지표 한 줄: 상태별 살아 있는 세션 수, 실행 중 서브에이전트 수, 5시간·1주일 사용률.
    10분마다 날짜별 토큰 합계(잔디), 30분마다 프로필 카드도 갱신한다. 세션 상태는 sessions 에 남기고, 사라진 세션은 closed 로 마감한다."""
    prev = unclosed()  # 앞 리더(끝난 세션의 MCP 서버)가 마감하지 못한 세션도 마감한다
    for i in itertools.count():
        try:
            if i % 10 == 0:
                save_daily()
            if i % 30 == 0:  # 30분마다 프로필 카드
                publish()
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
