// HUD 안 단축키. 설정(editable.shortcuts)을 읽어 키 하나를 동작 하나로 보낸다. 이 창에 포커스가 있을 때만 듣는다.
import { apiFetch } from './api.js';
import { isApprovalOpen } from './approval.js';
import { isConfirmOpen } from './confirm-dialog.js';
import { ACTIONS, DEFAULT_SHORTCUTS, matchCombo, resolveShortcuts } from './shortcut-combo.js';

// Esc 는 읽기를 멈춘 뒤에도 입력창의 턴 멈춤, 드로어 닫기, 화면 되돌리기가 이어서 받는다.
// 음성 승인 띠가 열려 있을 때도 Esc 로 읽기와 승인 듣기를 멈출 수 있어야 한다
const PASS_THROUGH = new Set(['voice_stop']);
const DURING_APPROVAL = new Set(['voice_stop']);

let _bindings = resolveShortcuts(DEFAULT_SHORTCUTS);
const _handlers = new Map();

// handler(e) 가 true 를 돌려주면 그 키를 쓴 것으로 보고 기본 동작을 막는다
export function onShortcut(action, handler) { _handlers.set(action, handler); }

export function setShortcuts(values) { _bindings = resolveShortcuts(values); }

// 시작할 때 한 번. 접근 키가 없거나 백엔드가 없으면 기본값으로 둔다
export async function loadShortcuts() {
  try {
    const res = await apiFetch('/api/settings');
    if (res.ok) setShortcuts((await res.json()).editable?.shortcuts);
  } catch { /* 기본값 유지 */ }
}

// capture 단계에서 먼저 본다. 쓴 키는 입력창의 Ctrl+Enter 같은 다른 처리로 넘기지 않는다.
// 확인 창도 같은 단계에서 Esc, Enter 를 받아 닫으므로 막힌 키(defaultPrevented)는 보지 않는다
document.addEventListener('keydown', (e) => {
  if (e.repeat || e.isComposing || e.defaultPrevented || isConfirmOpen()) return;
  const action = ACTIONS.find((a) => matchCombo(_bindings[a], e));
  if (!action || (isApprovalOpen() && !DURING_APPROVAL.has(action))) return;
  const handler = _handlers.get(action);
  if (!handler || !handler(e)) return;
  e.preventDefault();
  if (!PASS_THROUGH.has(action)) e.stopPropagation();
}, { capture: true });
