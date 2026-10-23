import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 빌드 결과는 저장소 루트의 dist/ — 플러그인 설치는 git 그대로 받으므로 커밋해 둔다
export default defineConfig({
  plugins: [react()],
  build: { outDir: '../dist', emptyOutDir: true, chunkSizeWarningLimit: 1000 },  // 로컬에서만 여는 화면이라 한 덩어리(cytoscape 포함)로 둔다
  // npm run dev: API 는 떠 있는 대시보드 서버로. POST 출처 검사를 통과하도록 Origin 을 서버 주소로 바꾼다
  server: { proxy: { '/api': { target: 'http://127.0.0.1:8765', headers: { origin: 'http://127.0.0.1:8765' } } } },
})
