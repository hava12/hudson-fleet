"""Claude Code 대화 기록(~/.claude/projects/*.jsonl) 읽기."""
import glob
import json
import re
from pathlib import Path

from .config import PROJECTS


def transcript(sid):
    if not re.fullmatch(r"[0-9a-f-]{36}", sid or ""):  # 세션 id 만 — ../ 로 기록 폴더 밖 파일을 읽지 못하게
        return None
    # ponytail: glob over all projects per request, index by sid if project count grows large
    hits = glob.glob(str(PROJECTS / "*" / f"{sid}.jsonl"))
    return Path(hits[0]) if hits else None


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
