import { useEffect, useRef, useState } from 'react'
import { fitBox, textW, useCy } from './Graph'
import { Dot, FILL, dark, get, useApp } from './lib'

export const MST = { ok: ['연결됨', '#16a34a'], auth: ['인증 필요', '#d97706'], fail: ['연결 실패', '#dc2626'], pending: ['승인 대기', '#64748b'] }
const STYLE = [
  { selector: 'node', style: { shape: 'round-rectangle', label: 'data(label)', width: 'data(w)', height: 28, 'font-size': 12, color: '#fff', 'text-valign': 'center', 'text-halign': 'center',
    'background-color': e => e.data('kind') === 'root' ? '#2563eb' : e.data('kind') === 'group' ? FILL.project : MST[e.data('ok')][1] } },
  { selector: 'node[kind="server"]', style: { cursor: 'pointer' } },
  { selector: 'edge', style: { width: 1.5, 'line-color': dark ? '#475569' : '#cbd5e1', 'curve-style': 'taxi', 'taxi-direction': 'rightward', 'taxi-turn': '50%' } },
  { selector: ':selected', style: { 'overlay-color': '#2563eb', 'overlay-opacity': 0.2, 'overlay-padding': 4 } }]

// MCP 서버: claude mcp list 결과를 출처별 그래프로
export default function Mcp() {
  const { side, openSide } = useApp()
  const ref = useRef()
  const cy = useCy(ref, { style: STYLE }, 640)
  const [ms, setMs] = useState(null)
  const [busy, setBusy] = useState(true)
  const load = refresh => { setBusy(true); get('/api/mcp' + (refresh ? '?refresh=1' : '')).then(setMs).finally(() => setBusy(false)) }
  useEffect(() => load(false), [])

  useEffect(() => {
    if (!cy || !ms) return
    const groups = [...new Set(ms.map(m => m.group))]
    const els = [{ data: { id: 'root', label: 'Claude Code', kind: 'root' } },
      ...groups.flatMap(g => [{ data: { id: 'g:' + g, label: `${g} (${ms.filter(m => m.group === g).length})`, kind: 'group' } }, { data: { id: 'e:' + g, source: 'root', target: 'g:' + g } }]),
      ...ms.flatMap((m, i) => [{ data: { id: 'm' + i, label: m.name, kind: 'server', ok: m.ok, m } }, { data: { id: 'em' + i, source: 'g:' + m.group, target: 'm' + i } }])]
    els.forEach(e => { if (e.data.label) e.data.w = textW(e.data.label) })
    cy.elements().remove()
    cy.add(els)
    cy.layout({ name: 'dagre', rankDir: 'LR', nodeSep: 8, rankSep: 80 }).run()
    fitBox(cy, 640)
  }, [cy, ms])

  useEffect(() => {
    if (!cy) return
    cy.on('tap', 'node[kind="server"]', e => openSide({ type: 'mcp', id: e.target.id(), m: e.target.data('m') }))
  }, [cy])
  useEffect(() => {
    if (!cy) return
    cy.$(':selected').unselect()
    if (side?.type === 'mcp') cy.getElementById(side.id).select()
  }, [cy, side])

  const cnt = {}
  ms?.forEach(m => cnt[m.ok] = (cnt[m.ok] || 0) + 1)
  return <div className="pg"><section className="card">
    <div className="sh"><h2>연결된 MCP 서버</h2>
      <div className="legend">{Object.values(MST).map(([l, c]) => <span key={l}><Dot c={c} />{l}</span>)}</div>
      <button className="sm" disabled={busy} onClick={() => load(true)}>다시 검사</button></div>
    <div className="gwrap"><div id="mcy" ref={ref} />
      {busy && <div className="loading">연결 상태 검사 중<span className="dots" />&nbsp;<span style={{ fontSize: 12 }}>(10초 정도 걸립니다)</span></div>}</div>
    <div className="stats">{Object.entries(MST).map(([k, [l, c]]) => <div key={k} className="stat"><b style={{ color: cnt[k] ? c : 'var(--mute)' }}>{cnt[k] || 0}</b><span><Dot c={c} />{l}</span></div>)}</div>
    <p className="meta" style={{ margin: '10px 0 0' }}>홈 폴더 기준 목록입니다. 프로젝트 폴더에만 설정한 서버(.mcp.json)는 빠질 수 있습니다.</p>
  </section></div>
}
