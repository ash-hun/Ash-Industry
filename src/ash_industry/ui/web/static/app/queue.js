// 일하는 동안 보낸 말 — 대화 아래 회색 대기 목록, 건네진 말을 대화에 붙이기, 되가져오기.
import { send } from './ws.js';
import { escapeHtml } from './markdown.js';
import { appendMsg, streamEnd } from './messages.js';

const $list = document.getElementById('queue-list');
const $items = document.getElementById('queue-items');
let _items = [];  // [{id, text}] 서버가 매번 대기열 전체를 보낸다
// 이 화면이 보낼 때 이미 대화에 붙인 말의 id. 서버가 건넸다고 알려 와도 다시 붙이지 않는다
const _shown = new Set();
const SHOWN_KEEP = 200;

export function markShown(id) {
  _shown.add(id);
  if (_shown.size > SHOWN_KEEP) _shown.delete(_shown.values().next().value);
}

export function queuedCount() { return _items.length; }

export function setQueue(items) {
  _items = Array.isArray(items) ? items : [];
  $items.replaceChildren(..._items.map((item) => {
    const li = document.createElement('li');
    li.className = 'queue-item';
    li.textContent = item.text;  // 사용자가 쓴 글. textContent 로만
    li.title = item.text;
    return li;
  }));
  $list.hidden = _items.length === 0;
}

// 모델에게 건네졌다. 지금까지 흘린 답을 닫고 사용자 말로 대화에 붙인다. 이어지는 답은 새 말풍선이 된다
export function onQueueDelivered(items) {
  if (!Array.isArray(items) || !items.length) return;
  const fresh = items.filter((i) => !_shown.has(i.id));
  if (fresh.length) streamEnd();
  for (const item of fresh) {
    appendMsg('USER', 'user', escapeHtml(item.text || ''));
    markShown(item.id);
  }
  const delivered = new Set(items.map((i) => i.id));
  setQueue(_items.filter((i) => !delivered.has(i.id)));
}

// 화면이 붙이는 대기 말 id. 서버가 같은 id 를 한 번만 담는다
export function newQueueId() {
  if (globalThis.crypto?.randomUUID) return crypto.randomUUID();
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

export function takeBack() { send({ type: 'queue_take' }); }
export function sendNow() { send({ type: 'send_now' }); }
