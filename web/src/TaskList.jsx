import { useState } from 'react'
import { TAGS, TASK, post, useApp } from './lib'

const SRC = { agent: '에이전트가 직접 기록', haiku: 'haiku 가 대화에서 정리', human: '사람이 고침' }
const ORDER = ['todo', 'stopped', 'done', 'rejected']  // 묶음 순서: 아직 할 일이 위로
const OPEN = { todo: true, stopped: true }  // 끝난 묶음(완료·반려)은 접어 둔다

// 작업 한 줄. 설명 줄·비고는 접어 두고 문장을 누르면 펼친다 — key=작업 id 라 5초 갱신에도 펼침이 남는다
// edit: false 읽기만 · 'status' 분류만 · 'all' 분류·태그·삭제. lead: 문장 앞에 붙일 것 (남은 작업의 [세션])
// 고칠 수 있는 줄에는 프로젝트가 하나라도 있으면 프로젝트 칸도 붙는다 (끝난 프로젝트는 이미 붙은 줄에만 보인다)
export function TaskRow({ t, edit, lead }) {
  const { setMsg, bump, P } = useApp()
  const [open, setOpen] = useState(false)
  let d = []
  try { d = JSON.parse(t.details || '[]') } catch { /* 옛 기록 */ }
  const note = t.note && t.status !== 'todo'
  const has = d.length || note
  const save = async b => {
    const r = await post('/api/task', { id: t.id, ...b })
    if (!r.ok) return setMsg(r.error || '저장 실패')
    bump()
  }
  const del = () => confirm('이 작업 기록을 지울까요?') && save({ delete: true })
  return (
    <li className={'t-' + t.status} title={SRC[t.source] || ''}>
      {edit
        ? <select className="pill tsel" value={t.status} style={{ color: TASK[t.status]?.[1] }} title="분류 바꾸기"
            onChange={e => save({ status: e.target.value })}>
            {Object.entries(TASK).map(([k, [l]]) => <option key={k} value={k}>{l}</option>)}
          </select>
        : <span className="pill" style={{ color: TASK[t.status]?.[1] }}>{TASK[t.status]?.[0] || t.status}</span>}
      {edit === 'all'
        ? <select className="pill tgsel" value={t.tag || ''} title="태그 바꾸기" onChange={e => save({ tag: e.target.value })}>
            {!t.tag && <option value="">태그</option>}
            {TAGS.map(k => <option key={k}>{k}</option>)}
          </select>
        : edit !== 'status' && t.tag && <span className="pill">{t.tag}</span>}
      {edit && P?.length > 0 && <select className="pill psel" value={t.project_id || ''} title="프로젝트 바꾸기 (PARA)"
        onChange={e => save({ project: +e.target.value || 0 })}>
        <option value="">프로젝트 없음</option>
        {P.filter(p => p.status !== 'done' || p.id === t.project_id).map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
      </select>}
      {' '}{lead}
      <div className="tbody">{/* 문장과 설명을 한 칸에 — 넘치는 줄·설명 줄이 문장 시작점에 맞춰 들어간다 */}
        <span className={'tx' + (has ? ' has' : '') + (open ? ' open' : '')} title={has ? '눌러서 설명 보기' : undefined}
          onClick={has ? e => { e.stopPropagation(); setOpen(!open) } : undefined}>{t.text}</span>
        <span className="tid" title="작업 번호 — 에이전트와 같은 번호로 부를 때">#{t.id}</span>
        {edit === 'all' && <button className="tdel" title="이 기록 삭제" onClick={del}>✕</button>}
        {has && open && <div className="dbox">
          {d.length > 0 && <ul className="dets">{d.map((x, i) => <li key={i}>{x}</li>)}</ul>}
          {note && <div className="tnote">결과 : {t.note}</div>}
        </div>}
      </div>
    </li>
  )
}

// 작업 목록. 상태가 섞여 있으면 남은 일 → 중단 → 완료 → 반려로 묶고 끝난 묶음은 접는다 (<details> 라 펼침은 갱신에도 남는다)
export function TaskList({ ts, edit, lead, className = 'tasks' }) {
  const rows = l => <ul className={className}>{l.map(t => <TaskRow key={t.id} t={t} edit={edit} lead={lead?.(t)} />)}</ul>
  const groups = ORDER.map(k => [k, ts.filter(t => t.status === k)]).filter(([, l]) => l.length)
  if (groups.length > 1) return groups.map(([k, l]) => <details key={k} className="tgrp" open={!!OPEN[k]}>
    <summary style={{ color: TASK[k][1] }}>{TASK[k][0]} {l.length}</summary>{rows(l)}</details>)
  return rows(ts)
}
