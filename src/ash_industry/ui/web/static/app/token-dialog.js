// 접근 키 입력 창. 브라우저 prompt() 대신 쓴다(데스크톱 셸인 Electron 은 prompt() 를 지원하지 않아 키를 넣을 길이 없었다).
const $overlay = document.getElementById('token-overlay');
const $input = document.getElementById('token-input');
const $save = document.getElementById('token-save');
const $cancel = document.getElementById('token-cancel');

let _pending = null;

function close(value) {
  if (!_pending) return;
  $overlay.classList.add('hidden');
  $input.value = '';
  const resolve = _pending;
  _pending = null;
  resolve(value);
}

// 이미 열려 있으면 같은 답을 기다린다. REST 401 과 ws 4401 이 함께 와도 창은 하나다
let _shared = null;
export function askTokenDialog() {
  if (_shared) return _shared;
  $overlay.classList.remove('hidden');
  $input.focus();
  _shared = new Promise((resolve) => { _pending = resolve; }).finally(() => { _shared = null; });
  return _shared;
}

$save.addEventListener('click', () => close($input.value.trim() || null));
$cancel.addEventListener('click', () => close(null));
document.addEventListener('keydown', (e) => {
  if (!_pending) return;
  if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); close(null); }
  else if (e.key === 'Enter' && !e.isComposing) { e.preventDefault(); e.stopPropagation(); close($input.value.trim() || null); }
}, { capture: true });
