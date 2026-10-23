import { useState } from 'react'
import { TaskSum, fmtTok, tilde, useApp, usePoll, when } from './lib'

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
      <span className="meta">{ps ? `Claude 가 실행한 git push ${ps.length}건 · 커밋 ${ps.reduce((a, p) => a + p.commits.length, 0)}개` : 'Claude 가 실행한 git push 만 모읍니다'}</span>
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

// ── 설정: 환경 변수 (읽기 전용) ──
export function Settings() {
  const { G } = useApp()
  const cs = usePoll('/api/config') || []
  const port = cs.find(c => c.name === 'HUDSON_FLEET_PORT')?.value
  return <div className="pg"><section className="card">
    <div className="sh"><h2>설정</h2><span className="meta">모두 환경 변수로 정합니다 · 이 화면은 지금 서버에 적용된 값입니다</span></div>
    <div className="tw"><table className="tbl"><tbody>
      <tr><th>환경 변수</th><th>지금 값</th><th>설명</th></tr>
      {cs.map(c => <tr key={c.name}>
        <td><code>{c.name}</code></td>
        <td><code>{tilde(c.value, G.home)}</code> <span className="pill" style={{ fontSize: 11 }}>{c.set ? '설정됨' : '기본값'}</span></td>
        <td className="meta" style={{ whiteSpace: 'normal' }}>{c.desc}</td></tr>)}
    </tbody></table></div>
    <h4>바꾸는 방법</h4>
    <ol className="meta" style={{ margin: 0, paddingLeft: 20, lineHeight: 1.8 }}>
      <li><code>~/.claude/settings.json</code> 의 <code>"env"</code> 에 적습니다. Claude Code 가 훅·MCP 서버에 넘겨 줍니다.</li>
      <li>떠 있는 대시보드 서버를 끕니다 (<code>lsof -ti :{port} | xargs kill</code>).</li>
      <li>새 Claude Code 세션을 시작하면 SessionStart 훅이 새 값으로 서버를 띄웁니다.</li></ol>
    <pre style={{ marginTop: 10 }}>{'// ~/.claude/settings.json (예시)\n' + JSON.stringify({ env: { HUDSON_FLEET_AUTO_SUMMARY: '0', HUDSON_FLEET_RETENTION_DAYS: '90' } }, null, 2)}</pre>
  </section></div>
}
