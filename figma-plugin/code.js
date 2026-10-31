// hudson-fleet DS builder — Untitled(BASE) 파일의 부품(1차)과 대시보드에만 있는 부품(2차)을 hudson-fleet 이름표로 만든다.
// 2차 부품의 치수·색은 web/src/style.css 값을 그대로 옮겼다.
// 실행: Figma 데스크톱 앱 → "hudson-fleet design system" 파일 → Plugins → Development → hudson-fleet DS builder
// 여러 번 실행해도 된다. 이미 있는 것은 건너뛰고 없는 것만 만든다. 확인 화면(Review)은 매번 새로 만든다.
// 결과는 섹션 위 "Build Log" 글과 실행 끝 알림에 남는다.

const FONT = 'Noto Sans KR';
const LOG = [];
const V = {};   // 변수 이름 → Variable
const STY = {}; // 글자 스타일 이름 → TextStyle
let SEC;        // "Main Components" 섹션

// #2563eb 씨앗의 M3 어두운 묶음에서 계산한 추가 이름표 (상태 바탕, 올렸을 때·눌렀을 때)
const NEW_VARS = {
  'acc-bg': ['primaryContainer', '#324478', ['FRAME_FILL', 'SHAPE_FILL']],
  'on-acc-bg': ['onPrimaryContainer', '#dbe1ff', ['TEXT_FILL']],
  'ok-bg': ['custom success colorContainer', '#005320', ['FRAME_FILL', 'SHAPE_FILL']],
  'wait-bg': ['custom wait colorContainer', '#6e3900', ['FRAME_FILL', 'SHAPE_FILL']],
  'bad-bg': ['errorContainer', '#93000a', ['FRAME_FILL', 'SHAPE_FILL']],
  'on-bad-bg': ['onErrorContainer', '#ffdad6', ['TEXT_FILL']],
  'acc-hover': ['primary + onPrimary 8% (hover)', '#a8b9f2', ['FRAME_FILL', 'SHAPE_FILL']],
  'acc-press': ['primary + onPrimary 10% (pressed)', '#a5b6ef', ['FRAME_FILL', 'SHAPE_FILL']],
  'press': ['surfaceContainerHighest (pressed)', '#34343a', ['FRAME_FILL', 'SHAPE_FILL']],
};

// Lucide 아이콘 (24 기준 경로, 16px 로 그린다)
const ICONS = {
  check: '<path d="M20 6 9 17l-5-5"/>',
  minus: '<path d="M5 12h14"/>',
  x: '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
  search: '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
  'loader-circle': '<path d="M21 12a9 9 0 1 1-6.219-8.56"/>',
  'circle-check': '<circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/>',
  'circle-alert': '<circle cx="12" cy="12" r="10"/><path d="M12 8v4"/><path d="M12 16h.01"/>',
  folder: '<path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"/>',
  'chevron-down': '<path d="m6 9 6 6 6-6"/>',
  'chevron-right': '<path d="m9 18 6-6-6-6"/>',
  'arrow-down': '<path d="M12 5v14"/><path d="m19 12-7 7-7-7"/>',
  'corner-down-right': '<path d="m15 10 5 5-5 5"/><path d="M4 4v7a4 4 0 0 0 4 4h12"/>',
};

// 굵은 글자 스타일 (CSS 의 b·font-weight:600 자리). 이름 → [글자 크기 이름표, 줄 높이 %, 쓰는 곳]
const NEW_STYLES = {
  value: ['fs-xl', 140, '지표 숫자 (Metric Card)'],
  'strong-l': ['fs-l', 130, '현황 숫자 칸의 숫자 (.stat b)'],
  'strong-s': ['fs-s', 160, '세션 이름·사용량 숫자 (.ncard b, .hu b)'],
  'strong-xs': ['fs-xs', 160, '흐름도 번호·물음표 (.fk, .tip)'],
};
const SIZE = { 'fs-xs': 12, 'fs-s': 13, 'fs-m': 15, 'fs-l': 18, 'fs-xl': 20 };

// 섹션 안 세로 순서: 왼쪽 열 = 1차(공통 부품), 오른쪽 열 = 2차(대시보드 부품)
const ORDER = ['Button', 'Input', 'Field', 'Checkbox', 'Pill', 'Card', 'Table Row', 'Table Toolbar', 'Pagination',
  'State Message', 'Notification', 'Dialog', 'Nav Item', 'Tab', 'Breadcrumbs', 'Metric Card', 'Top Bar', 'Icons'];
const ORDER2 = ['Select', 'Menu Item', 'Menu', 'Tooltip', 'Progress Bar', 'Usage Meter', 'Status Dot', 'Legend', 'Stat',
  'Toggle Button', 'Task Row', 'Collapsible', 'Key Value', 'Code Block', 'Flow Step', 'Flow', 'Session Card', 'Side Panel', 'Banner'];
// 현황 상태 점: 이름 → [색 이름표, 글, 네모(프로젝트·서브에이전트)]
const DOTS = { Work: ['ok', '작업 중'], Wait: ['wait', '입력 대기'], Idle: ['idle', '쉬는 중'], Done: ['off', '끝남'], Fail: ['bad', '실패'],
  Project: ['node-proj', '프로젝트', true], Agent: ['node-agent', '서브에이전트', true] };

// ── 작은 도구 ──
const rgb = h => ({ r: parseInt(h.slice(1, 3), 16) / 255, g: parseInt(h.slice(3, 5), 16) / 255, b: parseInt(h.slice(5, 7), 16) / 255 });
function paint(name) {
  if (!V[name]) throw new Error('이름표 없음: ' + name);
  return [figma.variables.setBoundVariableForPaint({ type: 'SOLID', color: { r: 0, g: 0, b: 0 } }, 'color', V[name])];
}
function radius(n, name) { for (const c of ['topLeftRadius', 'topRightRadius', 'bottomLeftRadius', 'bottomRightRadius']) n.setBoundVariable(c, V[name]); }
function border(n, color = 'line', w = 1, align = 'INSIDE') { n.strokes = paint(color); n.strokeWeight = w; n.strokeAlign = align; }
function pad(n, y, x) { n.paddingTop = n.paddingBottom = y; n.paddingLeft = n.paddingRight = x; }
function auto(n, dir, { gap = 0, py = 0, px = 0, align, width } = {}) {
  n.layoutMode = dir;
  if (width) {
    n.resize(width, 10);
    n.primaryAxisSizingMode = dir === 'HORIZONTAL' ? 'FIXED' : 'AUTO';
    n.counterAxisSizingMode = dir === 'HORIZONTAL' ? 'AUTO' : 'FIXED';
  } else { n.primaryAxisSizingMode = 'AUTO'; n.counterAxisSizingMode = 'AUTO'; }
  n.itemSpacing = gap; pad(n, py, px);
  if (align) n.counterAxisAlignItems = align;
  return n;
}
function box(name, dir, opts) { const f = figma.createFrame(); f.name = name; f.fills = []; f.clipsContent = false; return auto(f, dir, opts); }
function comp(name, dir, opts) { const c = figma.createComponent(); c.name = name; c.fills = []; return auto(c, dir, opts); }
function card(n) { n.fills = paint('card'); border(n); radius(n, 'r-m'); return n; }
async function text(chars, style, color, name = 'Text') {
  if (!STY[style]) throw new Error('글자 스타일 없음: ' + style);
  const t = figma.createText(); t.name = name;
  await t.setTextStyleIdAsync(STY[style].id);
  t.characters = chars; t.fills = paint(color);
  return t;
}
function fill(child) { child.layoutSizingHorizontal = 'FILL'; if (child.type === 'TEXT') child.textAutoResize = 'HEIGHT'; return child; }
function find(type, name) { return SEC.findOne(n => n.type === type && n.name === name); }
function variant(setName, props) {
  const s = find('COMPONENT_SET', setName);
  if (!s) throw new Error(setName + ' 부품 없음');
  const v = s.children.find(c => c.name === props);
  if (!v) throw new Error(`${setName} 에 ${props} 없음`);
  return v;
}
function key(owner, prop) { return Object.keys(owner.componentPropertyDefinitions).find(k => k.split('#')[0] === prop); }
function icon(name, color) {
  const c = find('COMPONENT', 'Icon/' + name);
  if (!c) throw new Error('아이콘 없음: ' + name);
  const i = c.createInstance();
  for (const n of i.findAll(n => 'strokes' in n && n.strokes.length)) n.strokes = paint(color);
  return i;
}
function btn(label, props = 'Style=Default, Size=Small, State=Default') {
  const i = variant('Button', props).createInstance();
  i.setProperties({ [key(find('COMPONENT_SET', 'Button'), 'Label')]: label });
  return i;
}
function input(value, props = 'Size=Small, State=Default') {
  const i = variant('Input', props).createInstance();
  i.setProperties({ [key(find('COMPONENT_SET', 'Input'), 'Value')]: value });
  return i;
}
function combine(vs, name, cellW, cellH, cols = vs.length) {
  const set = figma.combineAsVariants(vs, SEC);
  set.name = name;
  vs.forEach((c, i) => { c.x = 16 + (i % cols) * cellW; c.y = 16 + Math.floor(i / cols) * cellH; });
  set.resize(16 + Math.min(cols, vs.length) * cellW, 16 + Math.ceil(vs.length / cols) * cellH);
  return set;
}
function linkText(owner, nodes, prop, value) {
  const k = owner.addComponentProperty(prop, 'TEXT', value);
  for (const n of nodes) n.componentPropertyReferences = { characters: k };
  return k;
}
// 떠 있는 상자 그림자 (CSS 0 6px 20px rgba(0,0,0,.25) — 그림자는 이름표 예외)
function shadow(n) { n.effects = [{ type: 'DROP_SHADOW', color: { r: 0, g: 0, b: 0, a: 0.25 }, offset: { x: 0, y: 6 }, radius: 20, spread: 0, visible: true, blendMode: 'NORMAL' }]; }
function fixed(n, w, h) { n.resize(w, h); return n; }
// 막대: 옅은 바탕 위에 pct 만큼 색을 채운다 (.bar · .ncard .bar)
function bar(n, w, h, color, pct, r = 'r-full') {
  fixed(n, w, h); n.fills = paint('soft'); radius(n, r); n.clipsContent = true;
  const f = figma.createRectangle(); f.name = 'Fill'; f.resize(Math.round(w * pct), h); f.fills = paint(color); radius(f, r);
  n.appendChild(f);
  return n;
}
// 이름-값 줄 (dl): 이름 칸은 keyW 로 고정, 값 칸은 남은 폭. 값에 글 대신 프레임(막대 줄)을 넣을 수 있다
async function kvRows(parent, rows, style, keyW) {
  for (const [k, v] of rows) {
    const r = box('Row', 'HORIZONTAL', { gap: 12, align: 'CENTER' });
    parent.appendChild(r); fill(r);
    const kt = await text(k, style, 'mute', 'Key');
    r.appendChild(kt); kt.textAutoResize = 'HEIGHT'; kt.resize(keyW, kt.height);
    const vt = typeof v === 'string' ? await text(v, style, 'fg', 'Value') : v;
    r.appendChild(vt); fill(vt);
  }
}

// 한 덩어리씩 만든다. 실패하면 그 덩어리에서 만든 것만 지우고 다음으로 넘어간다.
async function part(name, fn) {
  const made = [];
  try {
    const r = await fn(n => (made.push(n), n));
    LOG.push(`[OK] ${name}${r ? ' - ' + r : ''}`);
  } catch (e) {
    for (const n of made.reverse()) if (!n.removed) n.remove();
    LOG.push(`[실패] ${name} - ${e.message}`);
  }
}

async function main() {
  const page = figma.root.children.find(p => p.name === 'Components') || figma.currentPage;
  await figma.setCurrentPageAsync(page);
  SEC = page.findOne(n => n.type === 'SECTION' && n.name === 'Main Components');
  if (!SEC) return 'hudson-fleet design system 파일(Components 페이지)에서 실행하세요';
  for (const v of await figma.variables.getLocalVariablesAsync()) V[v.name] = v;
  for (const s of await figma.getLocalTextStylesAsync()) STY[s.name] = s;
  for (const st of ['Regular', 'Medium', 'Bold']) await figma.loadFontAsync({ family: FONT, style: st });
  await figma.loadFontAsync({ family: 'Inter', style: 'Regular' });

  await part('이름표', async () => {
    const col = (await figma.variables.getLocalVariableCollectionsAsync()).find(c => c.name === 'Color');
    const mode = col.modes[0].modeId;
    let n = 0;
    for (const [name, [role, hex, scopes]] of Object.entries(NEW_VARS)) {
      if (V[name]) continue;
      const v = figma.variables.createVariable(name, col, 'COLOR');
      v.setValueForMode(mode, rgb(hex)); v.scopes = scopes;
      v.setVariableCodeSyntax('WEB', `var(--${name})`); v.description = 'M3 ' + role;
      V[name] = v; n++;
    }
    return `${n}개 추가`;
  });

  await part('글자 스타일', async () => {
    let n = 0;
    for (const [name, [size, lh, use]] of Object.entries(NEW_STYLES)) {
      if (STY[name]) continue;
      const t = figma.createTextStyle();
      t.name = name; t.fontName = { family: FONT, style: 'Bold' }; t.fontSize = SIZE[size];
      t.lineHeight = { unit: 'PERCENT', value: lh };
      t.setBoundVariable('fontSize', V[size]); t.description = use;
      STY[name] = t; n++;
    }
    return `${n}개 추가 (Bold)`;
  });

  await part('아이콘', async track => {
    let row = find('FRAME', 'Icons');
    if (!row) { row = track(box('Icons', 'HORIZONTAL', { gap: 16 })); SEC.appendChild(row); }
    let n = 0;
    for (const [name, body] of Object.entries(ICONS)) {
      if (find('COMPONENT', 'Icon/' + name)) continue;
      const f = figma.createNodeFromSvg(`<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#e3e2e9" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${body}</svg>`);
      const c = track(figma.createComponentFromNode(f));
      c.name = 'Icon/' + name; c.fills = [];
      for (const n of c.findAll(n => 'strokes' in n && n.strokes.length)) n.strokes = paint('fg');
      c.description = `Lucide ${name}. 선 색은 인스턴스에서 바꿔 쓴다`;
      row.appendChild(c); n++;
    }
    return `${n}개 추가`;
  });

  await part('버튼 상태', async track => {
    const set = find('COMPONENT_SET', 'Button');
    const k = key(set, 'Label');
    const labelColor = { Default: 'fg', Primary: 'on-acc', Danger: 'bad' };
    const add = (style, size, state, change) => {
      const name = `Style=${style}, Size=${size}, State=${state}`;
      if (set.children.some(c => c.name === name)) return;
      const c = track(variant('Button', `Style=${style}, Size=${size}, State=Default`).clone());
      set.appendChild(c); c.name = name; change(c);
      c.findOne(n => n.name === 'Label').componentPropertyReferences = { characters: k };
    };
    for (const size of ['Medium', 'Small']) add('Primary', size, 'Hover', c => { c.fills = paint('acc-hover'); });
    for (const style of ['Default', 'Primary', 'Danger']) {
      add(style, 'Medium', 'Pressed', c => { c.fills = paint(style === 'Primary' ? 'acc-press' : 'press'); });
      add(style, 'Medium', 'Focus', c => { border(c, 'fg', 2, 'OUTSIDE'); });
      add(style, 'Medium', 'Loading', c => { c.itemSpacing = 8; c.counterAxisAlignItems = 'CENTER'; c.insertChild(0, icon('loader-circle', labelColor[style])); });
    }
    const states = ['Default', 'Hover', 'Pressed', 'Focus', 'Disabled', 'Loading'];
    const rows = ['Default', 'Primary', 'Danger'].flatMap(s => ['Medium', 'Small'].map(z => `${s}/${z}`));
    for (const c of set.children) {
      const m = c.name.match(/Style=(\w+), Size=(\w+), State=(\w+)/);
      c.x = 16 + states.indexOf(m[3]) * 120; c.y = 16 + rows.indexOf(`${m[1]}/${m[2]}`) * 52;
    }
    set.resize(16 + states.length * 120, 16 + rows.length * 52);
    set.description = '코드: <button>. Primary = button.pri, Danger = .danger, Small = button.sm. Hover = :hover, Pressed = :active, Focus = :focus-visible (outline 2px fg), Disabled = :disabled (dis-bg·dis-fg), Loading = 앞에 loader 아이콘 + 다시 누르기 막기';
    return `${set.children.length}종`;
  });

  await part('입력칸 상태', async track => {
    const set = find('COMPONENT_SET', 'Input');
    const k = key(set, 'Value');
    for (const c of set.children) if (!c.name.includes('State=')) c.name += ', State=Default';
    const add = (state, change) => {
      const name = `Size=Medium, State=${state}`;
      if (set.children.some(c => c.name === name)) return;
      const c = track(variant('Input', 'Size=Medium, State=Default').clone());
      set.appendChild(c); c.name = name; c.itemSpacing = 8; c.counterAxisAlignItems = 'CENTER'; change(c);
      c.findOne(n => n.name === 'Value').componentPropertyReferences = { characters: k };
    };
    add('Focus', c => { border(c, 'acc', 2); c.appendChild(icon('x', 'mute')); });
    add('Error', c => { border(c, 'bad'); c.appendChild(icon('circle-alert', 'bad')); });
    add('Disabled', c => { c.fills = paint('dis-bg'); c.findOne(n => n.name === 'Value').fills = paint('dis-fg'); });
    const order = ['Default', 'Focus', 'Error', 'Disabled'].map(s => `Size=Medium, State=${s}`).concat('Size=Small, State=Default');
    for (const c of set.children) { const i = order.indexOf(c.name); c.x = 16 + (i % 4) * 260; c.y = 16 + Math.floor(i / 4) * 52; }
    set.resize(16 + 4 * 260, 16 + 2 * 52);
    set.description = '코드: input, select. 표 안의 입력칸(.tbl input)은 Small. Focus = 테두리 2px acc, Error = 테두리 bad + 경고 아이콘, Disabled = dis-bg·dis-fg';
    return `${set.children.length}종`;
  });

  await part('Field', async track => {
    if (find('COMPONENT_SET', 'Field')) return '있음';
    const help = {
      Default: ['2~40자로 입력하세요.', 'mute'], Focus: ['2~40자로 입력하세요.', 'mute'],
      Error: ['! 이미 쓰는 이름입니다. 다른 이름을 입력하세요.', 'bad'], Disabled: ['권한이 없어 고칠 수 없습니다.', 'mute'],
    };
    const vs = [];
    for (const st of Object.keys(help)) {
      const c = track(comp('State=' + st, 'VERTICAL', { gap: 6 }));
      c.appendChild(await text('프로젝트 이름 *', 'table-head', 'fg', 'Label'));
      c.appendChild(variant('Input', `Size=Medium, State=${st}`).createInstance());
      c.appendChild(await text(help[st][0], 'fs-xs', help[st][1], 'Help'));
      vs.push(c);
    }
    const set = track(combine(vs, 'Field', 300, 110));
    linkText(set, vs.map(c => c.findOne(n => n.name === 'Label')), 'Label', '프로젝트 이름 *');
    set.description = '레이블 + 입력칸 + 도움말(오류면 오류 문장). 도움말 글은 인스턴스에서 바로 고친다';
    return '4종';
  });

  await part('Checkbox', async track => {
    if (find('COMPONENT_SET', 'Checkbox')) return '있음';
    const vs = [];
    for (const st of ['Unchecked', 'Checked', 'Indeterminate', 'Disabled']) {
      const c = track(comp('State=' + st, 'HORIZONTAL', { gap: 8, align: 'CENTER' }));
      const b = figma.createFrame(); b.name = 'Box'; b.resize(16, 16); b.fills = []; radius(b, 'r-s');
      if (st === 'Unchecked') border(b, 'mute', 2);
      if (st === 'Disabled') border(b, 'dis-fg', 2);
      if (st === 'Checked' || st === 'Indeterminate') { b.fills = paint('acc'); b.appendChild(icon(st === 'Checked' ? 'check' : 'minus', 'on-acc')); }
      c.appendChild(b);
      c.appendChild(await text('항목', 'fs-m', st === 'Disabled' ? 'dis-fg' : 'fg', 'Label'));
      vs.push(c);
    }
    const set = track(combine(vs, 'Checkbox', 120, 40));
    linkText(set, vs.map(c => c.findOne(n => n.name === 'Label')), 'Label', '항목');
    set.description = '16×16, 모서리 r-s. 부분 선택은 aria-checked="mixed"';
    return '4종';
  });

  await part('Pill 상태 색', async track => {
    const old = SEC.findOne(n => n.type === 'COMPONENT' && n.name === 'Pill');
    if (!old) return '있음';
    const tones = {
      Neutral: ['soft', 'fg', '관리자', null], Success: ['ok-bg', 'ok', '완료', 'check'], Warning: ['wait-bg', 'wait', '검토 필요', 'circle-alert'],
      Danger: ['bad-bg', 'on-bad-bg', '실패', 'circle-alert'], Info: ['acc-bg', 'on-acc-bg', '진행 중', null],
    };
    const vs = [];
    for (const [tone, [bg, fg, label, ic]] of Object.entries(tones)) {
      const c = track(comp('Tone=' + tone, 'HORIZONTAL', { gap: 4, py: 1, px: 8, align: 'CENTER' }));
      c.fills = paint(bg); radius(c, 'r-full');
      if (ic) c.appendChild(icon(ic, fg));
      c.appendChild(await text(label, 'fs-s', fg, 'Label'));
      vs.push(c);
    }
    const set = track(combine(vs, 'Pill', 110, 40));
    set.description = '코드: .pill. 상태는 색만으로 알리지 않고 아이콘·글자를 함께 쓴다. 글은 인스턴스에서 바로 고친다';
    old.remove();
    return '5종 (옛 Pill 은 지움)';
  });

  await part('Table Toolbar', async track => {
    if (find('COMPONENT', 'Table Toolbar')) return '있음';
    const c = track(comp('Table Toolbar', 'HORIZONTAL', { width: 480, align: 'CENTER' }));
    c.primaryAxisAlignItems = 'SPACE_BETWEEN';
    c.appendChild(await text('전체 24개', 'fs-s', 'mute', 'Summary'));
    const right = box('Filters', 'HORIZONTAL', { gap: 8, align: 'CENTER' });
    c.appendChild(right);
    right.appendChild(input('프로젝트 검색'));
    right.appendChild(btn('모든 상태'));
    SEC.appendChild(c);
    c.description = '표 위 도구 모음: 결과 수 + 검색 + 필터';
  });

  await part('Pagination', async track => {
    if (find('COMPONENT', 'Pagination')) return '있음';
    const c = track(comp('Pagination', 'HORIZONTAL', { width: 480, align: 'CENTER' }));
    c.primaryAxisAlignItems = 'SPACE_BETWEEN';
    c.appendChild(await text('24개 중 1-5', 'fs-s', 'mute', 'Summary'));
    const right = box('Pages', 'HORIZONTAL', { gap: 8, align: 'CENTER' });
    c.appendChild(right);
    right.appendChild(btn('이전'));
    right.appendChild(await text('1 / 5', 'fs-s', 'fg', 'Page'));
    right.appendChild(btn('다음'));
    SEC.appendChild(c);
    c.description = '표 아래 페이지 이동';
  });

  await part('State Message', async track => {
    if (find('COMPONENT_SET', 'State Message')) return '있음';
    const T = {
      Empty: ['folder', 'mute', '첫 프로젝트를 만들어 보세요', '아직 등록된 프로젝트가 없습니다.', ['프로젝트 만들기', 'Style=Primary, Size=Small, State=Default']],
      'No Results': ['search', 'mute', '검색 결과가 없습니다', '검색어나 필터를 바꿔 보세요.', ['검색 초기화', 'Style=Default, Size=Small, State=Default']],
      Loading: ['loader-circle', 'acc', '불러오는 중입니다', '잠시만 기다려 주세요.', null],
      Error: ['circle-alert', 'bad', '목록을 불러오지 못했습니다', '네트워크 연결을 확인한 뒤 다시 시도하세요.', ['다시 시도', 'Style=Default, Size=Small, State=Default']],
    };
    const vs = [];
    for (const [type, [ic, icColor, title, desc, action]] of Object.entries(T)) {
      const c = track(card(comp('Type=' + type, 'VERTICAL', { width: 300, gap: 8, py: 24, px: 24, align: 'CENTER' })));
      c.appendChild(icon(ic, icColor));
      for (const [s, style, color, nm] of [[title, 'title', 'fg', 'Title'], [desc, 'fs-s', 'mute', 'Description']]) {
        const t = await text(s, style, color, nm);
        c.appendChild(t); fill(t); t.textAlignHorizontal = 'CENTER';
      }
      if (action) c.appendChild(btn(action[0], action[1]));
      else for (const w of [252, 180]) { const r = figma.createRectangle(); r.name = 'Skeleton'; r.resize(w, 10); r.fills = paint('soft'); radius(r, 'r-s'); c.appendChild(r); }
      vs.push(c);
    }
    const h = Math.max(...vs.map(v => v.height));
    const set = track(combine(vs, 'State Message', 320, h + 16));
    set.description = '빈 상태 / 검색 결과 없음 / 불러오는 중(aria-busy) / 실패(다시 시도)';
    return '4종';
  });

  await part('Notification', async track => {
    if (find('COMPONENT', 'Notification')) return '있음';
    const c = track(card(comp('Notification', 'HORIZONTAL', { width: 360, gap: 10, py: 14, px: 14 })));
    c.appendChild(icon('circle-check', 'ok'));
    const body = box('Content', 'VERTICAL', { gap: 2 });
    c.appendChild(body); fill(body);
    const title = await text('프로젝트가 만들어졌습니다', 'title', 'fg', 'Title');
    const desc = await text('‘고객 포털 리뉴얼’에 팀원을 초대할 수 있습니다.', 'fs-s', 'mute', 'Description');
    body.appendChild(title); fill(title); body.appendChild(desc); fill(desc);
    c.appendChild(btn('확인'));
    linkText(c, [title], 'Title', '프로젝트가 만들어졌습니다');
    linkText(c, [desc], 'Description', '‘고객 포털 리뉴얼’에 팀원을 초대할 수 있습니다.');
    SEC.appendChild(c);
    c.description = '완료 알림 (role=status)';
  });

  await part('Dialog', async track => {
    if (find('COMPONENT', 'Dialog')) return '있음';
    const c = track(card(comp('Dialog', 'VERTICAL', { width: 400, gap: 16, py: 24, px: 24 })));
    const head = box('Heading', 'HORIZONTAL', { gap: 8, align: 'CENTER' });
    c.appendChild(head); fill(head);
    const title = await text('프로젝트를 삭제할까요?', 'fs-l', 'fg', 'Title');
    head.appendChild(title); fill(title);
    head.appendChild(icon('x', 'mute'));
    const bodyText = await text('‘고객 포털 리뉴얼’의 프로젝트와 활동 기록이 영구적으로 삭제됩니다. 이 작업은 되돌릴 수 없습니다.', 'fs-m', 'mute', 'Body');
    c.appendChild(bodyText); fill(bodyText);
    const actions = box('Actions', 'HORIZONTAL', { gap: 8, align: 'CENTER' });
    c.appendChild(actions); fill(actions); actions.primaryAxisAlignItems = 'MAX';
    actions.appendChild(btn('취소', 'Style=Default, Size=Medium, State=Default'));
    actions.appendChild(btn('프로젝트 삭제', 'Style=Danger, Size=Medium, State=Default'));
    linkText(c, [title], 'Title', '프로젝트를 삭제할까요?');
    linkText(c, [bodyText], 'Body', bodyText.characters);
    SEC.appendChild(c);
    c.description = '확인 창 (role=dialog). 첫 초점은 취소, Escape 로 닫기';
  });

  await part('Nav Item', async track => {
    if (find('COMPONENT_SET', 'Nav Item')) return '있음';
    const vs = [];
    for (const st of ['Default', 'Active']) {
      const c = track(comp('State=' + st, 'HORIZONTAL', { width: 200, py: 8, px: 12, align: 'CENTER' }));
      radius(c, 'r-m'); if (st === 'Active') c.fills = paint('soft');
      c.appendChild(await text('개요', 'fs-m', st === 'Active' ? 'fg' : 'mute', 'Label'));
      vs.push(c);
    }
    const set = track(combine(vs, 'Nav Item', 220, 56));
    linkText(set, vs.map(c => c.findOne(n => n.name === 'Label')), 'Label', '개요');
    set.description = '옆 메뉴 한 줄. 지금 화면은 Active';
    return '2종';
  });

  await part('Tab', async track => {
    if (find('COMPONENT_SET', 'Tab')) return '있음';
    const vs = [];
    for (const st of ['Default', 'Active']) {
      const c = track(comp('State=' + st, 'VERTICAL', { gap: 6, px: 4 }));
      c.paddingTop = 6;
      c.appendChild(await text('전체 현황', 'fs-m', st === 'Active' ? 'fg' : 'mute', 'Label'));
      const r = figma.createRectangle(); r.name = 'Indicator'; r.resize(40, 2);
      c.appendChild(r); r.layoutSizingHorizontal = 'FILL';
      r.fills = st === 'Active' ? paint('acc') : [];
      vs.push(c);
    }
    const set = track(combine(vs, 'Tab', 120, 56));
    linkText(set, vs.map(c => c.findOne(n => n.name === 'Label')), 'Label', '전체 현황');
    set.description = '탭 하나. Active 는 아래 2px acc 선';
    return '2종';
  });

  await part('Breadcrumbs', async track => {
    if (find('COMPONENT', 'Breadcrumbs')) return '있음';
    const c = track(comp('Breadcrumbs', 'HORIZONTAL', { gap: 6, align: 'CENTER' }));
    c.appendChild(await text('워크스페이스', 'fs-s', 'mute', 'Parent'));
    c.appendChild(await text('/', 'fs-s', 'mute', 'Slash'));
    c.appendChild(await text('개요', 'fs-s', 'fg', 'Current'));
    SEC.appendChild(c);
    c.description = '경로 표시. 마지막이 지금 화면';
  });

  await part('Metric Card', async track => {
    if (find('COMPONENT', 'Metric Card')) return '있음';
    const c = track(card(comp('Metric Card', 'VERTICAL', { width: 220, gap: 4, py: 16, px: 16 })));
    const parts = [['활성 프로젝트', 'fs-s', 'mute', 'Label'], ['24', 'value', 'fg', 'Value'], ['+4개 · 지난 기간 대비', 'fs-xs', 'ok', 'Delta']];
    for (const [s, style, color, nm] of parts) {
      const t = await text(s, style, color, nm);
      c.appendChild(t); fill(t);
      linkText(c, [t], nm, s);
    }
    SEC.appendChild(c);
    c.description = '지표 카드: 이름 / 숫자 / 지난 기간 대비';
  });

  await part('Top Bar', async track => {
    if (find('COMPONENT', 'Top Bar')) return '있음';
    const c = track(comp('Top Bar', 'HORIZONTAL', { width: 720, py: 12, px: 16, align: 'CENTER' }));
    c.primaryAxisAlignItems = 'SPACE_BETWEEN'; c.fills = paint('card');
    c.strokes = paint('line'); c.strokeAlign = 'INSIDE';
    c.strokeTopWeight = 0; c.strokeLeftWeight = 0; c.strokeRightWeight = 0; c.strokeBottomWeight = 1;
    c.appendChild(find('COMPONENT', 'Breadcrumbs').createInstance());
    const right = box('Actions', 'HORIZONTAL', { gap: 12, align: 'CENTER' });
    c.appendChild(right);
    right.appendChild(input('프로젝트, 멤버 검색'));
    const av = figma.createFrame(); av.name = 'Avatar';
    av.layoutMode = 'HORIZONTAL'; av.resize(28, 28);
    av.primaryAxisSizingMode = 'FIXED'; av.counterAxisSizingMode = 'FIXED';
    av.primaryAxisAlignItems = 'CENTER'; av.counterAxisAlignItems = 'CENTER';
    av.fills = paint('acc-bg'); radius(av, 'r-full');
    av.appendChild(await text('서', 'fs-s', 'on-acc-bg', 'Initial'));
    right.appendChild(av);
    SEC.appendChild(c);
    c.description = '상단 바: 경로 + 검색 + 사용자';
  });

  // ── 2차: 대시보드에만 있는 부품 ──

  await part('Select', async track => {
    if (find('COMPONENT_SET', 'Select')) return '있음';
    const vs = [];
    for (const [size, w, py, px, style] of [['Medium', 240, 6, 10, 'fs-m'], ['Small', 160, 3, 8, 'fs-s']]) {
      const c = track(comp('Size=' + size, 'HORIZONTAL', { width: w, gap: 8, py, px, align: 'CENTER' }));
      c.fills = paint('card'); border(c); radius(c, 'r-m');
      const t = await text('모든 상태', style, 'fg', 'Value');
      c.appendChild(t); fill(t);
      c.appendChild(icon('chevron-down', 'mute'));
      vs.push(c);
    }
    const p = track(comp('Size=Pill', 'HORIZONTAL', { gap: 2, py: 1, px: 4, align: 'CENTER' }));
    p.fills = paint('soft'); border(p); radius(p, 'r-full');
    p.appendChild(await text('남은 일', 'fs-s', 'fg', 'Value'));
    p.appendChild(icon('chevron-down', 'mute'));
    const set = track(combine([...vs, p], 'Select', 260, 48));
    linkText(set, vs.map(c => c.findOne(n => n.name === 'Value')), 'Value', '모든 상태');
    set.description = '코드: select. 표 안은 Small. Pill = 작업 줄의 상태·태그·프로젝트 고르기(.tsel·.tgsel·.psel), 상태 글자색은 t-todo·t-stop·t-done·t-rej';
    return '3종';
  });

  await part('Menu', async track => {
    if (find('COMPONENT', 'Menu')) return '있음';
    const vs = [];
    for (const st of ['Default', 'Hover', 'Selected', 'Danger']) {
      const c = track(comp('State=' + st, 'HORIZONTAL', { width: 160, py: 8, px: 12, align: 'CENTER' }));
      radius(c, 'r-m'); if (st === 'Hover' || st === 'Selected') c.fills = paint('soft');
      c.appendChild(await text('세션 기록', 'fs-m', st === 'Danger' ? 'bad' : 'fg', 'Label'));
      vs.push(c);
    }
    const set = track(combine(vs, 'Menu Item', 180, 52));
    const k = linkText(set, vs.map(c => c.findOne(n => n.name === 'Label')), 'Label', '세션 기록');
    set.description = '펼침 메뉴 한 줄 (.ddm a, #menu div). Selected = 지금 화면, Danger = 세션 종료하기';
    const m = track(card(comp('Menu', 'VERTICAL', { width: 168, py: 4, px: 4 })));
    shadow(m);
    for (const [label, st] of [['세션 기록', 'Selected'], ['Push 기록', 'Default']]) {
      const i = variant('Menu Item', 'State=' + st).createInstance();
      m.appendChild(i); fill(i); i.setProperties({ [k]: label });
    }
    SEC.appendChild(m);
    m.description = '펼침 메뉴 (History ▾, 그래프 오른쪽 단추 메뉴). 단추 아래에 붙여 띄운다';
    return 'Menu Item 4종 + Menu';
  });

  await part('Tooltip', async track => {
    if (find('COMPONENT', 'Tooltip')) return '있음';
    const c = track(comp('Tooltip', 'VERTICAL', { gap: 6 }));
    const q = auto(figma.createFrame(), 'HORIZONTAL', { align: 'CENTER' });
    q.name = 'Trigger'; q.primaryAxisSizingMode = 'FIXED'; q.counterAxisSizingMode = 'FIXED'; fixed(q, 20, 20);
    q.primaryAxisAlignItems = 'CENTER'; q.fills = []; border(q); radius(q, 'r-full');
    q.appendChild(await text('?', 'strong-xs', 'mute', 'Mark'));
    c.appendChild(q);
    const b = card(box('Box', 'VERTICAL', { width: 380, py: 10, px: 14 }));
    shadow(b); c.appendChild(b);
    const t = await text('Projects: 끝이 있는 일입니다. 완료 조건을 채우면 Archives 로 옮깁니다.', 'fs-s', 'fg', 'Body');
    b.appendChild(t); fill(t);
    linkText(c, [t], 'Body', t.characters);
    SEC.appendChild(c);
    c.description = '설명 말풍선 (.tip · .tipbox). 물음표에 올리거나 초점이 가면 상자가 뜬다';
  });

  await part('Progress Bar', async track => {
    if (find('COMPONENT_SET', 'Progress Bar')) return '있음';
    const vs = [['Ok', 'ok', 0.3], ['Wait', 'wait', 0.6], ['Bad', 'bad', 0.9]].map(([tone, color, pct]) => {
      const c = track(bar(figma.createComponent(), 64, 6, color, pct));
      c.name = 'Tone=' + tone; return c;
    });
    const set = track(combine(vs, 'Progress Bar', 80, 22));
    set.description = '사용량 막대 (.bar). 50% 미만 Ok, 80% 미만 Wait, 그 위 Bad';
    return '3종';
  });

  await part('Usage Meter', async track => {
    if (find('COMPONENT', 'Usage Meter')) return '있음';
    const c = track(comp('Usage Meter', 'HORIZONTAL', { gap: 8, align: 'CENTER' }));
    const l = await text('5시간', 'fs-s', 'mute', 'Label');
    c.appendChild(l);
    c.appendChild(variant('Progress Bar', 'Tone=Ok').createInstance());
    const p = await text('30%', 'strong-s', 'fg', 'Percent');
    c.appendChild(p);
    linkText(c, [l], 'Label', '5시간'); linkText(c, [p], 'Percent', '30%');
    SEC.appendChild(c);
    c.description = '머리줄 사용량 (.hu): 이름 + 막대 + 숫자. 막대 색은 숫자에 따라 Progress Bar 를 바꿔 낀다';
  });

  await part('Status Dot', async track => {
    if (find('COMPONENT_SET', 'Status Dot')) return '있음';
    const vs = Object.entries(DOTS).map(([k, [color, , sq]]) => {
      const c = track(fixed(figma.createComponent(), 8, 8));
      c.name = 'Status=' + k; c.fills = paint(color); radius(c, sq ? 'r-xs' : 'r-full');
      return c;
    });
    const set = track(combine(vs, 'Status Dot', 28, 24));
    set.description = '상태 점 (.dot). 동그라미 = 세션 상태, 네모 = 그래프의 프로젝트·서브에이전트';
    return `${vs.length}종`;
  });

  await part('Legend', async track => {
    if (find('COMPONENT', 'Legend')) return '있음';
    const c = track(comp('Legend', 'HORIZONTAL', { gap: 12, align: 'CENTER' }));
    for (const k of ['Work', 'Wait', 'Idle', 'Project', 'Agent']) {
      const it = box(k, 'HORIZONTAL', { gap: 6, align: 'CENTER' });
      c.appendChild(it);
      it.appendChild(variant('Status Dot', 'Status=' + k).createInstance());
      it.appendChild(await text(DOTS[k][1], 'fs-s', 'mute', 'Label'));
    }
    SEC.appendChild(c);
    c.description = '그래프 범례 (.legend)';
  });

  await part('Stat', async track => {
    if (find('COMPONENT_SET', 'Stat')) return '있음';
    const vs = [];
    for (const st of ['Default', 'Hover', 'Selected']) {
      const c = track(comp('State=' + st, 'HORIZONTAL', { width: 140, gap: 8, py: 6, px: 10, align: 'CENTER' }));
      if (st === 'Hover') c.fills = paint('soft');
      border(c, st === 'Selected' ? 'acc' : 'line', st === 'Selected' ? 2 : 1); radius(c, 'r-m');
      c.appendChild(await text('3', 'strong-l', 'ok', 'Value'));
      const l = box('Label', 'HORIZONTAL', { gap: 6, align: 'CENTER' });
      c.appendChild(l);
      l.appendChild(variant('Status Dot', 'Status=Work').createInstance());
      l.appendChild(await text('작업 중', 'fs-s', 'mute', 'Text'));
      vs.push(c);
    }
    const set = track(combine(vs, 'Stat', 160, 52));
    linkText(set, vs.map(c => c.findOne(n => n.name === 'Value')), 'Value', '3');
    set.description = '현황 숫자 칸 (.stat). 누르면 그 상태만 보기(Selected = 테두리 acc). 숫자 색은 상태 색, 0 이면 mute';
    return '3종';
  });

  await part('Toggle Button', async track => {
    if (find('COMPONENT_SET', 'Toggle Button')) return '있음';
    const vs = [];
    for (const st of ['Default', 'Selected']) {
      const c = track(comp('State=' + st, 'HORIZONTAL', { gap: 6, py: 6, px: 10, align: 'CENTER' }));
      c.fills = paint('card'); border(c, st === 'Selected' ? 'acc' : 'line', st === 'Selected' ? 2 : 1); radius(c, 'r-m');
      c.appendChild(await text('Projects', st === 'Selected' ? 'title' : 'fs-m', 'fg', 'Label'));
      c.appendChild(await text('3', 'fs-xs', 'mute', 'Count'));
      vs.push(c);
    }
    const set = track(combine(vs, 'Toggle Button', 140, 52));
    linkText(set, vs.map(c => c.findOne(n => n.name === 'Label')), 'Label', 'Projects');
    linkText(set, vs.map(c => c.findOne(n => n.name === 'Count')), 'Count', '3');
    set.description = 'PARA 네 칸 고르기 (.ptabs button). 이름 + 개수, Selected = 테두리 acc + 굵게';
    return '2종';
  });

  await part('Task Row', async track => {
    if (find('COMPONENT_SET', 'Task Row')) return '있음';
    const ST = { Todo: ['남은 일', 't-todo'], Stopped: ['중단', 't-stop'], Done: ['완료', 't-done'], Rejected: ['반려', 't-rej'] };
    const sel = (v, color) => {
      const i = variant('Select', 'Size=Pill').createInstance();
      const t = i.findOne(n => n.name === 'Value');
      t.characters = v; if (color) t.fills = paint(color);
      return i;
    };
    const vs = [];
    for (const [st, open] of [['Todo', false], ['Todo', true], ['Stopped', false], ['Done', false], ['Rejected', false]]) {
      const [label, color] = ST[st];
      const c = track(comp(`Status=${st}, Open=${open ? 'Yes' : 'No'}`, 'HORIZONTAL', { width: 560, gap: 4 }));
      c.appendChild(sel(label, color)); c.appendChild(sel('개발')); c.appendChild(sel('대시보드 1.0'));
      const body = box('Body', 'VERTICAL', { gap: 2 });
      c.appendChild(body); fill(body);
      const line = box('Line', 'HORIZONTAL', { gap: 6, align: 'CENTER' });
      body.appendChild(line);
      const t = await text('세션 카드 위쪽 빛 띠를 고친다', 'fs-m', st === 'Done' || st === 'Rejected' ? 'mute' : 'fg', 'Text');
      if (st === 'Rejected') { t.textDecoration = 'STRIKETHROUGH'; t.setBoundVariable('fontSize', V['fs-m']); }
      line.appendChild(t);
      line.appendChild(icon(open ? 'chevron-down' : 'chevron-right', 'mute'));
      line.appendChild(await text('#109', 'fs-xs', 'mute', 'Id'));
      if (open) {
        line.appendChild(await text('· Flow', 'fs-xs', 'mute', 'Flow'));
        const d = box('Details', 'VERTICAL', { gap: 2 });
        d.paddingLeft = 16; body.appendChild(d); fill(d);
        for (const s of ['└ 빛 띠를 카드와 같은 모양 상자로 깔았다', '└ 확대 화면으로 모서리를 비교했다', '결과 : 모서리 곡선을 카드와 맞춤']) {
          const x = await text(s, 'fs-s', 'mute', 'Detail'); d.appendChild(x); fill(x);
        }
        c.appendChild(icon('x', 'mute'));
      }
      vs.push(c);
    }
    const set = track(combine(vs, 'Task Row', 600, 110, 1));
    set.description = '작업 한 줄 (TaskList.jsx TaskRow). 상태·태그·프로젝트 고르기 + 문장 + #번호. 문장을 누르면 └ 설명·결과·Flow 가 펼쳐진다(Open). x 는 올렸을 때만 보인다. 완료·반려는 흐린 글자, 반려는 취소선';
    return '5종';
  });

  await part('Collapsible', async track => {
    if (find('COMPONENT_SET', 'Collapsible')) return '있음';
    const vs = [];
    for (const open of [false, true]) {
      const c = track(comp('Open=' + (open ? 'Yes' : 'No'), 'VERTICAL', { width: 320, gap: 6 }));
      const head = box('Summary', 'HORIZONTAL', { gap: 4, align: 'CENTER' });
      c.appendChild(head);
      head.appendChild(icon(open ? 'chevron-down' : 'chevron-right', 'mute'));
      head.appendChild(await text('세션 요약', 'title', 'fg', 'Title'));
      if (open) {
        const b = box('Content', 'VERTICAL', { gap: 4 });
        b.paddingLeft = 16; c.appendChild(b); fill(b);
        const t = await text('09:12 → 11:40 · 기록할 작업 3건', 'fs-s', 'mute', 'Body');
        b.appendChild(t); fill(t);
      }
      vs.push(c);
    }
    const set = track(combine(vs, 'Collapsible', 340, 80));
    linkText(set, vs.map(c => c.findOne(n => n.name === 'Title')), 'Title', '세션 요약');
    set.description = '접는 칸 (details · .sec · .tgrp). 내용은 제목보다 16px 들여 쓴다. 작업 묶음 제목은 상태 색 글자';
    return '2종';
  });

  await part('Key Value', async track => {
    if (find('COMPONENT', 'Key Value')) return '있음';
    const c = track(comp('Key Value', 'VERTICAL', { width: 360, gap: 6 }));
    await kvRows(c, [['실행 앱', '백그라운드'], ['실행 위치', '~/Project/app'], ['일정', '평일 09:00'], ['모델', 'Sonnet 5.5']], 'fs-m', 72);
    SEC.appendChild(c);
    c.description = '이름-값 목록 (.kv · dl). 이름은 mute, 값은 fg';
  });

  await part('Code Block', async track => {
    if (find('COMPONENT', 'Code Block')) return '있음';
    const c = track(comp('Code Block', 'VERTICAL', { width: 400, py: 10, px: 10 }));
    c.fills = paint('soft'); border(c); radius(c, 'r-m');
    const t = await text('$ git push origin main\n   5b870d6..3fe46a9  main -> main', 'fs-s', 'fg', 'Code');
    c.appendChild(t); fill(t);
    linkText(c, [t], 'Code', t.characters);
    SEC.appendChild(c);
    c.description = '긴 글 상자 (pre). 코드에서는 고정폭 글꼴, 줄바꿈 유지, 높이 50vh 넘으면 안에서 스크롤';
  });

  await part('Flow Step', async track => {
    if (find('COMPONENT_SET', 'Flow Step')) return '있음';
    const T = {
      Start: ['시작', '사용자가 [맡기기]를 누름', '이슈 본문 · 추천 폴더', null, 'acc'],
      Step: ['1', '폴더 고르기', '같은 이슈를 했던 폴더를 먼저 추천한다', null, 'line'],
      Branch: ['2', '에이전트 띄우기', '지시문을 붙여 백그라운드로 실행한다', '폴더가 없음 → 최근 폴더를 쓴다', 'line'],
      End: ['결과', '새 세션 카드가 보임', '현황 그래프에 바로 나타난다', null, 'acc'],
    };
    const vs = [];
    for (const [type, [k, title, detail, branch, edge]] of Object.entries(T)) {
      const c = track(comp('Type=' + type, 'HORIZONTAL', { width: 480, gap: 10, py: 8, px: 12 }));
      c.fills = paint('soft'); border(c, edge); radius(c, 'r-m');
      const badge = box('Badge', 'HORIZONTAL', { px: 6, align: 'CENTER' });
      badge.primaryAxisAlignItems = 'CENTER'; badge.minWidth = 22; badge.fills = paint('acc'); radius(badge, 'r-full');
      badge.appendChild(await text(k, 'strong-xs', 'on-acc', 'Key'));
      c.appendChild(badge);
      const body = box('Body', 'VERTICAL', { gap: 2 });
      c.appendChild(body); fill(body);
      for (const [s, style, color, nm] of [[title, 'title', 'fg', 'Title'], [detail, 'fs-s', 'mute', 'Detail']]) {
        const t = await text(s, style, color, nm); body.appendChild(t); fill(t);
      }
      if (branch) {
        const b = box('Branch', 'HORIZONTAL', { gap: 4, align: 'CENTER' });
        body.appendChild(b);
        b.appendChild(icon('corner-down-right', 't-stop'));
        b.appendChild(await text(branch, 'fs-s', 't-stop', 'Branch text'));
      }
      vs.push(c);
    }
    const set = track(combine(vs, 'Flow Step', 500, 96, 1));
    set.description = '흐름도 한 칸 (.fbox · .fk). 시작·결과는 테두리 acc, Branch 는 조건에 따라 갈리는 처리(t-stop). 글은 인스턴스에서 바로 고친다';
    return '4종';
  });

  await part('Flow', async track => {
    if (find('COMPONENT', 'Flow')) return '있음';
    const c = track(comp('Flow', 'HORIZONTAL', { gap: 20 }));
    const col = box('Steps', 'VERTICAL', { width: 480, gap: 2 });
    c.appendChild(col);
    ['Start', 'Step', 'Branch', 'End'].forEach((type, i) => {
      if (i) {
        const a = box('Arrow', 'HORIZONTAL', {});
        col.appendChild(a); fill(a); a.primaryAxisAlignItems = 'CENTER';
        a.appendChild(icon('arrow-down', 'mute'));
      }
      const s = variant('Flow Step', 'Type=' + type).createInstance();
      col.appendChild(s); fill(s);
    });
    const rules = box('Rules', 'VERTICAL', { width: 220, gap: 6 });
    c.appendChild(rules);
    rules.appendChild(await text('지키는 규칙', 'title', 'fg', 'Heading'));
    const rt = await text('· 쉬운 말로 쓴다\n· 코드 이름은 괄호로만 붙인다', 'fs-s', 'mute', 'List');
    rules.appendChild(rt); fill(rt);
    SEC.appendChild(c);
    c.description = '흐름도 한 장 (Flow.jsx FlowView): 시작 → 단계 → 결과 + 오른쪽 규칙. 좁으면 규칙이 아래로';
  });

  await part('Session Card', async track => {
    if (find('COMPONENT_SET', 'Session Card')) return '있음';
    const color = { Work: 'ok', Wait: 'wait', Idle: 'idle' };
    const vs = [];
    for (const [st, on] of [['Work', false], ['Wait', false], ['Idle', false], ['Work', true]]) {
      const c = track(comp(`Status=${st}, Selected=${on ? 'Yes' : 'No'}`, 'VERTICAL', { width: 240 }));
      card(c); c.clipsContent = true; shadow(c);
      if (on) border(c, color[st], 2, 'OUTSIDE');
      const top = figma.createRectangle(); top.name = 'Status Line'; top.resize(240, 3); top.fills = paint(color[st]);
      c.appendChild(top); top.layoutSizingHorizontal = 'FILL';
      const body = box('Content', 'VERTICAL', { gap: 8, py: 10, px: 12 });
      c.appendChild(body); fill(body);
      const head = box('Header', 'HORIZONTAL', { gap: 6, align: 'CENTER' });
      body.appendChild(head); fill(head);
      head.appendChild(variant('Status Dot', 'Status=' + st).createInstance());
      const nm = await text('hudson-fleet-98', 'strong-s', 'fg', 'Name');
      head.appendChild(nm); fill(nm);
      head.appendChild(await text('Opus 5.5 · high', 'fs-xs', 'mute', 'Model'));
      const meter = async (pct, rest) => {
        const r = box('Meter', 'HORIZONTAL', { gap: 6, align: 'CENTER' });
        r.appendChild(bar(figma.createFrame(), 60, 5, color[st], pct, 'r-s'));
        r.appendChild(await text(Math.round(pct * 100) + '%', 'fs-s', 'fg', 'Percent'));
        r.appendChild(await text(rest, 'fs-s', 'mute', 'Rest'));
        return r;
      };
      await kvRows(body, [['실행 앱', '터미널'], ['실행 위치', '~/Project/app'], ['컨텍스트', await meter(0.42, '· 84K / 200K')], ['5시간 사용량', await meter(0.3, '· 1.2M 토큰')]], 'fs-s', 76);
      vs.push(c);
    }
    const set = track(combine(vs, 'Session Card', 260, 200));
    set.description = '현황 그래프 위 세션 카드 (.ncard). 위 3px 띠 = 상태 색. 작업 중이면 띠에 빛이 흐르고(코드만), 고르면 상태 색 2px 테두리, 끝난 세션은 흐리게(15%). 좁은 화면에서는 목록으로 쌓는다';
    return '4종';
  });

  await part('Side Panel', async track => {
    if (find('COMPONENT', 'Side Panel')) return '있음';
    const c = track(comp('Side Panel', 'VERTICAL', { width: 360, gap: 12, py: 20, px: 20 }));
    c.fills = paint('card'); c.strokes = paint('line'); c.strokeAlign = 'INSIDE';
    c.strokeTopWeight = 0; c.strokeRightWeight = 0; c.strokeBottomWeight = 0; c.strokeLeftWeight = 1;
    const head = box('Header', 'HORIZONTAL', { gap: 8, align: 'CENTER' });
    c.appendChild(head); fill(head); head.primaryAxisAlignItems = 'SPACE_BETWEEN';
    head.appendChild(await text('hudson-fleet-98', 'title', 'fg', 'Title'));
    const x = box('Close', 'HORIZONTAL', { py: 4, px: 4 });
    x.fills = paint('card'); border(x); radius(x, 'r-m'); x.appendChild(icon('x', 'mute'));
    head.appendChild(x);
    const meta = box('Meta', 'HORIZONTAL', { gap: 6, align: 'CENTER' });
    c.appendChild(meta); fill(meta);
    const pill = variant('Pill', 'Tone=Success').createInstance();
    pill.findOne(n => n.name === 'Label').characters = '작업 중';
    meta.appendChild(pill);
    const mt = await text('터미널 · 09:12 시작 · ~/Project/app', 'fs-s', 'mute', 'Meta text');
    meta.appendChild(mt); fill(mt);
    const ck = key(find('COMPONENT_SET', 'Collapsible'), 'Title');
    for (const [open, title] of [[true, '세션 요약'], [false, 'Push · 2건']]) {
      const i = variant('Collapsible', 'Open=' + (open ? 'Yes' : 'No')).createInstance();
      c.appendChild(i); fill(i); i.setProperties({ [ck]: title });
    }
    const h = figma.createRectangle(); h.name = 'Resize Handle';
    c.appendChild(h); h.layoutPositioning = 'ABSOLUTE'; h.x = 0; h.y = 0; h.resize(6, c.height);
    h.fills = paint('acc'); h.opacity = 0.4;
    SEC.appendChild(c);
    c.description = '오른쪽 세션 패널 (#side). 왼쪽 6px 손잡이를 끌어 폭을 바꾼다(올렸을 때만 보임). 900px 아래에서는 본문 아래로 내려간다';
  });

  await part('Banner', async track => {
    if (find('COMPONENT', 'Banner')) return '있음';
    const c = track(comp('Banner', 'HORIZONTAL', { width: 720, py: 8, px: 20, align: 'CENTER' }));
    c.fills = paint('t-todo');
    const t = await text('대시보드 서버에 닿지 않습니다. 세션을 하나 열면 1~2초 안에 다시 이어집니다.', 'fs-m', 'on-todo', 'Message');
    c.appendChild(t); fill(t);
    linkText(c, [t], 'Message', t.characters);
    SEC.appendChild(c);
    c.description = '화면 맨 위 안내 띠 (.down). 머리줄 새 알림(.hmsg)은 같은 노랑으로 1.5초 깜빡인다(코드만)';
  });

  await part('섹션 정리', async () => {
    let x = 24, h = 0;
    for (const col of [ORDER, ORDER2]) {
      let y = 24, w = 0;
      for (const name of col) {
        const n = SEC.children.find(c => c.name === name);
        if (!n) continue;
        n.x = x; n.y = y; y += n.height + 32; w = Math.max(w, n.width);
      }
      if (w) { x += w + 80; h = Math.max(h, y); }
    }
    SEC.resizeWithoutConstraints(x - 56, h - 8);
  });

  await part('확인 화면', async track => {
    const old = figma.currentPage.children.find(n => n.type === 'FRAME' && n.name === 'Review');
    const r = track(box('Review', 'VERTICAL', { gap: 24, py: 24, px: 24 }));
    r.fills = paint('bg');
    const row = (name, gap = 8) => { const b = box(name, 'HORIZONTAL', { gap, align: 'CENTER' }); r.appendChild(b); return b; };
    const all = (setName, order) => {
      const set = find('COMPONENT_SET', setName);
      const kids = order ? order.map(o => set.children.find(c => c.name === o)).filter(Boolean) : set.children;
      return kids.map(c => c.createInstance());
    };

    const buttons = box('Buttons', 'VERTICAL', { gap: 8 });
    r.appendChild(buttons);
    const states = ['Default', 'Hover', 'Pressed', 'Focus', 'Disabled', 'Loading'];
    for (const style of ['Default', 'Primary', 'Danger']) for (const size of ['Medium', 'Small']) {
      const line = box(`${style} ${size}`, 'HORIZONTAL', { gap: 12, align: 'CENTER' });
      buttons.appendChild(line);
      for (const i of all('Button', states.map(s => `Style=${style}, Size=${size}, State=${s}`))) line.appendChild(i);
    }
    const inputs = row('Inputs');
    for (const i of all('Input', ['Default', 'Focus', 'Error', 'Disabled'].map(s => `Size=Medium, State=${s}`).concat('Size=Small, State=Default'))) inputs.appendChild(i);
    const fields = row('Fields', 16);
    for (const i of all('Field')) fields.appendChild(i);
    const boxes = row('Checkboxes', 16);
    const cbLabels = ['미선택', '선택됨', '부분 선택', '비활성'];
    const cbKey = key(find('COMPONENT_SET', 'Checkbox'), 'Label');
    all('Checkbox').forEach((i, n) => { i.setProperties({ [cbKey]: cbLabels[n] }); boxes.appendChild(i); });
    const pills = row('Pills');
    for (const i of all('Pill')) pills.appendChild(i);

    const table = box('Table block', 'VERTICAL', { gap: 8 });
    r.appendChild(table);
    table.appendChild(find('COMPONENT', 'Table Toolbar').createInstance());
    const tbl = box('Table', 'VERTICAL');
    card(tbl); tbl.clipsContent = true;
    table.appendChild(tbl);
    const head = variant('Table Row', 'Type=Header').createInstance();
    ['작업', '상태', '업데이트'].forEach((s, i) => { head.findOne(n => n.name === `Col ${i + 1}`).characters = s; });
    tbl.appendChild(head);
    const bodyRows = [['블로그 글 정리', '완료', '10:24'], ['Figma 이름표 만들기', '진행 중', '11:02']];
    bodyRows.forEach((vals, ri) => {
      const b = variant('Table Row', 'Type=Body').createInstance();
      vals.forEach((s, ci) => { b.findOne(n => n.name === `Col ${ci + 1}`).characters = s; });
      if (ri === bodyRows.length - 1) b.strokeBottomWeight = 0;
      tbl.appendChild(b);
    });
    table.appendChild(find('COMPONENT', 'Pagination').createInstance());

    const msgs = row('State Messages', 16);
    for (const i of all('State Message')) msgs.appendChild(i);
    const over = row('Overlays', 16);
    over.counterAxisAlignItems = 'MIN';
    over.appendChild(find('COMPONENT', 'Notification').createInstance());
    over.appendChild(find('COMPONENT', 'Dialog').createInstance());
    const nav = row('Navigation', 16);
    for (const i of all('Nav Item', ['State=Active', 'State=Default'])) nav.appendChild(i);
    for (const i of all('Tab', ['State=Active', 'State=Default'])) nav.appendChild(i);
    nav.appendChild(find('COMPONENT', 'Breadcrumbs').createInstance());
    const metrics = row('Metrics', 16);
    const mc = find('COMPONENT', 'Metric Card');
    for (const [l, v, d] of [['활성 프로젝트', '24', '+4개 · 지난 기간 대비'], ['활성 멤버', '128', '+12명 · 지난 기간 대비'], ['실행 성공률', '99.8%', '+0.3%p · 지난 기간 대비']]) {
      const i = mc.createInstance();
      i.setProperties({ [key(mc, 'Label')]: l, [key(mc, 'Value')]: v, [key(mc, 'Delta')]: d });
      metrics.appendChild(i);
    }
    r.appendChild(find('COMPONENT', 'Top Bar').createInstance());

    r.x = SEC.x + SEC.width + 40; r.y = SEC.y;
    if (old) old.remove();
    return '모든 부품 인스턴스';
  });

  await part('확인 화면 (대시보드 부품)', async track => {
    const old = figma.currentPage.children.find(n => n.type === 'FRAME' && n.name === 'Review Dashboard');
    const r = track(box('Review Dashboard', 'VERTICAL', { gap: 24, py: 24, px: 24 }));
    r.fills = paint('bg');
    const row = (name, gap = 16) => { const b = box(name, 'HORIZONTAL', { gap }); r.appendChild(b); return b; };
    const one = name => find('COMPONENT', name).createInstance();
    const all = setName => find('COMPONENT_SET', setName).children.map(c => c.createInstance());

    r.appendChild(one('Banner'));
    const head = row('Header');
    head.counterAxisAlignItems = 'CENTER';
    head.appendChild(one('Usage Meter')); head.appendChild(one('Legend'));
    for (const name of ['Select', 'Progress Bar', 'Status Dot', 'Stat', 'Toggle Button']) {
      const b = row(name, 8); b.counterAxisAlignItems = 'CENTER';
      for (const i of all(name)) b.appendChild(i);
    }
    const menus = row('Menus');
    menus.appendChild(one('Menu')); menus.appendChild(one('Tooltip'));
    const tasks = box('Tasks', 'VERTICAL', { gap: 6 });
    r.appendChild(tasks);
    for (const i of all('Task Row')) tasks.appendChild(i);
    const folds = row('Collapsibles');
    for (const i of all('Collapsible')) folds.appendChild(i);
    const detail = row('Detail');
    detail.appendChild(one('Key Value')); detail.appendChild(one('Code Block'));
    r.appendChild(one('Flow'));
    const cards = row('Session Cards');
    for (const i of all('Session Card')) cards.appendChild(i);
    r.appendChild(one('Side Panel'));

    const prev = figma.currentPage.children.find(n => n.type === 'FRAME' && n.name === 'Review');
    r.x = prev ? prev.x + prev.width + 40 : SEC.x + SEC.width + 40; r.y = SEC.y;
    if (old) old.remove();
    return '대시보드 부품 인스턴스';
  });

  // 실행 기록을 섹션 위에 남긴다
  const prev = figma.currentPage.children.find(n => n.type === 'TEXT' && n.name === 'Build Log');
  if (prev) prev.remove();
  const kst = new Date(Date.now() + 9 * 3600e3).toISOString().slice(0, 16).replace('T', ' ');
  const log = await text(`hudson-fleet DS builder - ${kst}\n${LOG.join('\n')}`, 'fs-s', 'mute', 'Build Log');
  figma.currentPage.appendChild(log);
  log.x = SEC.x; log.y = SEC.y - log.height - 24;

  const failed = LOG.filter(l => l.startsWith('[실패]')).length;
  return failed ? `${failed}개 실패 — 섹션 위 Build Log 를 보세요` : `완료 (${LOG.length}단계) — 섹션 위 Build Log 에 기록`;
}

main()
  .then(msg => figma.closePlugin(msg))
  .catch(e => figma.closePlugin('오류: ' + e.message));
