// Workflow 화면 — 에이전트 지식 그래프(SVG), 지금 세션의 에이전트 지도, 백그라운드 작업. 서버 문자열은 전부 textContent 로만 넣는다.
// 그래프는 에이전트를 가로로 두고, 그 에이전트만 가진 능력(도구, sub-agent, 위임받는 노드)을 바깥쪽 세로 줄로 두어
// 허브에서 방사선으로 잇고, 여럿이 함께 쓰는 능력을 아래 상자에 쌓아 주인들과 잇는다. 잎이 많으면 그림(viewBox)이
// 자라고, 휠과 끌기로 확대, 축소, 이동한다.
// 지도는 보는 세션의 에이전트를 뿌리 카드로, 그 세션에서 나간 위임을 오른쪽 열의 카드로, 받는 쪽이 다시 맡긴 것을 다음 열로 둔다.
import { apiFetch } from './api.js';
import { onViewOpen, currentView } from './view.js';

const SVG_NS = 'http://www.w3.org/2000/svg';
const BASE_W = 960;          // 그림의 최소 크기. 잎이 많거나 에이전트가 많으면 자란다
const BASE_H = 540;
const AGENT_R = 30;
const LEAF_R = 5;
const SUB_R = 8;
const LEAF_DIST = 110;       // 허브에서 잎 세로 줄까지
const LEAF_ROW = 16;         // 세로 줄의 잎 간격(이름 한 줄)
const LABEL_W = 120;         // 잎 이름이 줄 바깥으로 뻗는 너비(18자)
const HUB_GAP = 60;          // 허브(와 그 잎 줄) 사이 간격
const ARC_BAND = 48;         // 맨 위, 허브 사이 위임 아치가 지나는 띠
const ZOOM_MIN = 0.5;
const ZOOM_MAX = 4;
const ZOOM_STEP = 1.2;
const BOX_ROW = 22;          // 공통 능력 상자 안 줄 간격
const BOX_COL = 150;         // 공통 능력 상자 안 칸 너비(이름 18자가 들어간다)
const BOX_PAD = 14;          // 상자 안쪽 여백
const BOX_TITLE = 18;        // 상자 제목 줄 높이
const BOX_BOTTOM = 14;       // 상자와 패널 아래 가장자리 사이
const LABEL_MAX = 18;
const MAP_LABEL_MAX = 60;
const MAP_DEPTH_MAX = 4;     // 뿌리 아래로 이만큼까지. 더 깊은 위임은 ask_agent 가 막는다
const JOBS_OPEN_KEY = 'wf-jobs-open';  // localStorage: 작업 표를 펼쳐 둔 사람
const MARGIN = 24;           // 노드 중심이 패널 가장자리에서 이만큼은 떨어진다
const NUDGE = 8;             // 방향키 한 번에 움직이는 거리(Shift 는 세 배)
const TIDY_ITER = 120;       // 정렬 최적화의 밀어내기 반복 상한
const TIDY_PAD = 6;          // 정렬 때 글상자 사이에 둘 틈
const LEGACY_LAYOUT_KEY = 'wf-layout-v2';  // 서버 저장 전에 브라우저에 남던 자리. 서버가 비어 있으면 한 번 올리고 지운다
const LAYOUT_URL = '/api/workflow/layout';
const LAYOUT_SAVE_MS = 600;  // 끌기와 방향키가 이어지는 동안은 마지막 자리만 보낸다
const ARROWS = { ArrowUp: [0, -1], ArrowDown: [0, 1], ArrowLeft: [-1, 0], ArrowRight: [1, 0] };
const KIND_LABEL = { ask: '질문', subagent: 'sub-agent', orchestrate: 'orchestrate', focus: 'focus', background: '뒤에서 이어 하기' };
// 선응답으로 닫고 뒤에서 이어 도는 턴의 받는 쪽 id(background:<에이전트>). 서버 workflow_tracker 와 같은 꼴
const BACKGROUND_PREFIX = 'background:';

const $graph = document.getElementById('wf-graph');
const $summary = document.getElementById('wf-summary');
const $map = document.getElementById('wf-map');
const $mapLinks = document.getElementById('wf-map-links');
const $mapCols = document.getElementById('wf-map-cols');
const $mapCount = document.getElementById('wf-map-count');
const $jobs = document.getElementById('wf-jobs');
const $jobsEmpty = document.getElementById('wf-jobs-empty');
const $jobsBody = document.getElementById('wf-jobs-body');
const $jobsToggle = document.getElementById('wf-jobs-toggle');
const $jobsBrief = document.getElementById('wf-jobs-brief');
const $daemon = document.getElementById('wf-daemon');
const $card = document.querySelector('.wf-graph-card');
const $tip = document.getElementById('wf-tip');
const $tidy = document.getElementById('wf-tidy');
const $reset = document.getElementById('wf-reset');
const $zoomIn = document.getElementById('wf-zoom-in');
const $zoomOut = document.getElementById('wf-zoom-out');
const $zoomFit = document.getElementById('wf-zoom-fit');

let _agents = [];
let _subagents = [];
let _owners = {};     // sub-agent → 주인 최상위 에이전트(parent 가 있는 기능 담당). 없으면 main 이 주인
let _caps = [];       // { name, description, approval, agents[] }. 한 에이전트만 가진 것이 먼저
const _edgeMap = new Map();  // edge_id → edge. 서버가 보낸 순서(오래된 것부터)
const _jobMap = new Map();   // job_id → job
let _daemonCfg = null;
let _root = null;            // 지도의 뿌리 {session_id, agent, name, model, context_tokens}. 세션을 바꾸면 다시 받는다
let _renderQueued = false;
let _layout = new Map();     // 이번 그림의 노드 자리 key → {x, y, hub?}
let _box = null;             // 공통 능력 상자 {x, y, w, h}. 없으면 null
let _vw = BASE_W;            // 이번 그림의 크기(viewBox 단위)
let _vh = BASE_H;
const _view = { k: 1, x: 0, y: 0 };  // 확대 배율과 보이는 창의 왼쪽 위(viewBox 단위)
const _moved = new Map();    // 사용자가 옮기거나 정렬이 정한 자리 key → {x, y}. 정본은 서버(설치 하나에 하나)
let _layoutLoaded = false;
let _saveTimer = null;

function el(tag, cls, text) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined) node.textContent = text;
  return node;
}

function svg(tag, attrs = {}) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, String(v));
  return node;
}

function clock(ms) {
  if (!ms) return '—';
  return new Date(ms).toLocaleTimeString('ko-KR', { hour12: false });
}

function duration(edge) {
  if (edge.ended_ms == null) return '진행 중';
  const sec = Math.max(0, (edge.ended_ms - edge.started_ms) / 1000);
  return sec < 60 ? `${sec.toFixed(1)}s` : `${Math.round(sec / 60)}m`;
}

function tokens(n) {
  if (n == null) return '';
  return n >= 1000 ? `${(n / 1000).toFixed(1)}k tokens` : `${n} tokens`;
}

function currentSession() {
  return document.body.dataset.session || 'default';
}

function nameOf(id) {
  if (id.startsWith(BACKGROUND_PREFIX)) return '뒤에서 이어 하기';
  const a = _agents.find((x) => x.id === id);
  return a ? a.name : id;
}

// 최상위가 아닌 받는 쪽(sub-agent, focus, orchestrate)과 그 노드를 부른 에이전트. 위임 기록이 없으면 main 의 것
function delegates() {
  const top = new Set(_agents.map((a) => a.id));
  const main = (_agents.find((a) => a.main) || _agents[0] || {}).id;
  const owner = new Map(_subagents.map((id) => [id, top.has(_owners[id]) ? _owners[id] : main]));
  for (const e of _edgeMap.values()) {
    if (!top.has(e.target) && top.has(e.source)) owner.set(e.target, e.source);
  }
  return owner;
}

function shortLabel(name) {
  const plain = name.replace(/^procedure_/, '');
  return plain.length > LABEL_MAX ? `${plain.slice(0, LABEL_MAX - 1)}…` : plain;
}

// 허브마다 잎 줄을 둘 쪽. 왼쪽 절반은 왼쪽으로, 오른쪽 절반은 오른쪽으로 뻗어 이웃 허브의 줄과 섞이지 않는다
function sideOf(i, n) {
  return n === 1 || i >= n / 2 ? 1 : -1;
}

// 허브를 가로로 늘어놓는다. 잎이 있는 허브는 그 쪽에 줄 너비(LEAF_DIST + LABEL_W)를 비운다. 그림 너비는 여기서 정해진다
function plan(owned) {
  const n = _agents.length;
  const hubs = new Map();
  let x = MARGIN;
  _agents.forEach((a, i) => {
    const side = sideOf(i, n);
    const w = (owned.get(a.id) || []).length ? LEAF_DIST + LABEL_W : 0;
    if (side < 0) x += w;
    hubs.set(a.id, { x: x + AGENT_R, side });
    x += AGENT_R * 2 + (side > 0 ? w : 0) + HUB_GAP;
  });
  const width = Math.max(BASE_W, x - HUB_GAP + MARGIN);
  const rows = Math.max(0, ...[...owned.values()].map((l) => l.length));
  return { hubs, width, rows };
}

// 공통 능력 상자의 자리와 칸. 패널 가장 아래에 가로로 길게, 이름이 들어갈 칸 수만큼 열을 두고 줄을 늘린다
function sharedBox(count, width, height) {
  if (!count) return null;
  const w = width - MARGIN * 2;
  const cols = Math.max(1, Math.min(count, Math.floor((w - BOX_PAD * 2) / BOX_COL)));
  const rows = Math.ceil(count / cols);
  const h = BOX_TITLE + BOX_PAD + rows * BOX_ROW + BOX_PAD / 2;
  return { x: MARGIN, y: height - BOX_BOTTOM - h, w, h, cols, rows };
}

function boxHeight(count, width) {
  const b = sharedBox(count, width, 0);
  return b ? b.h + BOX_BOTTOM : 0;
}

// 허브에서 상자 위 모서리로 내려오는 선의 끝. 허브 바로 아래, 상자 너비 안
function boxAnchor(hub) {
  return { x: Math.min(_box.x + _box.w - 30, Math.max(_box.x + 30, hub.x)), y: _box.y };
}

// 잎을 허브 바깥쪽 세로 줄에 LEAF_ROW 간격으로, 허브 높이를 가운데로 둔다. 허브에서 잎으로 가는 직선은
// 위에서 아래로 차례라 서로 안 겹치고, 이름은 줄 바깥으로 뻗어 선과도 안 겹친다
function column(center, side, count) {
  return Array.from({ length: count }, (_, k) => ({
    x: center.x + side * LEAF_DIST,
    y: center.y + (k - (count - 1) / 2) * LEAF_ROW,
    cos: side,
  }));
}

// (부른 쪽, 받는 쪽) 쌍마다 하나로 묶는다. 진행 중이 하나라도 있으면 live, 마지막이 실패면 err
function pairs() {
  const map = new Map();
  for (const e of _edgeMap.values()) {
    const key = `${e.source}→${e.target}`;
    const p = map.get(key) || { source: e.source, target: e.target, count: 0, live: false, lastOk: null };
    p.count += 1;
    if (e.ended_ms == null) p.live = true; else p.lastOk = e.ok;
    map.set(key, p);
  }
  return [...map.values()];
}

function labelAt(x, y, text, cos, cls) {
  const anchor = cos < -0.25 ? 'end' : cos > 0.25 ? 'start' : 'middle';
  const dx = anchor === 'end' ? -10 : anchor === 'start' ? 10 : 0;
  const t = svg('text', { x: x + dx, y: y + (anchor === 'middle' ? 16 : 3.5), class: cls, 'text-anchor': anchor });
  t.textContent = text;
  return t;
}

function titled(node, text) {
  const title = svg('title');
  title.textContent = text;
  node.appendChild(title);
  return node;
}

// ── 자리 ─────────────────────────────────────────────────────────────────────
// 노드마다 키 하나(agent:<id>, leaf:<에이전트>:<이름>, shared:<이름>). 사용자가 옮기거나 정렬이 정한 자리는
// _moved 에 남겨 다시 그려도 지킨다. 서버(/api/workflow/layout)가 정본이고, 받지 못하면 기본 배치로 그린다

function validEntries(obj) {
  return Object.entries(obj || {}).filter(([, v]) => Number.isFinite(v?.x) && Number.isFinite(v?.y));
}

function takeLegacyLayout() {
  try {
    const raw = localStorage.getItem(LEGACY_LAYOUT_KEY);
    return raw ? validEntries(JSON.parse(raw)) : [];
  } catch { return []; }
}

function dropLegacyLayout() {
  try { localStorage.removeItem(LEGACY_LAYOUT_KEY); } catch { /* 못 지워도 서버 값이 먼저다 */ }
}

// 화면을 처음 열 때 한 번. 실패하면 다음에 열 때 다시 받는다
async function loadLayout() {
  if (_layoutLoaded) return;
  const res = await apiFetch(LAYOUT_URL);
  if (!res.ok) return;
  const body = await res.json();
  _layoutLoaded = true;
  const saved = validEntries(body.nodes);
  const legacy = takeLegacyLayout();
  _moved.clear();
  for (const [k, v] of saved.length ? saved : legacy) _moved.set(k, { x: v.x, y: v.y });
  // 서버가 비어 있을 때만 브라우저에 남던 자리를 올린다. 서버에 이미 있으면 그쪽이 이긴다
  if (!saved.length && legacy.length && !(await putLayout())) return;
  if (legacy.length) dropLegacyLayout();
}

async function putLayout() {
  try {
    const res = await apiFetch(LAYOUT_URL, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ nodes: Object.fromEntries(_moved) }),
    });
    return res.ok;
  } catch { return false; }
}

function saveLayout() {
  // 서버 값을 받기 전에 보내면 다른 기기에서 저장한 배치를 덮는다
  if (!_layoutLoaded) return;
  clearTimeout(_saveTimer);
  _saveTimer = setTimeout(putLayout, LAYOUT_SAVE_MS);
}

function clampPos(x, y) {
  return { x: Math.min(_vw - MARGIN, Math.max(MARGIN, x)), y: Math.min(_vh - MARGIN, Math.max(MARGIN, y)) };
}

// ── 확대, 축소, 이동 ─────────────────────────────────────────────────────────
// viewBox 를 옮기고 줄인다. 노드 끌기는 getScreenCTM 을 쓰므로 배율과 무관하게 맞는다
function applyView() {
  $graph.setAttribute('viewBox', `${_view.x} ${_view.y} ${_vw / _view.k} ${_vh / _view.k}`);
}

function zoomAt(factor, px, py) {
  const k = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, _view.k * factor));
  // 포인터 아래 점이 그대로 있도록 창의 왼쪽 위를 옮긴다
  _view.x = px - (px - _view.x) * (_view.k / k);
  _view.y = py - (py - _view.y) * (_view.k / k);
  _view.k = k;
  applyView();
}

function fitView() {
  _view.k = 1; _view.x = 0; _view.y = 0;
  applyView();
}

let _pan = null;

$graph.addEventListener('wheel', (e) => {
  e.preventDefault();
  const p = toView(e);
  zoomAt(e.deltaY < 0 ? ZOOM_STEP : 1 / ZOOM_STEP, p.x, p.y);
}, { passive: false });
// 빈 곳을 끌면 이동. 노드 위에서는 노드가 끌린다(노드 핸들러가 먼저 받고 전파를 막는다)
$graph.addEventListener('pointerdown', (e) => {
  if (e.button !== 0 || e.target.closest('[data-key]')) return;
  e.preventDefault();
  $graph.setPointerCapture(e.pointerId);
  _pan = { cx: e.clientX, cy: e.clientY, vx: _view.x, vy: _view.y, scale: $graph.getScreenCTM()?.a || 1 };
  hideTip();
  $graph.classList.add('panning');
});
$graph.addEventListener('pointermove', (e) => {
  if (!_pan) return;
  _view.x = _pan.vx - (e.clientX - _pan.cx) / _pan.scale;
  _view.y = _pan.vy - (e.clientY - _pan.cy) / _pan.scale;
  applyView();
});
const stopPan = () => { _pan = null; $graph.classList.remove('panning'); };
$graph.addEventListener('pointerup', stopPan);
$graph.addEventListener('pointercancel', stopPan);
$zoomIn?.addEventListener('click', () => zoomAt(ZOOM_STEP, _view.x + _vw / _view.k / 2, _view.y + _vh / _view.k / 2));
$zoomOut?.addEventListener('click', () => zoomAt(1 / ZOOM_STEP, _view.x + _vw / _view.k / 2, _view.y + _vh / _view.k / 2));
$zoomFit?.addEventListener('click', fitView);

function toView(e) {
  const pt = $graph.createSVGPoint();
  pt.x = e.clientX; pt.y = e.clientY;
  const ctm = $graph.getScreenCTM();
  return ctm ? pt.matrixTransform(ctm.inverse()) : { x: 0, y: 0 };
}

// 노드 하나의 자리를 바꾸고 그 노드와 닿은 선만 고친다. 전부 다시 그리면 드래그 중인 요소가 사라진다
function place(key, x, y) {
  const at = _layout.get(key);
  if (!at) return;
  const c = clampPos(x, y);
  at.x = c.x; at.y = c.y;
  _moved.set(key, { x: c.x, y: c.y });
  const g = $graph.querySelector(`[data-key="${CSS.escape(key)}"]`);
  if (g) g.setAttribute('transform', `translate(${c.x},${c.y})`);
  if (at.hub) {
    // 잎의 이름은 허브 반대쪽에 둔다. 옮기면 방향이 바뀐다
    const hub = _layout.get(at.hub);
    const dist = Math.hypot(c.x - hub.x, c.y - hub.y) || 1;
    const label = g?.querySelector('text');
    if (label) {
      const fresh = labelAt(0, 0, label.textContent, (c.x - hub.x) / dist, label.getAttribute('class'));
      for (const name of ['x', 'y', 'text-anchor']) label.setAttribute(name, fresh.getAttribute(name));
    }
  }
  $graph.querySelectorAll(`line[data-from="${CSS.escape(key)}"]`).forEach((l) => { l.setAttribute('x1', c.x); l.setAttribute('y1', c.y); });
  $graph.querySelectorAll(`line[data-to="${CSS.escape(key)}"]`).forEach((l) => { l.setAttribute('x2', c.x); l.setAttribute('y2', c.y); });
  if (_box) {
    $graph.querySelectorAll(`line[data-from="${CSS.escape(key)}"][data-to="box"]`).forEach((l) => {
      const end = boxAnchor(c);
      l.setAttribute('x2', end.x); l.setAttribute('y2', end.y);
    });
  }
  $graph.querySelectorAll(`path.wf-edge[data-from="${CSS.escape(key)}"], path.wf-edge[data-to="${CSS.escape(key)}"]`).forEach((path) => {
    const a = _layout.get(path.dataset.from), b = _layout.get(path.dataset.to);
    if (!a || !b) return;
    const { d, mx, my } = edgePath(a, b, path.dataset);
    path.setAttribute('d', d);
    const count = path.nextElementSibling;
    if (count?.classList.contains('wf-edge-count')) { count.setAttribute('x', mx); count.setAttribute('y', my); }
  });
}

// 같은 쌍의 반대 방향과 겹치지 않게 휜 곡선
function curve(a, b, bend) {
  const mx = (a.x + b.x) / 2 + (b.y - a.y) * bend, my = (a.y + b.y) / 2 - (b.x - a.x) * bend;
  return { d: `M${a.x},${a.y} Q${mx},${my} ${b.x},${b.y}`, mx, my };
}

// 허브 사이 위임: 잎 줄 위의 띠로 올라가는 아치. 꼭대기 높이(peak)를 정해 두면 잎 이름을 가로지르지 않는다
function arch(a, b, peak) {
  // 세제곱 곡선의 t=0.5 높이가 peak 가 되는 제어점 높이
  const top = (4 * peak - (a.y + b.y) / 2) / 3;
  return { d: `M${a.x},${a.y} C${a.x},${top} ${b.x},${top} ${b.x},${b.y}`, mx: (a.x + b.x) / 2, my: peak - 4 };
}

function edgePath(a, b, data) {
  return data.peak ? arch(a, b, +data.peak) : curve(a, b, +data.bend);
}

let _drag = null;

// 끌어서, 또는 방향키로 패널 안에서 옮긴다. 놓으면 자리를 기억한다
function movable(g, key) {
  g.dataset.key = key;
  g.setAttribute('tabindex', '0');
  g.addEventListener('pointerdown', (e) => {
    if (e.button !== 0) return;
    e.preventDefault();
    g.setPointerCapture(e.pointerId);
    const p = toView(e), at = _layout.get(key);
    _drag = { key, dx: at.x - p.x, dy: at.y - p.y, moved: false };
    hideTip();
    $graph.classList.add('dragging');
  });
  g.addEventListener('pointermove', (e) => {
    if (!_drag || _drag.key !== key) { moveTip(e); return; }
    const p = toView(e);
    place(key, p.x + _drag.dx, p.y + _drag.dy);
    _drag.moved = true;
  });
  const stop = () => {
    if (!_drag || _drag.key !== key) return;
    if (_drag.moved) saveLayout();
    _drag = null;
    $graph.classList.remove('dragging');
  };
  g.addEventListener('pointerup', stop);
  g.addEventListener('pointercancel', stop);
  g.addEventListener('keydown', (e) => {
    const d = ARROWS[e.key];
    if (!d) return;
    e.preventDefault();
    const at = _layout.get(key), step = e.shiftKey ? NUDGE * 3 : NUDGE;
    place(key, at.x + d[0] * step, at.y + d[1] * step);
    saveLayout();
  });
}

// ── 호버 한 줄 설명 ───────────────────────────────────────────────────────────
function describe(g, name, text) {
  g.addEventListener('pointerenter', (e) => {
    if (_drag) return;
    $tip.querySelector('b').textContent = name;
    $tip.querySelector('span').textContent = text || '설명 없음';
    $tip.hidden = false;
    moveTip(e);
  });
  g.addEventListener('pointerleave', hideTip);
}

function moveTip(e) {
  if ($tip.hidden) return;
  const r = $card.getBoundingClientRect();
  let x = e.clientX - r.left + 14, y = e.clientY - r.top + 14;
  if (x + $tip.offsetWidth > r.width - 8) x = Math.max(8, e.clientX - r.left - $tip.offsetWidth - 14);
  if (y + $tip.offsetHeight > r.height - 8) y = Math.max(8, e.clientY - r.top - $tip.offsetHeight - 14);
  $tip.style.left = `${x}px`;
  $tip.style.top = `${y}px`;
}

function hideTip() { $tip.hidden = true; }

// ── 정렬 최적화 ──────────────────────────────────────────────────────────────
// 그려진 글상자(원과 이름)를 재서 겹치는 쌍을 겹침이 작은 축으로 밀어낸다. 에이전트 허브는 고정이고 잎과 공통 능력만
// 움직인다. 패널 밖으로는 못 나간다. 겹침이 없어지거나 TIDY_ITER 번 돌면 멈춘다
function tidy() {
  const boxes = [];
  for (const g of $graph.querySelectorAll('.wf-nodes [data-key]')) {
    const at = _layout.get(g.dataset.key);
    const b = g.getBBox();
    if (!at || !b.width) continue;
    boxes.push({ key: g.dataset.key, fixed: g.classList.contains('top'), x: at.x, y: at.y,
      l: b.x - TIDY_PAD, t: b.y - TIDY_PAD, w: b.width + TIDY_PAD * 2, h: b.height + TIDY_PAD * 2 });
  }
  const left = (o) => o.x + o.l, top = (o) => o.y + o.t;
  for (let iter = 0; iter < TIDY_ITER; iter++) {
    let moved = false;
    for (let i = 0; i < boxes.length; i++) {
      for (let j = i + 1; j < boxes.length; j++) {
        const a = boxes[i], b = boxes[j];
        if (a.fixed && b.fixed) continue;
        const ox = Math.min(left(a) + a.w, left(b) + b.w) - Math.max(left(a), left(b));
        const oy = Math.min(top(a) + a.h, top(b) + b.h) - Math.max(top(a), top(b));
        if (ox <= 0 || oy <= 0) continue;
        moved = true;
        const axis = ox < oy ? 'x' : 'y';
        const push = (axis === 'x' ? ox : oy) + 1;
        const sign = (axis === 'x' ? a.x <= b.x : a.y <= b.y) ? -1 : 1;
        const share = a.fixed || b.fixed ? push : push / 2;
        if (!a.fixed) a[axis] += sign * share;
        if (!b.fixed) b[axis] -= sign * share;
      }
    }
    for (const o of boxes) {
      if (o.fixed) continue;
      o.x = Math.min(_vw - o.l - o.w, Math.max(-o.l, o.x));
      o.y = Math.min(_vh - o.t - o.h, Math.max(-o.t, o.y));
    }
    if (!moved) break;
  }
  for (const o of boxes) {
    const at = _layout.get(o.key);
    if (!o.fixed && (Math.abs(at.x - o.x) > 0.5 || Math.abs(at.y - o.y) > 0.5)) _moved.set(o.key, { x: o.x, y: o.y });
  }
  saveLayout();
  queueRender();
}

function resetLayout() {
  _moved.clear();
  saveLayout();
  queueRender();
}

$tidy?.addEventListener('click', tidy);
$reset?.addEventListener('click', resetLayout);

// ── 그리기 ───────────────────────────────────────────────────────────────────
function renderGraph() {
  $graph.replaceChildren();
  hideTip();
  const color = new Map(_agents.map((a) => [a.id, a.primary]));
  _layout = new Map();
  const at = (key, x, y, extra = {}) => {
    const saved = _moved.get(key);
    const node = { x: saved ? saved.x : x, y: saved ? saved.y : y, ...extra };
    _layout.set(key, node);
    return node;
  };
  const agentKey = (id) => `agent:${id}`;
  const known = new Set(_agents.map((a) => a.id));
  const shared = _caps.filter((c) => c.agents.length > 1 && c.agents.every((id) => known.has(id)));

  // 잎: 에이전트마다 그 에이전트만 가진 능력과 위임받는 노드. 배치는 잎 수를 알아야 정해진다
  const owned = new Map(_agents.map((a) => [a.id, []]));
  for (const cap of _caps) if (cap.agents.length === 1 && owned.has(cap.agents[0])) owned.get(cap.agents[0]).push({ cap });
  for (const [id, by] of delegates()) if (owned.has(by)) owned.get(by).push({ sub: id });
  const { hubs, width, rows } = plan(owned);
  _vw = width;
  const top = MARGIN + ARC_BAND;
  _vh = Math.max(BASE_H, top + rows * LEAF_ROW + MARGIN + boxHeight(shared.length, _vw));
  _box = sharedBox(shared.length, _vw, _vh);
  const floor = _box ? _box.y : _vh;
  for (const [id, h] of hubs) at(agentKey(id), h.x, top + (floor - top) / 2);
  applyView();
  const pos = (id) => _layout.get(agentKey(id));

  const linkLayer = svg('g', { class: 'wf-links' });
  const nodeLayer = svg('g', { class: 'wf-nodes' });
  $graph.append(linkLayer, nodeLayer);

  for (const [agentId, leaves] of owned) {
    const center = pos(agentId);
    column(center, hubs.get(agentId).side, leaves.length).forEach((p, k) => {
      const leaf = leaves[k];
      const name = leaf.sub || leaf.cap.name;
      const key = `leaf:${agentId}:${name}`;
      const n = at(key, p.x, p.y, { hub: agentKey(agentId) });
      const dist = Math.hypot(n.x - center.x, n.y - center.y) || 1;
      linkLayer.appendChild(svg('line', { x1: center.x, y1: center.y, x2: n.x, y2: n.y, class: 'wf-cap-link', 'data-owners': agentId, 'data-from': agentKey(agentId), 'data-to': key, style: `--node-color:${color.get(agentId)}` }));
      const g = svg('g', { class: `wf-leaf ${leaf.sub ? 'sub' : ''} ${leaf.cap?.approval ? 'approval' : ''}`, 'data-owners': agentId, transform: `translate(${n.x},${n.y})` });
      g.style.setProperty('--node-color', color.get(agentId));
      g.appendChild(svg('circle', { r: leaf.sub ? SUB_R : LEAF_R }));
      g.appendChild(labelAt(0, 0, shortLabel(leaf.sub ? nameOf(name) : name), (n.x - center.x) / dist, 'wf-leaf-label'));
      movable(g, key);
      describe(g, leaf.sub ? nameOf(leaf.sub) : `${name}${leaf.cap.approval ? ' · 승인 필요' : ''}`,
        leaf.sub ? `${nameOf(agentId)} 가 위임하는 에이전트` : leaf.cap.description);
      nodeLayer.appendChild(g);
    });
  }

  // 공통 능력: 패널 가장 아래 상자 안에 줄지어 두고, 그 능력을 함께 쓰는 허브마다 상자로 선 하나를 내린다
  if (_box) {
    const boxOwners = _agents.filter((a) => shared.some((c) => c.agents.includes(a.id))).map((a) => a.id);
    const rect = svg('rect', { x: _box.x, y: _box.y, width: _box.w, height: _box.h, rx: 6, class: 'wf-box', 'data-owners': boxOwners.join(' ') });
    linkLayer.appendChild(rect);
    const title = svg('text', { x: _box.x + BOX_PAD, y: _box.y + 13, class: 'wf-box-title', 'data-owners': boxOwners.join(' ') });
    title.textContent = `함께 쓰는 능력 · ${shared.length}`;
    linkLayer.appendChild(title);
    for (const id of boxOwners) {
      const a = pos(id), end = boxAnchor(a);
      linkLayer.appendChild(svg('line', { x1: a.x, y1: a.y, x2: end.x, y2: end.y, class: 'wf-cap-link shared', 'data-owners': id, 'data-from': agentKey(id), 'data-to': 'box', style: `--node-color:${color.get(id)}` }));
    }
  }
  shared.forEach((cap, i) => {
    const col = i % _box.cols, row = Math.floor(i / _box.cols);
    const key = `shared:${cap.name}`;
    const n = at(key, _box.x + BOX_PAD + 6 + col * BOX_COL, _box.y + BOX_TITLE + BOX_PAD + row * BOX_ROW);
    const owners = cap.agents.join(' ');
    const g = svg('g', { class: `wf-leaf shared ${cap.approval ? 'approval' : ''}`, 'data-owners': owners, transform: `translate(${n.x},${n.y})` });
    g.appendChild(svg('circle', { r: LEAF_R - 1 }));
    const label = svg('text', { x: 9, y: 3.5, class: 'wf-leaf-label', 'text-anchor': 'start' });
    label.textContent = shortLabel(cap.name);
    g.appendChild(label);
    movable(g, key);
    describe(g, `${cap.name}${cap.approval ? ' · 승인 필요' : ''} · ${cap.agents.map(nameOf).join(', ')} 공통`, cap.description);
    nodeLayer.appendChild(g);
  });

  // 위임: 최상위 에이전트 사이, 또는 에이전트와 위임받는 잎 사이. 같은 쌍은 하나로 묶는다
  const leafKey = new Map();
  for (const [agentId, leaves] of owned) for (const leaf of leaves) if (leaf.sub) leafKey.set(leaf.sub, `leaf:${agentId}:${leaf.sub}`);
  const keyFor = (id) => (pos(id) ? agentKey(id) : leafKey.get(id));
  const busy = new Set();
  const links = pairs();
  for (const p of links) {
    const ka = keyFor(p.source), kb = keyFor(p.target);
    const a = ka && _layout.get(ka), b = kb && _layout.get(kb);
    if (!a || !b) continue;
    if (p.live) { busy.add(p.source); busy.add(p.target); }
    // 에이전트 사이 위임은 맨 위 띠로 올라가는 아치. 반대 방향은 조금 더 높게 둬 둘이 겹치지 않는다
    const between = pos(p.source) && pos(p.target);
    const data = between ? { 'data-peak': MARGIN + (a.x < b.x ? ARC_BAND * 0.6 : ARC_BAND * 0.25) } : { 'data-bend': 0.12 };
    const { d, mx, my } = between ? arch(a, b, data['data-peak']) : curve(a, b, data['data-bend']);
    const cls = ['wf-edge', p.live ? 'live' : '', p.lastOk === false ? 'err' : ''].join(' ').trim();
    const path = svg('path', { d, class: cls, 'marker-end': 'url(#wf-arrow)', 'data-owners': `${p.source} ${p.target}`, 'data-from': ka, 'data-to': kb, ...data });
    linkLayer.appendChild(titled(path, `${nameOf(p.source)} → ${nameOf(p.target)} · ${p.count}회`));
    const count = svg('text', { x: mx, y: my, class: 'wf-edge-count', 'text-anchor': 'middle' });
    count.textContent = `×${p.count}`;
    linkLayer.appendChild(count);
  }
  const defs = svg('defs');
  const marker = svg('marker', { id: 'wf-arrow', viewBox: '0 0 10 10', refX: 10 + AGENT_R / 2, refY: 5, markerWidth: 6, markerHeight: 6, orient: 'auto-start-reverse' });
  marker.appendChild(svg('path', { d: 'M0,0 L10,5 L0,10 z', fill: 'currentColor', class: 'wf-arrow' }));
  defs.appendChild(marker);
  $graph.prepend(defs);

  // 에이전트 허브. 올리면 그 에이전트의 능력만 밝게 남는다
  for (const a of _agents) {
    const p = pos(a.id);
    const g = svg('g', { class: `wf-node top ${busy.has(a.id) ? 'busy' : ''}`, 'data-owners': a.id, transform: `translate(${p.x},${p.y})` });
    g.style.setProperty('--node-color', a.primary);
    g.appendChild(svg('circle', { r: AGENT_R }));
    const initial = svg('text', { y: 5, class: 'wf-node-initial' });
    initial.textContent = a.name.replace(/[^A-Za-z0-9가-힣]/g, '').slice(0, 1).toUpperCase() || '•';
    const name = svg('text', { y: AGENT_R + 16 });
    name.textContent = a.name;
    g.append(initial, name);
    const ownCount = (owned.get(a.id) || []).length;
    const sub = svg('text', { y: AGENT_R + 29, class: 'wf-node-sub' });
    sub.textContent = `${a.main ? 'main · ' : ''}고유 ${ownCount}`;
    g.appendChild(sub);
    g.addEventListener('pointerenter', () => spotlight(a.id));
    g.addEventListener('pointerleave', () => spotlight(null));
    movable(g, agentKey(a.id));
    describe(g, a.name, a.description || (a.main ? 'main 에이전트' : ''));
    nodeLayer.appendChild(g);
  }
  const live = links.filter((p) => p.live).length;
  const own = [...owned.values()].reduce((n, l) => n + l.length, 0);
  $summary.textContent = `${_agents.length} agents · 고유 ${own} · 공통 ${shared.length} · ${live} live`;
}

// 에이전트 하나에 닿은 것만 밝히고 나머지는 흐리게. null 이면 모두 원래대로
function spotlight(agentId) {
  $graph.classList.toggle('spotlight', !!agentId);
  $graph.querySelectorAll('[data-owners]').forEach((node) => {
    node.classList.toggle('lit', !!agentId && node.dataset.owners.split(' ').includes(agentId));
  });
}

// ── 에이전트 지도 ─────────────────────────────────────────────────────────────
// 받는 쪽 세션 id. 서버의 peer_session_id 와 같은 꼴이라 그 세션에서 나간 위임을 자식으로 잇는다
function peerSession(edge) {
  return `peer-${edge.source}-${edge.target}`;
}

// 보는 세션에서 나간 위임을 뿌리 아래 깊이 1, 그 받는 쪽 세션(ask)에서 부모가 열려 있는 동안 나간 위임을 깊이 2... 로.
// 옛 간선(session_id 없음)은 어느 세션 것인지 몰라 빼고, 같은 세션의 위임은 시작 순이다. 순수 함수
function mapTree(edges, sessionId) {
  const all = [...edges].sort((a, b) => a.started_ms - b.started_ms);
  const nodes = [];
  const walk = (parent, sid, depth) => {
    if (depth > MAP_DEPTH_MAX) return;
    for (const e of all) {
      if (e.session_id !== sid) continue;
      if (parent && (e.started_ms < parent.started_ms || (parent.ended_ms != null && e.started_ms > parent.ended_ms))) continue;
      const node = { edge: e, parent, depth };
      nodes.push(node);
      if (e.kind === 'ask') walk(e, peerSession(e), depth + 1);
    }
  };
  walk(null, sessionId, 1);
  return nodes;
}

function mapCard(cls, title, meta, dotted) {
  const card = el('div', `wf-map-node ${cls}`.trim());
  const ttl = el('div', 'ttl');
  if (dotted) ttl.appendChild(el('i', 'dot'));
  ttl.appendChild(el('span', '', title));
  card.append(ttl, el('div', 'meta', meta));
  return card;
}

function renderMap() {
  const sid = currentSession();
  const nodes = mapTree(_edgeMap.values(), sid);
  $mapCount.textContent = `${sid} · 위임 ${nodes.length}`;
  $mapLinks.replaceChildren();
  if (!_root) { $mapCols.replaceChildren(); return; }
  const rootAgent = _agents.find((a) => a.id === _root.agent);
  const root = mapCard('root', _root.name || _root.agent, `${_root.model || '—'} · ${tokens(_root.context_tokens) || '0 tokens'} in context`, false);
  root.style.setProperty('--node-color', rootAgent?.primary || '');
  root.dataset.key = 'root';
  const depths = Math.max(0, ...nodes.map((n) => n.depth));
  const cols = [el('div', 'wf-map-col')];
  cols[0].appendChild(root);
  for (let d = 1; d <= depths; d++) cols.push(el('div', 'wf-map-col'));
  nodes.forEach((n, i) => {
    const e = n.edge;
    const label = (e.label || '—').length > MAP_LABEL_MAX ? `${e.label.slice(0, MAP_LABEL_MAX - 1)}…` : (e.label || '—');
    const state = e.ended_ms == null ? 'live' : (e.ok === false ? 'err' : '');
    const bits = [nameOf(e.target), duration(e)];
    if (e.tokens != null) bits.push(tokens(e.tokens));
    if (e.ok === false) bits.push('실패');
    const card = mapCard(`${state} ${e.kind === 'ask' ? 'link' : ''}`, label, bits.join(' · '), true);
    card.title = `${nameOf(e.source)} → ${nameOf(e.target)} · ${KIND_LABEL[e.kind] || e.kind} · ${clock(e.started_ms)}\n${e.label || ''}`;
    card.dataset.key = String(i);
    card.dataset.parent = n.parent ? String(nodes.indexOf(n.parent)) : 'root';
    card.dataset.state = state;
    if (e.kind === 'ask') {
      // 받는 쪽 세션으로. 세션 목록이 아니라 지도에서 바로 들어간다
      card.setAttribute('role', 'button');
      card.setAttribute('tabindex', '0');
      const open = () => document.dispatchEvent(new CustomEvent('session:open', { detail: peerSession(e) }));
      card.addEventListener('click', open);
      card.addEventListener('keydown', (ev) => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); open(); } });
    }
    cols[n.depth].appendChild(card);
  });
  $mapCols.replaceChildren(...cols);
  requestAnimationFrame(drawMapLinks);
}

// 카드 자리를 재서 부모 오른쪽 가운데에서 자식 왼쪽 가운데로 직각 선을 긋는다. 열 사이 가운데에서 꺾는다
function drawMapLinks() {
  $mapLinks.replaceChildren();
  const base = $mapCols.getBoundingClientRect();
  const rect = (card) => {
    const r = card.getBoundingClientRect();
    return { l: r.left - base.left + $mapCols.offsetLeft, r: r.right - base.left + $mapCols.offsetLeft, cy: r.top - base.top + $mapCols.offsetTop + r.height / 2 };
  };
  const byKey = new Map([...$mapCols.querySelectorAll('.wf-map-node')].map((c) => [c.dataset.key, c]));
  for (const card of byKey.values()) {
    const parent = byKey.get(card.dataset.parent);
    if (!parent) continue;
    const a = rect(parent), b = rect(card);
    const mid = (a.r + b.l) / 2;
    const path = svg('path', { d: `M${a.r},${a.cy} H${mid} V${b.cy} H${b.l}`, class: card.dataset.state || '' });
    $mapLinks.appendChild(path);
  }
}

new ResizeObserver(() => { if (currentView() === 'workflow') drawMapLinks(); }).observe($map);

function jobState(job) {
  if (job.running) return ['실행 중', 'st-run'];
  if (job.enabled === false) return ['꺼짐', 'st-off'];
  if (job.last_ok === false) return ['실패', 'st-err'];
  if (job.last_ok === true) return ['성공', 'st-ok'];
  return ['대기', 'st-off'];
}

function jobsOpen() {
  try { return localStorage.getItem(JOBS_OPEN_KEY) === '1'; } catch { return false; }
}

function setJobsOpen(open) {
  $jobsBody.hidden = !open;
  $jobsToggle.setAttribute('aria-expanded', String(open));
  try { localStorage.setItem(JOBS_OPEN_KEY, open ? '1' : '0'); } catch { /* 기억 못 해도 이번 화면은 바뀐다 */ }
}

$jobsToggle?.addEventListener('click', () => setJobsOpen($jobsBody.hidden));
setJobsOpen(jobsOpen());

function renderJobs() {
  const jobs = [..._jobMap.values()];
  $jobsEmpty.hidden = jobs.length > 0;
  const running = jobs.filter((j) => j.running).length, failed = jobs.filter((j) => j.last_ok === false).length;
  $jobsBrief.textContent = jobs.length ? `${jobs.length} 작업 · 실행 중 ${running} · 실패 ${failed}` : '작업 없음';
  $jobs.replaceChildren(...jobs.map((job) => {
    const tr = el('tr');
    const [state, cls] = jobState(job);
    const name = el('td', '', job.label || job.job_id);
    name.title = job.last_error || job.job_id;
    const next = job.next_run ? new Date(job.next_run).toLocaleString('ko-KR', { hour12: false }) : '—';
    tr.append(name, el('td', cls, state), el('td', '', String(job.runs)), el('td', '', clock(job.last_ended_ms || job.last_started_ms)), el('td', '', next));
    return tr;
  }));
  if (_daemonCfg) {
    const d = _daemonCfg;
    $daemon.textContent = d.enabled ? `성찰 ${d.trigger} · ${d.interval_sec}s` : '성찰 꺼짐';
  }
}

function render() {
  _renderQueued = false;
  if (currentView() !== 'workflow') return;
  renderGraph();
  renderMap();
  renderJobs();
}

// 이벤트가 몰려도 한 프레임에 한 번만 그린다
function queueRender() {
  if (_renderQueued) return;
  _renderQueued = true;
  requestAnimationFrame(render);
}

export async function loadWorkflow() {
  try { await loadLayout(); } catch { /* 배치를 못 받아도 기본 배치로 그린다 */ }
  try {
    const [graph, jobs] = await Promise.all([
      apiFetch(`/api/workflow?session=${encodeURIComponent(currentSession())}`).then((r) => (r.ok ? r.json() : null)),
      apiFetch('/api/jobs').then((r) => (r.ok ? r.json() : null)),
    ]);
    if (graph) {
      _agents = graph.agents || [];
      _subagents = graph.subagents || [];
      _owners = graph.subagent_owners || {};
      _caps = graph.capabilities || [];
      _root = graph.root || null;
      _edgeMap.clear();
      for (const e of graph.edges || []) _edgeMap.set(e.edge_id, e);
    }
    if (jobs) {
      _jobMap.clear();
      for (const j of jobs.jobs || []) _jobMap.set(j.job_id, j);
      _daemonCfg = jobs.daemon || null;
    }
  } catch { /* 연결이 끊겼으면 다음에 열 때 다시 받는다 */ }
  queueRender();
}

export function onWorkflowEdge(edge) {
  if (!edge || !edge.edge_id) return;
  // 받은 위임은 맨 뒤로. 같은 id 로 다시 열린 Focus 영역도 최신 자리에 온다
  if (edge.ended_ms == null) _edgeMap.delete(edge.edge_id);
  _edgeMap.set(edge.edge_id, { ...(_edgeMap.get(edge.edge_id) || {}), ...edge });
  queueRender();
}

export function onJobChanged(job) {
  if (!job || !job.job_id) return;
  // 스케줄 목록에서 온 enabled, next_run 은 실행 기록에 없다. 있던 값을 지킨다
  _jobMap.set(job.job_id, { ...(_jobMap.get(job.job_id) || {}), ...job });
  queueRender();
}

onViewOpen('workflow', loadWorkflow);
// 세션이 바뀌면 지도의 뿌리도 바뀐다. 화면이 열려 있을 때만 다시 받고, 아니면 열 때 받는다
document.addEventListener('session:connected', () => { if (currentView() === 'workflow') loadWorkflow(); });
