// Settings 화면 — 서버가 준 필드 정의(fields)로 폼을 그리고, 바뀐 값만 PUT 하면 서버가 바로 반영한다.
// 재시작은 Ion 이 먼저, 안 되면 백엔드 자기 재시작. 데스크톱 앱이면 앱 설정도.
import { apiFetch } from './api.js';
import { onViewOpen } from './view.js';
import { setLinkState, logActivity, SYSTEM } from './shell.js';
import { connect } from './session.js';

const SECTION_LABEL = { voice: 'Voice', proactive: 'Proactive', thought: 'Thought', focus: 'Focus' };
// 데스크톱 셸 설정. 값의 정본은 셸(desktop/desktop_settings.js)이고 여기서는 보여 주고 보낸다
const DESKTOP_FIELDS = {
  hotkey: { title: '전역 단축키 (듣기 시작)', type: 'string' },
  autoLaunch: { title: '로그인 때 자동 실행', type: 'boolean' },
  backendUrl: { title: '백엔드 주소 (재시작 후 반영)', type: 'string' },
};

const $form = document.getElementById('settings-form');
const $fields = document.getElementById('settings-fields');
const $path = document.getElementById('settings-path');
const $status = document.getElementById('settings-status');
const $restart = document.getElementById('settings-restart');
const $effective = document.getElementById('settings-effective');
const $desktopCard = document.getElementById('desktop-card');
const $desktopFields = document.getElementById('desktop-fields');
const $desktopStatus = document.getElementById('desktop-status');
const $desktopSave = document.getElementById('desktop-save');

let _loaded = {};  // section → field → 적용값. 바뀐 값만 보내려고 들고 있다
let _desktop = {};

function status($el, text, cls = '') {
  $el.textContent = text;
  $el.className = `settings-status ${cls}`.trim();
}

function inputFor(id, spec, value) {
  let input;
  if (spec.enum) {
    input = document.createElement('select');
    for (const opt of spec.enum) {
      const o = document.createElement('option');
      o.value = opt;
      o.textContent = opt === '' ? '(없음)' : opt;
      input.appendChild(o);
    }
    input.value = value ?? '';
  } else if (spec.type === 'boolean') {
    input = document.createElement('input');
    input.type = 'checkbox';
    input.checked = !!value;
  } else if (spec.type === 'number' || spec.type === 'integer') {
    input = document.createElement('input');
    input.type = 'number';
    input.step = spec.type === 'integer' ? '1' : '0.01';
    if (spec.minimum !== undefined) input.min = String(spec.minimum);
    if (spec.maximum !== undefined) input.max = String(spec.maximum);
    input.value = value ?? '';
  } else {
    input = document.createElement('input');
    input.type = 'text';
    if (spec.pattern) input.pattern = spec.pattern;
    input.value = value ?? '';
  }
  input.id = id;
  input.dataset.type = spec.enum ? 'enum' : spec.type;
  return input;
}

function readInput(input) {
  if (input.dataset.type === 'boolean') return input.checked;
  if (input.dataset.type === 'number') return input.value === '' ? null : Number(input.value);
  if (input.dataset.type === 'integer') return input.value === '' ? null : Math.round(Number(input.value));
  return input.value;
}

function row(id, spec, value, pending) {
  const wrap = document.createElement('div');
  wrap.className = pending ? 'settings-row pending' : 'settings-row';
  const label = document.createElement('label');
  label.htmlFor = id;
  label.textContent = spec.title;
  wrap.append(label, inputFor(id, spec, value));
  return wrap;
}

function savedStatus(body) {
  const applied = body.applied || [];
  const restartKeys = body.restart_keys || [];
  if (body.restart_required) {
    return [`저장됨 · ${restartKeys.join(', ')} 은 백엔드를 다시 띄우면 반영됩니다`, 'warn'];
  }
  if (applied.length) return [`반영됨 · ${applied.join(', ')}`, 'ok'];
  if (body.changed === false) return ['바뀐 값이 없습니다', ''];
  return ['저장됨', 'ok'];
}

function renderForm(body, saved = false) {
  _loaded = body.editable || {};
  const pending = body.pending || {};
  $path.textContent = body.path || '—';
  $path.title = body.path || '';
  const groups = Object.entries(body.fields || {}).map(([section, fields]) => {
    const fs = document.createElement('fieldset');
    fs.className = 'settings-group';
    const legend = document.createElement('legend');
    legend.textContent = SECTION_LABEL[section] || section;
    fs.appendChild(legend);
    for (const [name, spec] of Object.entries(fields)) {
      const saved = pending[section] && name in pending[section] ? pending[section][name] : _loaded[section]?.[name];
      fs.appendChild(row(`set-${section}-${name}`, spec, saved, !!(pending[section] && name in pending[section])));
    }
    return fs;
  });
  $fields.replaceChildren(...groups);
  $effective.textContent = JSON.stringify(body.effective || {}, null, 2);
  const waiting = Object.keys(pending).length > 0;
  if (saved) status($status, ...savedStatus(body));
  else status($status, waiting ? '저장됨 · 백엔드를 다시 띄우면 반영됩니다' : '', waiting ? 'warn' : '');
  $restart.hidden = !waiting;
}

// 화면의 값 중 지금 적용값과 다른 것만. 같은 값을 다시 보내지 않으니 저장을 여러 번 눌러도 결과가 같다
function collectPatch(fields) {
  const patch = {};
  for (const [section, specs] of Object.entries(fields)) {
    for (const name of Object.keys(specs)) {
      const input = document.getElementById(`set-${section}-${name}`);
      if (!input) continue;
      const value = readInput(input);
      if (value === null || value === _loaded[section]?.[name]) continue;
      (patch[section] ||= {})[name] = value;
    }
  }
  return patch;
}

let _fields = {};

export async function loadSettings() {
  try {
    const res = await apiFetch('/api/settings');
    if (!res.ok) { status($status, `설정을 읽지 못했습니다 (${res.status})`, 'err'); return; }
    const body = await res.json();
    _fields = body.fields || {};
    renderForm(body);
  } catch {
    status($status, '백엔드에 연결되지 않았습니다', 'err');
  }
  await loadDesktop();
  await loadMcp();
}

$form.addEventListener('submit', async (e) => {
  e.preventDefault();
  const bad = $form.querySelector(':invalid');
  if (bad) { status($status, '범위나 형식이 맞지 않는 값이 있습니다', 'err'); bad.focus(); return; }
  const patch = collectPatch(_fields);
  if (!Object.keys(patch).length) { status($status, '바뀐 값이 없습니다'); return; }
  try {
    const res = await apiFetch('/api/settings', {
      method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(patch),
    });
    if (!res.ok) { status($status, `저장 실패 (${res.status})`, 'err'); return; }
    const body = await res.json();
    renderForm(body, true);
    // 음성 설정은 접속 인사(connected)가 모드와 언어를 정한다. 다시 붙어야 이 화면도 새 값을 쓴다
    if ((body.applied || []).some((k) => k.startsWith('voice.'))) connect();
  } catch {
    status($status, '백엔드에 연결되지 않았습니다', 'err');
  }
});

const MANUAL_RESTART = 'docker compose restart ash-backend 를 직접 실행하세요';

async function postRestart(path) {
  try {
    const res = await apiFetch(path, { method: 'POST' });
    const body = await res.json().catch(() => ({}));
    return { ok: res.ok && body.ok === true, reason: body.result || String(res.status) };
  } catch {
    return { ok: false, reason: '연결되지 않음' };
  }
}

// Ion(/ion/restart, docker 소켓 프록시)이 먼저다. 컨테이너 재시작이라 Docker 의 RestartCount 가 늘지 않는다.
// Ion 이 없거나 거절하면 백엔드가 스스로 종료해 restart 정책으로 다시 뜬다(/api/restart). 둘 다 안 되면 직접 실행
$restart.addEventListener('click', async () => {
  $restart.disabled = true;
  status($status, '백엔드를 다시 띄우는 중…', 'warn');
  setLinkState(false, '연결 끊김 — 재시작 중');
  let result = await postRestart('/ion/restart');
  if (!result.ok) {
    logActivity(`ion restart 실패 (${result.reason}) · 백엔드 자기 재시작으로`, 'err', SYSTEM);
    result = await postRestart('/api/restart');
  }
  if (result.ok) {
    // 성공하면 ws 가 끊겼다 재접속 루프로 다시 붙는다. 데스크톱 앱은 페이지를 새로 읽는다
    status($status, '재시작 중 · 연결이 돌아오면 다시 붙습니다', 'warn');
  } else {
    setLinkState(true);
    status($status, `재시작 실패: ${result.reason}. ${MANUAL_RESTART}`, 'err');
  }
  $restart.disabled = false;
});

async function loadDesktop() {
  const bridge = window.ashDesktop;
  $desktopCard.hidden = !bridge;
  if (!bridge) return;
  _desktop = await bridge.getSettings().catch(() => ({}));
  $desktopFields.replaceChildren(...Object.entries(DESKTOP_FIELDS).map(
    ([name, spec]) => row(`desk-${name}`, spec, _desktop[name], false),
  ));
}

$desktopSave.addEventListener('click', async () => {
  const bridge = window.ashDesktop;
  if (!bridge) return;
  const next = {};
  for (const name of Object.keys(DESKTOP_FIELDS)) {
    const input = document.getElementById(`desk-${name}`);
    if (input) next[name] = readInput(input);
  }
  const result = await bridge.setSettings(next).catch((err) => ({ ok: false, error: String(err) }));
  if (result.ok) { _desktop = result.settings || next; status($desktopStatus, '저장됨'); }
  else status($desktopStatus, `저장 실패: ${result.error || '알 수 없음'}`, 'err');
});

onViewOpen('settings', loadSettings);

// ── MCP 도구 정책 ────────────────────────────────────────────────────────────
// 서버·도구 표에서 모드(기본, allow, ask, deny), 시간당 상한, 인자 고정(key=v1|v2; key2=v)을 고치고 SAVE 로 정책 전체를
// 보낸다. 판정(effective)은 서버가 다시 계산해 돌려준다. 호출 기록은 최근 50건
const $mcpCard = document.getElementById('mcp-card');
const $mcpPath = document.getElementById('mcp-path');
const $mcpDefaults = document.getElementById('mcp-defaults');
const $mcpTools = document.getElementById('mcp-tools');
const $mcpStatus = document.getElementById('mcp-status');
const $mcpSave = document.getElementById('mcp-save');
const $mcpAudit = document.getElementById('mcp-audit');
const $mcpAuditCount = document.getElementById('mcp-audit-count');
const MODES = ['allow', 'ask', 'deny'];
const KIND_LABEL = { read: '읽기', write: '쓰기', unknown: '모름' };
let _mcpPolicy = null;   // 서버가 준 정책 문서. agents 는 화면에서 안 고치므로 그대로 돌려보낸다

function modeSelect(id, value, withDefault) {
  const sel = document.createElement('select');
  sel.id = id;
  const opts = withDefault ? [['', '기본'], ...MODES.map((m) => [m, m])] : MODES.map((m) => [m, m]);
  for (const [v, label] of opts) {
    const o = document.createElement('option');
    o.value = v; o.textContent = label; o.selected = (value || '') === v;
    sel.appendChild(o);
  }
  return sel;
}

function lockText(lock) {
  return Object.entries(lock || {}).map(([k, vs]) => `${k}=${(vs || []).join('|')}`).join('; ');
}

function parseLock(text) {
  const lock = {};
  for (const part of text.split(';')) {
    const [key, values] = part.split('=').map((s) => s.trim());
    if (!key || values === undefined) continue;
    const list = values.split('|').map((s) => s.trim()).filter(Boolean);
    if (list.length) lock[key] = list;
  }
  return lock;
}

function renderMcp(body) {
  _mcpPolicy = body.policy || { defaults: {}, servers: {}, agents: {} };
  $mcpCard.hidden = !body.enabled;
  if (!body.enabled) return;
  $mcpPath.textContent = body.path || '—';
  $mcpDefaults.replaceChildren(...['read', 'write', 'unknown'].map((kind) => {
    const label = document.createElement('label');
    label.append(`${KIND_LABEL[kind]} 도구 기본`, modeSelect(`mcp-default-${kind}`, _mcpPolicy.defaults?.[kind] || (kind === 'read' ? 'allow' : 'ask'), false));
    return label;
  }));
  const table = document.createElement('table');
  const head = table.createTHead().insertRow();
  for (const text of ['서버', '도구', '종류', '모드', '시간당', '인자 고정', '판정']) {
    const th = document.createElement('th'); th.textContent = text; head.appendChild(th);
  }
  const tbody = table.createTBody();
  for (const t of body.tools || []) {
    const tp = _mcpPolicy.servers?.[t.server]?.tools?.[t.name] || {};
    const tr = tbody.insertRow();
    tr.dataset.server = t.server; tr.dataset.tool = t.name;
    const srv = tr.insertCell(); srv.className = 'srv'; srv.textContent = t.server;
    const name = tr.insertCell(); name.textContent = t.name; name.title = t.description || '';
    const kind = tr.insertCell(); kind.className = `kind-${t.kind}`; kind.textContent = KIND_LABEL[t.kind] || t.kind;
    tr.insertCell().appendChild(modeSelect(`mcp-mode-${t.server}-${t.name}`, tp.mode, true));
    const limit = document.createElement('input');
    limit.type = 'number'; limit.min = '0'; limit.max = '10000'; limit.className = 'limit';
    limit.value = tp.calls_per_hour ?? ''; limit.placeholder = '없음';
    tr.insertCell().appendChild(limit);
    const lock = document.createElement('input');
    lock.type = 'text'; lock.className = 'lock'; lock.placeholder = 'to=a@x.com|b@x.com; cc=…';
    lock.value = lockText(tp.lock);
    tr.insertCell().appendChild(lock);
    const eff = tr.insertCell(); eff.className = `eff-${t.effective}`; eff.textContent = t.effective || '—';
  }
  $mcpTools.replaceChildren(table);
}

function collectMcpPolicy() {
  const doc = { defaults: {}, servers: {}, agents: _mcpPolicy?.agents || {} };
  for (const kind of ['read', 'write', 'unknown']) {
    const sel = document.getElementById(`mcp-default-${kind}`);
    if (sel && sel.value) doc.defaults[kind] = sel.value;
  }
  for (const tr of $mcpTools.querySelectorAll('tbody tr')) {
    const [, , , modeCell, limitCell, lockCell] = tr.cells;
    const entry = {};
    const mode = modeCell.querySelector('select').value;
    if (mode) entry.mode = mode;
    const limit = limitCell.querySelector('input').value.trim();
    if (limit !== '') entry.calls_per_hour = Number(limit);
    const lock = parseLock(lockCell.querySelector('input').value);
    if (Object.keys(lock).length) entry.lock = lock;
    if (Object.keys(entry).length) ((doc.servers[tr.dataset.server] ||= { tools: {} }).tools)[tr.dataset.tool] = entry;
  }
  return doc;
}

function renderMcpAudit(entries) {
  $mcpAuditCount.textContent = String(entries.length);
  $mcpAudit.replaceChildren(...entries.map((e) => {
    const li = document.createElement('li');
    const when = document.createElement('span'); when.className = 'when';
    when.textContent = e.ts ? new Date(e.ts).toLocaleTimeString('ko-KR', { hour12: false }) : '—';
    const what = document.createElement('span');
    if (e.type === 'result') { what.className = e.ok ? 'ok' : 'err'; what.textContent = e.ok ? '성공' : '실패'; }
    else { what.className = e.decision || ''; what.textContent = `${e.agent || ''} ${e.decision || ''}`.trim(); }
    const call = document.createElement('span'); call.className = 'call';
    call.textContent = e.type === 'result' ? `${e.server}.${e.tool}${e.error ? ' · ' + e.error : ''}` : `${e.call || e.tool} · ${e.reason || ''}`;
    call.title = call.textContent;
    li.append(when, what, call);
    return li;
  }));
}

export async function loadMcp() {
  try {
    const [policy, audit] = await Promise.all([apiFetch('/api/mcp/policy'), apiFetch('/api/mcp/audit?limit=50')]);
    if (!policy.ok) { $mcpCard.hidden = true; return; }
    renderMcp(await policy.json());
    if (audit.ok) renderMcpAudit((await audit.json()).entries || []);
  } catch { $mcpCard.hidden = true; }
}

$mcpSave?.addEventListener('click', async () => {
  const doc = collectMcpPolicy();
  try {
    const res = await apiFetch('/api/mcp/policy', {
      method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(doc),
    });
    if (!res.ok) { status($mcpStatus, `저장 실패 (${res.status})`, 'err'); return; }
    renderMcp(await res.json());
    status($mcpStatus, '저장됨 · 바로 적용', 'ok');
  } catch {
    status($mcpStatus, '백엔드에 연결되지 않았습니다', 'err');
  }
});
