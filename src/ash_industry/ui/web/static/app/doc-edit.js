// 문서 창의 편집 보기. 구조는 /api/docs/* 로 받아 글자(textContent)로만 넣는다.
// 고친 곳은 [저장](plan_edit 뒤 apply_edit)으로 새 파일에 저장한다. 말로 맡기는 편집은 채팅에서 Evi 가 받는다.
import { logActivity } from './shell.js';
import { el, button, callApi, postJson, errorLines } from './doc-ui.js';
import { showMedia, adoptDocument } from './media.js';

const EDITABLE = /\.(docx|hwpx|hwp|xlsx|pptx)$/i;
const GRID_MAX = 3000;       // 이보다 칸이 많은 표는 격자 대신 칸 목록으로 그린다

const $stage = document.getElementById('media-stage');
const $pager = document.getElementById('media-pager');
const $edit = document.getElementById('media-edit');

let _artifact = null;        // 문서 창에 띄운 문서 첨부. source 가 원본 경로다
let _edits = new Map();      // target id -> { before, text }
let _seq = 0;
let _acts = null;            // 편집 보기 머리의 단추 자리
let _msg = null;             // 편집 보기 위쪽의 문제 알림 자리
let _mode = '';              // 'edit' | '' (그림)

function panel(title, ...children) {
  $pager.classList.add('hidden');
  $stage.classList.add('doc', 'doc-panel');
  const head = el('div', { className: 'doc-panel-head' }, title ? el('span', { textContent: title }) : el('span'));
  $stage.replaceChildren(el('div', { className: 'doc-panel-body' }, head, ...children));
  $stage.scrollTop = 0;
  return head;
}

function loading(text) {
  $stage.classList.add('doc', 'doc-panel');
  $stage.replaceChildren(el('p', { className: 'media-loading', textContent: text }));
}

// 머리의 [편집] 은 켜고 끄는 단추다. 다시 누르면 그림으로 돌아간다
function setMode(mode) {
  _mode = mode;
  $edit?.classList.toggle('active', mode === 'edit');
}

function backToView() {
  setMode('');
  $stage.classList.remove('doc-panel');
  if (_artifact) showMedia(_artifact);
}

// ── 편집 보기(에디터) ─────────────────────────────────────
// 흰 종이에 문서 순서대로(표는 anchor 자리에) 그리고, 문단과 칸을 그 자리에서 바로 고친다.
// 문단을 새로 만들거나 지우지는 못하므로 문단 안의 Enter 는 막고, 칸 안에서만 줄을 바꾼다

const PLAIN = (() => { try { const d = document.createElement('div'); d.contentEditable = 'plaintext-only'; return true; } catch { return false; } })();

function refreshActs() {
  if (!_acts) return;
  const n = _edits.size;
  _acts.replaceChildren(
    el('span', { className: 'doc-count', textContent: n ? `${n}곳 고침` : '편집 중' }),
    button('저장', () => saveEdits(), { disabled: !n, title: 'Ctrl+S' }),
    button('취소', () => { _edits.clear(); openEditor(); }, { disabled: !n }),
  );
}

function showMessages(lines, kind = 'doc-error') {
  _msg?.replaceChildren(...lines.map((t) => el('p', { className: kind, textContent: t })));
}

function editableText(node) {
  return node.innerText.replace(/\n$/, '');
}

// 문단이나 칸 하나를 바로 고칠 수 있게 한다. Esc 는 그 자리를 원래 글로 되돌린다
function editable(node, id, text, { multiline = false } = {}) {
  node.dataset.id = id;
  node.classList.add('doc-editable');
  node.contentEditable = PLAIN ? 'plaintext-only' : 'true';
  node.spellcheck = false;
  const pending = _edits.get(id);
  node.textContent = pending ? pending.text : text;
  const mark = () => {
    const changed = _edits.has(id);
    node.classList.toggle('changed', changed);
    if (changed) node.title = `원래: ${text || '(빈 칸)'}`;
    else node.removeAttribute('title');
  };
  mark();
  node.addEventListener('input', () => {
    const now = editableText(node);
    if (now === text) _edits.delete(id);
    else _edits.set(id, { before: text, text: now });
    mark();
    refreshActs();
  });
  node.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      e.stopPropagation();
      node.textContent = text;
      _edits.delete(id);
      mark();
      refreshActs();
    } else if (e.key === 'Enter' && !multiline) {
      e.preventDefault();
    }
  });
}

// DOCX 는 스타일 이름(Title, Heading 1), PPTX 는 도형 이름(Title 1, Subtitle 2)이 온다
function blockTag(style = '') {
  if (/^(title(\s*\d+)?|제목)$/i.test(style)) return ['h1', 'doc-title'];
  if (/^subtitle/i.test(style)) return ['h3', 'doc-h2'];
  if (/heading\s*1|제목\s*1|개요\s*1/i.test(style)) return ['h2', 'doc-h1'];
  if (/heading\s*[2-9]|제목\s*[2-9]|개요\s*[2-9]/i.test(style)) return ['h3', 'doc-h2'];
  return ['p', 'doc-p'];
}

function paragraphBlock(p) {
  const [tag, cls] = blockTag(p.style);
  const node = el(tag, { className: cls });
  node.dataset.text = p.text;
  if (p.readonly) {
    node.textContent = p.text;
    node.classList.add('readonly');
    node.title = '읽기 전용(노트, 차트, PDF 글 줄)';
  } else {
    editable(node, p.id, p.text);
  }
  return node;
}

// 병합 폭(row_span, col_span)을 rowspan, colspan 으로. 병합에 덮인 자리는 칸을 만들지 않는다
function tableGrid(table) {
  const wrap = el('div', { className: 'doc-table' });
  if (table.name) wrap.append(el('div', { className: 'doc-sheet', textContent: table.name }));
  if (table.rows * table.cols > GRID_MAX) {
    for (const c of table.cells) {
      const row = el('div', { className: 'doc-cell-line' });
      if (c.address) row.append(el('span', { className: 'doc-id', textContent: c.address }));
      const body = el('div', { className: 'doc-p' });
      editable(body, c.id, c.text, { multiline: true });
      if (c.address) body.dataset.addr = c.address;
      row.append(body);
      wrap.append(row);
    }
    return wrap;
  }
  const byPos = new Map(table.cells.map((c) => [`${c.row},${c.col}`, c]));
  const covered = new Set();
  for (const c of table.cells) {
    for (let r = c.row; r < c.row + (c.row_span || 1); r++) {
      for (let k = c.col; k < c.col + (c.col_span || 1); k++) if (r !== c.row || k !== c.col) covered.add(`${r},${k}`);
    }
  }
  const grid = el('table', { className: 'doc-grid' });
  for (let r = 0; r < table.rows; r++) {
    const tr = el('tr');
    for (let k = 0; k < table.cols; k++) {
      const key = `${r},${k}`;
      if (covered.has(key)) continue;
      const c = byPos.get(key);
      const td = el('td');
      if (c) {
        if ((c.row_span || 1) > 1) td.rowSpan = c.row_span;
        if ((c.col_span || 1) > 1) td.colSpan = c.col_span;
        editable(td, c.id, c.text, { multiline: true });
        if (c.address) td.dataset.addr = c.address;
      } else {
        // XLSX 의 값 없는 칸은 구조에 없어 고칠 대상이 아니다
        td.className = 'doc-void';
      }
      tr.append(td);
    }
    grid.append(tr);
  }
  wrap.dataset.table = table.name || table.id;
  wrap.append(grid);
  return wrap;
}

// 본문 문단(p0, p1…) 사이에 표를 anchor 자리에 끼운다. anchor 가 없는 표는 끝에 둔다
function bodyBlocks(paragraphs, tables) {
  const placed = tables.filter((t) => Number.isInteger(t.anchor)).sort((a, b) => a.anchor - b.anchor);
  const rest = tables.filter((t) => !Number.isInteger(t.anchor));
  const out = [];
  let ti = 0;
  paragraphs.forEach((p, i) => {
    const at = /^p(\d+)$/.exec(p.id) ? Number(p.id.slice(1)) : i;
    while (ti < placed.length && placed[ti].anchor <= at) out.push(tableGrid(placed[ti++]));
    out.push(paragraphBlock(p));
  });
  while (ti < placed.length) out.push(tableGrid(placed[ti++]));
  return [...out, ...rest.map(tableGrid)];
}

// PPTX 는 슬라이드마다 종이 한 장(도형 글, 표, 차트, 노트 순)
function slidePages(paragraphs, tables) {
  const slides = new Map();
  const page = (n) => {
    if (!slides.has(n)) slides.set(n, { body: [], tables: [] });
    return slides.get(n);
  };
  for (const p of paragraphs) {
    const m = /^s(\d+)/.exec(p.id);
    if (m) page(Number(m[1])).body.push(p);
  }
  for (const t of tables) {
    const m = /(\d+)\s*$/.exec(t.name || '');
    if (m) page(Number(m[1]) - 1).tables.push({ ...t, name: '' });
  }
  return [...slides.keys()].sort((a, b) => a - b).map((n) => {
    const { body, tables: ts } = slides.get(n);
    const notes = body.filter((p) => /^s\d+np/.test(p.id));
    const main = body.filter((p) => !/^s\d+np/.test(p.id));
    return el('div', { className: 'doc-paper doc-slide' },
      el('div', { className: 'doc-sheet', textContent: `슬라이드 ${n + 1}` }),
      ...main.map(paragraphBlock), ...ts.map(tableGrid),
      ...(notes.length ? [el('div', { className: 'doc-notes' }, ...notes.map(paragraphBlock))] : []),
    );
  });
}

function pages(body) {
  const paragraphs = body.paragraphs || [];
  const tables = body.tables || [];
  if (body.format === 'pptx') return slidePages(paragraphs, tables);
  if (body.format === 'xlsx') return tables.map((t) => el('div', { className: 'doc-paper doc-sheet-page' }, tableGrid(t)));
  return [el('div', { className: 'doc-paper' }, ...bodyBlocks(paragraphs, tables))];
}

async function openEditor(focusId = '') {
  if (!_artifact?.source) return;
  setMode('edit');
  const seq = ++_seq;
  loading('문서를 여는 중…');
  const { ok, status, body } = await callApi(`/api/docs/structure?path=${encodeURIComponent(_artifact.source)}`);
  if (seq !== _seq) return;
  if (!ok) { panel('', ...errorLines(body, status).map((t) => el('p', { className: 'doc-error', textContent: t }))); return; }
  _acts = el('div', { className: 'doc-acts' });
  _msg = el('div', { className: 'doc-msg' });
  const omitted = (body.tables_omitted || []).map((stub) =>
    el('p', { className: 'doc-hint', textContent: `${stub.name || '표'}: 칸 ${stub.cells_total}개라 여기서는 빼고 보입니다` }));
  const head = panel('', _msg, ...omitted, el('div', { className: 'doc-desk' }, ...pages(body)));
  head.classList.add('doc-toolbar');
  head.append(_acts);
  refreshActs();
  if (focusId) highlight(focusId);
}

function highlight(id) {
  let target;
  if (id.startsWith('addr:')) target = $stage.querySelector(`[data-addr="${CSS.escape(id.slice(5))}"]`);
  else if (id.startsWith('text:')) target = [...$stage.querySelectorAll('[data-text]')].find((n) => n.dataset.text.includes(id.slice(5)));
  else target = $stage.querySelector(`[data-id="${CSS.escape(id)}"]`);
  if (!target) return;
  target.classList.add('doc-focus');
  target.scrollIntoView({ block: 'center' });
}

function editList() {
  return [..._edits].map(([target, e]) => ({ target, text: e.text }));
}

// 미리보기(plan)에 문제가 없으면 바로 적용(apply)하고, 새 파일을 그대로 편집 보기로 다시 연다.
// 문제가 있으면 고친 곳을 그대로 두고 문제만 보인다
async function saveEdits() {
  if (!_edits.size) return;
  const seq = ++_seq;
  _acts?.replaceChildren(el('span', { className: 'doc-count', textContent: '저장하는 중…' }));
  showMessages([]);
  const plan = await postJson('/api/docs/plan', { path: _artifact.source, replacements: editList() });
  if (seq !== _seq) return;
  if (!plan.ok || !plan.body.ok) {
    showMessages(plan.ok ? (plan.body.issues || ['저장할 수 없습니다']) : errorLines(plan.body, plan.status));
    refreshActs();
    return;
  }
  const { ok, status, body } = await postJson('/api/docs/apply', { plan_id: plan.body.plan_id });
  if (seq !== _seq) return;
  if (!ok) { showMessages(errorLines(body, status)); refreshActs(); return; }
  _edits.clear();
  const verify = body.verify?.ok ? '검증 통과' : `검증 문제 ${(body.verify?.issues || []).length}건`;
  logActivity(`▤ 저장 · ${body.output} (${verify})`, body.verify?.ok ? 'ok' : 'warn');
  if (body.document) { _artifact = body.document; adoptDocument(body.document); }
  else _artifact = { ..._artifact, source: body.output };
  await openEditor();
  showMessages([`${body.output} 에 저장했습니다 (${verify})`], body.verify?.ok ? 'doc-ok' : 'doc-error');
}

// media.js 가 문서를 띄우거나 닫을 때 알린다. 원본 경로가 있을 때만 버튼을 보인다
document.addEventListener('media:document', (e) => {
  _seq++;
  const source = e.detail?.source || '';
  // 다른 문서로 바뀌면 고친 곳을 버린다. 그 문서의 id 가 아니다
  if (source !== (_artifact?.source || '')) _edits.clear();
  _artifact = e.detail;
  setMode('');
  $edit.hidden = !EDITABLE.test(source);
});

// 편집 보기에서 Ctrl+S(⌘S)는 브라우저 저장 대신 문서 저장
document.addEventListener('keydown', (e) => {
  if (_mode === 'edit' && (e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
    e.preventDefault();
    saveEdits();
  }
});

$edit?.addEventListener('click', () => (_mode === 'edit' ? backToView() : openEditor()));
// 양식 등록 창이 후보의 자리를 짚는다. 그 문서가 문서 창에 떠 있을 때만
export function showSpot(source, id) {
  if (!id || !_artifact || _artifact.source !== source) return false;
  openEditor(id);
  return true;
}
