import { Fragment, useEffect, useState } from 'react'
import { post, useApp, when } from './lib'
import { Button } from './ui'

// Flow: 흐름도 한 장 — 시작 → 단계(조건 분기는 ⤷) → 결과, 옆에 지키는 규칙. 모양은 fleet/tasks.py norm_flow
// 예약 작업(AI 가 지시문을 정리) · 프로젝트(AI 가 작업 기록을 정리) · 작업(에이전트가 끝낼 때 직접 남김)이 같이 쓴다
export function FlowView({ d }) {
  const box = (k, body, cls = '') => <div className={'fbox ' + cls}><span className="fk">{k}</span><div>{body}</div></div>
  const list = l => l?.length > 0 && <ul>{l.map((x, i) => <li key={i}>{x}</li>)}</ul>
  return <div className="rmap">
    {d.summary && <p className="rsum">{d.summary}</p>}
    <div className="rcols"><div className="flow">
      {box('시작', <>{d.trigger}{list(d.inputs)}</>, 'fstart')}
      {d.steps.map((s, i) => <Fragment key={i}><i className="farrow" aria-hidden>↓</i>
        {box(i + 1, <><b>{s.title}</b> <span className="meta">{s.detail}</span>{s.branch && <div className="fbr">⤷ {s.branch}</div>}</>)}</Fragment>)}
      {d.outputs?.length > 0 && <><i className="farrow" aria-hidden>↓</i>{box('결과', list(d.outputs), 'fend')}</>}
    </div>
    {d.rules?.length > 0 && <div className="frules"><b>지키는 규칙</b>{list(d.rules)}</div>}</div>
  </div>
}

// AI 가 만들어 DB 에 저장해 둔 Flow (m: {data, at, stale, making}). 저장본이 없거나 바탕 글이 바뀌었으면(stale) 처음 보일 때 만든다.
// 서버가 이미 다시 만드는 중(making)이면 기다린다. what: 바탕 글 이름 (지시문 · 작업 기록), ok: 바탕 글이 있나
export function FlowMaker({ m, url, body, ok, done, what }) {
  const { setMsg } = useApp()
  const [busy, setBusy] = useState(false)
  const make = async () => {
    setBusy(true)
    const x = await post(url, body)
    setBusy(false)
    if (x.error) setMsg(x.error)
    done()
  }
  useEffect(() => { if ((!m || (m.stale && !m.making)) && ok) make() }, [])
  if (!m) return <div className="meta">{busy ? `AI(haiku)가 ${what}을 읽고 흐름을 정리하는 중… (10~30초)` : ok ? '흐름도를 만들지 못했습니다 ' : `${what}이 없습니다`}
    {!busy && ok && <Button onClick={make}>다시 시도</Button>}</div>
  return <>
    <FlowView d={m.data} />
    <div className="meta" style={{ marginTop: 8 }}>{when(m.at)} 에 AI(haiku)가 정리했습니다{m.stale && <b style={{ color: 'var(--t-todo)' }}> · {what}이 바뀌어 {busy || m.making ? '다시 만드는 중…' : '다시 만들어야 합니다'}</b>}{' '}
      <Button disabled={busy || m.making} onClick={make} title="AI 로 다시 만듭니다 (haiku 사용)">{busy || m.making ? '만드는 중…' : '새로 만들기'}</Button></div>
  </>
}
