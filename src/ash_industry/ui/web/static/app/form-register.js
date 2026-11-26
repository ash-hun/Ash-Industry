// 양식 등록 창. 사용자가 등록을 시켜 detect_fields 가 돌면 열린다. 문서 창과 따로 뜨고 함께 떠 있을 수 있다.
import { logActivity } from './shell.js';
import { dockFrame } from './media.js';
import { showSpot } from './doc-edit.js';
import { el, button, callApi, postJson, errorLines } from './doc-ui.js';

const TYPES = ['text', 'long_text', 'date', 'date_range', 'number', 'choice'];

const $overlay = document.getElementById('form-overlay');
const $title = document.getElementById('form-title');
const $body = document.getElementById('form-body');
const $close = document.getElementById('form-close');

let _source = '';            // 열린 양식(문서 폴더 기준). 닫혀 있으면 빈 글
let _seq = 0;

function closeForm() {
  _source = '';
  _seq++;
  $overlay.classList.add('hidden');
  $body.replaceChildren();
}

function lines(texts, cls) {
  return texts.map((t) => el('p', { className: cls, textContent: t }));
}

function where(loc) {
  switch (loc.kind) {
    case 'table_cell': return { text: `표 t${loc.table} r${loc.row} c${loc.col}`, id: `t${loc.table}r${loc.row}c${loc.col}` };
    case 'anchor_text': return { text: `"${loc.after}" 뒤`, id: `text:${loc.after}` };
    case 'sheet_cell': return { text: `${loc.sheet}!${loc.cell}`, id: `addr:${loc.cell}` };
    case 'shape_text': return { text: `슬라이드 ${loc.slide + 1} 도형 ${loc.shape}`, id: `s${loc.slide}sh${loc.shape}p0` };
    case 'form_field': return { text: `폼 ${loc.name}`, id: '' };
    case 'inline_slot': return { text: `${loc.paragraph} "${loc.label}(  )"`, id: cellOf(loc.paragraph) };
    case 'checkbox': return { text: `${loc.paragraph} □ ${loc.options.join(' / ')}`, id: cellOf(loc.paragraph) };
    default: return { text: loc.kind, id: '' };
  }
}

// 칸 안 문단(t0r1c2p0)은 편집 보기에서 칸(t0r1c2) 하나로 보인다
function cellOf(pid) {
  const m = /^(t\d+r\d+c\d+)p\d+$/.exec(pid);
  return m ? m[1] : pid;
}

function candidateRow(c) {
  const include = el('input', { type: 'checkbox', checked: true });
  const name = el('input', { className: 'doc-field-name', value: c.name, maxLength: 64 });
  const type = el('select');
  for (const t of TYPES) type.append(el('option', { value: t, textContent: t, selected: t === c.type }));
  const required = el('input', { type: 'checkbox', checked: !!c.required });
  const options = el('input', { className: 'doc-field-options', value: (c.options || []).join(', '), placeholder: 'choice 선택지' });
  const spot = where(c.locator);
  const place = el('td', { className: 'doc-where', textContent: spot.text });
  if (c.locator.kind !== 'form_field') {
    place.title = '문서 창에 이 문서가 떠 있으면 그 자리를 보여 줍니다';
    const source = _source;
    place.addEventListener('click', () => {
      if (!showSpot(source, spot.id)) logActivity('이 문서를 문서 창에 띄우면 자리를 짚어 줍니다', 'warn');
    });
  }
  const tr = el('tr', { className: c.confidence === 'low' ? 'low' : '' },
    el('td', {}, include), el('td', {}, name), el('td', { textContent: c.label }), el('td', {}, type),
    el('td', {}, required), el('td', {}, options), place,
  );
  if (c.confidence === 'low') tr.title = '확인이 필요한 후보';
  tr.read = () => include.checked ? {
    name: name.value.trim(), type: type.value, required: required.checked,
    options: type.value === 'choice' ? options.value.split(',').map((s) => s.trim()).filter(Boolean) : [],
    locator: c.locator,
  } : null;
  return tr;
}

// 같은 양식이 이미 열려 있으면 그대로 둔다. 고치던 표를 지우지 않는다
async function openForm(artifact) {
  const source = artifact?.source;
  if (!source || source === _source) return;
  _source = source;
  const seq = ++_seq;
  dockFrame($overlay);
  $title.textContent = artifact.title || source;
  $body.replaceChildren(el('p', { className: 'media-loading', textContent: '채울 자리를 찾는 중…' }));
  $overlay.classList.remove('hidden');
  const { ok, status, body } = await callApi(`/api/docs/fields?path=${encodeURIComponent(source)}`);
  if (seq !== _seq) return;
  if (!ok) { $body.replaceChildren(...lines(errorLines(body, status), 'doc-error')); return; }
  const candidates = body.candidates || [];
  if (!candidates.length) {
    $body.replaceChildren(...lines(['채울 자리를 찾지 못했습니다. 채팅으로 위치를 말해 등록할 수 있습니다.'], 'doc-hint'));
    return;
  }
  const rows = candidates.map(candidateRow);
  const headRow = el('tr', {}, ...['포함', '이름', '라벨', '형식', '필수', '선택지', '위치'].map((t) => el('th', { textContent: t })));
  const table = el('table', { className: 'doc-fields' }, headRow, ...rows);
  const templateId = el('input', { className: 'doc-template-id', value: body.template_id || '', maxLength: 64 });
  const result = el('div', { className: 'doc-result' });
  const register = async () => {
    const fields = rows.map((r) => r.read()).filter(Boolean);
    if (!fields.length) { result.replaceChildren(el('p', { className: 'doc-error', textContent: '포함한 필드가 없습니다' })); return; }
    const res = await postJson('/api/docs/templates', { path: source, template_id: templateId.value.trim(), fields });
    if (res.ok) {
      const what = res.body.registered ? '등록했습니다' : '이미 같은 것이 등록돼 있습니다';
      result.replaceChildren(el('p', { className: 'doc-ok', textContent: `${res.body.template_id}: ${what} (필드 ${res.body.fields?.length ?? fields.length}개)` }));
      logActivity(`▤ 양식 등록 · ${res.body.template_id}`, 'ok');
    } else {
      result.replaceChildren(...errorLines(res.body, res.status).map((t) => el('p', { className: 'doc-error', textContent: t })));
    }
  };
  const extra = body.truncated ? lines([body.truncated], 'doc-hint') : [];
  $body.replaceChildren(
    ...lines(['주황 줄은 확인이 필요한 후보입니다.'], 'doc-hint'), ...extra, table,
    el('label', { className: 'doc-template' }, el('span', { textContent: '템플릿 id' }), templateId, button('등록', register)), result,
  );
}

$close?.addEventListener('click', closeForm);
document.addEventListener('form:open', (e) => openForm(e.detail));
