import { useEffect, useReducer, useRef, useState } from 'react'
import { fitBox, textW, useCy } from './Graph'
import { TaskList } from './TaskList'
import { Dot, FILL, GINFO, LIVE, dark, fmtTok, grp, modelName, post, tilde, useApp, usePoll } from './lib'

// 세션 노드는 자리만 카드 크기로 잡고, 그 위에 카드(SessionCard)를 겹친다 (노드 이름표로는 줄마다 모양을 줄 수 없다)
const NW = 300, NH = 148  // NH 는 .ncard 글자 크기·줄 간격(13px × 1.6, 제목 + 4줄)에 맞춘다. 글자를 키우면 같이 키운다
const STYLE = [
  { selector: 'node', style: { shape: 'round-rectangle', label: 'data(short)', width: 'data(w)', height: 'data(h)', 'font-size': 12, color: '#fff', 'text-wrap': 'wrap', 'line-height': 1.5,
    'text-valign': 'center', 'text-halign': 'center', 'background-color': e => e.data('type') === 'session' ? GINFO[grp(e.data('status'))][1] : FILL[e.data('type')], 'border-width': 0 } },
  { selector: 'node[type="project"]', style: { 'font-weight': 'bold' } },
  { selector: 'node[?big]', style: { label: '', 'background-opacity': 0 } },
  { selector: '.faded', style: { opacity: 0.12 } },
  { selector: 'edge', style: { width: 1.5, 'line-color': dark ? '#57534e' : '#d6d3d1', 'target-arrow-color': dark ? '#57534e' : '#d6d3d1',
    'target-arrow-shape': 'triangle', 'arrow-scale': 0.8, 'curve-style': 'taxi', 'taxi-direction': 'rightward', 'taxi-turn': '50%' } },
  { selector: ':selected', style: { 'overlay-color': '#c2410c', 'overlay-opacity': 0.2, 'overlay-padding': 4 } },
  { selector: 'node[?big]', style: { 'overlay-opacity': 0 } },
  { selector: 'edge.flow', style: { 'line-style': 'dashed', 'line-dash-pattern': [6, 4], 'line-color': GINFO.work[1], 'target-arrow-color': GINFO.work[1] } }]

function SessionCard({ e, n, u = {}, on, home }) {
  const col = GINFO[grp(n.status)][1]
  const b = e.renderedBoundingBox({ includeLabels: false, includeOverlays: false })
  const r = n.ctx / n.ctxMax
  return (
    <div className={`ncard ${grp(n.status)}${on ? ' on' : ''}${e.hasClass('faded') ? ' faded' : ''}`}
      style={{ '--c': col, left: b.x1, top: b.y1, width: NW, height: NH, transform: `scale(${e.cy().zoom()})` }}>
      <b><Dot c={col} />{n.label}{n.model && <span className="mdl">{modelName(n.model)}{n.effort ? ' · ' + n.effort : ''}</span>}</b>
      <dl>
        <dt>실행 앱</dt><dd>{n.kind === 'background' ? '백그라운드' : n.app || '?'}</dd>
        <dt>실행 위치</dt><dd title={n.cwd}>{tilde(n.cwd, home)}</dd>
        {n.ctx > 0 && <><dt>컨텍스트</dt><dd><span className="bar"><i style={{ width: Math.min(r * 100, 100) + '%', background: r > .8 ? 'var(--warn)' : 'var(--c)' }} /></span>
          {Math.round(r * 100)}% <span className="meta">· {fmtTok(n.ctx)} / {fmtTok(n.ctxMax)}</span></dd></>}
        <dt>5시간 사용량</dt><dd><span className="bar"><i style={{ width: Math.min(u.pct || 0, 100) + '%' }} /></span>
          {u.pct == null ? '?' : u.pct + '%'} <span className="meta">· {fmtTok(u.tokens)} 토큰</span></dd>
      </dl>
    </div>)
}

export default function Home() {
  const { G, side, openSide, stopSession, ver } = useApp()
  const ref = useRef(), sig = useRef('')
  const cy = useCy(ref, { style: STYLE }, 1020)
  const [, redraw] = useReducer(x => x + 1, 0)  // 이동·확대 때 카드 자리만 다시
  const [statF, setStatF] = useState('')  // 숫자 타일로 고른 상태 ('' = 전체)
  const [menu, setMenu] = useState(null)  // 우클릭 메뉴 {x, y, n}
  const U5 = usePoll('/api/usage5h', 60000) || {}
  const TODO = usePoll('/api/todo', 10000, [ver])
  const pick = n => statF === 'agent' ? G.nodes.some(a => a.type === 'agent' && a.sid === n.sessionId) : grp(n.status) === statF

  useEffect(() => {
    if (!cy) return
    cy.on('pan zoom resize position layoutstop', redraw)  // render 는 초당 60번이라 무겁다
    cy.on('tap', 'node', e => {
      const d = e.target.data()
      if (d.type === 'project') return openSide({ type: 'project', id: d.id, label: d.label, n: e.target.outgoers('node').length })
      openSide({ type: 'session', sid: d.type === 'agent' ? d.sid : d.sessionId, agent: d.type === 'agent' ? d.label : null })
    })
    cy.on('cxttap', 'node[type="session"]', e => setMenu({ x: e.originalEvent.clientX, y: e.originalEvent.clientY, n: e.target.data() }))
    cy.on('tap cxttap', e => { if (e.target === cy) setMenu(null) })
    const hide = () => setMenu(null)
    document.addEventListener('click', hide)
    // 작업 중 세션으로 들어가는 선이 오른쪽으로 흐른다. 초당 12번만, 화면에 보이고 흐를 선이 있을 때만
    let dash = 0, t
    if (!matchMedia('(prefers-reduced-motion:reduce)').matches) t = setInterval(() => {
      const f = cy.edges('.flow')
      if (!f.length || document.hidden) return
      dash = (dash - 2) % 20
      f.style('line-dash-offset', dash)
    }, 83)
    return () => { clearInterval(t); document.removeEventListener('click', hide) }
  }, [cy])

  useEffect(() => {  // 구조가 그대로면 데이터만, 바뀌면 다시 배치
    if (!cy) return
    const nodes = G.nodes.map(n => {
      const l = n.label || '', short = l.length > 26 ? l.slice(0, 25) + '…' : l
      return n.type === 'session' ? { ...n, short, w: NW, h: NH, big: 1 } : { ...n, short, w: textW(short), h: 28 }
    })
    const s = nodes.map(n => n.id).sort().join() + '|' + G.edges.length
    if (s === sig.current) nodes.forEach(n => cy.getElementById(n.id).data(n))
    else {
      sig.current = s
      cy.elements().remove()
      cy.add([...nodes.map(d => ({ data: d })), ...G.edges.map(e => ({ data: { id: e.source + '>' + e.target, ...e } }))])
      cy.layout({ name: 'dagre', rankDir: 'LR', nodeSep: 14, rankSep: 60 }).run()
      fitBox(cy, 1020)
    }
    cy.edges().forEach(e => e.toggleClass('flow', e.target().data('type') === 'session' && grp(e.target().data('status')) === 'work'))
    redraw()
  }, [cy, G])

  useEffect(() => {  // 고른 상태의 세션과 그 프로젝트·서브에이전트만 또렷하게
    if (!cy) return
    cy.elements().removeClass('faded')
    if (statF) {
      const on = cy.nodes('[type="session"]').filter(n => pick(n.data()))
      cy.elements().not(on.union(on.successors()).union(on.predecessors())).addClass('faded')
    }
    redraw()
  }, [cy, G, statF])

  useEffect(() => {  // 패널에 열린 세션을 그래프에서도 고른다
    if (!cy) return
    cy.$(':selected').unselect()
    if (side?.type === 'session') cy.getElementById('s:' + side.sid).select()
  }, [cy, side, G])

  const ss = G.nodes.filter(n => n.type === 'session'), cnt = {}
  ss.forEach(n => cnt[grp(n.status)] = (cnt[grp(n.status)] || 0) + 1)
  const live = new Map(ss.map(n => [n.sessionId, n]))
  const todo = (TODO || []).filter(t => !statF || (live.has(t.sid) && pick(live.get(t.sid))))
  const setStat = k => { setStatF(statF === k ? '' : k); if (k !== statF) document.getElementById('tblh').scrollIntoView({ behavior: 'smooth', block: 'center' }) }
  const Tile = ({ k, n, l, c }) => <div className={'stat' + (statF === k ? ' on' : '')} onClick={() => setStat(k)}>
    <b style={{ color: n ? c : 'var(--mute)' }}>{n || 0}</b><span><Dot c={c} />{l}</span></div>

  return <div className="pg">
    <section className="card"><div className="sh"><h2>상태별 노드</h2><div className="legend">
      {LIVE.map(k => <span key={k}><Dot c={GINFO[k][1]} />{GINFO[k][0]}</span>)}
      <span><Dot c={FILL.project} sq />프로젝트</span><span><Dot c={FILL.agent} sq />서브에이전트</span></div></div>
      <div id="cy" ref={ref} onContextMenu={e => e.preventDefault()}>
        {cy && <div id="cards">{cy.nodes('[type="session"]').map(e => <SessionCard key={e.id()} e={e} n={e.data()} u={U5[e.data('sessionId')]} home={G.home}
          on={side?.type === 'session' && side.sid === e.data('sessionId')} />)}</div>}
      </div>
      <div className="stats">
        {LIVE.map(k => <Tile key={k} k={k} n={cnt[k]} l={GINFO[k][0]} c={GINFO[k][1]} />)}
        <Tile k="agent" n={G.nodes.filter(n => n.type === 'agent').length} l="서브에이전트" c={FILL.agent} />
      </div></section>

    <section className="card"><div className="sh"><h2 id="tblh">{statF
      ? <>남은 작업 · {statF === 'agent' ? '서브에이전트가 있는 세션' : GINFO[statF][0]}만 보기 <button className="sm" onClick={() => setStatF('')}>필터 해제</button></>
      : '남은 작업'}</h2></div>
      {!TODO ? <div className="meta">불러오는 중…</div>
        : todo.length ? <TaskList ts={todo} className="todo" edit="status" lead={t => {
          const nm = t.name || t.sid.slice(0, 8)
          return <>{live.has(t.sid) ? <a className="lk" onClick={() => openSide({ type: 'session', sid: t.sid })}>[{nm}]</a>
            : <><span className="meta" title={'끝난 세션 · ' + (t.title || '')}>[{nm}]</span><MoveTo t={t} to={ss} /></>} - </>
        }} />
        : <div className="meta">{statF ? '해당하는 세션의 남은 일이 없습니다' : '남은 일이 없습니다'}</div>}
    </section>

    {menu && <div id="menu" style={{ display: 'block', left: menu.x, top: menu.y }}>
      <div className="danger" onClick={() => stopSession(menu.n)}>세션 종료하기</div></div>}
  </div>
}

// 끝난 세션의 남은 일을 살아 있는 세션으로 옮긴다 — 실행은 그 세션에서 사람이 시킨다
function MoveTo({ t, to }) {
  const { setMsg, bump } = useApp()
  const move = async e => {
    const r = await post('/api/task', { id: t.id, to: e.target.value })
    r.ok ? bump() : setMsg(r.error)
  }
  return <select className="pill tsel" value="" title="살아 있는 세션으로 옮기기" onChange={move}>
    <option value="">세션으로 옮기기</option>
    {to.map(n => <option key={n.sessionId} value={n.sessionId}>{n.label}</option>)}
  </select>
}
