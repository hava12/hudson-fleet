import { Fragment, useState } from 'react'
import { TaskList } from './TaskList'
import { TaskSum, Tip, post, useApp, usePoll, when } from './lib'

// ── PARA: 일과 자료를 실행 가능성 순서로 네 칸에 나눈다 (fleet/para.py) ──
// 프로젝트·영역은 사람이 여기서 만들고, 에이전트는 작업을 기록할 때 프로젝트 번호를 적고 자료를 MCP 로 남긴다.
// 보관은 따로 만들지 않는다 — 끝난 프로젝트와 보관한 영역이 보관 칸에 모인다
// 칸 순서: 프로젝트가 영역 아래에 달리므로 Areas 를 맨 앞에 둔다 (PARA 이름 순서는 P·A·R·A)
const PARA = [  // [키, 이름, 뜻, 판별 질문]
  ['a', 'Areas', '끝나지 않고 계속 지킬 책임', '계속 유지해야 하나?'],
  ['p', 'Projects', '끝나는 때와 완료 조건이 있는 일', '언제 끝나는지 말할 수 있나?'],
  ['r', 'Resources', '지금 할 일은 아니지만 나중에 다시 쓸 참고', '나중에 다시 꺼내 쓸까?'],
  ['x', 'Archives', '끝났거나 더는 책임지지 않는 것', '끝났거나 관심이 식었나?'],
]
const ST = { active: ['진행 중', 'var(--acc)'], pending: ['시작 전', 'var(--t-todo)'], done: ['끝남 (보관)', 'var(--t-done)'] }
const ORDER = ['active', 'pending', 'done']
const saved = () => { try { return localStorage.getItem('paratab') || 'a' } catch { return 'a' } }

// 영역 고르기: 보관한 영역은 고를 수 없다 (이미 붙어 있으면 그대로 보인다)
const AreaSel = ({ as, v, set }) => <select value={v || ''} onChange={e => set(e.target.value ? +e.target.value : null)}>
  <option value="">영역 없음</option>
  {as.filter(a => !a.archived_at || a.id === v).map(a => <option key={a.id} value={a.id}>{a.name}{a.archived_at ? ' (보관)' : ''}</option>)}</select>

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
    <tr><th>Project</th><th style={{ width: 170 }}>Area</th><th style={{ width: 130 }}>상태</th><th style={{ width: 200 }}>기간</th>
      <th style={{ width: 190 }}>작업</th><th style={{ width: 140 }} /></tr>
    {ps.map(({ tasks, ...p }) => <Fragment key={p.id}><tr>
      <td style={{ whiteSpace: 'normal' }}><a className="lk" onClick={() => setOpen(open === p.id ? 0 : p.id)}>{p.name}</a>
        <span className="tid" title="에이전트가 작업을 기록할 때 적는 번호"> #{p.id}</span>
        <div className="meta">{p.kind === 'jira' ? <>Jira 에픽 <a className="lk" href={p.url} target="_blank" rel="noopener">{p.epic}</a></>
          : <>완료 조건: {p.done_when}</>}</div></td>
      <td><AreaSel as={as} v={p.area_id} set={v => save({ ...p, area_id: v })} /></td>
      <td>{p.kind === 'jira'
        ? <span className="pill" style={{ color: ST[p.status]?.[1] }} title="Jira 에픽 상태 (10분마다 받아 옴). 에픽이 Done 이 되면 보관으로 갑니다">{p.jira_status}</span>
        : <select className="pill tsel" value={p.status} style={{ color: ST[p.status][1] }} title="끝남으로 바꾸면 보관 칸으로 갑니다"
            onChange={e => save({ ...p, status: e.target.value })}>{ORDER.map(k => <option key={k} value={k}>{ST[k][0]}</option>)}</select>}</td>
      <td className="meta">{p.start} ~ {p.end || ''}</td>
      <td><TaskSum ts={tasks} />{tasks.length > 0 && <span className="meta"> · 세션 {new Set(tasks.map(t => t.sid)).size}개</span>}</td>
      <td className="acts">{p.kind === 'own' && <button className="sm" onClick={() => edit(p)}>고치기</button>}
        <button className="sm danger" onClick={() => confirm(`"${p.name}" 프로젝트를 지울까요?\n적힌 작업·자료는 프로젝트 없음으로 남습니다.`) && save({ id: p.id, delete: true })}>삭제</button></td></tr>
      {open === p.id && <tr><td colSpan="6">{tasks.length
        ? <TaskList ts={tasks} edit="status" lead={t => <span className="meta">[{t.session || t.sid.slice(0, 8)}]</span>} />
        : <span className="meta">아직 이 프로젝트로 기록된 작업이 없습니다. 에이전트가 작업을 기록할 때 #{p.id} 를 적으면 여기에 모입니다</span>}</td></tr>}
    </Fragment>)}</tbody></table></div>
}

function Projects({ ps, as, save }) {
  const [add, setAdd] = useState('')  // 펼친 만들기 칸: own · jira
  const btn = (k, l) => <button className={'sm' + (add === k ? ' pri' : '')} onClick={() => setAdd(add === k ? '' : k)}>{l}</button>
  const done = b => save(b).then(ok => ok && setAdd(''))
  const live = ps.filter(p => p.status !== 'done')
  return <>
    <div style={{ display: 'flex', gap: 6 }}>{btn('own', '+ 직접 만들기')}{btn('jira', '+ Jira 에픽 연결')}</div>
    {add === 'own' && <OwnForm as={as} save={done} />}
    {add === 'jira' && <EpicForm as={as} save={done} />}
    {['active', 'pending'].map(k => {
      const l = live.filter(p => p.status === k)
      return l.length > 0 && <Fragment key={k}><h4 style={{ color: ST[k][1] }}>{ST[k][0]} {l.length}</h4><ProjTable ps={l} as={as} save={save} /></Fragment>
    })}
    {!live.length && <p className="meta">진행 중인 프로젝트가 없습니다. 마감과 완료 조건이 있는 일을 직접 만들거나 Jira 에픽에 연결하세요</p>}
  </>
}

function Areas({ as, ps, save }) {
  const [f, setF] = useState({ name: '', keep: '' })
  const live = as.filter(a => !a.archived_at)
  const edit = a => {
    const name = prompt('영역 이름', a.name), keep = name && prompt('유지할 상태 (한 줄)', a.keep || '')
    if (name && keep !== null) save({ id: a.id, name, keep })
  }
  return <>
    <div className="tw"><table className="tbl" style={{ minWidth: 640 }}><tbody>
      <tr><th>Area</th><th>유지할 상태</th><th>Projects (진행 중·시작 전)</th><th /></tr>
      {live.map(a => <tr key={a.id}><td><b>{a.name}</b></td><td style={{ whiteSpace: 'normal' }}>{a.keep}</td>
        <td style={{ whiteSpace: 'normal' }}>{ps.filter(p => p.area_id === a.id && p.status !== 'done').map(p => <span key={p.id} className="pill" style={{ margin: '0 4px 4px 0' }}>{p.name}</span>)}</td>
        <td className="acts"><button className="sm" onClick={() => edit(a)}>고치기</button>
          <button className="sm" title="더는 책임지지 않으면 보관 칸으로" onClick={() => save({ id: a.id, archive: true })}>보관</button>
          <button className="sm danger" onClick={() => confirm(`"${a.name}" 영역을 지울까요?\n프로젝트·자료는 영역 없음으로 남습니다.`) && save({ id: a.id, delete: true })}>삭제</button></td></tr>)}
      {!live.length && <tr><td colSpan="4" className="meta">아직 영역이 없습니다</td></tr>}</tbody></table></div>
    <form className="uadd" onSubmit={e => { e.preventDefault(); save(f).then(ok => ok && setF({ name: '', keep: '' })) }}>
      <input value={f.name} onChange={e => setF({ ...f, name: e.target.value })} placeholder="영역 이름 (예: 결제 서비스 운영)" style={{ width: 220 }} />
      <input value={f.keep} onChange={e => setF({ ...f, keep: e.target.value })} placeholder="유지할 상태 (예: 결제 장애 0건)" style={{ flex: 1, minWidth: 220 }} />
      <button className="sm pri" disabled={!f.name.trim()}>추가</button></form>
  </>
}

// 자료: 에이전트가 MCP(resource_save)로 남긴다 — 사용자가 남기라고 할 때와 프로젝트를 보관할 때만. 여기서는 찾고 지운다
function Resources({ rs, del }) {
  const [q, setQ] = useState('')
  const ws = q.toLowerCase().split(/\s+/).filter(Boolean)
  const hit = rs.filter(r => ws.every(w => `${r.title} ${r.summary} ${r.body || ''}`.toLowerCase().includes(w)))
  return <>
    <input value={q} onChange={e => setQ(e.target.value)} placeholder="낱말로 찾기 (제목·요약·본문)" style={{ width: '100%', maxWidth: 420 }} />
    {hit.map(r => <details key={r.id} className="res"><summary><b>{r.title}</b> <span className="meta">— {r.summary}</span></summary>
      <div className="meta">{[r.project && '프로젝트 ' + r.project, r.area && '영역 ' + r.area, when(r.created_at), r.session && '남긴 세션 ' + r.session].filter(Boolean).join(' · ')}
        <button className="sm danger" style={{ marginLeft: 8 }} onClick={() => confirm(`"${r.title}" 자료를 지울까요?`) && del(r.id)}>삭제</button></div>
      <pre className="rbody">{r.body}</pre></details>)}
    {!rs.length ? <p className="meta">아직 자료가 없습니다. 대화에서 에이전트에게 "이거 자료로 남겨"라고 하거나, 프로젝트를 보관할 때 에이전트가 정리 한 장을 남깁니다</p>
      : !hit.length && <p className="meta">찾는 낱말이 들어간 자료가 없습니다</p>}
  </>
}

function Archives({ ps, as, save, saveA }) {
  const done = ps.filter(p => p.status === 'done'), gone = as.filter(a => a.archived_at)
  return <>
    <h4>Projects {done.length}</h4>
    {done.length ? <ProjTable ps={done} as={as} save={save} /> : <p className="meta">없습니다. 직접 만든 프로젝트는 상태를 끝남으로 바꾸면, Jira 에픽 프로젝트는 에픽이 Done 이 되면 여기로 옵니다</p>}
    <h4>Areas {gone.length}</h4>
    {gone.length ? <div className="tw"><table className="tbl" style={{ minWidth: 640 }}><tbody>
      <tr><th>Area</th><th>유지할 상태</th><th>보관한 날</th><th /></tr>
      {gone.map(a => <tr key={a.id}><td><b>{a.name}</b></td><td style={{ whiteSpace: 'normal' }}>{a.keep}</td><td className="meta">{when(a.archived_at)}</td>
        <td className="acts"><button className="sm" onClick={() => saveA({ id: a.id, archive: false })}>되살리기</button>
          <button className="sm danger" onClick={() => confirm(`"${a.name}" 영역을 지울까요?`) && saveA({ id: a.id, delete: true })}>삭제</button></td></tr>)}
    </tbody></table></div> : <p className="meta">없습니다</p>}
  </>
}

export default function Para() {
  const { ver, bump, setMsg } = useApp()
  const P = usePoll('/api/para', 10000, [ver])
  const [tab, setTab] = useState(saved)
  const go = k => { setTab(k); try { localStorage.setItem('paratab', k) } catch { /* 저장소 막힘 */ } }
  const send = path => async b => {
    const r = await post(path, b)
    if (r.error) { setMsg(r.error); return false }
    bump()
    return true
  }
  const saveP = send('/api/project'), saveA = send('/api/area'), delR = id => send('/api/resource')({ id })
  if (!P) return <div className="pg"><section className="card meta">불러오는 중…</section></div>
  const { areas: as, projects: ps, resources: rs } = P
  const n = { p: ps.filter(p => p.status !== 'done').length, a: as.filter(a => !a.archived_at).length, r: rs.length,
    x: ps.filter(p => p.status === 'done').length + as.filter(a => a.archived_at).length }
  const [, name, def, ask] = PARA.find(x => x[0] === tab)
  return <div className="pg"><section className="card">
    <div className="sh"><h2>PARA</h2>
      <Tip><b>PARA</b> 는 일과 자료를 <b>지금 얼마나 행동할 수 있나</b> 순서(Projects → Areas → Resources → Archives)로 네 칸에 나누는 방법입니다 (티아고 포르테). 주제가 아니라 실행 가능성으로 나눕니다.
        <ul>{PARA.map(([k, name, def]) => <li key={k}><b>{name}</b>: {def}</li>)}</ul>
        이 화면에서는 프로젝트가 영역 아래에 달리므로 Areas 를 맨 앞에 둡니다. Areas·Projects 는 사람이 만들고, 에이전트는 작업에 프로젝트 번호를 적고 Resources 를 남깁니다.</Tip>
      <div className="ptabs">{PARA.map(([k, name]) => <button key={k} className={tab === k ? 'on' : ''} onClick={() => go(k)}>
        {name}<span className="cnt">{n[k]}</span></button>)}</div></div>
    <p className="meta pdef"><b>{name}</b> — {def}. 판별 질문: {ask}</p>
    {tab === 'a' && <Areas as={as} ps={ps} save={saveA} />}
    {tab === 'p' && <Projects ps={ps} as={as} save={saveP} />}
    {tab === 'r' && <Resources rs={rs} del={delR} />}
    {tab === 'x' && <Archives ps={ps} as={as} save={saveP} saveA={saveA} />}
  </section></div>
}
