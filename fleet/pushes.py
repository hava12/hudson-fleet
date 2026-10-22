"""Claude 가 실행한 git push 기록."""
import json
import os
import re
import sqlite3
import subprocess

from .config import PROJECTS
from .db import db
from .transcripts import by_mtime


@by_mtime
def pushes_in(path):
    """대화 기록 하나에서 Claude 가 실행한 git push 와 그 결과(To <주소>, old..new ref -> ref)를 찾는다."""
    pend, out = {}, []
    for line in path.open(encoding="utf-8", errors="replace"):
        if "git push" not in line and "tool_use_id" not in line:  # 대부분의 줄은 해석 없이 건너뛴다
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        blocks = (rec.get("message") or {}).get("content")
        for b in blocks if isinstance(blocks, list) else []:
            if b.get("type") == "tool_use" and "git push" in (b.get("input") or {}).get("command", ""):
                pend[b["id"]] = (b["input"]["command"], rec.get("timestamp", ""), rec.get("cwd", ""), rec.get("sessionId", ""))
            elif b.get("type") == "tool_result" and b.get("tool_use_id") in pend:
                cmd, ts, cwd, sid = pend.pop(b["tool_use_id"])
                t = b.get("content")
                t = t if isinstance(t, str) else "\n".join(x.get("text", "") for x in t or [] if isinstance(x, dict))
                if m := re.match(r"\s*cd\s+([^\s;&|]+)", cmd):  # cd <폴더> && ... git push (cd <폴더>; 처럼 붙은 ; 는 빼고)
                    cwd = os.path.expanduser(m[1].strip("'\""))
                to = re.search(r"^To (\S+)", t, re.M)
                for r in re.finditer(r"^\s*[+*]?\s*([0-9a-f]{7,})\.\.\.?([0-9a-f]{7,})\s+(\S+)\s+->\s+(\S+)", t, re.M):
                    out.append({"id": f"{b['tool_use_id']}:{r[4]}", "ts": ts, "sid": sid, "cwd": cwd,
                                "remote": to[1] if to else "", "ref": r[4], "old": r[1], "new": r[2]})
    return out


def pushes(limit=200, sid=None):
    """새 push 를 DB 에 넣고(커밋 메시지는 그때 git log 로 읽어 둔다) 최근 것부터 돌려준다. sid 를 주면 그 세션 것만."""
    c = db()
    c.row_factory = sqlite3.Row
    # 커밋 목록이 빈 행은 다시 읽는다 (폴더를 못 찾았던 옛 기록 — 폴더가 지금도 없으면 또 빈다)
    have = {r[0] for r in c.execute("SELECT id FROM pushes WHERE commits != '[]'")}
    for p in [*PROJECTS.glob("*/*.jsonl"), *PROJECTS.glob("*/*/subagents/agent-*.jsonl")]:
        try:
            found = pushes_in(p)
        except OSError:  # 목록을 읽은 사이에 지워진 대화 기록
            continue
        for e in found:
            if e["id"] in have:
                continue
            git = lambda *a: subprocess.run(["git", "-C", e["cwd"], *a], capture_output=True, text=True).stdout.strip()
            log = git("log", "--format=%h%x09%s", f"{e['old']}..{e['new']}") if os.path.isdir(e["cwd"]) else ""
            remote = e["remote"] or (git("remote", "get-url", "origin") if os.path.isdir(e["cwd"]) else "")
            c.execute("INSERT OR REPLACE INTO pushes VALUES (?,?,?,?,?,?,?,?,?)",
                      (e["id"], e["ts"], e["sid"], e["cwd"], remote, e["ref"], e["old"], e["new"],
                       json.dumps([ln.split("\t", 1) for ln in log.splitlines()], ensure_ascii=False)))
            have.add(e["id"])
    c.commit()
    out = [dict(r) for r in c.execute(
        "SELECT p.*, coalesce(s.my_title, s.title, s.name) AS session FROM pushes p LEFT JOIN sessions s USING (sid)"
        + (" WHERE p.sid = ?" if sid else "") + " ORDER BY p.ts DESC LIMIT ?", (*([sid] if sid else []), limit))]
    c.close()
    for r in out:
        r["commits"] = json.loads(r["commits"] or "[]")
    return out
