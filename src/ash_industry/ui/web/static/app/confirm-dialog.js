// HUD 확인 창 — 브라우저 confirm() 대신 승인 창과 같은 모양으로 묻는다. Enter 는 확인, Esc 와 바깥 클릭은 취소.
const $overlay = document.getElementById('confirm-overlay');
const $title = document.getElementById('confirm-title');
const $message = document.getElementById('confirm-message');
const $ok = document.getElementById('confirm-ok');
const $cancel = document.getElementById('confirm-cancel');

let _resolve = null;

function close(answer) {
  if (!_resolve) return;
  $overlay.classList.add('hidden');
  const resolve = _resolve;
  _resolve = null;
  resolve(answer);
}

// 열려 있는 확인이 있으면 그것을 취소로 닫고 새로 묻는다. 글은 textContent 로만 넣는다(작업 이름은 사용자 요청에서 왔다)
export function askConfirm({ title, message, ok = '확인', cancel = '취소' }) {
  close(false);
  $title.textContent = title;
  $message.textContent = message;
  $ok.textContent = ok;
  $cancel.textContent = cancel;
  $overlay.classList.remove('hidden');
  $ok.focus();
  return new Promise((resolve) => { _resolve = resolve; });
}

$ok.addEventListener('click', () => close(true));
$cancel.addEventListener('click', () => close(false));
$overlay.addEventListener('click', (e) => { if (e.target === $overlay) close(false); });
document.addEventListener('keydown', (e) => {
  if (!_resolve) return;
  if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); close(false); }
  else if (e.key === 'Enter') { e.preventDefault(); e.stopPropagation(); close(true); }
}, { capture: true });
