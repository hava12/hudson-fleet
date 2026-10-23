import { useState } from 'react'
import { TaskSum, fmtTok, post, tilde, useApp, usePoll, when } from './lib'

export const REASON = { switched: '세션 전환 (/clear·/resume)', exited: '프로세스 종료', stopped: '중지', failed: '실패', completed: '완료', gone: '사라짐' }

// ── 세션 기록: 끝난 세션 (sessions 1 : session_tasks N) ──
export function History() {
  const { G, ver, openSide } = useApp()
  const [n, setN] = useState(0)  // 새로 고침
  const H = usePoll('/api/sessions?status=closed&limit=200', 0, [ver, n])
  return <div className="pg"><section className="card">
    <div className="sh"><h2>끝난 세션</h2>
      {H && <span className="meta">{H.length}개 · 토큰 합계 {fmtTok(H.reduce((t, s) => t + (s.tokens || 0), 0))}</span>}
      <button className="sm" style={{ marginLeft: 'auto' }} onClick={() => setN(n + 1)}>새로 고침</button></div>
    <div className="tw"><table className="tbl"><tbody>
      <tr><th>끝난 시각</th><th>세션</th><th>종료 이유</th><th>작업</th><th>토큰</th></tr>
      {H?.map(s => <tr key={s.sid}>
        <td className="meta">{when(s.ended_at)}</td>
        <td><a className="lk" onClick={() => openSide({ type: 'history', sid: s.sid })}>{s.title || s.name || s.sid.slice(0, 8)}</a>
          <div className="meta" title={s.cwd}>{tilde(s.cwd, G.home)} · {s.kind === 'background' ? '백그라운드' : s.app || '대화형'}</div></td>
        <td><span className="pill">{REASON[s.end_reason] || s.end_reason}</span></td>
        <td><TaskSum ts={s.tasks} /></td><td className="meta">{fmtTok(s.tokens)}</td></tr>)}
      {H && !H.length && <tr><td colSpan="5" className="meta">아직 기록된 세션이 없습니다</td></tr>}
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

// ── 설정: 로그인 계정 + 환경 변수 (읽기 전용) ──
function Accounts() {
  const { setMsg } = useApp()
  const [n, setN] = useState(0)
  const us = usePoll('/api/users', 0, [n]) || []
  const save = async b => {
    const r = await post('/api/users', b)
    if (r.error) return setMsg(r.error), false
    setN(n + 1)
    return true
  }
  const add = async e => {
    e.preventDefault()
    const f = new FormData(e.target)
    if (await save({ name: f.get('name'), password: f.get('password') })) e.target.reset()
  }
  return <section className="card">
    <div className="sh"><h2>로그인 계정</h2><span className="meta">모두 같은 권한입니다</span></div>
    <div className="tw"><table className="tbl"><tbody>
      <tr><th>아이디</th><th>만든 때</th><th /></tr>
      {us.map(u => <tr key={u.name}><td><b>{u.name}</b></td>
        <td className="meta">{u.env ? '.env 관리자 (HUDSON_FLEET_ADMIN_*)' : when(u.created_at)}</td>
        <td>{!u.env && <button className="sm danger" onClick={() => confirm(`${u.name} 계정을 지울까요?`) && save({ name: u.name, delete: true })}>삭제</button>}</td></tr>)}
    </tbody></table></div>
    <form className="uadd" onSubmit={add}>
      <input name="name" placeholder="아이디" autoComplete="off" required />
      <input name="password" type="password" placeholder="비밀번호 (8자 이상)" autoComplete="new-password" minLength={8} required />
      <button className="pri">계정 추가</button></form>
    <PasswordForm />
  </section>
}

function PasswordForm() {
  const { me, setMsg } = useApp()
  const submit = async e => {
    e.preventDefault()
    const f = new FormData(e.target), t = e.target
    const r = await post('/api/password', { old: f.get('old'), new: f.get('new') })
    setMsg(r.error || '비밀번호를 바꿨습니다')
    if (r.ok) t.reset()
  }
  return <><h4>내 비밀번호 바꾸기 · {me}</h4>
    <form className="uadd" onSubmit={submit}>
      <input name="old" type="password" placeholder="지금 비밀번호" autoComplete="current-password" required />
      <input name="new" type="password" placeholder="새 비밀번호 (8자 이상)" autoComplete="new-password" minLength={8} required />
      <button>바꾸기</button></form></>
}

// 내 API 키: PC 의 MCP 서버·수집기가 서버에 "누구인지" 알릴 때 쓴다. 원문은 발급 직후 한 번만 보인다
function ApiKeys() {
  const { setMsg } = useApp()
  const [n, setN] = useState(0)
  const [fresh, setFresh] = useState('')
  const ks = usePoll('/api/keys', 0, [n]) || []
  const issue = async () => {
    const r = await post('/api/keys', {})
    r.key ? setFresh(r.key) : setMsg(r.error)
    setN(n + 1)
  }
  const del = async k => {
    if (!confirm(`${k.hint} 키를 지울까요? 이 키를 쓰는 PC 는 기록을 보내지 못합니다.`)) return
    const r = await post('/api/keys', { id: k.id, delete: true })
    if (r.error) setMsg(r.error)
    setN(n + 1)
  }
  return <section className="card">
    <div className="sh"><h2>API 키</h2><span className="meta">내 PC 의 MCP 서버가 이 서버에 기록을 보낼 때 "누구인지" 알리는 키입니다</span>
      <button className="sm pri" style={{ marginLeft: 'auto' }} onClick={issue}>새 키 발급</button></div>
    {fresh && <div className="kfresh">
      <b>지금만 볼 수 있습니다. 복사해 두세요.</b>
      <pre>{'// ~/.claude/settings.json\n' + JSON.stringify({ env: { HUDSON_FLEET_URL: location.origin, HUDSON_FLEET_KEY: fresh } }, null, 2)}</pre>
      <button className="sm" onClick={() => navigator.clipboard.writeText(fresh).then(() => setMsg('키를 복사했습니다'))}>키 복사</button>{' '}
      <button className="sm" onClick={() => setFresh('')}>닫기</button></div>}
    <div className="tw"><table className="tbl"><tbody>
      <tr><th>키</th><th>만든 때</th><th>마지막 사용</th><th /></tr>
      {ks.map(k => <tr key={k.id}><td><code>{k.hint}</code></td><td className="meta">{when(k.created_at)}</td>
        <td className="meta">{k.last_used ? when(k.last_used) : '아직 안 씀'}</td>
        <td><button className="sm danger" onClick={() => del(k)}>삭제</button></td></tr>)}
      {!ks.length && <tr><td colSpan="4" className="meta">발급한 키가 없습니다</td></tr>}
    </tbody></table></div>
  </section>
}

const SRC = { screen:['화면에서 바꿈', 'var(--acc)'], env: ['환경 변수', ''], default: ['기본값', ''] }
// 고칠 수 있는 값: 입력 칸 + 저장. 비우고 저장하면 환경 변수·기본값으로 돌아간다
function SettingValue({ c, done }) {
  const { G, setMsg } = useApp()
  const [v, setV] = useState(c.src === 'screen' ? c.value : '')
  if (!c.edit) return <code>{tilde(c.value, G.home)}</code>
  const save = async e => {
    e.preventDefault()
    const r = await post('/api/config', { name: c.name, value: v })
    setMsg(r.error || '저장했습니다')
    if (r.ok) done()
  }
  return <form className="uadd" style={{ marginTop: 0 }} onSubmit={save}>
    <input value={v} placeholder={c.value} onChange={e => setV(e.target.value)} style={{ width: 160 }} />
    <button className="sm">저장</button></form>
}

export function Settings() {
  const [n, setN] = useState(0)
  const cs = usePoll('/api/config', 0, [n]) || []
  const port = cs.find(c => c.name === 'HUDSON_FLEET_PORT')?.value
  return <div className="pg"><Accounts /><ApiKeys /><section className="card">
    <div className="sh"><h2>설정</h2><span className="meta">입력 칸이 있는 값은 여기서 바꾸면 바로 적용됩니다 (비우고 저장하면 원래대로) · 나머지는 환경 변수로만</span></div>
    <div className="tw"><table className="tbl"><tbody>
      <tr><th>이름</th><th>지금 값</th><th>설명</th></tr>
      {cs.map(c => <tr key={c.name}>
        <td><code>{c.name}</code> <span className="pill" style={{ fontSize: 11, color: SRC[c.src]?.[1] }}>{SRC[c.src]?.[0]}</span></td>
        <td><SettingValue key={n} c={c} done={() => setN(n + 1)} /></td>
        <td className="meta" style={{ whiteSpace: 'normal' }}>{c.desc}</td></tr>)}
    </tbody></table></div>
    <h4>환경 변수로 바꾸는 방법 (포트·DB 경로·관리자 아이디)</h4>
    <ol className="meta" style={{ margin: 0, paddingLeft: 20, lineHeight: 1.8 }}>
      <li><code>~/.claude/settings.json</code> 의 <code>"env"</code> 에 적습니다. Claude Code 가 훅·MCP 서버에 넘겨 줍니다. (서버만 쓰는 값은 <code>~/.local/share/hudson-fleet/.env</code> 에 적어도 됩니다)</li>
      <li>떠 있는 대시보드 서버를 끕니다 (<code>lsof -ti :{port} | xargs kill</code>).</li>
      <li>새 Claude Code 세션을 시작하면 SessionStart 훅이 새 값으로 서버를 띄웁니다.</li></ol>
    <pre style={{ marginTop: 10 }}>{'// ~/.claude/settings.json (예시)\n' + JSON.stringify({ env: { HUDSON_FLEET_PORT: '8766' } }, null, 2)}</pre>
  </section></div>
}
