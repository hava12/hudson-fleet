"""Claude Code 대화 기록(~/.claude/projects/*.jsonl) 읽기."""
import difflib
import glob
import json
import re
from pathlib import Path

from .config import EDIT_TOOLS, PROJECTS


def transcript(sid):
    # ponytail: glob over all projects per request, index by sid if project count grows large
    hits = glob.glob(str(PROJECTS / "*" / f"{glob.escape(sid)}.jsonl"))
    return Path(hits[0]) if sid and hits else None


def model_of(sid):
    """마지막 응답의 모델과 effort. 대화 기록 끝 256KB 만 읽는다."""
    p = transcript(sid)
    if not p:
        return {}
    with p.open("rb") as f:
        f.seek(max(0, p.stat().st_size - 262144))
        lines = f.read().decode("utf-8", "replace").splitlines()
    for line in reversed(lines):
        if '"type":"assistant"' in line:
            try:
                rec = json.loads(line)
            except ValueError:  # 잘려 시작한 첫 줄
                continue
            m = rec.get("message") or {}
            u = m.get("usage") or {}
            ctx = u.get("input_tokens", 0) + u.get("cache_read_input_tokens", 0) + u.get("cache_creation_input_tokens", 0)
            model = m.get("model") or ""
            # 지금 모델은 모두 1M. 200K 는 Claude 3·4.5 이전 세대 (Haiku 4.5 등)
            window = 200_000 if re.search(r"claude-3|-4-[0-5](?!\d)", model) and ctx <= 200_000 else 1_000_000
            return {"model": model, "effort": rec.get("effort"), "ctx": ctx, "ctxMax": window}
    return {}


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
    custom, ai, prompts, first, last = "", "", [], "", ""
    for line in path.open(encoding="utf-8", errors="replace"):
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        custom, ai = rec.get("customTitle") or custom, rec.get("aiTitle") or ai
        ts = rec.get("timestamp", "")
        if ts:
            first, last = first or ts, ts
        if p := prompt_text(rec):
            prompts.append({"ts": ts, "text": p[:300]})
    return {"title": custom or ai, "prompts": prompts, "first": first, "last": last}


@by_mtime
def changes_of(sid, path):
    changes, _ = scan(path, "main")
    for aid, desc, p in subagents(sid):
        changes += scan(p, desc or aid)[0]
    return sorted(changes, key=lambda e: e["ts"])


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
