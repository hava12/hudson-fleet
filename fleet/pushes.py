"""Claude 가 실행한 git push 기록 (사용자가 세션 안에서 ! 로 실행한 것 포함)."""
import html
import json
import os
import re
import sqlite3
import subprocess

from .config import PROJECTS
from .db import db
from .transcripts import by_mtime


def _parse(t, key, cmd, ts, cwd, sid):
    """push 출력(To <주소>, old..new ref -> ref)을 ref 마다 한 행으로."""
    if m := re.match(r"\s*cd\s+([^\s;&|]+)", cmd):  # cd <폴더> && ... git push (cd <폴더>; 처럼 붙은 ; 는 빼고)
        cwd = os.path.expanduser(m[1].strip("'\""))
    to = re.search(r"^To (\S+)", t, re.M)
    return [{"id": f"{key}:{r[4]}", "ts": ts, "sid": sid, "cwd": cwd, "remote": to[1] if to else "", "ref": r[4], "old": r[1], "new": r[2]}
            for r in re.finditer(r"^\s*[+*]?\s*([0-9a-f]{7,})\.\.\.?([0-9a-f]{7,})\s+(\S+)\s+->\s+(\S+)", t, re.M)]


@by_mtime
def pushes_in(path):
    """대화 기록 하나에서 git push 와 그 결과를 찾는다.
    Claude 의 Bash 도구: tool_use ↔ tool_result 를 id 로 짝짓는다.
    사용자의 ! 명령: <bash-input> 메시지 바로 다음의 <bash-stdout>·<bash-stderr> 메시지가 결과다 (> 가 &gt; 로 저장된다)."""
    pend, bang, out = {}, None, []
    for line in path.open(encoding="utf-8", errors="replace"):
        if "git push" not in line and "tool_use_id" not in line and not (bang and "<bash-std" in line):  # 대부분의 줄은 해석 없이 건너뛴다
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        meta = (rec.get("timestamp", ""), rec.get("cwd", ""), rec.get("sessionId", ""))
        blocks = (rec.get("message") or {}).get("content")
        if rec.get("type") == "user" and isinstance(blocks, str):  # ! 명령과 그 출력은 문자열 content 로 남는다
            if m := re.search(r"<bash-input>(.*?)</bash-input>", blocks, re.S):
                bang = (rec.get("uuid", ""), m[1], *meta) if "git push" in m[1] else None
            elif bang and "<bash-std" in blocks:
                out += _parse(html.unescape(re.sub(r"</?bash-std(?:out|err)>", "\n", blocks)), *bang)
                bang = None
            continue
        for b in blocks if isinstance(blocks, list) else []:
            if b.get("type") == "tool_use" and "git push" in (b.get("input") or {}).get("command", ""):
                pend[b["id"]] = (b["input"]["command"], *meta)
            elif b.get("type") == "tool_result" and b.get("tool_use_id") in pend:
                t = b.get("content")
                t = t if isinstance(t, str) else "\n".join(x.get("text", "") for x in t or [] if isinstance(x, dict))
                out += _parse(t, b["tool_use_id"], *pend.pop(b["tool_use_id"]))
    return out


_tried = set()  # 이 프로세스에서 이미 읽어 본 push — 커밋 목록이 빈 행(폴더가 없거나 커밋을 못 찾음)을 요청마다 다시 읽지 않는다


def pushes(limit=200, sid=None):
    """새 push 를 DB 에 넣고(커밋 메시지는 그때 git log 로 읽어 둔다) 최근 것부터 돌려준다. sid 를 주면 그 세션 것만.
    git 은 DB 를 열기 전에 다 부른다 — 쓰기 잠금을 쥔 채 부르면 그동안 작업 기록이 database is locked 로 실패한다."""
    c = db()
    have = {r[0] for r in c.execute("SELECT id FROM pushes WHERE commits != '[]'")} | _tried
    c.close()
    rows = []
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
            rows.append((e["id"], e["ts"], e["sid"], e["cwd"], remote, e["ref"], e["old"], e["new"],
                         json.dumps([ln.split("\t", 1) for ln in log.splitlines()], ensure_ascii=False)))
            have.add(e["id"])
            _tried.add(e["id"])
    c = db()
    c.row_factory = sqlite3.Row
    c.executemany("INSERT OR REPLACE INTO pushes VALUES (?,?,?,?,?,?,?,?,?)", rows)
    c.commit()
    out = [dict(r) for r in c.execute(
        "SELECT p.*, coalesce(s.my_title, s.title, s.name) AS session FROM pushes p LEFT JOIN sessions s USING (sid)"
        + (" WHERE p.sid = ?" if sid else "") + " ORDER BY p.ts DESC LIMIT ?", (*([sid] if sid else []), limit))]
    c.close()
    for r in out:
        r["commits"] = json.loads(r["commits"] or "[]")
    return out
