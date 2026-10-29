"""예약 작업: Claude 예약 작업(루틴 — 데스크톱 앱·클라우드)과, 살아 있는 세션이 걸어 둔 예약(/loop·CronCreate)."""
import json
import re
import shutil
import subprocess
import threading
import time
from datetime import datetime

from .agents import agents
from .config import DEAD, PROJECTS, QUIET, now_iso
from .db import DB, db
from .transcripts import by_mtime, transcript


# 루틴은 claude.ai 서버에만 있다 (이 PC 의 데스크톱 앱 파일은 비어 있다). 로그인 토큰을 읽지 않고,
# Claude Code 의 RemoteTrigger 도구를 haiku 로 한 번 불러 받는다 — 한 번에 ~9초, ~0.5센트
WORK = DB.parent / "routines"  # 이 호출의 작업 폴더. 결과가 크면 Claude 가 이 폴더의 기록 폴더에 파일로 남기므로 끝나면 지운다
ASK = "RemoteTrigger 도구를 action=list 로 한 번만 호출해. 결과를 요약하지 말고 '끝' 이라고만 답해."
_busy = threading.Lock()


def fetch():
    """루틴 목록을 claude.ai 에서 받는다. 못 받으면 RuntimeError."""
    WORK.mkdir(exist_ok=True)
    r = subprocess.run(["claude", "-p", "--model", "haiku", *QUIET, "--allowedTools", "RemoteTrigger ToolSearch",
                        "--output-format", "stream-json", "--verbose", ASK],
                       cwd=WORK, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=120)
    shutil.rmtree(PROJECTS / re.sub(r"[^A-Za-z0-9]", "-", str(WORK)), ignore_errors=True)
    for line in r.stdout.splitlines():
        try:
            res = json.loads(line).get("tool_use_result")
        except ValueError:
            continue
        if isinstance(res, dict) and "json" in res:  # RemoteTrigger 의 원래 응답 {status, json}
            if res.get("status") != 200:
                raise RuntimeError(f"예약 작업 목록을 받지 못했습니다 (HTTP {res.get('status')})")
            # ponytail: 첫 쪽만 (has_more 무시), 루틴이 한 쪽을 넘으면 cursor 로 이어 받는다
            return [trim(x) for x in json.loads(res["json"])["data"]]
    raise RuntimeError("예약 작업 목록을 받지 못했습니다: " + (r.stderr or r.stdout).strip()[-200:])


def trim(x):
    """루틴 한 건(지시문 전문·실행 설정이 들어 있어 수백 KB) → 화면에 보일 칸만."""
    ds, last = x.get("derived_state") or {}, x.get("last_run") or {}
    tz, cron = re.fullmatch(r"(?:CRON_TZ=(\S+)\s+)?(.*)", x.get("cron_expression") or "").groups()
    why = last.get("failure_reason", "").removeprefix("ROUTINE_RUN_FAILURE_REASON_")
    return {"id": x.get("id"), "name": x.get("name") or "", "enabled": bool(x.get("enabled")), "cron": cron, "tz": tz,
            "next": x.get("next_run_at"), "last": last.get("fired_at"),
            "result": last.get("status", "").removeprefix("ROUTINE_RUN_STATUS_"), "why": "" if why == "UNSPECIFIED" else why,
            "device": (x.get("bound_device") or {}).get("display_name") or "클라우드", "folders": ds.get("folders") or [],
            "model": ds.get("model") or "", "mode": ds.get("permission_mode") or "", "prompt": ds.get("prompt") or "",
            "stopped": x.get("suspension_reason") or x.get("ended_reason") or ""}


def saved():
    c = db()
    row = c.execute("SELECT at, data FROM routines").fetchone()
    c.close()
    return {"at": row[0], "items": json.loads(row[1])} if row else {"at": None, "items": []}


def refresh():
    """루틴을 새로 받아 저장한다. 못 받으면 저장본에 error 를 붙여 돌려준다."""
    if not _busy.acquire(blocking=False):
        return {**saved(), "error": "이미 받는 중입니다"}
    try:
        items = fetch()
        c = db()
        c.execute("INSERT OR REPLACE INTO routines VALUES (1, ?, ?)", (now_iso(), json.dumps(items, ensure_ascii=False)))
        c.commit()
        c.close()
    except (RuntimeError, OSError, ValueError, KeyError, subprocess.TimeoutExpired) as e:
        return {**saved(), "error": str(e)}
    finally:
        _busy.release()
    return saved()


@by_mtime
def schedules_in(path):
    """대화 기록 하나에서 세션 안 예약을 찾는다 → ([CronCreate 예약], 마지막 ScheduleWakeup).
    결과는 기록 줄의 toolUseResult 에 있다: CronCreate {id, recurring, nextFireAt} · CronDelete {id} · CronList {jobs}."""
    pend, jobs, wake = {}, {}, None
    for line in path.open(encoding="utf-8", errors="replace"):
        if "Cron" not in line and "ScheduleWakeup" not in line and not any(k in line for k in pend):  # 대부분의 줄은 건너뛴다
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        for b in (rec.get("message") or {}).get("content") or []:
            if not isinstance(b, dict):
                continue
            if b.get("type") == "tool_use" and b.get("name") in ("CronCreate", "CronDelete", "CronList", "ScheduleWakeup"):
                pend[b["id"]] = (b["name"], b.get("input") or {}, rec.get("timestamp", ""))
            elif b.get("type") == "tool_result" and b.get("tool_use_id") in pend:
                name, inp, ts = pend.pop(b["tool_use_id"])
                res = rec.get("toolUseResult") if isinstance(rec.get("toolUseResult"), dict) else {}
                if name == "CronCreate" and res.get("id"):
                    jobs[res["id"]] = {"id": res["id"], "cron": inp.get("cron"), "prompt": inp.get("prompt") or "",
                                       "recurring": res.get("recurring", True), "at": ts, "next": res.get("nextFireAt")}
                elif name == "CronDelete":
                    jobs.pop(res.get("id") or inp.get("id"), None)
                elif name == "CronList" and "jobs" in res:  # 목록에 없는 예약은 실행·만료로 사라졌다
                    now = {j["id"]: j for j in res["jobs"]}
                    jobs = {k: {**v, "next": now[k].get("nextFireAt")} for k, v in jobs.items() if k in now}
                elif name == "ScheduleWakeup":
                    wake = None if inp.get("stop") else {**inp, "at": ts}
    return list(jobs.values()), wake


def epoch(ts):
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()


def session_schedules():
    """살아 있는 세션의 예약. 세션이 끝나면 예약도 사라진다 (Claude Code 는 디스크에 남기지 않는다)."""
    out, now = [], time.time()
    for s in agents():
        p = transcript(s["sessionId"])
        if (s.get("status") or s.get("state")) in DEAD or not p:
            continue
        jobs, wake = schedules_in(p)
        base = {"sid": s["sessionId"], "session": s.get("name") or s["sessionId"][:8]}
        for j in jobs:
            end = epoch(j["at"]) + 7 * 86400  # 반복 예약은 7일 뒤 저절로 지워진다
            if (j["recurring"] and end < now) or (not j["recurring"] and (j["next"] or 0) / 1000 < now):  # 한 번짜리는 실행되면 지워진다
                continue
            out.append({**base, **j, "kind": "cron", "expires": end * 1000 if j["recurring"] else None})
        if wake and epoch(wake["at"]) + wake.get("delaySeconds", 0) > now - 60:
            out.append({**base, "kind": "loop", "prompt": wake.get("prompt") or "", "reason": wake.get("reason") or "", "at": wake["at"],
                        "next": (epoch(wake["at"]) + wake.get("delaySeconds", 0)) * 1000})
    return out


if __name__ == "__main__":  # 확인: python3 -m fleet.routines (대화 기록 해석과 루틴 다듬기만, claude 는 부르지 않는다)
    import tempfile
    from pathlib import Path
    rows = [
        {"message": {"content": [{"type": "tool_use", "id": "u1", "name": "CronCreate", "input": {"cron": "7 3 1 1 *", "prompt": "a", "recurring": False}}]}, "timestamp": "2026-10-29T01:00:00Z"},
        {"message": {"content": [{"type": "tool_result", "tool_use_id": "u1", "content": "Scheduled one-shot task j1"}]}, "toolUseResult": {"id": "j1", "recurring": False, "nextFireAt": 4102444800000}},
        {"message": {"content": [{"type": "tool_use", "id": "u2", "name": "CronCreate", "input": {"cron": "*/5 * * * *", "prompt": "b"}}]}, "timestamp": "2026-10-29T01:01:00Z"},
        {"message": {"content": [{"type": "tool_result", "tool_use_id": "u2", "content": "ok"}]}, "toolUseResult": {"id": "j2", "recurring": True, "nextFireAt": 1}},
        {"message": {"content": [{"type": "tool_use", "id": "u3", "name": "CronDelete", "input": {"id": "j1"}}]}, "timestamp": "2026-10-29T01:02:00Z"},
        {"message": {"content": [{"type": "tool_result", "tool_use_id": "u3", "content": "Cancelled job j1."}]}, "toolUseResult": {"id": "j1"}},
        {"message": {"content": [{"type": "tool_use", "id": "u4", "name": "ScheduleWakeup", "input": {"delaySeconds": 1200, "prompt": "/loop x"}}]}, "timestamp": "2026-10-29T01:03:00Z"},
        {"message": {"content": [{"type": "tool_result", "tool_use_id": "u4", "content": "ok"}]}},
    ]
    f = Path(tempfile.mkdtemp()) / "t.jsonl"
    f.write_text("\n".join(json.dumps(r) for r in rows))
    jobs, wake = schedules_in(f)
    assert [j["id"] for j in jobs] == ["j2"] and jobs[0]["cron"] == "*/5 * * * *" and wake["delaySeconds"] == 1200
    t = trim({"id": "trig_1", "name": "n", "enabled": True, "cron_expression": "CRON_TZ=Asia/Seoul 30 9 * * *",
              "last_run": {"status": "ROUTINE_RUN_STATUS_SUCCEEDED", "failure_reason": "ROUTINE_RUN_FAILURE_REASON_UNSPECIFIED"},
              "bound_device": {"display_name": "Claude Desktop (macOS)"}, "derived_state": {"prompt": "p", "folders": ["/x"]}})
    assert (t["cron"], t["tz"], t["result"], t["why"], t["device"]) == ("30 9 * * *", "Asia/Seoul", "SUCCEEDED", "", "Claude Desktop (macOS)")
    assert trim({"name": "m"})["cron"] == "" and trim({"name": "m"})["device"] == "클라우드"
    print("ok")
