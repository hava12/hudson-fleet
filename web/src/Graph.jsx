import { useEffect, useState } from 'react'
import cytoscape from 'cytoscape'
import dagre from 'cytoscape-dagre'

cytoscape.use(dagre)

const ctx = document.createElement('canvas').getContext('2d')
ctx.font = '12px system-ui'
export const textW = s => Math.ceil(ctx.measureText(s).width) + 24  // 이름을 상자 안에 넣을 폭

// 그래프 영역 높이를 내용에 맞춘다. 확대는 1배까지 — 노드가 적을 때 글씨가 커지지 않게
export function fitBox(c, max) {
  const el = c.container(), h = c.elements().boundingBox().h
  el.style.height = Math.min(Math.max(h + 48, 374), max) + 'px'
  c.resize()
  c.fit(undefined, 24)
}

// ref 의 div 에 cytoscape 를 띄운다. 폭이 바뀌면(오른쪽 패널 열고 닫기) 다시 맞춘다
export function useCy(ref, opts, max) {
  const [cy, setCy] = useState(null)
  useEffect(() => {
    const c = cytoscape({ container: ref.current, wheelSensitivity: 0.3, maxZoom: 1, minZoom: 0.3, ...opts })
    let w = ref.current.clientWidth
    const ro = new ResizeObserver(() => { const nw = ref.current?.clientWidth; if (nw && nw !== w) { w = nw; fitBox(c, max) } })
    ro.observe(ref.current)
    setCy(c)
    return () => { ro.disconnect(); c.destroy() }
  }, [])
  return cy
}
