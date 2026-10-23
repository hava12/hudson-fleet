import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { createRoot } from 'react-dom/client'
import './style.css'
import Home from './Home'
import Mcp from './Mcp'
import { History, Pushes, Settings } from './Pages'
import SidePanel from './SidePanel'
import { App as Ctx, grp, isDead, post, tilde, usePoll } from './lib'

const PAGES = { home: ['현황', Home], history: ['세션 기록', History], pushes: ['Push 기록', Pushes], mcp: ['MCP 서버', Mcp], settings: ['설정', Settings] }
const page = () => PAGES[location.hash.slice(1)] ? location.hash.slice(1) : 'home'
const sideKey = k => k && k.type + ':' + (k.sid || k.id) + (k.agent || '')

// 끝난 세션과 그 서브에이전트, 끝난 서브에이전트, 살아 있는 세션이 없는 프로젝트는 빼고 그린다
function live(g) {
  const gone = new Set(g.nodes.filter(n => n.type === 'session' && isDead(n.status)).map(n => n.sessionId))
  let nodes = g.nodes.filter(n => !gone.has(n.type === 'session' ? n.sessionId : n.sid) && !(n.type === 'agent' && isDead(n.status)))
  const ids = new Set(nodes.map(n => n.id)), edges = g.edges.filter(e => ids.has(e.source) && ids.has(e.target))
  const used = new Set(edges.map(e => e.source))
  nodes = nodes.filter(n => n.type !== 'project' || used.has(n.id))
  return { ...g, nodes, edges }
}

// ── 사용량: /usage 의 5시간(Current session)·1주일(Current week) 한도, 헤더 오른쪽에 작게 ──
const barColor = p => p >= 80 ? '#dc2626' : p >= 50 ? '#d97706' : '#16a34a'
function Usage() {
  const U = usePoll('/api/usage', 60000)
  if (!U) return <div className="hu"><span>사용량<span className="dots" /></span></div>
  return <div className="hu">{[['5시간', 'Current session'], ['1주일', 'Current week (all models)']].map(([l, k]) => {
    const v = U.limits.find(x => x.label === k)
    if (!v) return <span key={l}>{l} <b>—</b></span>
    const tip = `${l} 한도 · 남음 ${Math.max(100 - v.pct, 0)}% · ${v.resets} 초기화`
    return <span key={l} title={tip} style={{ display: 'contents' }}><span>{l}</span>
      <div className="bar"><i style={{ width: Math.min(v.pct, 100) + '%', background: barColor(v.pct) }} /></div><b>{v.pct}%</b></span>
  })}</div>
}

// 알림: 세션이 입력 대기로 바뀌거나 사라지면(끝남) 브라우저 알림
const notiOn = () => window.Notification && Notification.permission === 'granted'
function useNotify(G, openSide) {
  const prev = useRef(null)
  useEffect(() => {
    if (!G.nodes.length && !prev.current) return
    const now = new Map(G.nodes.filter(n => n.type === 'session').map(n => [n.sessionId, n]))
    if (prev.current && notiOn()) for (const [sid, p] of prev.current) {
      const n = now.get(sid)
      const msg = !n ? '끝났습니다' : grp(n.status) === 'wait' && grp(p.status) !== 'wait' ? '입력을 기다립니다' : ''
      if (!msg) continue
      const nt = new Notification(`${p.label} ${msg}`, { body: tilde(p.cwd, G.home) || '', tag: sid })
      nt.onclick = () => { window.focus(); if (n) openSide({ type: 'session', sid }, true); nt.close() }
    }
    prev.current = now
  }, [G])
}

// 패널 폭: 손잡이를 끌어 300px ~ 화면 80% 사이로. 이 브라우저에만 기억한다
const sideW = w => w ? document.documentElement.style.setProperty('--sidew', w + 'px') : document.documentElement.style.removeProperty('--sidew')
try { sideW(+localStorage.getItem('sidew') || 0) } catch { /* 저장소 막힘 */ }
function Handle() {
  const [on, setOn] = useState(false), w = useRef(0)
  const save = v => { try { v ? localStorage.setItem('sidew', v) : localStorage.removeItem('sidew') } catch { /* 저장소 막힘 */ } }
  return <div id="sideH" className={on ? 'on' : ''} title="끌어서 폭 조절 · 두 번 누르면 기본 폭"
    onPointerDown={e => { e.currentTarget.setPointerCapture(e.pointerId); setOn(true); document.body.style.userSelect = 'none' }}
    onPointerMove={e => { if (!e.currentTarget.hasPointerCapture(e.pointerId)) return; w.current = Math.round(Math.min(Math.max(innerWidth - e.clientX, 300), innerWidth * .8)); sideW(w.current) }}
    onPointerUp={() => { setOn(false); document.body.style.userSelect = ''; save(w.current) }}
    onDoubleClick={() => { w.current = 0; sideW(0); save(0) }} />
}

function App() {
  const [pg, setPg] = useState(page)
  const [side, setSide] = useState(null)  // 오른쪽 패널에 열린 것 — 같은 것을 다시 누르면 닫는다
  const [msg, setMsg] = useState('')
  const [ver, setVer] = useState(0)  // 작업·제목을 고치면 올려서 목록을 다시 받는다
  const [, setNoti] = useState(0)
  const raw = usePoll('/api/graph', 5000)
  const G = useMemo(() => raw ? live(raw) : { nodes: [], edges: [], home: '' }, [raw])
  const bump = useCallback(() => setVer(v => v + 1), [])
  // keep: 이미 열려 있어도 닫지 않는다 (더보기·알림)
  const openSide = useCallback((k, keep) => {
    setSide(cur => !keep && sideKey(cur) === sideKey(k) ? null : k)
    if (innerWidth <= 900) requestAnimationFrame(() => document.getElementById('side')?.scrollIntoView({ behavior: 'smooth' }))
  }, [])
  const stopSession = async d => {
    if (!d || !confirm(`"${d.label}" 세션을 종료할까요?\n진행 중인 작업이 중단됩니다.`)) return
    const r = await post('/api/stop', { sid: d.sessionId })
    setMsg(r.text || r.error)
  }
  useEffect(() => {
    const f = () => { setPg(page()); setSide(null) }
    addEventListener('hashchange', f)
    return () => removeEventListener('hashchange', f)
  }, [])
  useNotify(G, openSide)
  const Page = PAGES[pg][1]
  return <Ctx.Provider value={{ G, side, openSide, setMsg, stopSession, ver, bump }}>
    <header><h1>Hudson <span>Fleet</span></h1>
      <nav>{Object.entries(PAGES).map(([k, [l]]) => <a key={k} href={'#' + k} className={pg === k ? 'on' : ''}>{l}</a>)}</nav>
      <span className="meta" style={{ marginLeft: 'auto' }}>{msg}</span>
      <button className="sm" disabled={notiOn() || !window.Notification} title="세션이 입력 대기로 바뀌거나 끝나면 알립니다"
        onClick={() => Notification.requestPermission().then(() => setNoti(n => n + 1))}>{notiOn() ? '알림 켜짐' : '알림 켜기'}</button>
      <Usage /></header>
    <main className={side ? '' : 'noside'}>
      <div id="dash"><Page /></div>
      <div id="side"><Handle /><button className="sm" id="sideX" title="패널 닫기" onClick={() => setSide(null)}>✕</button>
        <div id="sidec">{side && <SidePanel />}</div></div>
    </main>
  </Ctx.Provider>
}

createRoot(document.getElementById('root')).render(<App />)
