// 공통 부품 — Figma 'hudson-fleet design system' 의 부품과 이름·속성을 맞춘다. 모양은 style.css 규칙(.sm·.pri·.pill·.card·.tbl)이 정한다.
// 화면 코드는 button.sm·.pill·.card·.tbl·<details> 를 직접 쓰지 않고 이 부품을 쓴다 (vite.config.js 의 ui-check 가 빌드 때 막는다)
const cx = (...a) => a.filter(Boolean).join(' ') || undefined
const STYLE = { primary: 'pri', danger: 'danger' }

// Button — Figma Style(Default·Primary·Danger) → variant, Size(Small·Medium) → size. 대시보드 단추는 거의 작아서 기본이 small.
// Figma State 중 Hover·Pressed·Focus 는 CSS 가 맡고, Disabled 는 disabled 속성
export const Button = ({ variant, size = 'small', className, ...p }) =>
  <button className={cx(size === 'small' && 'sm', STYLE[variant], className)} {...p} />

// Pill — 꼬리표. Figma Pill 의 Tone(Neutral·Success·Warning·Danger·Info) → tone (기본 neutral). 바탕을 채우고, 색만으로 알리지 않게
// Success 는 체크, Warning·Danger 는 느낌표 아이콘을 붙인다 (Figma 와 같은 Lucide 모양). 색은 style.css 의 .pill.<tone>
const ALERT = <><circle cx="12" cy="12" r="10" /><path d="M12 8v4M12 16h.01" /></>
const ICON = { success: <path d="M20 6 9 17l-5-5" />, warning: ALERT, danger: ALERT }
export const Pill = ({ tone, className, children, ...p }) =>
  <span className={cx('pill', tone !== 'neutral' && tone, className)} {...p}>
    {ICON[tone] && <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{ICON[tone]}</svg>}
    {children}</span>

// Card — 흰(어두운 화면은 진한) 바탕 칸
export const Card = ({ className, ...p }) => <section className={cx('card', className)} {...p} />

// Collapsible — 접는 칸. Figma Open(Yes·No) → open, Title → summary. summaryProps 는 제목 줄 속성(작업 묶음의 상태 색 등)
export const Collapsible = ({ summary, summaryProps, children, ...p }) =>
  <details {...p}><summary {...summaryProps}>{summary}</summary>{children}</details>

// Table — 넓으면 안에서 가로로 미는 표. 줄(tr)은 그대로 쓴다: 머리 줄은 th(Figma Table Row Type=Header), 본문은 td(Type=Body)
export const Table = ({ style, children }) =>
  <div className="tw"><table className="tbl" style={style}><tbody>{children}</tbody></table></div>

// 부품 모음 (#ui, 메뉴에 없음) — Figma 의 Review 확인 화면처럼 부품의 모든 모양을 한 화면에 늘어놓는다
export function Gallery() {
  const row = { display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', margin: '8px 0' }
  return <div className="pg">
    <Card><div className="sh"><h2>Button</h2><span className="meta">variant × size, disabled</span></div>
      {['small', 'medium'].map(s => <div key={s} style={row}>
        {['default', 'primary', 'danger'].map(v => <Button key={v} variant={v} size={s}>{v} · {s}</Button>)}
        <Button size={s} disabled>disabled</Button></div>)}</Card>
    <Card><div className="sh"><h2>Pill</h2><span className="meta">tone — 작업 상태: 남은 일 info · 중단 warning · 완료 success · 반려 neutral</span></div>
      <div style={row}>{['neutral', 'success', 'warning', 'danger', 'info'].map(t => <Pill key={t} tone={t}>{t}</Pill>)}</div></Card>
    <Card><div className="sh"><h2>Collapsible</h2><span className="meta">open · className="sec" 는 내용을 16px 들여 쓴다</span></div>
      <Collapsible summary="접힌 칸">내용</Collapsible>
      <Collapsible open className="sec" summary={<h4 style={{ display: 'inline-block' }}>펼친 칸 (sec)</h4>}><div className="meta">09:12 → 11:40 · 기록할 작업 3건</div></Collapsible></Card>
    <Card><div className="sh"><h2>Table</h2><span className="meta">th 머리 줄 · td 본문 줄</span></div>
      <Table><tr><th>이름</th><th>상태</th><th>시각</th></tr>
        <tr><td>세션 카드 빛 띠 고치기</td><td><Pill tone="success">완료</Pill></td><td>10/31 14:20</td></tr>
        <tr><td>Figma 변수 내보내기</td><td><Pill tone="info">남은 일</Pill></td><td>11/01 09:05</td></tr></Table></Card>
  </div>
}
