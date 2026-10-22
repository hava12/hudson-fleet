"""세션이 바꾼 파일: A/M/D 판정과 처음 → 지금 diff."""
import difflib
import json
import os
from datetime import datetime
from pathlib import Path

from .agents import find_session, proc_chain
from .transcripts import changes_of, overview, transcript


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
