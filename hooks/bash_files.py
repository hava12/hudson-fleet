"""Pre/PostToolUse(Bash) 훅: Bash 가 바꾼 파일을 DB 에 남긴다. 대화 기록에는 Bash 가 바꾼 파일이 드러나지 않는다.
Pre 에서 시작 시각을 적어 두고, Post 에서 작업 폴더를 훑어 그 뒤에 수정 시각이 바뀐 파일을 찾는다.
ponytail: 수정 시각만 본다 — 지운 파일은 못 잡고 Bash 가 도는 동안 사람이 고친 파일도 섞인다. 지운 파일까지 필요하면 Pre 에서 목록을 떠 둔다
"""
import json
import os
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fleet.db import DB, db  # noqa: E402

SKIP = {".git", "node_modules", "build", "target", ".gradle", ".venv", "venv", "__pycache__", "dist", ".idea"}
MAX_FILES = 50_000  # ponytail: 이보다 큰 폴더는 앞쪽만 훑는다 — Bash 마다 도는 훅이라 느려지지 않게


def changed(cwd, since):
    n = 0
    for root, dirs, files in os.walk(cwd):
        dirs[:] = [d for d in dirs if d not in SKIP]
        for f in files:
            n += 1
            if n > MAX_FILES:
                return
            p = os.path.join(root, f)
            try:
                if os.stat(p).st_mtime >= since:
                    yield p
            except OSError:  # 훑는 사이에 지워진 파일
                continue


def main():
    h = json.load(sys.stdin)
    if h.get("tool_name") != "Bash" or not h.get("tool_use_id"):
        return
    mark = DB.parent / "bash-start" / h["tool_use_id"]
    if h.get("hook_event_name") == "PreToolUse":
        mark.parent.mkdir(parents=True, exist_ok=True)
        mark.write_text(str(time.time()))
        return
    try:
        since = float(mark.read_text())
        mark.unlink()
    except (OSError, ValueError):  # Pre 가 안 돌았다 (플러그인을 Bash 도중에 설치 등)
        return
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"  # 대화 기록의 timestamp 형식
    rows = [(h["session_id"], h["tool_use_id"], p, ts) for p in changed(h.get("cwd") or ".", since)]
    if rows:
        c = db()
        c.executemany("INSERT OR IGNORE INTO bash_files VALUES (?,?,?,?)", rows)
        c.commit()
        c.close()


if __name__ == "__main__":
    try:
        main()
    except Exception:  # 훅이 실패해도 Bash 실행은 막지 않는다
        pass
