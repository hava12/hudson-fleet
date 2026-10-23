import { createContext, useContext, useEffect, useState } from 'react'

export const when = ts => ts ? new Date(ts).toLocaleString('ko-KR', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : ''
export const dark = matchMedia('(prefers-color-scheme: dark)').matches
// 상태값(interactive 의 status, background 의 state) → 화면 분류
const GROUP = { busy: 'work', running: 'work', blocked: 'wait', waiting: 'wait', needs_input: 'wait', idle: 'idle',
  stopped: 'done', completed: 'done', done: 'done', failed: 'fail' }
export const GINFO = { work: ['작업 중', '#16a34a'], wait: ['입력 대기', '#d97706'], idle: ['쉬는 중', '#64748b'], done: ['끝남', '#a8a29e'], fail: ['실패', '#dc2626'] }
export const grp = st => GROUP[st] || 'idle', isDead = st => ['done', 'fail'].includes(grp(st))  // 끝난 세션: 흐리게, 종료 메뉴 숨김
export const FILL = { project: dark ? '#334155' : '#475569', agent: '#7c3aed' }
// 작업 상태 색: 남은 일은 노랑으로 눈에 띄게, 중단은 주황으로 남은 일과 구분 (style.css 의 --t-*)
export const TASK = { done: ['완료', 'var(--t-done)'], stopped: ['중단', 'var(--t-stop)'], todo: ['남은 일', 'var(--t-todo)'], rejected: ['반려', 'var(--t-rej)'] }
export const TAGS = ['개발', '디자인', '기획', '테스트', '문서', '디버그', '데이터', '운영', '기타']  // fleet/tasks.py TAGS 와 같은 순서
export const LIVE = ['work', 'wait', 'idle']  // 메인 화면은 살아 있는 세션만 — 끝남·실패는 게시글에서만
export const fmtTok = n => n >= 1e6 ? (n / 1e6).toFixed(1) + 'M' : n >= 1e3 ? Math.round(n / 1e3) + 'K' : String(n || 0)
export const modelName = m => m.replace(/^claude-/, '').replace(/-(\d+)-(\d+).*$/, ' $1.$2').replace(/^./, c => c.toUpperCase())  // claude-opus-5-5 → Opus 5.5

// 401 이면 'logout' 이벤트 — main.jsx 의 Gate 가 받아 로그인 창으로 돌아간다 (서버를 다시 켜면 로그인이 풀린다)
const json = r => { if (r.status === 401) dispatchEvent(new Event('logout')); return r.json() }
export const get = async p => json(await fetch(p))
export const post = async (p, b) => json(await fetch(p, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(b) }))

// ms 마다 다시 받는다. 실패하면 3초 뒤 다시. deps 가 바뀌면 바로 다시 (ms 가 없으면 deps 가 바뀔 때만)
export function usePoll(url, ms, deps = []) {
  const [data, setData] = useState(null)
  useEffect(() => {
    let t, live = true
    const run = () => get(url).then(d => { if (live) { setData(d); if (ms) t = setTimeout(run, ms) } },
      () => { if (live) t = setTimeout(run, 3000) })
    run()
    return () => { live = false; clearTimeout(t) }
  }, [url, ms, ...deps])
  return data
}

// 앱 전체가 함께 쓰는 것: 그래프(G), 메시지, 오른쪽 패널, 다시 받기(ver)
export const App = createContext(null)
export const useApp = () => useContext(App)
export const tilde = (p, home) => p && home && p.startsWith(home) ? '~' + p.slice(home.length) : p

export const Dot = ({ c, sq }) => <i className="dot" style={{ background: c, borderRadius: sq ? 2 : undefined }} />
export const Pill = ({ st }) => <span className="pill"><Dot c={GINFO[grp(st)][1]} />{GINFO[grp(st)][0]}</span>
export const TaskSum = ({ ts }) => ts.length
  ? Object.entries(TASK).filter(([k]) => ts.some(t => t.status === k))
    .map(([k, [l, c]], i) => <span key={k}>{i ? ' · ' : ''}<span style={{ color: c }}>{l} {ts.filter(t => t.status === k).length}</span></span>)
  : <span className="meta">없음</span>
