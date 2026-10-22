"""구독 사용량(/usage)과 토큰 집계."""
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from .config import PROJECTS, QUIET, claude
from .transcripts import token_rows


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
