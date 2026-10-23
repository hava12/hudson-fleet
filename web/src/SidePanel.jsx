import { useState } from 'react'
import { TaskList } from './TaskList'
import { Pill, fmtTok, get, post, tilde, useApp, usePoll, when } from './lib'
import { MST } from './Mcp'
import { REASON, Commits, RepoLink } from './Pages'

// 오른쪽 패널: side.type 에 따라 프로젝트 · 세션 · MCP 서버 · 끝난 세션
export default function SidePanel() {
  const { side, G } = useApp()
  if (side.type === 'project') return <><h3>{side.label}</h3><p className="meta">{tilde(side.id.slice(2), G.home)} · 세션 {side.n}개</p></>
  if (side.type === 'mcp') {
    const m = side.m
    return <><h3>{m.name}</h3><div className="meta">{m.group}</div>
      <h4>상태</h4><span className="pill"><i className="dot" style={{ background: MST[m.ok][1] }} />{MST[m.ok][0]}</span>
      <div className="meta" style={{ marginTop: 6 }}>{m.state}</div>
      <h4>연결 대상</h4><pre>{m.target}</pre></>
  }
  if (side.type === 'history') return <HistoryPanel sid={side.sid} />
  return <SessionPanel key={side.sid + (side.agent || '')} sid={side.sid} agent={side.agent} />
}

// 제목 바꾸기 — 대시보드 DB 에만. 비우면 원래 제목으로
function TitleBtn({ sid, title }) {
  const { setMsg, bump } = useApp()
  const go = async () => {
    const t = prompt('대시보드에서 쓸 제목 (비우면 원래 제목으로)', title || '')
    if (t === null) return
    const r = await post('/api/title', { sid, title: t })
    r.ok ? bump() : setMsg(r.error)
  }
  return <button className="sm" title="대시보드에서만 쓰는 제목으로 바꿉니다" onClick={go}>제목 바꾸기</button>
}

// 그 세션이 한 push 만. push 안 한 커밋은 대화 기록에 push 결과가 없어 여기 안 나온다
function SessionPushes({ sid }) {
  const ps = usePoll('/api/pushes?sid=' + encodeURIComponent(sid))
  return <details open><summary><h4 style={{ display: 'inline-block' }}>Push{ps ? ` · ${ps.length}건` : ''}</h4></summary>
    {!ps ? <div className="meta">불러오는 중…</div> : ps.length ? ps.map(p => <details key={p.id} className="push">{/* 한 건씩 접어 두고 누르면 커밋 목록 */}
      <summary className="meta">{when(p.ts)} · <RepoLink r={p.remote} /> {p.ref} · 커밋 {p.commits.length}개</summary>
      <div className="pcommits"><Commits p={p} /></div></details>)
      : <div className="meta">이 세션에서 push 한 기록이 없습니다</div>}
  </details>
}

let sumOpen = true, taskOpen = true  // 세션을 바꿔 열어도 접힘 상태를 이어 간다
function SessionPanel({ sid, agent }) {
  const { G, ver, stopSession, setMsg, bump } = useApp()
  const r = usePoll('/api/session?sid=' + encodeURIComponent(sid), 0, [ver])
  const [log, setLog] = useState(null)
  const [ai, setAi] = useState({ busy: false, err: '', label: '' })
  const s = G.nodes.find(n => n.sessionId === sid)
  if (!s) return null
  const head = <h3>{agent ? '🔷 ' + agent : s.label}</h3>
  if (!r) return <>{head}<div className="meta">불러오는 중…</div></>
  const ov = r.overview || {}, proc = r.proc || [], ts = r.tasks || []
  const summarize = async () => {
    setAi({ busy: true })
    const x = await post('/api/summary', { sid })
    setAi({ err: x.error || '', label: x.cached ? '정리됨 (저장본)' : '다시 정리' })
    if (x.error) setMsg(x.error)
    bump()
  }
  return <>{head}
    <div className="meta"><Pill st={s.status} /> {s.kind === 'background' ? '백그라운드' : s.app || '?'} · {when(s.startedAt)} 시작 · {tilde(s.cwd, G.home)}</div>
    <div style={{ display: 'flex', gap: 6, marginTop: 6 }}>
      {s.kind === 'background' && <button className="sm" onClick={async () => { setLog('불러오는 중…'); setLog((await get('/api/logs?id=' + encodeURIComponent(s.bgId))).text) }}>로그</button>}
      <button className="sm danger" onClick={() => stopSession(s)}>종료하기</button></div>
    {proc.length > 0 && <div className="meta" title={proc.map(p => p.path).join('\n')}>
      🖥 {[...proc].reverse().map(p => p.name + (p === proc[0] ? `(${p.pid})` : '')).join(' › ')}</div>}
    {log != null && <pre style={{ marginTop: 8 }}>{log}</pre>}
    {!agent && <details open={sumOpen} onToggle={e => { if (e.target === e.currentTarget) sumOpen = e.target.open }}>
      <summary><h4 style={{ display: 'inline-block' }}>세션 요약</h4></summary>
      <div><b>{ov.title || '(제목 없음)'}</b> <TitleBtn sid={sid} title={ov.title} /></div>
      <div className="meta">{when(ov.first)} → {when(ov.last)}</div>
      <details open={taskOpen} onToggle={e => { e.stopPropagation(); taskOpen = e.target.open }}>
        <summary><h4 style={{ display: 'inline-block', fontSize: 13 }}>기록할 작업 · {ts.length}건</h4></summary>
        {ai.err ? <div>{ai.err}</div> : ts.length ? <TaskList ts={ts} edit="all" /> : <div className="meta">아직 정리하지 않았습니다</div>}
        <div style={{ marginTop: 6 }}><button className="sm" disabled={ai.busy} onClick={summarize}>{ai.busy ? '요약 중…' : ai.label || (ts.length ? '다시 정리' : '작업 정리')}</button>
          {' '}<span className="meta">haiku · 토큰 사용 · 기록이 그대로면 저장본 재사용</span></div>
      </details></details>}
    <SessionPushes sid={sid} /></>
}

// 끝난 세션. 다시 열기: 터미널 새 창에서 claude --resume (HUDSON_FLEET_TERMINAL)
function HistoryPanel({ sid }) {
  const { G, ver, setMsg } = useApp()
  const H = usePoll('/api/sessions?status=closed&limit=200', 0, [ver])
  const [busy, setBusy] = useState(false)
  const s = H?.find(x => x.sid === sid)
  if (!s) return <div className="meta">불러오는 중…</div>
  const reopen = async fork => {
    setBusy(true)
    const r = await post('/api/reopen', { sid, fork })
    setMsg(r.text || r.error)
    setBusy(false)
  }
  const app = s.kind === 'background' ? '백그라운드' : s.app || '대화형'
  return <>
    <h3>{s.title || s.name} <TitleBtn sid={sid} title={s.title || s.name} /></h3>
    <div className="meta">{REASON[s.end_reason] || s.end_reason} · {app} · {tilde(s.cwd, G.home)}</div>
    <div className="meta">{when(s.started_at)} → {when(s.ended_at)} · 토큰 {fmtTok(s.tokens)}</div>
    <div style={{ display: 'flex', gap: 6, marginTop: 8 }}>
      <button className="sm" disabled={busy} onClick={() => reopen(false)} title="같은 세션 ID 로 이어서 엽니다. 다시 살아나면 현황으로 돌아갑니다">이어서 열기</button>
      <button className="sm" disabled={busy} onClick={() => reopen(true)} title="대화를 복사한 새 세션으로 엽니다 (--fork-session). 이 기록은 그대로 남습니다">복사해 열기</button></div>
    <details open><summary><h4 style={{ display: 'inline-block' }}>기록한 작업 · {s.tasks.length}건</h4></summary>
      {s.tasks.length ? <TaskList ts={s.tasks} /> : <div className="meta">기록할 작업 없음</div>}</details>
    <SessionPushes sid={sid} /></>
}
