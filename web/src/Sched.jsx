import { Fragment, useEffect, useState } from 'react'
import { post, press, tilde, useApp, usePoll, when } from './lib'

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

// ── 예약 작업: Claude 예약 작업(루틴 — claude.ai 에 저장, 데스크톱 앱·클라우드에서 실행)과 살아 있는 세션의 예약 ──
export default function Sched() {
  const { G, setMsg } = useApp()
  const [n, setN] = useState(0), [busy, setBusy] = useState(false), [open, setOpen] = useState('')  // open: 지시문을 펼친 루틴
  const S = usePoll('/api/schedules', 30000, [n])
  const R = S?.routines
  const pull = async () => {
    setBusy(true)
    const r = await post('/api/schedules/refresh', {})
    setBusy(false)
    if (r.error) setMsg(r.error)
    setN(x => x + 1)
  }
  useEffect(() => { if (R && (!R.at || Date.now() - new Date(R.at) > STALE)) pull() }, [!!R])  // 처음 열 때 저장본이 없거나 오래됐으면
  const rs = [...(R?.items || [])].sort((a, b) => b.enabled - a.enabled || (a.next || '9').localeCompare(b.next || '9'))
  return <div className="pg">
    <section className="card"><div className="sh"><h2>Claude 예약 작업</h2>
      <span className="meta">{R?.at ? `${rs.filter(r => r.enabled).length}개 켜짐 · 전체 ${rs.length}개 · ${when(R.at)} 에 받음` : ''}</span>
      <button className="sm" style={{ marginLeft: 'auto' }} disabled={busy} onClick={pull}
        title="claude.ai 에서 다시 받습니다. haiku 를 짧게 한 번 실행합니다 (약 10초 · 0.5센트)">{busy ? '받는 중… (10초쯤)' : '새로 받기'}</button></div>
      {!R ? <div className="meta">불러오는 중…</div> : !R.at ? <div className="meta">{busy ? '처음 받는 중입니다…' : '아직 받지 않았습니다'}</div>
        : <div className="tw"><table className="tbl"><tbody>
          <tr><th>이름</th><th>일정</th><th>다음 실행</th><th>마지막 실행</th><th>실행 위치</th><th>모델 · 권한</th></tr>
          {rs.map(r => <Fragment key={r.id}><tr style={{ opacity: r.enabled ? 1 : .55 }}>
            <td><a className="lk" {...press(() => setOpen(open === r.id ? '' : r.id))} aria-expanded={open === r.id} title="눌러서 지시문 보기">{r.name || '(이름 없음)'}</a>
              {' '}<span className="pill" style={{ color: r.enabled ? 'var(--t-done)' : 'var(--mute)' }}>{r.enabled ? '켜짐' : '꺼짐'}</span>
              {r.stopped && <div className="meta">{STOP[r.stopped] || r.stopped}</div>}</td>
            <td title={r.cron ? `${r.cron}${r.tz ? ' · ' + r.tz : ''}` : ''}>{cronText(r.cron)}</td>
            <td className="meta">{r.enabled && r.cron ? when(r.next) : '—'}</td>
            <td className="meta">{r.last ? <>{when(r.last)} <span style={{ color: RESULT[r.result]?.[1] }}>{RESULT[r.result]?.[0] || r.result}</span>{r.why && ` · ${r.why}`}</> : '—'}</td>
            <td className="meta">{r.device}{r.folders.map(f => <div key={f} title={f}>{tilde(f, G.home)}</div>)}</td>
            <td className="meta">{r.model.replace(/^claude-/, '')}{r.mode && <div>{r.mode}</div>}</td></tr>
            {/* 표가 화면보다 넓으면(휴대폰) 지시문은 화면 폭에 맞추고 왼쪽에 붙여 둔다 — 옆으로 밀지 않고 읽게 */}
            {open === r.id && <tr><td colSpan="6"><pre style={{ position: 'sticky', left: 0, maxWidth: 'calc(100vw - 72px)' }}>{r.prompt || '(지시문 없음)'}</pre></td></tr>}</Fragment>)}
          {!rs.length && <tr><td colSpan="6" className="meta">예약 작업이 없습니다</td></tr>}
        </tbody></table></div>}
      <p className="meta" style={{ margin: '10px 0 0' }}>예약 작업은 claude.ai 에 저장되고 Claude 데스크톱 앱이나 클라우드에서 실행됩니다. 로그인 토큰을 읽지 않으려고, [새로 받기] 는 Claude Code 의 예약 작업 조회 도구를 haiku 로 한 번 불러 받아 옵니다. 페이지를 열 때 저장본이 1시간보다 오래됐으면 저절로 다시 받습니다.</p>
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
