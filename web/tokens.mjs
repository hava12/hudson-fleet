// Figma 변수 내보내기(Export modes) JSON → src/tokens.css
// 쓰는 법: node web/tokens.mjs ~/Downloads/Dark.tokens.json "~/Downloads/Mode 1.tokens.json"
//   파일 이름이 Dark 로 시작하면 어두운 화면 칸, 나머지는 공통 칸(:root)에 넣는다.
//   이름은 Figma 변수의 코드 이름(codeSyntax WEB, var(--acc))을 쓰고, 없으면 묶음 경로를 - 로 잇는다.
// 인자 없이 돌리면 작은 자체 검사만 한다.
import { readFileSync, writeFileSync } from 'node:fs'
import { basename } from 'node:path'
import assert from 'node:assert'

const HEAD = '/* Figma 변수에서 만든 파일 — 손으로 고치지 말고 Figma 에서 고친 뒤 node web/tokens.mjs 로 다시 만든다.\n   밝은 화면 색은 Figma 에 모드가 없어(무료 요금제) style.css 맨 위에 그대로 둔다 */'
const hex2 = n => Math.round(n * 255).toString(16).padStart(2, '0')

function leaves(o, path = [], out = []) {  // $value 가 있는 칸이 변수 하나
  for (const [k, v] of Object.entries(o)) {
    if (k.startsWith('$') || !v || typeof v !== 'object') continue
    '$value' in v ? out.push([path.concat(k), v]) : leaves(v, path.concat(k), out)
  }
  return out
}
const nameOf = (p, t) => (t.$extensions?.['com.figma']?.codeSyntax?.WEB || '').match(/--[\w-]+/)?.[0] || '--' + p.join('-')

function value(t, names) {
  const v = t.$value
  if (typeof v === 'string' && /^\{.+\}$/.test(v)) return `var(${names[v.slice(1, -1)] || '--' + v.slice(1, -1).replaceAll('.', '-')})`  // 별칭 → 그 이름표
  if (t.$type === 'color') {
    const c = typeof v === 'string' ? { hex: v } : v
    const h = (c.hex || '#' + c.components.map(hex2).join('')).toLowerCase()
    return (c.alpha ?? 1) < 1 && h.length === 7 ? h + hex2(c.alpha) : h
  }
  if (typeof v === 'number') return v + 'px'  // 이 파일의 숫자 변수는 글자 크기·모서리라 모두 px
  if (v && typeof v === 'object' && 'unit' in v) return v.value + v.unit
  return typeof v === 'string' ? v : null  // 참/거짓 변수는 CSS 에 쓰지 않는다
}

export function build(files) {  // [[파일 이름, JSON]] → tokens.css 글
  const all = files.flatMap(([f, j]) => leaves(j).map(([p, t]) => ({ dark: /^dark/i.test(f), p, t, n: nameOf(p, t) })))
  const names = Object.fromEntries(all.map(x => [x.p.join('.'), x.n]))
  const base = [], dark = []
  for (const x of all) { const v = value(x.t, names); if (v != null) (x.dark ? dark : base).push(`  ${x.n}:${v};`) }
  return [HEAD, base.length && `:root{\n${base.join('\n')}\n}`, dark.length && `@media (prefers-color-scheme:dark){:root{\n${dark.join('\n')}\n}}`].filter(Boolean).join('\n') + '\n'
}

const args = process.argv.slice(2)
if (!args.length) {
  const fig = w => ({ 'com.figma': { codeSyntax: { WEB: `var(--${w})` } } })
  const out = build([
    ['Dark.tokens.json', { acc: { $type: 'color', $value: { colorSpace: 'srgb', components: [0.7, 0.77, 1], alpha: 1, hex: '#B4C5FF' }, $extensions: fig('acc') },
      'dis-bg': { $type: 'color', $value: { colorSpace: 'srgb', components: [1, 1, 1], alpha: 0.12 }, $extensions: fig('dis-bg') },
      grp: { link: { $type: 'color', $value: '{acc}' } } }],
    ['Mode 1.tokens.json', { 'fs-m': { $type: 'number', $value: 15, $extensions: fig('fs-m') } }]])
  for (const s of [':root{\n  --fs-m:15px;\n}', '--acc:#b4c5ff;', '--dis-bg:#ffffff1f;', '--grp-link:var(--acc);', '@media (prefers-color-scheme:dark)']) assert(out.includes(s), s)
  console.log('자체 검사 통과\n쓰는 법: node web/tokens.mjs <내보낸 .tokens.json 파일들>')
} else {
  const css = build(args.map(f => [basename(f), JSON.parse(readFileSync(f, 'utf8'))]))
  writeFileSync(new URL('src/tokens.css', import.meta.url), css)
  console.log(`src/tokens.css 에 ${(css.match(/^ {2}--/gm) || []).length}개를 썼다`)
}
