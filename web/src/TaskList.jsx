import { useState } from 'react'
import { TAGS, TASK, post, useApp } from './lib'

const SRC = { agent: '에이전트가 직접 기록', haiku: 'haiku 가 대화에서 정리', human: '사람이 고침' }

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
        {note && <div className="tnote">비고 · {t.note}</div>}
      </div>}
    </li>
  )
}

// 작업 목록. max 를 넘으면 sid 가 있을 때 더보기(패널에서 전체), 없으면 "외 N건"
export function TaskList({ ts, max, sid, edit, lead, className = 'tasks', as: L = 'ol' }) {
  const { openSide } = useApp()
  return <>
    <L className={className}>{ts.slice(0, max || ts.length).map(t => <TaskRow key={t.id} t={t} edit={edit} lead={lead?.(t)} />)}</L>
    {max > 0 && ts.length > max && (sid
      ? <button className="sm more" onClick={e => { e.stopPropagation(); openSide({ type: 'session', sid }, true) }}>더보기 (+{ts.length - max})</button>
      : <div className="meta">외 {ts.length - max}건</div>)}
  </>
}
