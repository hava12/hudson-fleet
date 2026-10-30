import { Fragment, useState } from 'react'
import { TaskSum, fmtTok, post, press, tilde, useApp, usePoll, when } from './lib'

export const REASON = { switched: '세션 전환 (/clear·/resume)', exited: '프로세스 종료', stopped: '중지', failed: '실패', completed: '완료', gone: '사라짐' }

// ── 세션 기록: 끝난 세션 (sessions 1 : session_tasks N) ──
export function History() {
  const { G, ver, side, openSide, setMsg, bump } = useApp()
  const [n, setN] = useState(0)  // 새로 고침
  const H = usePoll('/api/sessions?status=closed&limit=200', 0, [ver, n])
  const del = async s => {  // soft delete — DB 에는 남고, --resume 으로 다시 살아나면 되돌아온다
    if (!confirm(`"${s.title || s.name || s.sid.slice(0, 8)}" 기록을 지울까요?\n세션 기록과 남은 일 목록에서 사라집니다.`)) return
    const r = await post('/api/session/delete', { sid: s.sid })
    if (r.error) return setMsg(r.error)
    if (side?.type === 'history' && side.sid === s.sid) openSide(side)  // 같은 키로 부르면 패널이 닫힌다
    bump()
  }
  return <div className="pg"><section className="card">
    <div className="sh"><h2>끝난 세션</h2>
      {H && <span className="meta">{H.length}개 · 토큰 합계 {fmtTok(H.reduce((t, s) => t + (s.tokens || 0), 0))}</span>}
      <button className="sm" style={{ marginLeft: 'auto' }} onClick={() => setN(n + 1)}>새로 고침</button></div>
    <div className="tw"><table className="tbl"><tbody>
      <tr><th>끝난 시각</th><th>세션</th><th>종료 이유</th><th>작업</th><th>토큰</th><th /></tr>
      {H?.map(s => <tr key={s.sid}>
        <td className="meta">{when(s.ended_at)}</td>
        <td><a className="lk" {...press(() => openSide({ type: 'history', sid: s.sid }))}>{s.title || s.name || s.sid.slice(0, 8)}</a>
          <div className="meta" title={s.cwd}>{tilde(s.cwd, G.home)} · {s.kind === 'background' ? '백그라운드' : s.app || '대화형'}</div></td>
        <td><span className="pill">{REASON[s.end_reason] || s.end_reason}</span></td>
        <td><TaskSum ts={s.tasks} /></td><td className="meta">{fmtTok(s.tokens)}</td>
        <td className="acts"><button className="sm danger" onClick={() => del(s)}>삭제</button></td></tr>)}
      {H && !H.length && <tr><td colSpan="6" className="meta">아직 기록된 세션이 없습니다</td></tr>}
    </tbody></table></div>
    <p className="meta" style={{ margin: '10px 0 0' }}>대시보드 서버가 켜져 있는 동안 끝난 세션을 1분 안에 저장합니다. 저장 전에 haiku 로 작업 내용을 요약합니다.</p>
  </section></div>
}

// ── Push 기록: 언제 · 어느 레포·브랜치 · 어떤 커밋 · 어느 세션 ──
const repoName = r => (r || '').replace(/^.*github\.com[:/]/, '').replace(/\.git$/, '') || '?'
const ghUrl = r => /github\.com[:/]/.test(r || '') ? 'https://github.com/' + repoName(r) : ''  // GitHub 이 아닌 원격은 링크 없이
const GhA = ({ u, t }) => u ? <a className="lk" href={u} target="_blank" rel="noopener">{t}</a> : t
export const RepoLink = ({ r }) => <GhA u={ghUrl(r)} t={repoName(r)} />
export const Commits = ({ p }) => {
  const g = ghUrl(p.remote)
  return p.commits.length
    ? p.commits.map(([h, m]) => <div key={h}><code><GhA u={g && g + '/commit/' + h} t={h} /></code> {m || ''}</div>)
    : <span className="meta"><GhA u={g && `${g}/compare/${p.old}...${p.new}`} t={p.old.slice(0, 7) + '..' + p.new.slice(0, 7)} /></span>
}

export function Pushes() {
  const [n, setN] = useState(0)
  const ps = usePoll('/api/pushes', 0, [n])
  return <div className="pg"><section className="card">
    <div className="sh"><h2>Push 기록</h2>
      <span className="meta">{ps ? `세션에서 실행한 git push ${ps.length}건 · 커밋 ${ps.reduce((a, p) => a + p.commits.length, 0)}개` : '세션에서 실행한 git push 만 모읍니다 (Claude 와 ! 명령)'}</span>
      <button className="sm" style={{ marginLeft: 'auto' }} onClick={() => setN(n + 1)}>새로 고침</button></div>
    <div className="tw"><table className="tbl"><tbody>
      {!ps ? <tr><td className="meta">불러오는 중…</td></tr> : <>
        <tr><th>시각</th><th>레포 · 브랜치</th><th>커밋</th><th>세션</th></tr>
        {ps.map((p, i) => <tr key={i}>
          <td className="meta">{when(p.ts)}</td>
          <td><b><RepoLink r={p.remote} /></b><div className="meta">{p.ref}</div></td>
          <td style={{ whiteSpace: 'normal' }}><Commits p={p} /></td>
          <td className="meta">{p.session || p.sid.slice(0, 8)}</td></tr>)}
        {!ps.length && <tr><td className="meta">아직 기록된 push 가 없습니다</td></tr>}</>}
    </tbody></table></div>
  </section></div>
}

// ── 이슈·PR: 나에게 할당된 Jira 이슈, 내 PR·리뷰 요청 PR (설정 ⚙ → 연결). API 를 아끼려고 자동 갱신 없이 [새로 고침] ──
const JCAT = { new: 'var(--t-todo)', indeterminate: 'var(--acc)', done: 'var(--t-done)' }  // Jira 상태 분류 → 색
const Ext = ({ u, t }) => <a className="lk" href={u} target="_blank" rel="noopener">{t}</a>
const Off = ({ e }) => <div className="meta">{e} <a className="lk" href="#settings">설정으로 가기</a></div>
// 내 PR·리뷰 요청 두 표의 칸 폭을 고정해 제목 칸이 같은 자리에서 시작하게
const PrTable = ({ ps }) => <div className="tw"><table className="tbl"><tbody>
  {ps.map(p => <tr key={p.url}><td style={{ width: 260 }}><Ext u={p.url} t={`${p.repo}#${p.num}`} /></td>
    <td style={{ whiteSpace: 'normal' }}>{p.title}{p.draft && <span className="pill" style={{ marginLeft: 6 }}>초안</span>}</td>
    <td className="meta" style={{ width: 140 }}>{when(p.updated)}</td></tr>)}
  {!ps.length && <tr><td className="meta">없음</td></tr>}</tbody></table></div>
// 맡기기: 이슈를 고른 폴더의 새 백그라운드 에이전트에게. 폴더는 지난 세션 기록으로 미리 골라 두고, 틀리면 바꾼다
function Assign({ k }) {
  const { G, setMsg, bump } = useApp()
  const g = usePoll('/api/assign?key=' + k, 0)
  const [cwd, setCwd] = useState(null), [busy, setBusy] = useState(false), [res, setRes] = useState('')
  if (!g) return <span className="meta">폴더 찾는 중…</span>
  if (g.error) return <span className="meta">{g.error}</span>
  const v = cwd ?? g.cwd
  const go = async () => {
    setBusy(true)
    const r = await post('/api/assign', { key: k, cwd: v })
    setBusy(false)
    setRes(r.error || r.text)
    if (!r.error) { setMsg(`${k} 를 에이전트에게 맡겼습니다`); bump() }
  }
  return <div className="uadd" style={{ marginTop: 0, alignItems: 'center' }}>
    <span className="meta">일할 폴더</span>
    <select value={v} onChange={e => setCwd(e.target.value)}>{g.recent.map(d => <option key={d} value={d}>{tilde(d, G.home)}</option>)}</select>
    <span className="meta">{v === g.cwd ? g.why : '직접 고름'}</span>
    <button className="sm pri" disabled={busy || !v || !!res} onClick={go}>{busy ? '띄우는 중…' : '새 에이전트에게 맡기기'}</button>
    {res && <pre style={{ width: '100%' }}>{res}</pre>}</div>
}

export function Issues() {
  const [n, setN] = useState(0), [open, setOpen] = useState('')  // open: [맡기기] 를 펼친 이슈 키
  const J = usePoll('/api/jira', 0, [n]), GH = usePoll('/api/github', 0, [n])
  const again = <button className="sm" style={{ marginLeft: 'auto' }} onClick={() => setN(n + 1)}>새로 고침</button>
  return <div className="pg">
    <section className="card"><div className="sh"><h2>Jira</h2>
      <span className="meta">{J?.items ? `나에게 할당된, 끝나지 않은 이슈 ${J.items.length}건` : ''}</span>{again}</div>
      {!J ? <div className="meta">불러오는 중…</div> : J.error ? <Off e={J.error} /> : <div className="tw"><table className="tbl"><tbody>
        <tr><th>키</th><th>제목</th><th>상태</th><th>프로젝트</th><th>업데이트</th><th /></tr>
        {J.items.map(i => <Fragment key={i.key}><tr><td><Ext u={i.url} t={i.key} /></td><td style={{ whiteSpace: 'normal' }}>{i.title}</td>
          <td><span className="pill" style={{ color: JCAT[i.cat] }}>{i.status}</span></td>
          <td className="meta">{i.project} · {i.type}</td><td className="meta">{when(i.updated)}</td>
          <td><button className="sm" onClick={() => setOpen(open === i.key ? '' : i.key)}>{open === i.key ? '닫기' : '맡기기'}</button></td></tr>
          {open === i.key && <tr><td colSpan="6"><Assign k={i.key} /></td></tr>}</Fragment>)}
        {!J.items.length && <tr><td colSpan="6" className="meta">할당된 이슈가 없습니다</td></tr>}</tbody></table></div>}
    </section>
    <section className="card"><div className="sh"><h2>GitHub</h2>
      <span className="meta">{GH?.mine ? `열린 내 PR ${GH.mine.length}건 · 리뷰 요청 ${GH.review.length}건` : ''}</span>{again}</div>
      {!GH ? <div className="meta">불러오는 중…</div> : GH.error ? <Off e={GH.error} /> : <>
        <h4>내 PR</h4><PrTable ps={GH.mine} /><h4>나에게 리뷰 요청</h4><PrTable ps={GH.review} /></>}
    </section>
  </div>
}

// ── 설정: 환경 변수. 쓸 때마다 읽는 값은 화면에서 바꾼다 (DB settings 표) ──
const SRC = { screen:['화면에서 바꿈', 'var(--acc)'], env: ['환경 변수', ''], default: ['기본값', ''] }
// 고칠 수 있는 값: 입력 칸 + 저장. 비우고 저장하면 환경 변수·기본값으로 돌아간다
// 토큰(secret)은 칸을 미리 채우지 않고(서버도 끝 4글자만 준다), 빈 칸 저장 대신 [지우기] 로 지운다
function SettingValue({ c, done, w }) {  // w: 입력 칸 폭 — 연결 칸은 모두 같은 폭으로
  const { G, setMsg } = useApp()
  const [v, setV] = useState(c.src === 'screen' && !c.secret ? c.value : '')
  if (!c.edit) return <code>{tilde(c.value, G.home)}</code>
  const save = async value => {
    const r = await post('/api/config', { name: c.name, value })
    setMsg(r.error || (value ? '저장했습니다' : '지웠습니다'))
    if (r.ok) done()
  }
  return <form className="uadd" style={{ marginTop: 0 }} onSubmit={e => { e.preventDefault(); save(v) }}>
    <input type={c.secret ? 'password' : 'text'} autoComplete="off" value={v} onChange={e => setV(e.target.value)}
      placeholder={c.secret ? c.value || '비어 있음' : c.value} style={{ width: w || (c.secret ? 240 : 160) }} />
    <button className="sm" disabled={c.secret && !v}>저장</button>
    {c.secret && c.src === 'screen' && <button type="button" className="sm" onClick={() => save('')}>지우기</button>}</form>
}

// 연결: GitHub·Jira. [사용] 을 켜야 입력 칸이 보이고 쓰인다 (꺼도 값은 남음). [연결 확인] 은 저장된 토큰으로 내 계정 이름을 받아 온다
const LINKS = [['github', 'GitHub', 'HUDSON_FLEET_GITHUB_ON', ['HUDSON_FLEET_GITHUB_TOKEN']],
  ['jira', 'Jira', 'HUDSON_FLEET_JIRA_ON', ['HUDSON_FLEET_JIRA_SITE', 'HUDSON_FLEET_JIRA_EMAIL', 'HUDSON_FLEET_JIRA_TOKEN']]]
const LINK_NAMES = new Set(LINKS.flatMap(l => [l[2], ...l[3]]))
function Links({ cs, done }) {
  const { setMsg } = useApp()
  const [res, setRes] = useState({})  // 서비스 → 확인 결과 문장
  const toggle = async (name, on) => {
    const r = await post('/api/config', { name, value: on ? '1' : '0' })
    if (r.error) setMsg(r.error)
    done()
  }
  const test = async k => {
    setRes(r => ({ ...r, [k]: '확인 중…' }))
    const x = await post('/api/connect', { service: k })
    setRes(r => ({ ...r, [k]: x.ok ? `연결됨: ${x.who}` : x.error }))
  }
  return <section className="card">
    <div className="sh"><h2>연결</h2><span className="meta">토큰은 이 PC 의 DB 에만 저장합니다. 에이전트는 fleet MCP 로 이 서버를 거쳐 씁니다</span></div>
    {LINKS.map(([k, label, onName, names]) => {
      const on = cs.find(x => x.name === onName)?.value === '1'
      return <div key={k}>
      <h4>{label} <label className="meta" style={{ fontWeight: 400 }}><input type="checkbox" checked={on} onChange={e => toggle(onName, e.target.checked)} /> 사용</label>
        {on && <> <button className="sm" onClick={() => test(k)}>연결 확인</button> <span className="meta" style={{ fontWeight: 400 }}>{res[k]}</span></>}</h4>
      {on && <div className="tw"><table className="tbl"><tbody>{names.map(nm => {
        const c = cs.find(x => x.name === nm)
        return c && <tr key={nm}><td className="meta" style={{ whiteSpace: 'normal', width: '45%', verticalAlign: 'middle' }}>{c.desc}</td><td><SettingValue key={c.src + c.value} c={c} done={done} w={280} /></td></tr>
      })}</tbody></table></div>}</div>
    })}
  </section>
}

export function Settings() {
  const [n, setN] = useState(0)
  const cs = usePoll('/api/config', 0, [n]) || []
  return <div className="pg"><Links cs={cs} done={() => setN(n + 1)} /><section className="card">
    <div className="sh"><h2>설정</h2><span className="meta">입력 칸이 있는 값은 여기서 바꾸면 바로 적용됩니다 (비우고 저장하면 원래대로) · 나머지는 환경 변수로만</span></div>
    {/* 칸 폭을 고정한다 — 긴 값(DB 경로)이 칸을 넓혀 설명 칸이 좁아지면 설명이 글자마다 꺾여 줄 높이가 들쭉날쭉해진다 */}
    <div className="tw"><table className="tbl" style={{ tableLayout: 'fixed', minWidth: 900 }}><tbody>
      <tr><th style={{ width: 360 }}>이름</th><th style={{ width: 320 }}>지금 값</th><th>설명</th></tr>
      {cs.filter(c => !LINK_NAMES.has(c.name)).map(c => <tr key={c.name}>
        <td><code>{c.name}</code> <span className="pill" style={{ fontSize: 'var(--fs-xs)', color: SRC[c.src]?.[1] }}>{SRC[c.src]?.[0]}</span></td>
        <td style={{ whiteSpace: 'normal', wordBreak: 'break-all' }}><SettingValue key={c.src + c.value} c={c} done={() => setN(n + 1)} /></td>
        <td className="meta" style={{ whiteSpace: 'normal' }}>{c.desc}</td></tr>)}
    </tbody></table></div>
    <h4>환경 변수로 바꾸는 방법 (포트·DB 경로)</h4>
    <ol className="meta" style={{ margin: 0, paddingLeft: 20, lineHeight: 1.8 }}>
      <li><code>~/.claude/settings.json</code> 의 <code>"env"</code> 에 적습니다. Claude Code 가 MCP 서버에 넘겨 줍니다. (서버만 쓰는 값은 <code>~/.local/share/hudson-fleet/.env</code> 에 적어도 됩니다)</li>
      <li>Claude Code 세션을 모두 닫았다 다시 열면, 새로 리더가 된 MCP 서버가 새 값으로 대시보드를 띄웁니다.</li></ol>
    <pre style={{ marginTop: 10 }}>{'// ~/.claude/settings.json (예시)\n' + JSON.stringify({ env: { HUDSON_FLEET_PORT: '8766' } }, null, 2)}</pre>
  </section></div>
}
