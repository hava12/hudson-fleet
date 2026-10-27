import { useEffect, useState } from 'react'
import cytoscape from 'cytoscape'
import dagre from 'cytoscape-dagre'

cytoscape.use(dagre)

const ctx = document.createElement('canvas').getContext('2d')
ctx.font = '12px system-ui'
export const textW = s => Math.ceil(ctx.measureText(s).width) + 24  // 이름을 상자 안에 넣을 폭

// 그래프를 영역 안에 다 보이게 맞춘다. 확대는 1배까지 — 노드가 적을 때 글씨가 커지지 않게
// max 를 주면 영역 높이도 내용에 맞춘다 (MCP 서버: 한 번 그리면 거의 안 바뀜). 현황은 높이를 CSS 로 고정하고 배율로만 맞춘다
export function fitBox(c, max) {
  if (max) c.container().style.height = Math.min(Math.max(c.elements().boundingBox().h + 48, 374), max) + 'px'
  c.resize()
  c.fit(undefined, 24)
}

// ref 의 div 에 cytoscape 를 띄운다. 크기가 바뀌면(오른쪽 패널 열고 닫기, 창 높이) 다시 맞춘다
export function useCy(ref, opts, max) {
  const [cy, setCy] = useState(null)
  useEffect(() => {
    const c = cytoscape({ container: ref.current, wheelSensitivity: 0.3, maxZoom: 1, minZoom: 0.3, ...opts })
    const size = () => ref.current ? ref.current.clientWidth + 'x' + ref.current.clientHeight : ''
    let s = size()
    const ro = new ResizeObserver(() => { const n = size(); if (n && n !== s) { s = n; fitBox(c, max) } })
    ro.observe(ref.current)
    setCy(c)
    return () => { ro.disconnect(); c.destroy() }
  }, [])
  return cy
}
