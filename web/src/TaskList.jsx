import { useState } from 'react'
import { TAGS, TASK, post, useApp } from './lib'

const SRC = { agent: '에이전트가 직접 기록', haiku: 'haiku 가 대화에서 정리', human: '사람이 고침' }
const ORDER = ['todo', 'stopped', 'done', 'rejected']  // 묶음 순서: 아직 할 일이 위로
const OPEN = { todo: true, stopped: true }  // 끝난 묶음(완료·반려)은 접어 둔다

// 작업 한 줄. 설명 줄·비고는 접어 두고 문장을 누르면 펼친다 — key=작업 id 라 5초 갱신에도 펼침이 남는다
// edit: false 읽기만 · 'status' 분류만 · 'all' 분류·태그·삭제. lead: 문장 앞에 붙일 것 (남은 작업의 [세션])
export function TaskRow({ t, edit, lead }) {
  const { setMsg, bump } = useApp()
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
      {' '}{lead}
      <span className={'tx' + (has ? ' has' : '') + (open ? ' open' : '')} title={has ? '눌러서 설명 보기' : undefined}
        onClick={has ? e => { e.stopPropagation(); setOpen(!open) } : undefined}>{t.text}</span>
      {edit === 'all' && <button className="tdel" title="이 기록 삭제" onClick={del}>✕</button>}
      {has && open && <div className="dbox">
        {d.length > 0 && <ul className="dets">{d.map((x, i) => <li key={i}>{x}</li>)}</ul>}
        {note && <div className="tnote">결과 : {t.note}</div>}
      </div>}
    </li>
  )
}

// 작업 목록. 상태가 섞여 있으면 남은 일 → 중단 → 완료 → 반려로 묶고 끝난 묶음은 접는다 (<details> 라 펼침은 갱신에도 남는다)
// max 를 넘으면 sid 가 있을 때 더보기(패널에서 전체), 없으면 "외 N건" — max 는 한 가지 상태만 보여 주는 곳(작업 현황 카드)에서 쓴다
export function TaskList({ ts, max, sid, edit, lead, className = 'tasks' }) {
  const { openSide } = useApp()
  const rows = l => <ul className={className}>{l.map(t => <TaskRow key={t.id} t={t} edit={edit} lead={lead?.(t)} />)}</ul>
  const groups = ORDER.map(k => [k, ts.filter(t => t.status === k)]).filter(([, l]) => l.length)
  if (groups.length > 1) return groups.map(([k, l]) => <details key={k} className="tgrp" open={!!OPEN[k]}>
    <summary style={{ color: TASK[k][1] }}>{TASK[k][0]} {l.length}</summary>{rows(l)}</details>)
  return <>
    {rows(ts.slice(0, max || ts.length))}
    {max > 0 && ts.length > max && (sid
      ? <button className="sm more" onClick={e => { e.stopPropagation(); openSide({ type: 'session', sid }, true) }}>더보기 (+{ts.length - max})</button>
      : <div className="meta">외 {ts.length - max}건</div>)}
  </>
}
