// 입력창 첨부 — 📎 버튼과 끌어다 놓기로 고른 파일을 /api/uploads 로 올리고, 보낼 때 그 id 를 메시지에 싣는다.
import { apiFetch } from './api.js';

const MAX_BYTES = 50 * 1024 * 1024;

const $composer = document.getElementById('composer');
const $button   = document.getElementById('attach-btn');
const $picker   = document.getElementById('attach-input');
const $chips    = document.getElementById('attach-chips');

// 고른 순서대로 { key, name, state: 'uploading'|'ready'|'error', upload, promise, error }
let _items = [];
let _seq = 0;

function render() {
  $chips.hidden = _items.length === 0;
  $chips.replaceChildren(..._items.map((item) => {
    const chip = document.createElement('span');
    chip.className = `attach-chip ${item.state}`;
    chip.title = item.error || item.upload?.path || item.name;
    const label = document.createElement('span');
    label.className = 'name';
    label.textContent = item.state === 'uploading' ? `${item.name} …` : item.name;
    const remove = document.createElement('button');
    remove.type = 'button';
    remove.className = 'remove';
    remove.setAttribute('aria-label', `${item.name} 빼기`);
    remove.textContent = '✕';
    remove.addEventListener('click', () => { _items = _items.filter((x) => x !== item); render(); });
    chip.append(label, remove);
    return chip;
  }));
}

async function upload(item, file) {
  const form = new FormData();
  form.append('file', file, file.name);
  try {
    const res = await apiFetch('/api/uploads', { method: 'POST', body: form });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(body.error || `업로드 실패 (${res.status})`);
    item.upload = body;
    item.state = 'ready';
  } catch (err) {
    item.state = 'error';
    item.error = err.message || '업로드 실패';
  }
  render();
}

export function addFiles(files) {
  for (const file of files) {
    const item = { key: ++_seq, name: file.name, state: 'uploading' };
    if (file.size > MAX_BYTES) {
      item.state = 'error';
      item.error = '50MB 를 넘는 파일은 올릴 수 없습니다';
    } else {
      item.promise = upload(item, file);
    }
    _items.push(item);
  }
  render();
}

export function hasAttachments() { return _items.length > 0; }

// 올리는 중인 파일을 기다린 뒤, 올라간 것만 꺼내고 비운다. 실패한 것은 남겨 사용자가 보고 뺀다
export async function takeAttachments() {
  await Promise.all(_items.map((x) => x.promise).filter(Boolean));
  const ready = _items.filter((x) => x.state === 'ready').map((x) => x.upload);
  _items = _items.filter((x) => x.state === 'error');
  render();
  return ready;
}

$button?.addEventListener('click', () => $picker.click());
$picker?.addEventListener('change', () => {
  addFiles([...$picker.files]);
  $picker.value = '';
});

// 입력창 위로 끌어다 놓기
for (const type of ['dragenter', 'dragover']) {
  $composer.addEventListener(type, (e) => {
    if (!e.dataTransfer?.types?.includes('Files')) return;
    e.preventDefault();
    $composer.classList.add('dropping');
  });
}
$composer.addEventListener('dragleave', () => $composer.classList.remove('dropping'));
$composer.addEventListener('drop', (e) => {
  if (!e.dataTransfer?.files?.length) return;
  e.preventDefault();
  $composer.classList.remove('dropping');
  addFiles([...e.dataTransfer.files]);
});
