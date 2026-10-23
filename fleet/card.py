"""프로필 카드: 최근 7일·30일 완료한 작업을 태그별로 센 카드와 1년 토큰 잔디를 SVG 로 그려 Gist 에 덮어쓴다 (30분마다, recorder).
작업 문장·경로는 넣지 않는다 — 공개되는 그림이라 일의 종류(태그)와 건수만."""
import json
import os
import subprocess
from datetime import date, datetime, timedelta, timezone
from html import escape

from .config import CFG
from .db import db
from .tasks import TAGS

FILE = "hudson-fleet.svg"
TOKENS_FILE = "hudson-fleet-tokens.svg"


def counts(days):
    """최근 days 일 동안 완료한 작업 수 {태그: 건수}. updated_at 기준, 태그가 없는 옛 행(태그 기능 이전)은 뺀다."""
    # ponytail: 완료 뒤에 태그만 고쳐도 updated_at 이 바뀐다 — 정확한 완료 시각이 필요하면 task_events 의 done 시각으로
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
    c = db()
    rows = c.execute("SELECT tag, count(*) FROM session_tasks WHERE status = 'done' AND tag IS NOT NULL AND updated_at >= ?"
                     " GROUP BY 1", (since,)).fetchall()
    c.close()
    return dict(rows)


def card_svg():
    w7, w30 = counts(7), counts(30)
    tags = sorted((t for t in TAGS if w30.get(t)), key=lambda t: -w30[t]) or ["개발"]  # 많이 한 일부터
    top = max(w30.values(), default=1)
    rows, y = [], 78
    for t in tags:
        a, b = w7.get(t, 0), w30.get(t, 0)
        rows.append(f'<text x="20" y="{y + 11}" class="l">{escape(t)}</text>'
                    f'<rect x="80" y="{y}" width="{max(2, 150 * a / top):.0f}" height="12" rx="3" class="b7"/>'
                    f'<text x="236" y="{y + 11}" class="n">{a}</text>'
                    f'<rect x="270" y="{y}" width="{max(2, 150 * b / top):.0f}" height="12" rx="3" class="b30"/>'
                    f'<text x="426" y="{y + 11}" class="n">{b}</text>')
        y += 22
    h = y + 14
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="470" height="{h}" viewBox="0 0 470 {h}">
<style>
.bg{{fill:#fff;stroke:#d0d7de}}.t{{font:600 15px sans-serif;fill:#1f2328}}.s,.n,.h{{font:12px sans-serif;fill:#59636e}}
.l{{font:13px sans-serif;fill:#1f2328}}.b7{{fill:#1f883d}}.b30{{fill:#0969da}}
@media (prefers-color-scheme: dark){{.bg{{fill:#0d1117;stroke:#30363d}}.t,.l{{fill:#e6edf3}}.s,.n,.h{{fill:#9198a1}}
.b7{{fill:#3fb950}}.b30{{fill:#4493f8}}}}
</style>
<rect x=".5" y=".5" width="469" height="{h - 1}" rx="8" class="bg"/>
<text x="20" y="30" class="t">Claude Code 와 완료한 작업</text>
<text x="450" y="30" text-anchor="end" class="s">{stamp} · hudson-fleet</text>
<text x="80" y="62" class="h">최근 7일 · {sum(w7.values())}건</text>
<text x="270" y="62" class="h">최근 30일 · {sum(w30.values())}건</text>
{"".join(rows)}
</svg>'''


def won(n):
    """토큰 수를 읽기 쉽게: 1.2억 · 345만 · 9,800."""
    return f"{n / 1e8:.1f}억" if n >= 1e8 else f"{n / 1e4:.0f}만" if n >= 1e4 else f"{n:,}"


def tokens_svg():
    """최근 1년(53주) 하루 토큰 잔디. 색 단계는 0 과, 쓴 날들의 4분위 (GitHub 잔디와 같은 방식)."""
    c = db()
    days = dict(c.execute("SELECT day, tokens FROM daily WHERE day >= date('now', '-371 days')"))
    c.close()
    today = date.today()
    start = today - timedelta(days=(today.weekday() + 1) % 7 + 52 * 7)  # 53주 전 일요일
    used = sorted(v for v in days.values() if v)
    cut = [used[len(used) * k // 4] for k in (1, 2, 3)] if used else []
    cells, months, d = [], [], start
    while d <= today:
        x, y = 40 + (d - start).days // 7 * 12, 52 + (d.weekday() + 1) % 7 * 12
        v = days.get(d.isoformat(), 0)
        cells.append(f'<rect x="{x}" y="{y}" width="10" height="10" rx="2" class="g{sum(v >= k for k in cut) + 1 if v else 0}"/>')
        if d.day == 1:
            months.append(f'<text x="{x}" y="44" class="s">{d.month}월</text>')
        d += timedelta(days=1)
    w = 40 + 53 * 12 + 18
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="150" viewBox="0 0 {w} 150">
<style>
.bg{{fill:#fff;stroke:#d0d7de}}.t{{font:600 15px sans-serif;fill:#1f2328}}.s{{font:11px sans-serif;fill:#59636e}}
.g0{{fill:#eff2f5}}.g1{{fill:#aceebb}}.g2{{fill:#4ac26b}}.g3{{fill:#2da44e}}.g4{{fill:#116329}}
@media (prefers-color-scheme: dark){{.bg{{fill:#0d1117;stroke:#30363d}}.t{{fill:#e6edf3}}.s{{fill:#9198a1}}
.g0{{fill:#151b23}}.g1{{fill:#033a16}}.g2{{fill:#196c2e}}.g3{{fill:#2ea043}}.g4{{fill:#56d364}}}}
</style>
<rect x=".5" y=".5" width="{w - 1}" height="149" rx="8" class="bg"/>
<text x="20" y="26" class="t">Claude Code 토큰 활동</text>
<text x="{w - 20}" y="26" text-anchor="end" class="s">최근 1년 {won(sum(days.values()))} 토큰 · {len(used)}일 · 하루 최대 {won(max(used, default=0))}</text>
{"".join(months)}<text x="12" y="73" class="s">월</text><text x="12" y="97" class="s">수</text><text x="12" y="121" class="s">금</text>
{"".join(cells)}
</svg>'''


def publish():
    """HUDSON_FLEET_GIST 가 있으면 카드를 그 Gist 에 덮어쓴다. gh CLI 로 보낸다 (HUDSON_FLEET_GIST_USER 계정의 토큰)."""
    gist = CFG["HUDSON_FLEET_GIST"]
    if not gist:
        return
    env = None
    if user := CFG["HUDSON_FLEET_GIST_USER"]:
        tok = subprocess.run(["gh", "auth", "token", "--user", user], capture_output=True, text=True).stdout.strip()
        env = {**os.environ, "GH_TOKEN": tok}
    body = json.dumps({"files": {FILE: {"content": card_svg()}, TOKENS_FILE: {"content": tokens_svg()}}})
    r = subprocess.run(["gh", "api", "-X", "PATCH", f"gists/{gist}", "--input", "-"], input=body, env=env,
                       capture_output=True, text=True, timeout=30)
    if r.returncode:
        print("프로필 카드 올리기 실패:", r.stderr.strip()[:200])
