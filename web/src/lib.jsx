import { createContext, useContext, useEffect, useState } from 'react'

export const when = ts => ts ? new Date(ts).toLocaleString('ko-KR', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : ''
// 색·글자 크기·모서리는 style.css 맨 위 이름표(:root) 한 곳에서 정한다. 화면 코드는 'var(--이름)' 만 쓴다.
// 그래프(cytoscape)는 CSS 이름표를 못 읽으므로 그릴 때 실제 값으로 바꿔 준다
export const tok = v => v.startsWith('var(') ? getComputedStyle(document.documentElement).getPropertyValue(v.slice(4, -1)).trim() : v
// 상태값(interactive 의 status, background 의 state) → 화면 분류
const GROUP = { busy: 'work', running: 'work', blocked: 'wait', waiting: 'wait', needs_input: 'wait', idle: 'idle',
  stopped: 'done', completed: 'done', done: 'done', failed: 'fail' }
export const GINFO = { work: ['작업 중', 'var(--ok)'], wait: ['입력 대기', 'var(--wait)'], idle: ['쉬는 중', 'var(--idle)'], done: ['끝남', 'var(--off)'], fail: ['실패', 'var(--bad)'] }
export const grp = st => GROUP[st] || 'idle', isDead = st => ['done', 'fail'].includes(grp(st))  // 끝난 세션: 흐리게, 종료 메뉴 숨김
export const FILL = { project: 'var(--node-proj)', agent: 'var(--node-agent)' }
// 작업 상태 색: 남은 일은 노랑으로 눈에 띄게, 중단은 주황으로 남은 일과 구분 (style.css 의 --t-*)
export const TASK = { done: ['완료', 'var(--t-done)'], stopped: ['중단', 'var(--t-stop)'], todo: ['남은 일', 'var(--t-todo)'], rejected: ['반려', 'var(--t-rej)'] }
export const TAGS = ['개발', '디자인', '기획', '테스트', '문서', '디버그', '데이터', '운영', '기타']  // fleet/tasks.py TAGS 와 같은 순서
export const LIVE = ['work', 'wait', 'idle']  // 메인 화면은 살아 있는 세션만 — 끝남·실패는 게시글에서만
export const fmtTok = n => n >= 1e6 ? (n / 1e6).toFixed(1) + 'M' : n >= 1e3 ? Math.round(n / 1e3) + 'K' : String(n || 0)
export const modelName = m => m.replace(/^claude-/, '').replace(/-(\d+)-(\d+).*$/, ' $1.$2').replace(/^./, c => c.toUpperCase())  // claude-opus-5-5 → Opus 5.5

// 서버에 닿는지: 실패하면 'fleet-down', 다시 닿으면 'fleet-up' 이벤트 — 리더가 없거나 바뀌는 중이면 main.jsx 가 안내를 띄운다
let down = false
const reach = ok => { if (down === ok) { down = !ok; dispatchEvent(new Event(ok ? 'fleet-up' : 'fleet-down')) } }
export const get = async p => {
  try { const r = await fetch(p); reach(true); return r.json() } catch (e) { reach(false); throw e }
}
// 서버에 닿지 않아도 {error} 로 돌려준다 — 부르는 쪽이 오류 문장을 띄우고 버튼('요약 중…' 등)을 되돌리게
export const post = (p, b) => fetch(p, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(b) })
  .then(r => r.json()).catch(() => ({ error: '서버에 닿지 않습니다' }))

// ms 마다 다시 받는다. 실패하면 1초 뒤 다시 (리더가 바뀌는 1~2초 동안은 마지막 값을 그대로 보여 준다). deps 가 바뀌면 바로 다시 (ms 가 없으면 deps 가 바뀔 때만)
// 주소가 바뀌면 새 값이 올 때까지 null — 앞 주소의 값(다른 세션의 push 등)을 잠깐 보여 주지 않는다. 받은 값이 그대로면 다시 그리지 않는다
export function usePoll(url, ms, deps = []) {
  const [[at, data], setData] = useState([null, null])
  useEffect(() => {
    let t, live = true
    const run = () => get(url).then(d => {
      if (!live) return
      setData(p => p[0] === url && JSON.stringify(p[1]) === JSON.stringify(d) ? p : [url, d])
      if (ms) t = setTimeout(run, ms)
    },
      () => { if (live) t = setTimeout(run, 1000) })
    run()
    return () => { live = false; clearTimeout(t) }
  }, [url, ms, ...deps])
  return at === url ? data : null
}

// 누르는 것(링크 모양 a·span·div)을 키보드로도: Tab 으로 가서 Enter·Space 로 누른다
export const press = f => ({ role: 'button', tabIndex: 0, onClick: f,
  onKeyDown: e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); f(e) } } })

// 앱 전체가 함께 쓰는 것: 그래프(G), 메시지, 오른쪽 패널, 다시 받기(ver), 프로젝트 이름(P)
export const App = createContext(null)
export const useApp = () => useContext(App)
export const tilde = (p, home) => p && home && p.startsWith(home) ? '~' + p.slice(home.length) : p

// 물음표에 마우스를 올리거나(휴대폰은 누르면) 설명 상자가 뜬다
export const Tip = ({ children }) => <span className="tip" tabIndex={0} aria-label="설명 보기">?<span className="tipbox" role="tooltip">{children}</span></span>
export const Dot = ({ c, sq }) => <i className="dot" style={{ background: c, borderRadius: sq ? 'var(--r-xs)' : undefined }} />
export const Pill = ({ st }) => <span className="pill"><Dot c={GINFO[grp(st)][1]} />{GINFO[grp(st)][0]}</span>
export const TaskSum = ({ ts }) => ts.length
  ? Object.entries(TASK).filter(([k]) => ts.some(t => t.status === k))
    .map(([k, [l, c]], i) => <span key={k}>{i ? ' · ' : ''}<span style={{ color: c }}>{l} {ts.filter(t => t.status === k).length}</span></span>)
  : <span className="meta">없음</span>
