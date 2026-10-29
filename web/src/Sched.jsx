import { Fragment, useEffect, useRef, useState } from 'react'
import { post, tilde, useApp, usePoll, when } from './lib'

// cron 5칸 → 쉬운 말. 자주 쓰는 모양만 바꾸고 나머지는 그대로 보인다
const DOW = '일월화수목금토'
function cronText(c) {
  if (!c) return '일정 없음 (직접 실행)'
  const [mi, h, dom, mon, dow] = c.split(/\s+/), num = x => /^\d+$/.test(x)
  const hm = num(mi) && num(h) ? `${+h < 12 ? '오전' : '오후'} ${+h % 12 || 12}:${mi.padStart(2, '0')}` : ''
  const any = dom === '*' && mon === '*' && dow === '*'
  if (/^\*\/\d+$/.test(mi) && h === '*' && any) return `${mi.slice(2)}분마다`
  if (num(mi) && h === '*' && any) return `매시 ${mi}분`
  if (hm && dom === '*' && mon === '*') return dow === '*' ? `매일 ${hm}` : dow === '1-5' ? `평일 ${hm}` : num(dow) ? `매주 ${DOW[+dow % 7]}요일 ${hm}` : c
  if (hm && num(dom) && num(mon)) return `${mon}월 ${dom}일 ${hm}`
  return c
}

const RESULT = { SUCCEEDED: ['성공', 'var(--t-done)'], FAILED: ['실패', '#dc2626'] }
const STOP = { device_absent: '실행할 기기가 연결돼 있지 않아 멈춤' }  // 루틴이 멈춘 이유 (suspension_reason)
const STALE = 3600e3  // 저장본이 이보다 오래됐으면 페이지를 열 때 새로 받는다

// Flow: AI 가 지시문을 정리한 흐름도 — 시작 → 단계(조건 분기는 ⤷) → 결과, 옆에 지키는 규칙.
// 저장본이 없거나 지시문이 바뀌었으면(stale) 상세 페이지에 들어올 때 만든다. 서버가 이미 다시 만드는 중(making)이면 기다린다
function RoutineMap({ r, m, done }) {
  const { setMsg } = useApp()
  const [busy, setBusy] = useState(false)
  const make = async () => {
    setBusy(true)
    const x = await post('/api/routine-map', { id: r.id })
    setBusy(false)
    if (x.error) setMsg(x.error)
    done()
  }
  useEffect(() => { if ((!m || (m.stale && !m.making)) && r.prompt) make() }, [])
  if (!m) return <div className="meta">{busy ? 'AI(haiku)가 지시문을 읽고 흐름을 정리하는 중… (10~30초)' : r.prompt ? '흐름도를 만들지 못했습니다 ' : '지시문이 없습니다'}
    {!busy && r.prompt && <button className="sm" onClick={make}>다시 시도</button>}</div>
  const d = m.data
  const box = (k, body, cls = '') => <div className={'fbox ' + cls}><span className="fk">{k}</span><div>{body}</div></div>
  const list = l => l.length > 0 && <ul>{l.map((x, i) => <li key={i}>{x}</li>)}</ul>
  return <div className="rmap">
    <p className="rsum">{d.summary}</p>
    <div className="rcols"><div className="flow">
      {box('시작', <>{d.trigger}{list(d.inputs)}</>, 'fstart')}
      {d.steps.map((s, i) => <Fragment key={i}><i className="farrow" aria-hidden>↓</i>
        {box(i + 1, <><b>{s.title}</b> <span className="meta">{s.detail}</span>{s.branch && <div className="fbr">⤷ {s.branch}</div>}</>)}</Fragment>)}
      {d.outputs.length > 0 && <><i className="farrow" aria-hidden>↓</i>{box('결과', list(d.outputs), 'fend')}</>}
    </div>
    {d.rules.length > 0 && <div className="frules"><b>지키는 규칙</b>{list(d.rules)}</div>}</div>
    <div className="meta" style={{ marginTop: 8 }}>{when(m.at)} 에 AI(haiku)가 정리했습니다{m.stale && <b style={{ color: 'var(--t-todo)' }}> · 지시문이 바뀌어 {busy || m.making ? '다시 만드는 중…' : '다시 만들어야 합니다'}</b>}{' '}
      <button className="sm" disabled={busy || m.making} onClick={make} title="AI 로 다시 만듭니다 (haiku 사용)">{busy || m.making ? '만드는 중…' : '새로 만들기'}</button></div>
  </div>
}

const nextRun = r => r.enabled && r.cron ? when(r.next) : '—'
const lastRun = r => r.last ? <>{when(r.last)} <span style={{ color: RESULT[r.result]?.[1] }}>{RESULT[r.result]?.[0] || r.result}</span>{r.why && ` · ${r.why}`}</> : '—'
const OnOff = ({ r }) => <span className="pill" style={{ color: r.enabled ? 'var(--t-done)' : 'var(--mute)' }}>{r.enabled ? '켜짐' : '꺼짐'}</span>

// 예약 작업 상세 (#sched/<id>): 설정 한눈에 → Flow(접고 펴기, 다른 루틴을 열어도 접힘 상태를 이어 간다) → 지시문 전문
let flowOpen = true
function Detail({ r, loaded, m, done, pull }) {
  const { G } = useApp()
  // 지시문은 claude.ai 예약 작업 페이지에서 고친다 (수정 API 는 110KB 실행 설정을 통째로 바꿔야 해 여기서 고치지 않는다).
  // 고치러 갔다가 이 창으로 돌아오면 목록을 새로 받는다 — 지시문이 바뀌었으면 서버가 Flow 를 다시 만든다
  const armed = useRef(false)
  useEffect(() => {
    const back = () => { if (armed.current && document.visibilityState === 'visible') { armed.current = false; pull() } }
    addEventListener('focus', back); document.addEventListener('visibilitychange', back)
    return () => { removeEventListener('focus', back); document.removeEventListener('visibilitychange', back) }
  }, [pull])
  const back = <div className="sh"><a className="lk" href="#sched">← 예약 작업 목록</a></div>
  if (!r) return <div className="pg"><section className="card">{back}
    <div className="meta">{loaded ? '이 예약 작업을 찾지 못했습니다. 목록에서 [새로 받기] 를 눌러 보세요' : '불러오는 중…'}</div></section></div>
  const kv = [['일정', <>{cronText(r.cron)}{r.cron && <span className="meta"> ({r.cron}{r.tz ? ' · ' + r.tz : ''})</span>}</>], ['다음 실행', nextRun(r)],
    ['마지막 실행', lastRun(r)], ['실행 기기', r.device], ['작업 폴더', r.folders.map(f => <div key={f} title={f}>{tilde(f, G.home)}</div>)],
    ['모델', r.model.replace(/^claude-/, '') || '—'], ['권한 모드', r.mode || '—'], ...r.stopped ? [['멈춘 이유', STOP[r.stopped] || r.stopped]] : []]
  return <div className="pg">
    <section className="card">{back}
      <h3 className="dtitle">{r.name || '(이름 없음)'} <OnOff r={r} />
        <a className="lk" href={'https://claude.ai/code/routines/' + encodeURIComponent(r.id)} target="_blank" rel="noopener" onClick={() => { armed.current = true }}
          style={{ marginLeft: 'auto', fontSize: 13 }} title="claude.ai 의 예약 작업 페이지에서 지시문·일정을 고칩니다. 고치고 이 창으로 돌아오면 새로 받아 Flow 를 다시 만듭니다">claude.ai 에서 고치기 ↗</a></h3>
      <dl className="kv">{kv.map(([k, v]) => <Fragment key={k}><dt>{k}</dt><dd>{v}</dd></Fragment>)}</dl></section>
    <section className="card"><details open={flowOpen} onToggle={e => { flowOpen = e.target.open }}>
      <summary><h2 style={{ display: 'inline-block' }}>Flow</h2> <span className="meta">AI 가 지시문을 정리한 흐름</span></summary>
      <div style={{ marginTop: 10 }}><RoutineMap key={r.id} r={r} m={m} done={done} /></div></details></section>
    <section className="card"><details><summary><h2 style={{ display: 'inline-block' }}>지시문 전문</h2></summary>
      <pre style={{ marginTop: 10 }}>{r.prompt || '(지시문 없음)'}</pre></details></section>
  </div>
}

// ── 예약 작업: Claude 예약 작업(루틴 — claude.ai 에 저장, 데스크톱 앱·클라우드에서 실행)과 살아 있는 세션의 예약. sub 가 있으면 그 루틴의 상세 ──
export default function Sched({ sub }) {
  const { G, setMsg } = useApp()
  const [n, setN] = useState(0), [busy, setBusy] = useState(false)
  const S = usePoll('/api/schedules', sub ? 10000 : 30000, [n])  // 상세에서는 다시 만든 Flow 가 빨리 보이게
  const R = S?.routines
  const pull = async () => {
    setBusy(true)
    const r = await post('/api/schedules/refresh', {})
    setBusy(false)
    if (r.error) setMsg(r.error)
    setN(x => x + 1)
  }
  useEffect(() => { if (R && (!R.at || Date.now() - new Date(R.at) > STALE)) pull() }, [!!R])  // 처음 열 때 저장본이 없거나 오래됐으면
  if (sub) return <Detail r={R?.items.find(x => x.id === sub)} loaded={!!R?.at && !busy} m={S?.maps?.[sub]} done={() => setN(x => x + 1)} pull={pull} />
  const rs = [...(R?.items || [])].sort((a, b) => b.enabled - a.enabled || (a.next || '9').localeCompare(b.next || '9'))
  return <div className="pg">
    <section className="card"><div className="sh"><h2>Claude 예약 작업</h2>
      <span className="meta">{R?.at ? `${rs.filter(r => r.enabled).length}개 켜짐 · 전체 ${rs.length}개 · ${when(R.at)} 에 받음` : ''}</span>
      <button className="sm" style={{ marginLeft: 'auto' }} disabled={busy} onClick={pull}
        title="claude.ai 에서 다시 받습니다. haiku 를 짧게 한 번 실행합니다 (약 10초 · 0.5센트)">{busy ? '받는 중… (10초쯤)' : '새로 받기'}</button></div>
      {!R ? <div className="meta">불러오는 중…</div> : !R.at ? <div className="meta">{busy ? '처음 받는 중입니다…' : '아직 받지 않았습니다'}</div>
        : <div className="tw"><table className="tbl"><tbody>
          <tr><th>이름</th><th>일정</th><th>다음 실행</th><th>마지막 실행</th><th>실행 위치</th><th>모델 · 권한</th></tr>
          {rs.map(r => <tr key={r.id} style={{ opacity: r.enabled ? 1 : .55 }}>
            <td><a className="lk" href={'#sched/' + encodeURIComponent(r.id)} title="상세 페이지: Flow(AI 가 정리한 흐름도)와 지시문">{r.name || '(이름 없음)'}</a> <OnOff r={r} />
              {r.stopped && <div className="meta">{STOP[r.stopped] || r.stopped}</div>}</td>
            <td title={r.cron ? `${r.cron}${r.tz ? ' · ' + r.tz : ''}` : ''}>{cronText(r.cron)}</td>
            <td className="meta">{nextRun(r)}</td>
            <td className="meta">{lastRun(r)}</td>
            <td className="meta">{r.device}{r.folders.map(f => <div key={f} title={f}>{tilde(f, G.home)}</div>)}</td>
            <td className="meta">{r.model.replace(/^claude-/, '')}{r.mode && <div>{r.mode}</div>}</td></tr>)}
          {!rs.length && <tr><td colSpan="6" className="meta">예약 작업이 없습니다</td></tr>}
        </tbody></table></div>}
      <p className="meta" style={{ margin: '10px 0 0' }}>이름을 누르면 상세 페이지에서 Flow(AI 가 지시문을 정리한 흐름도)를 봅니다. 처음 한 번 만들어 저장해 두고, 새로 받은 지시문이 바뀌었으면 저절로 다시 만듭니다. 예약 작업은 claude.ai 에 저장되고 Claude 데스크톱 앱이나 클라우드에서 실행됩니다. 로그인 토큰을 읽지 않으려고, [새로 받기] 는 Claude Code 의 예약 작업 조회 도구를 haiku 로 한 번 불러 받아 옵니다. 페이지를 열 때 저장본이 1시간보다 오래됐으면 저절로 다시 받습니다.</p>
    </section>

    <section className="card"><div className="sh"><h2>세션 안 예약</h2><span className="meta">살아 있는 세션이 /loop·예약 도구로 걸어 둔 것 — 세션이 끝나면 사라집니다</span></div>
      {!S ? <div className="meta">불러오는 중…</div> : <div className="tw"><table className="tbl"><tbody>
        <tr><th>세션</th><th>종류</th><th>일정</th><th>다음 실행</th><th>지시문</th></tr>
        {S.sessions.map((j, i) => <tr key={i}>
          <td>{j.session}</td>
          <td><span className="pill">{j.kind === 'loop' ? '/loop' : j.recurring ? '반복' : '한 번'}</span></td>
          <td>{j.kind === 'loop' ? j.reason || '스스로 정한 간격' : cronText(j.cron)}{j.expires && <div className="meta">{when(j.expires)} 에 끝남 (7일)</div>}</td>
          <td className="meta">{j.next > Date.now() ? when(j.next) : '일정대로'}</td>
          <td style={{ whiteSpace: 'normal' }}>{j.prompt}</td></tr>)}
        {!S.sessions.length && <tr><td colSpan="5" className="meta">걸어 둔 예약이 없습니다</td></tr>}
      </tbody></table></div>}
    </section>
  </div>
}
