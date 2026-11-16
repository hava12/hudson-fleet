"""옵시디언 기록 (설정 ⚙ → 연결 → Obsidian). DB 가 원본이고, 볼트 폴더의 md 노트는 그 사본이다.
기록기가 1분마다 write_notes() — 세션마다 한 장(세션/), 프로젝트마다 한 장(프로젝트/). 내용이 바뀐 노트만 다시 쓴다.
노트의 MARK 줄 위는 DB 내용으로 덮어쓰고, 아래에 사람이 쓴 메모는 그대로 둔다."""
import json
import re
import sqlite3
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from .config import CFG
from .db import db
from .links import LinkError, _on

MARK = "%% 이 줄 아래에 쓴 메모는 대시보드가 지우지 않습니다 %%"
BOX = {"todo": " ", "done": "x", "stopped": "-", "rejected": "-"}  # 체크 상자. 중단·반려는 앞에 낱말도 붙인다
WORD = {"stopped": "중단 · ", "rejected": "반려 · "}
PST = {"pending": "시작 전", "active": "진행 중", "done": "끝남"}
q = lambda v: json.dumps(v, ensure_ascii=False)  # 머리말(YAML) 문자열 — JSON 문자열은 YAML 로도 읽힌다


def safe(s):
    """파일 이름·[[링크]] 에 못 쓰는 글자를 뺀다."""
    return re.sub(r'[\\/:*?"<>|#^\[\]\s]+', " ", s or "").strip()[:60]


def local(ts):
    try:
        return datetime.fromisoformat(ts).astimezone().strftime("%Y-%m-%dT%H:%M")
    except (TypeError, ValueError):
        return ts or ""


def tilde(p):
    h = str(Path.home())
    return "~" + p[len(h):] if p and p.startswith(h) else p or ""


def task(t, link):
    """작업 한 줄 + 설명 줄. link: 줄 끝에 붙일 [[링크]] (세션 노트에는 프로젝트, 프로젝트 노트에는 세션)."""
    try:
        d, fl = json.loads(t["details"] or "[]"), json.loads(t["flow"] or "null")
    except ValueError:  # 옛 기록
        d, fl = [], None
    out = [f"- [{BOX.get(t['status'], ' ')}] {WORD.get(t['status'], '')}{t['text']}{' #' + t['tag'] if t['tag'] else ''} (#{t['id']}){link}"]
    out += [f"  - {x}" for x in d]
    if t["note"] and t["status"] != "todo":
        out.append(f"  - 결과: {t['note']}")
    if fl:
        out.append("  - 흐름: " + " → ".join([fl.get("trigger", ""), *(s.get("title", "") for s in fl.get("steps", []))])
                   + " → 결과: " + ", ".join(fl.get("outputs", [])))
    return out


def put(path, body, old=None):
    """MARK 위는 body 로, 아래(사람 메모)는 그대로. old: 제목이 바뀌어 이름이 달라진 예전 파일. 쓴 때만 True."""
    src = old or path
    text = src.read_text() if src.is_file() else ""
    new = body + "\n" + MARK + (text.partition(MARK)[2] or "\n")
    if src == path and new == text:
        return False
    path.write_text(new)
    if src != path:
        src.unlink()
    return True


def folder():
    """노트를 쓸 폴더와 볼트 이름. 볼트(.obsidian 이 있는 폴더) 안이어야 한다 — 엉뚱한 곳에 파일을 뿌리지 않게."""
    if not CFG["HUDSON_FLEET_OBSIDIAN_DIR"]:
        raise LinkError("노트를 쓸 폴더를 넣으세요 (볼트 폴더 또는 그 안의 폴더)")
    f = Path(CFG["HUDSON_FLEET_OBSIDIAN_DIR"]).expanduser()
    vault = next((p for p in (f, *f.parents) if (p / ".obsidian").is_dir()), None)
    if not vault:
        raise LinkError(f"옵시디언 볼트 안의 폴더가 아닙니다 (.obsidian 폴더를 찾지 못함): {f}")
    return f, vault.name


def sync():
    """노트를 DB 와 맞춘다 → (볼트 이름, 노트 수, 이번에 쓴 수). 지운 세션·자동 호출은 쓰지 않는다 (이미 쓴 노트는 남김)."""
    f, vault = folder()
    sd, pd = f / "세션", f / "프로젝트"
    sd.mkdir(parents=True, exist_ok=True)
    pd.mkdir(exist_ok=True)
    c = db()
    c.row_factory = sqlite3.Row
    P = {r["id"]: r for r in c.execute("SELECT p.*, a.name AS area FROM projects p LEFT JOIN areas a ON a.id = p.area_id")}
    S = c.execute("SELECT * FROM sessions WHERE status IS NOT NULL AND deleted_at IS NULL AND kind IS NOT 'auto' ORDER BY started_at").fetchall()
    T, U = defaultdict(list), defaultdict(list)
    for t in c.execute("SELECT * FROM session_tasks ORDER BY sort, id"):
        T[t["sid"]].append(t)
    for p in c.execute("SELECT * FROM pushes ORDER BY ts"):
        U[p["sid"]].append(p)
    c.close()
    have = {p.stem[-9:-1]: p for p in sd.glob("*.md") if p.stem.endswith(")")}  # 세션 id 앞 8글자 → 지금 파일
    stem, wrote = {}, 0
    for s in S:
        title = s["my_title"] or s["title"] or s["name"] or s["sid"][:8]
        stem[s["sid"]] = (st := f"{local(s['started_at'])[:10]} {safe(title)} ({s['sid'][:8]})".strip())
        ts = T[s["sid"]]
        projs = sorted({P[t["project_id"]]["name"] for t in ts if t["project_id"] in P})
        body = ["---", f"title: {q(title)}", f"session: {s['sid']}", f"folder: {q(tilde(s['cwd']))}",
                f"app: {q('백그라운드' if s['kind'] == 'background' else s['app'] or '')}",
                f"status: {'끝남' if s['status'] == 'closed' else '진행 중'}", f"started: {local(s['started_at'])}",
                *([f"ended: {local(s['ended_at'])}"] if s["ended_at"] else []), *([f"tokens: {s['tokens']}"] if s["tokens"] else []),
                *(["projects:", *(f"  - {q(f'[[{safe(n)}]]')}" for n in projs)] if projs else []), "---",
                f"# {title}", "", "## 작업", *(x for t in ts for x in task(t, f" [[{safe(P[t['project_id']]['name'])}]]" if t["project_id"] in P else ""))]
        if not ts:
            body.append("기록한 작업 없음")
        if U[s["sid"]]:
            body += ["", "## Push"]
            for p in U[s["sid"]]:
                cs = json.loads(p["commits"] or "[]")
                body += [f"- {local(p['ts']).replace('T', ' ')} · {p['remote']} {p['ref']} · 커밋 {len(cs)}개", *(f"  - {h[:7]} {m}" for h, m in cs)]
        old = have.get(s["sid"][:8])
        wrote += put(sd / f"{st}.md", "\n".join(body) + "\n", old if old and old.stem != st else None)
    for p in P.values():
        ts = [t for sid in stem for t in T[sid] if t["project_id"] == p["id"]]  # 지운 세션의 작업은 뺀다 (남은 작업 칸과 같게)
        n = {k: sum(t["status"] == k for t in ts) for k in BOX}
        body = ["---", f"status: {PST.get(p['status'], p['status'] or '')}", *([f"area: {q(p['area'])}"] if p["area"] else []),
                *([f"start: {p['start']}"] if p["start"] else []), *([f"end: {p['end']}"] if p["end"] else []), "---",
                f"# {p['name']}", "", f"완료 조건: {p['done_when'] or '없음'}", "",
                f"남은 일 {n['todo']} · 완료 {n['done']} · 중단 {n['stopped']} · 반려 {n['rejected']} (완료한 일은 세션 노트에서, 이 노트의 백링크로 모아 봅니다)",
                "", "## 남은 일", *(x for t in ts if t["status"] == "todo" for x in task(t, f" [[{stem[t['sid']]}]]" if t["sid"] in stem else ""))]
        if not n["todo"]:
            body.append("없음")
        wrote += put(pd / f"{safe(p['name'])}.md", "\n".join(body) + "\n")
    return vault, len(S) + len(P), wrote


def write_notes():
    """기록기가 1분마다 부른다. 꺼져 있으면 아무것도 안 한다."""
    if CFG["HUDSON_FLEET_OBSIDIAN_ON"] == "1":
        sync()


def check():
    """[연결 확인]: 바로 한 번 맞추고 결과를 문장으로."""
    _on("OBSIDIAN", "Obsidian")
    try:
        vault, n, w = sync()
    except OSError as e:  # macOS 가 문서 폴더 등을 막았거나 디스크 오류
        raise LinkError(f"노트를 쓰지 못했습니다: {e}") from None
    return f"{vault} 볼트 · 노트 {n}장 (이번에 쓴 것 {w}장)"


if __name__ == "__main__":  # 확인: python3 -m fleet.obsidian — 메모 보존과 이름 바꾸기
    import tempfile
    d = Path(tempfile.mkdtemp())
    a, b = d / "a.md", d / "b.md"
    assert put(a, "본문1\n") and not put(a, "본문1\n")  # 같으면 다시 쓰지 않는다
    a.write_text(a.read_text() + "내 메모\n")
    assert put(a, "본문2\n") and a.read_text() == f"본문2\n\n{MARK}\n내 메모\n"
    assert put(b, "본문3\n", a) and not a.exists() and b.read_text().endswith("내 메모\n")  # 제목이 바뀌면 메모째 옮긴다
    assert safe('a/b: "c" [d]#e') == "a b c d e"
    print("ok")
