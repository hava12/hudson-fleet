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
    rows, y = [], 58
    for t in tags:
        a, b = w7.get(t, 0), w30.get(t, 0)
        rows.append(f'<text x="20" y="{y + 10}" class="l">{escape(t)}</text>'
                    f'<rect x="80" y="{y}" width="{max(2, 150 * a / top):.0f}" height="11" rx="3" class="b7"/>'
                    f'<text x="236" y="{y + 10}" class="n">{a}</text>'
                    f'<rect x="270" y="{y}" width="{max(2, 150 * b / top):.0f}" height="11" rx="3" class="b30"/>'
                    f'<text x="426" y="{y + 10}" class="n">{b}</text>')
        y += 18
    h = y + 10
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="470" height="{h}" viewBox="0 0 470 {h}">
<style>
.bg{{fill:#fff;stroke:#d0d7de}}.t{{font:600 15px sans-serif;fill:#1f2328}}.s,.n,.h{{font:12px sans-serif;fill:#59636e}}
.l{{font:13px sans-serif;fill:#1f2328}}.b7{{fill:#1f883d}}.b30{{fill:#0969da}}
@media (prefers-color-scheme: dark){{.bg{{fill:#0d1117;stroke:#30363d}}.t,.l{{fill:#e6edf3}}.s,.n,.h{{fill:#9198a1}}
.b7{{fill:#3fb950}}.b30{{fill:#4493f8}}}}
</style>
<rect x=".5" y=".5" width="469" height="{h - 1}" rx="8" class="bg"/>
<text x="20" y="28" class="t">Claude Code 와 완료한 작업</text>
<text x="450" y="28" text-anchor="end" class="s">{stamp} · hudson-fleet</text>
<text x="80" y="48" class="h">최근 7일 · {sum(w7.values())}건</text>
<text x="270" y="48" class="h">최근 30일 · {sum(w30.values())}건</text>
{"".join(rows)}
</svg>'''


def won(n):
    """토큰 수를 읽기 쉽게: 1.2억 · 3,636만 · 9,800."""
    return f"{n / 1e8:.1f}억" if n >= 1e8 else f"{n / 1e4:,.0f}만" if n >= 1e4 else f"{n:,}"


def tokens_svg():
    """토큰 사용량 카드: 위에 오늘·7일·30일·1년 합계, 아래에 최근 12주 주간 막대.
    README 의 <img> 에서는 hover 가 안 되므로 숫자를 그림에 직접 쓴다 (눈금 2줄 + 가장 많은 주·이번 주 값)."""
    c = db()
    days = dict(c.execute("SELECT day, tokens FROM daily WHERE day >= date('now', '-371 days')"))
    c.close()
    today = date.today()

    def total(n):  # 오늘 포함 최근 n 일
        return sum(days.get((today - timedelta(days=k)).isoformat(), 0) for k in range(n))

    tiles = [("오늘", total(1)), ("최근 7일", total(7)), ("최근 30일", total(30)), ("최근 1년", sum(days.values()))]
    monday = today - timedelta(days=today.weekday())
    weeks = [(monday - timedelta(weeks=k), sum(days.get((monday - timedelta(weeks=k, days=-d)).isoformat(), 0)
                                               for d in range(7))) for k in range(11, -1, -1)]
    top = max(v for _, v in weeks) or 1
    w, x0, bw, gap, base, ph = 612, 64, 38, 6, 162, 44  # 막대 영역: 왼쪽 눈금 글자 뒤 x=64, 바닥 y=162, 높이 44
    tile = "".join(f'<text x="{20 + k * 145}" y="52" class="s">{t}</text>'
                   f'<text x="{20 + k * 145}" y="76" class="big">{won(v)}</text>' for k, (t, v) in enumerate(tiles))
    step = next(m * 10 ** e for e in range(3, 12) for m in (1, 2, 5) if m * 10 ** e >= top / 2)  # 눈금은 1·2·5 단위, 2줄 이하
    grid = "".join(f'<line x1="{x0}" x2="{w - 20}" y1="{base - ph * g / top:.0f}" y2="{base - ph * g / top:.0f}" class="gl"/>'
                   f'<text x="{x0 - 8}" y="{base - ph * g / top + 4:.0f}" text-anchor="end" class="s">{won(g)}</text>'
                   for g in range(step, top + 1, step))
    peak = max(range(12), key=lambda k: weeks[k][1])
    bars = []
    for k, (wk, v) in enumerate(weeks):
        x, h = x0 + k * (bw + gap), max(2, ph * v / top) if v else 0
        if h:  # 위쪽만 4px 둥글게, 바닥에 붙인다
            bars.append(f'<path d="M{x},{base} v{-(h - 4):.1f} q0,-4 4,-4 h{bw - 8} q4,0 4,4 v{h - 4:.1f} z" class="bar"/>')
        if k in (peak, 11) and v:
            bars.append(f'<text x="{x + bw / 2}" y="{base - h - 6:.0f}" text-anchor="middle" class="v">{won(v)}</text>')
        if k % 2 == 1 or k == 11:
            bars.append(f'<text x="{x + bw / 2}" y="{base + 14}" text-anchor="middle" class="s">'
                        f'{"이번 주" if k == 11 else f"{wk.month}/{wk.day}"}</text>')
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    h = base + 30
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">
<style>
.bg{{fill:#fff;stroke:#d0d7de}}.t{{font:600 15px sans-serif;fill:#1f2328}}.s{{font:11px sans-serif;fill:#59636e}}
.big{{font:600 22px sans-serif;fill:#1f2328}}.v{{font:600 12px sans-serif;fill:#1f2328}}.gl{{stroke:#d8dee4;stroke-dasharray:2 3}}
.bar{{fill:#0969da}}.ax{{stroke:#d0d7de}}
@media (prefers-color-scheme: dark){{.bg{{fill:#0d1117;stroke:#30363d}}.t,.big,.v{{fill:#e6edf3}}.s{{fill:#9198a1}}
.gl{{stroke:#30363d}}.bar{{fill:#4493f8}}.ax{{stroke:#3d444d}}}}
</style>
<rect x=".5" y=".5" width="{w - 1}" height="{h - 1}" rx="8" class="bg"/>
<text x="20" y="28" class="t">Claude Code 토큰 사용량</text>
<text x="{w - 20}" y="28" text-anchor="end" class="s">{stamp} · hudson-fleet</text>
{tile}
<text x="20" y="100" class="s">주간 토큰 · 최근 12주</text>
{grid}<line x1="{x0}" x2="{w - 20}" y1="{base}" y2="{base}" class="ax"/>
{"".join(bars)}
</svg>'''


def publish():
    """HUDSON_FLEET_GIST 가 있으면 카드를 그 Gist 에 덮어쓴다. gh CLI 로 보낸다 (HUDSON_FLEET_GIST_USER 계정의 토큰)."""
    gist = CFG["HUDSON_FLEET_GIST"]
    if not gist:
        return
    env = None
    if user := CFG["HUDSON_FLEET_GIST_USER"]:
        tok = subprocess.run(["gh", "auth", "token", "--user", user], capture_output=True, text=True, timeout=30).stdout.strip()
        env = {**os.environ, "GH_TOKEN": tok}
    body = json.dumps({"files": {FILE: {"content": card_svg()}, TOKENS_FILE: {"content": tokens_svg()}}})
    r = subprocess.run(["gh", "api", "-X", "PATCH", f"gists/{gist}", "--input", "-"], input=body, env=env,
                       capture_output=True, text=True, timeout=30)
    if r.returncode:
        print("프로필 카드 올리기 실패:", r.stderr.strip()[:200])
