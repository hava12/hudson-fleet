# 화면 디자인 규칙

web/ 의 화면을 만들거나 고칠 때 먼저 읽는다. 값의 원본은 Figma 'hudson-fleet design system' 이다.

- 어두운 화면 색과 크기: Figma 변수 → hudson-fleet 플러그인 [토큰 보내기] → `src/tokens.css` (손으로 고치지 않는다)
- 밝은 화면 색: `src/style.css` 맨 위 `:root` (Figma 무료 요금제라 모드가 없다)
- 부품: `src/ui.jsx` (Figma 부품과 이름·속성이 같다). 모든 모양은 대시보드 주소 `#ui` 의 부품 모음에서 본다

## 이름표 역할

| 묶음 | 이름표 | 쓰는 곳 |
| --- | --- | --- |
| 바탕 | `--bg` · `--card` · `--soft` · `--line` | 페이지 바탕 · 카드·입력칸·메뉴 바탕 · 옅은 칸(마우스 올림, 막대 바탕) · 테두리·구분선 |
| 글자 | `--fg` · `--mute` | 본문 · 흐린 글자(설명, 카드 제목 h2) |
| 칠한 바탕 위 글자 | `--on-acc` · `--on-fill` · `--on-todo` | 강조색 위 · 상태 색으로 칠한 칸 위(그래프 노드) · 남은 일 색 위(서버 끊김 띠) |
| 강조 | `--acc` · `--acc-hover` · `--acc-press` · `--press` | 주 단추·링크·고른 것 · 주 단추 올림·누름 · 보통 단추 누름 |
| 상태 바탕 | `--acc-bg` · `--ok-bg` · `--wait-bg` · `--bad-bg` (+ `--on-acc-bg` · `--on-bad-bg`) | 꼬리표(Pill) 바탕과 그 위 글자 |
| 비활성 | `--dis-bg` · `--dis-fg` | 누를 수 없는 단추의 바탕·글자 |
| 세션 상태 | `--ok` · `--wait` · `--idle` · `--off` · `--bad` | 작업 중 · 입력 대기 · 쉬는 중 · 끝남 · 실패·위험 (`lib.jsx` GINFO) |
| 작업 상태 | `--t-todo` · `--t-stop` · `--t-done` · `--t-rej` | 남은 일 · 중단 · 완료 · 반려 (`lib.jsx` TASK) |
| 그래프 | `--node-proj` · `--node-agent` · `--edge` | 프로젝트 노드 · 서브에이전트 노드 · 선 |
| 그 밖 | `--warn` · `--del` · `--shadow` · `--shine` | 컨텍스트 80% 넘은 막대 · 지우기 단추 올림 · 떠 있는 칸 그림자 · 작업 중 카드의 빛 띠 |
| 글자 크기 | `--fs-xs` 12 · `--fs-s` 13 · `--fs-m` 15 · `--fs-l` 18 · `--fs-xl` 20 | 꼬리표·보조 · 표·설명 · 본문·카드 제목 · 숫자 타일·패널 제목 · 설정 톱니 |
| 간격 | `--sp-1` 2 · `--sp-2` 4 · `--sp-3` 6 · `--sp-4` 8 · `--sp-5` 10 · `--sp-6` 12 · `--sp-7` 16 · `--sp-8` 20 | 안쪽 여백·사이 간격·바깥 여백 |
| 모서리 | `--r-xs` 2 · `--r-s` 4 · `--r-m` 8 · `--r-full` | 네모 점 · 막대·메뉴 줄 · 카드·단추·입력칸 · 꼬리표·동그란 점 |

필요한 색이 없으면 새로 만들기 전에 위에서 뜻이 같은 것을 찾는다. 정말 없으면 `:root` 에 밝은 화면 값을, Figma 변수에 어두운 화면 값을 더하고 [토큰 보내기]로 받는다.

## 부품 쓰임

| 부품 | 쓰는 법 |
| --- | --- |
| `Button` | 기본은 작은 단추. variant 없음 = 보통, `primary` = 그 칸에서 가장 중요한 동작 하나, `danger` = 지우기·종료(누르기 전에 confirm). 못 누르게 할 때는 `disabled` |
| `Pill` | 꼬리표. tone 은 뜻에 맞춘다 — 작업: 남은 일 `info` · 중단 `warning` · 완료 `success` · 반려 neutral / 세션: 작업 중 `success` · 입력 대기 `warning` · 실패 `danger`. 색만으로 알리지 않게 아이콘이 붙는다 |
| `Card` | 화면의 큰 칸. 제목 줄은 `<div className="sh"><h2>제목</h2>…</div>` |
| `Collapsible` | 접는 칸. 내용을 들여 쓰려면 `className="sec"` |
| `Table` | 넓으면 안에서 가로로 미는 표. 표가 여럿이라 줄을 맞춰야 하면 `tableLayout: 'fixed'` 와 th 폭 |
| `lib.jsx` | `Tip`(물음표 설명 상자) · `Dot`(색 점, `sq` 면 네모) · 작업 목록은 언제나 `TaskList`/`TaskRow` |

## 하지 않는 것

- 색 값(`#…`, `rgb()`, `hsl()`)을 화면 코드나 style.css 규칙에 쓰지 않는다. 이름표 `var(--…)` 만 쓴다.
- 글자 크기·간격·모서리를 숫자로 쓰지 않는다(`font-size:13px`, `padding:8px`). 폭·높이·위치·선 굵기는 숫자로 써도 된다.
- `button.sm`·`.pill`·`.card`·`.tbl`·`<details>` 를 직접 쓰지 않는다. ui.jsx 부품을 쓴다.
- 그래프(cytoscape)는 CSS 이름표를 읽지 못하므로 `tok('var(--이름)')` 으로 넘긴다.

## 점검

`npm run build` 가 막는다(vite.config.js 의 ui-check): 부품 대신 쓴 class, 화면 코드·style.css 의 색 값, 숫자 글자 크기. 간격 숫자는 위치·크기와 가르기 어려워 사람이 본다. 새 부품이나 모양을 더하면 `#ui` 부품 모음에도 넣는다.
