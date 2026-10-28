import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { createRoot } from 'react-dom/client'
import './style.css'
import Home from './Home'
import Mcp from './Mcp'
import { History, Issues, Pushes, Settings } from './Pages'
import Para from './Para'
import SidePanel from './SidePanel'
import { App as Ctx, grp, isDead, post, tilde, useApp, usePoll } from './lib'

const PAGES = { home: ['현황', Home], para: ['PARA', Para], history: ['세션 기록', History], pushes: ['Push 기록', Pushes], issues: ['이슈·PR', Issues], mcp: ['MCP 서버', Mcp], settings: ['설정', Settings] }
const page = () => PAGES[location.hash.slice(1)] ? location.hash.slice(1) : 'home'
// 상단 메뉴: 현황은 로고로 간다. 기록 페이지는 History 아래로 묶는다 (설정은 오른쪽 ⚙)
const NAV = ['para', ['History', ['history', 'pushes']], 'issues', 'mcp']
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

// 버전: 화면을 띄운 리더의 버전. 더 새 버전이 설치돼 있으면 알리고, 리더가 바뀌어 버전이 달라지면 새 화면으로 새로 고친다
const newer = (a, b) => { const x = (a || '').split('.').map(Number), y = (b || '').split('.').map(Number); for (let i = 0; i < 3; i++) if ((x[i] || 0) !== (y[i] || 0)) return (x[i] || 0) > (y[i] || 0); return false }
// [새 버전으로 바꾸기]: 서버가 설치된 새 버전을 세션과 따로 띄우고 자리를 넘긴다. 새 버전이 뜨면 새로 고치고, 세션마다 할 일을 알린다
const RELOAD = '열린 세션에서 /reload-plugins 를 하면 에이전트 도구도 새 버전이 됩니다'
function Version() {
  const { setMsg } = useApp()
  const V = usePoll('/api/version', 10000)
  const first = useRef(null), [busy, setBusy] = useState(false)
  useEffect(() => {
    if (!V?.version) return
    if (!first.current) first.current = V.version
    else if (first.current !== V.version) location.reload()
  }, [V])
  useEffect(() => {  // 바꾼 뒤 새로 고친 화면에서 한 번만
    try { const v = sessionStorage.getItem('upgraded'); if (v) { sessionStorage.removeItem('upgraded'); setMsg(`v${v} 로 바꿨습니다 · ${RELOAD}`) } } catch { /* 저장소 막힘 */ }
  }, [])
  const up = async () => {
    setBusy(true)
    const r = await post('/api/upgrade', {})
    if (r.error) { setBusy(false); return setMsg(r.error) }
    try { sessionStorage.setItem('upgraded', r.version) } catch { /* 저장소 막힘 */ }
    for (let i = 0; i < 30; i++) {  // 새 서버가 포트를 잡을 때까지 (보통 1~2초)
      await new Promise(f => setTimeout(f, 500))
      try { if ((await (await fetch('/api/version')).json()).version === r.version) return location.reload() } catch { /* 바뀌는 중 */ }
    }
    setBusy(false)
    setMsg('새 버전이 뜨지 않았습니다. Claude Code 세션을 새로 열어 보세요')
  }
  if (!V?.version) return null
  return newer(V.installed, V.version)
    ? <><span className="pill" style={{ color: 'var(--t-todo)' }} title="새 버전이 설치됐지만 지금 화면은 옛 버전이 띄우고 있습니다">v{V.version} → v{V.installed} 설치됨</span>
      <button className="sm pri" disabled={busy} onClick={up} title={'대시보드를 바로 새 버전으로 바꿉니다. 바꾼 대시보드는 세션을 모두 꺼도 켜져 있습니다. ' + RELOAD}>
        {busy ? '바꾸는 중…' : '새 버전으로 바꾸기'}</button></>
    : <span className="meta" title="이 화면을 띄운 플러그인 버전">v{V.version}</span>
}

// 서버가 없을 때: 리더 세션이 모두 꺼졌거나 옛 버전(0.5.15 이하)만 남았다. 리더가 바뀌는 1~2초는 띄우지 않는다
function useDown() {
  const [down, setDown] = useState(false)
  useEffect(() => {
    let t
    const off = () => { t = setTimeout(() => setDown(true), 3000) }, on = () => { clearTimeout(t); setDown(false) }
    addEventListener('fleet-down', off); addEventListener('fleet-up', on)
    return () => { clearTimeout(t); removeEventListener('fleet-down', off); removeEventListener('fleet-up', on) }
  }, [])
  return down
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

// 드롭다운 메뉴: 누르면 펼치고, 아무 데나 다시 누르면(항목 포함) 닫는다
function NavMenu({ label, keys, pg }) {
  const [open, setOpen] = useState(false)
  useEffect(() => {
    if (!open) return
    const close = () => setOpen(false), t = setTimeout(() => addEventListener('click', close))  // 여는 클릭은 건너뛴다
    return () => { clearTimeout(t); removeEventListener('click', close) }
  }, [open])
  return <div className="dd">
    <a className={keys.includes(pg) ? 'on' : ''} role="button" aria-expanded={open} onClick={() => setOpen(!open)}>{label} ▾</a>
    {open && <div className="ddm">{keys.map(k => <a key={k} href={'#' + k} className={pg === k ? 'on' : ''}>{PAGES[k][0]}</a>)}</div>}</div>
}

function App() {
  const [pg, setPg] = useState(page)
  const [side, setSide] = useState(null)  // 오른쪽 패널에 열린 것 — 같은 것을 다시 누르면 닫는다
  const [msg, setMsg] = useState('')
  const [ver, setVer] = useState(0)  // 작업·제목을 고치면 올려서 목록을 다시 받는다
  const P = usePoll('/api/projects', 60000, [ver])  // 작업 줄의 프로젝트 고르기 칸 (fleet/para.py names)
  const [, setNoti] = useState(0)
  const raw = usePoll('/api/graph', 5000)
  const G = useMemo(() => raw ? live(raw) : { nodes: [], edges: [], home: '' }, [raw])
  const bump = useCallback(() => setVer(v => v + 1), [])
  // keep: 이미 열려 있어도 닫지 않는다 (알림)
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
  const down = useDown()
  const Page = PAGES[pg][1]
  return <Ctx.Provider value={{ G, side, openSide, setMsg, stopSession, ver, bump, P }}>
    <header><h1><a href="#home" title="현황">Hudson <span>Fleet</span></a></h1>
      <nav>{NAV.map(n => typeof n === 'string' ? <a key={n} href={'#' + n} className={pg === n ? 'on' : ''}>{PAGES[n][0]}</a>
        : <NavMenu key={n[0]} label={n[0]} keys={n[1]} pg={pg} />)}</nav>
      <div className="hr"><span className="meta hmsg" title={msg}>{msg}</span>
      <button className="sm" disabled={notiOn() || !window.Notification} title="세션이 입력 대기로 바뀌거나 끝나면 알립니다"
        onClick={() => Notification.requestPermission().then(() => setNoti(n => n + 1))}>{notiOn() ? '알림 켜짐' : '알림 켜기'}</button>
      <Usage />
      <Version />
      <a href="#settings" className={'gear' + (pg === 'settings' ? ' on' : '')} title="설정" aria-label="설정">⚙</a></div></header>
    {down && <div className="down">대시보드 서버에 닿지 않습니다. 대시보드는 Claude Code 세션(MCP 서버)이 띄우므로, 세션이 모두 꺼졌거나 옛 버전 세션만 남았을 수 있습니다. 세션을 하나 열면 1~2초 안에 다시 이어집니다.</div>}
    <main className={side ? '' : 'noside'}>
      <div id="dash"><Page /></div>
      <div id="side"><Handle /><button className="sm" id="sideX" title="패널 닫기" onClick={() => setSide(null)}>✕</button>
        <div id="sidec">{side && <SidePanel />}</div></div>
    </main>
  </Ctx.Provider>
}

createRoot(document.getElementById('root')).render(<App />)
