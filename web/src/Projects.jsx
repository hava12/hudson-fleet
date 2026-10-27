import { Fragment, useState } from 'react'
import { TaskList } from './TaskList'
import { TaskSum, post, useApp, usePoll } from './lib'

// ── 프로젝트 (PARA): 영역과 프로젝트는 사람이 여기서 만들고, 에이전트는 작업을 기록할 때 프로젝트 번호를 적는다 (fleet/para.py) ──
// 직접 만든 프로젝트는 상태를 여기서 바꾸고, Jira 에픽 프로젝트는 10분마다 에픽의 이름·상태를 받아 온다 (영역만 바꿀 수 있다)
const ST = { active: ['진행 중', 'var(--acc)'], pending: ['시작 전', 'var(--t-todo)'], done: ['끝남', 'var(--t-done)'] }
const ORDER = ['active', 'pending', 'done']

const AreaSel = ({ as, v, set }) => <select value={v || ''} onChange={e => set(e.target.value ? +e.target.value : null)}>
  <option value="">영역 없음</option>{as.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}</select>

// 직접 만들기: 완료 조건을 한 줄로 못 적으면 프로젝트가 아니라 영역이다
function OwnForm({ as, save }) {
  const [f, setF] = useState({ kind: 'own', name: '', done_when: '', area_id: null })
  const set = k => e => setF({ ...f, [k]: e.target.value })
  return <form className="uadd" onSubmit={e => { e.preventDefault(); save(f) }}>
    <input value={f.name} onChange={set('name')} placeholder="프로젝트 이름" style={{ width: 200 }} />
    <input value={f.done_when} onChange={set('done_when')} placeholder="완료 조건: 무엇이 되면 끝인가 (한 줄)" style={{ flex: 1, minWidth: 240 }} />
    <AreaSel as={as} v={f.area_id} set={v => setF({ ...f, area_id: v })} />
    <button className="sm pri" disabled={!f.name.trim() || !f.done_when.trim()}>만들기</button></form>
}

// Jira 에픽 연결: 키만 받는다 (이름·상태는 Jira 에서). 후보는 나에게 할당된 이슈가 속한 에픽
function EpicForm({ as, save }) {
  const J = usePoll('/api/jira', 0)
  const [epic, setEpic] = useState(''), [area, setArea] = useState(null)
  const eps = [...new Map((J?.items || []).filter(i => i.epic).map(i => i.epic))]
  return <form className="uadd" onSubmit={e => { e.preventDefault(); save({ kind: 'jira', epic, area_id: area }) }}>
    <input list="epics" value={epic} onChange={e => setEpic(e.target.value)} placeholder="에픽 키 (예: BVVB-1300)" style={{ width: 220 }} />
    <datalist id="epics">{eps.map(([k, t]) => <option key={k} value={k}>{t}</option>)}</datalist>
    <AreaSel as={as} v={area} set={setArea} />
    <button className="sm pri" disabled={!epic.trim()}>연결</button>
    <span className="meta">{!J ? '에픽 후보 찾는 중…' : J.error || (eps.length ? `내 이슈가 속한 에픽 ${eps.length}개를 목록에 넣었습니다` : '')}</span></form>
}

function ProjTable({ ps, as, save }) {
  const [open, setOpen] = useState(0)  // 작업 목록을 펼친 프로젝트 id
  const edit = p => {
    const name = prompt('프로젝트 이름', p.name), done_when = name && prompt('완료 조건 (한 줄)', p.done_when)
    if (name && done_when) save({ ...p, name, done_when })
  }
  // 상태별 표가 여럿이라 칸 폭을 고정해 줄을 맞춘다. 좁은 화면에서는 가로로 밀린다
  return <div className="tw"><table className="tbl" style={{ tableLayout: 'fixed', minWidth: 1060 }}><tbody>
    <tr><th>프로젝트</th><th style={{ width: 170 }}>영역</th><th style={{ width: 110 }}>상태</th><th style={{ width: 200 }}>기간</th>
      <th style={{ width: 190 }}>작업</th><th style={{ width: 140 }} /></tr>
    {ps.map(({ tasks, ...p }) => <Fragment key={p.id}><tr>
      <td style={{ whiteSpace: 'normal' }}><a className="lk" onClick={() => setOpen(open === p.id ? 0 : p.id)}>{p.name}</a>
        <span className="tid" title="에이전트가 작업을 기록할 때 적는 번호"> #{p.id}</span>
        <div className="meta">{p.kind === 'jira' ? <>Jira 에픽 <a className="lk" href={p.url} target="_blank" rel="noopener">{p.epic}</a></>
          : <>완료 조건: {p.done_when}</>}</div></td>
      <td><AreaSel as={as} v={p.area_id} set={v => save({ ...p, area_id: v })} /></td>
      <td>{p.kind === 'jira'
        ? <span className="pill" style={{ color: ST[p.status]?.[1] }} title="Jira 에픽 상태 (10분마다 받아 옴)">{p.jira_status}</span>
        : <select className="pill tsel" value={p.status} style={{ color: ST[p.status][1] }} onChange={e => save({ ...p, status: e.target.value })}>
            {ORDER.map(k => <option key={k} value={k}>{ST[k][0]}</option>)}</select>}</td>
      <td className="meta">{p.start} ~ {p.end || ''}</td>
      <td><TaskSum ts={tasks} />{tasks.length > 0 && <span className="meta"> · 세션 {new Set(tasks.map(t => t.sid)).size}개</span>}</td>
      <td className="acts">{p.kind === 'own' && <button className="sm" onClick={() => edit(p)}>고치기</button>}
        <button className="sm danger" onClick={() => confirm(`"${p.name}" 프로젝트를 지울까요?\n적힌 작업은 프로젝트 없음으로 남습니다.`) && save({ id: p.id, delete: true })}>삭제</button></td></tr>
      {open === p.id && <tr><td colSpan="6">{tasks.length
        ? <TaskList ts={tasks} edit="status" lead={t => <span className="meta">[{t.session || t.sid.slice(0, 8)}]</span>} />
        : <span className="meta">아직 이 프로젝트로 기록된 작업이 없습니다. 에이전트가 작업을 기록할 때 #{p.id} 를 적으면 여기에 모입니다</span>}</td></tr>}
    </Fragment>)}</tbody></table></div>
}

function Areas({ as, ps, save }) {
  const [f, setF] = useState({ name: '', keep: '' })
  const edit = a => {
    const name = prompt('영역 이름', a.name), keep = name && prompt('유지할 상태 (한 줄)', a.keep || '')
    if (name && keep !== null) save({ id: a.id, name, keep })
  }
  return <section className="card"><div className="sh"><h2>영역</h2>
    <span className="meta">끝나지 않고 계속 책임지는 일. 이름과 유지할 상태 한 줄만 적습니다</span></div>
    <div className="tw"><table className="tbl"><tbody>
      <tr><th>영역</th><th>유지할 상태</th><th>프로젝트</th><th /></tr>
      {as.map(a => <tr key={a.id}><td><b>{a.name}</b></td><td style={{ whiteSpace: 'normal' }}>{a.keep}</td>
        <td className="meta">{ps.filter(p => p.area_id === a.id && p.status !== 'done').length}개 진행·대기</td>
        <td className="acts"><button className="sm" onClick={() => edit(a)}>고치기</button>
          <button className="sm danger" onClick={() => confirm(`"${a.name}" 영역을 지울까요?\n프로젝트는 영역 없음으로 남습니다.`) && save({ id: a.id, delete: true })}>삭제</button></td></tr>)}
      {!as.length && <tr><td colSpan="4" className="meta">아직 영역이 없습니다</td></tr>}</tbody></table></div>
    <form className="uadd" onSubmit={e => { e.preventDefault(); save(f).then(ok => ok && setF({ name: '', keep: '' })) }}>
      <input value={f.name} onChange={e => setF({ ...f, name: e.target.value })} placeholder="영역 이름 (예: 결제 서비스 운영)" style={{ width: 220 }} />
      <input value={f.keep} onChange={e => setF({ ...f, keep: e.target.value })} placeholder="유지할 상태 (예: 결제 장애 0건)" style={{ flex: 1, minWidth: 220 }} />
      <button className="sm pri" disabled={!f.name.trim()}>추가</button></form>
  </section>
}

export default function Projects() {
  const { ver, bump, setMsg } = useApp()
  const P = usePoll('/api/para', 10000, [ver])
  const [add, setAdd] = useState('')  // 펼친 만들기 칸: own · jira
  const send = path => async b => {
    const r = await post(path, b)
    if (r.error) { setMsg(r.error); return false }
    bump()
    return true
  }
  const saveP = send('/api/project')
  if (!P) return <div className="pg"><section className="card meta">불러오는 중…</section></div>
  const { areas: as, projects: ps } = P
  const btn = (k, l) => <button className={'sm' + (add === k ? ' pri' : '')} onClick={() => setAdd(add === k ? '' : k)}>{l}</button>
  return <div className="pg">
    <section className="card"><div className="sh"><h2>프로젝트</h2>
      <span className="meta">{ORDER.map(k => `${ST[k][0]} ${ps.filter(p => p.status === k).length}`).join(' · ')}</span>
      <span style={{ marginLeft: 'auto', display: 'flex', gap: 6 }}>{btn('own', '+ 직접 만들기')}{btn('jira', '+ Jira 에픽 연결')}</span></div>
      {add === 'own' && <OwnForm as={as} save={b => saveP(b).then(ok => ok && setAdd(''))} />}
      {add === 'jira' && <EpicForm as={as} save={b => saveP(b).then(ok => ok && setAdd(''))} />}
      {ORDER.map(k => {
        const l = ps.filter(p => p.status === k)
        if (!l.length) return null
        const t = <ProjTable ps={l} as={as} save={saveP} />
        return k === 'done'
          ? <details key={k} className="tgrp"><summary>{ST[k][0]} {l.length}</summary>{t}</details>
          : <Fragment key={k}><h4 style={{ color: ST[k][1] }}>{ST[k][0]} {l.length}</h4>{t}</Fragment>
      })}
      {!ps.length && <p className="meta">아직 프로젝트가 없습니다. 마감과 완료 조건이 있는 일을 직접 만들거나, Jira 에픽에 연결하세요</p>}
    </section>
    <Areas as={as} ps={ps} save={send('/api/area')} />
  </div>
}
