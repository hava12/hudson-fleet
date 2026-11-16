import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 공통 부품 검사: 화면 코드는 button.sm·.pill·.card·.tbl·details 를 직접 쓰지 않고 src/ui.jsx 의 부품(Button·Pill·Card·Table·Collapsible)을 쓴다
const RAW = /className="(?:sm|sm \w+|pill|card|card \w+|tbl)"|<details[\s>]/
// 디자인 규칙(web/CLAUDE.md): 색 값과 숫자 글자 크기는 이름표(var(--…))로만. 값은 style.css 의 :root(밝은 화면)와 tokens.css(Figma)에만 둔다
const JSX_COLOR = /['"`](?:#(?:[0-9a-f]{3,4}|[0-9a-f]{6}|[0-9a-f]{8})['"`]|(?:rgba?|hsla?)\()|fontSize: *['"`]?\d/i
const CSS_COLOR = /:[^;{}]*?(#[0-9a-f]{3,8}\b|(?:rgba?|hsla?)\()|(font-size:\s*\d+\w*)/i
const blank = s => s.replace(/[^\n]/g, ' ')  // 줄 번호가 맞게 지운 자리를 빈칸으로
const uiCheck = { name: 'ui-check', enforce: 'pre', transform(code, id) {
  const at = (m, why) => m && this.error(`${id.split('/src/')[1].split('?')[0]}:${code.slice(0, m.index).split('\n').length} — ${(m[1] || m[2] || m[0]).trim()} ${why}`)
  if (/\/src\/(?!ui\.jsx)[^/]+\.jsx$/.test(id)) at(RAW.exec(code), '대신 ui.jsx 부품을 쓰세요')
  if (/\/src\/[^/]+\.jsx$/.test(id)) at(JSX_COLOR.exec(code), '대신 이름표 var(--…)를 쓰세요 (web/CLAUDE.md)')
  // 주석·:root·mask(#000 은 색이 아니라 모양) 는 빼고 본다
  if (/\/src\/style\.css(\?|$)/.test(id)) at(CSS_COLOR.exec(code.replace(/\/\*[\s\S]*?\*\/|:root\{[^}]*\}|mask:[^;}]*/g, blank)), '대신 이름표 var(--…)를 쓰세요 (web/CLAUDE.md)')
} }

// 빌드 결과는 저장소 루트의 dist/ — 플러그인 설치는 git 그대로 받으므로 커밋해 둔다
export default defineConfig({
  plugins: [uiCheck, react()],
  build: { outDir: '../dist', emptyOutDir: true, chunkSizeWarningLimit: 1000 },  // 로컬에서만 여는 화면이라 한 덩어리(cytoscape 포함)로 둔다
  // npm run dev: API 는 떠 있는 대시보드 서버로. POST 출처 검사를 통과하도록 Origin 을 서버 주소로 바꾼다
  server: { proxy: { '/api': { target: 'http://127.0.0.1:8765', headers: { origin: 'http://127.0.0.1:8765' } } } },
})
