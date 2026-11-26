// 입력창 — 전송(첨부 포함), 일하는 동안 보낸 말(대기, 지금 보내기, 되가져오기), 슬래시 명령 자동완성, 입력 하이라이트, 중단.
import { send } from './ws.js';
import { newQueueId, queuedCount, sendNow, takeBack, markShown } from './queue.js';
import { escapeHtml } from './markdown.js';
import { setStatus } from './shell.js';
import { appendMsg, streamEnd, showAwaitPlaceholder, hideAwaitPlaceholder } from './messages.js';
import { noteFocusCommand } from './focus.js';
import { hasAttachments, takeAttachments } from './attachments.js';

const $input          = document.getElementById('chat-input');
const $sendBtn        = document.getElementById('send-btn');
const $slashPopup     = document.getElementById('slash-popup');
const $highlight      = document.getElementById('input-highlight');
const $highlightInner = document.getElementById('input-highlight-inner');

// 서버는 첫 이벤트(agent_start) 전에 inner thought 를 먼저 돌려 몇 초간 아무 이벤트도 오지 않는다.
// 그동안 HUD 가 쉬는 것처럼 보이지 않게 하고, 응답이 끝내 오지 않으면 이 시간 뒤 원래대로 돌린다.
const AWAIT_TIMEOUT_MS = 90000;
const CMD_HIGHLIGHT_RE = /(?<!\S)\/([a-zA-Z?][a-zA-Z0-9_-]*)/g;

let _awaitTimer    = null;
let _slashCmds     = [];  // [{name, description}, ...] — 서버가 connected 에 내려준다
let _slashFiltered = [];
let _slashVisible  = false;
let _slashIdx      = -1;
// 에이전트가 이 화면의 턴을 도는 중인가. 그동안 보낸 말은 대기열로 간다(events.js 가 agent_start, agent_end 로 켜고 끈다)
let _turnBusy      = false;

export function setTurnBusy(busy) { _turnBusy = busy; }
export function isTurnBusy() { return _turnBusy; }

// 되가져온 대기 말을 입력창으로. 이미 쓰던 글이 있으면 그 앞에 둔다
export function fillInput(text) {
  if (!text) return;
  $input.value = $input.value.trim() ? `${text}\n${$input.value}` : text;
  updateHighlight();
  $input.focus();
}

export function setInputEnabled(enabled) {
  $input.disabled           = !enabled;
  $sendBtn.disabled         = !enabled;
  $highlight.style.opacity  = enabled ? '1' : '0.4';
  if (enabled) $input.focus();
}

export function setSlashCommands(cmds) { _slashCmds = cmds; }

// ── 대기 표시 ─────────────────────────────────────────────────────────────────
export function beginAwaitingReply() {
  setStatus('THINKING', 'thinking');
  HUD.setState('thinking');
  clearTimeout(_awaitTimer);
  showAwaitPlaceholder();
  _awaitTimer = setTimeout(() => {
    hideAwaitPlaceholder();
    setStatus('READY');
    HUD.setState('idle');
  }, AWAIT_TIMEOUT_MS);
}

export function endAwaitingReply() {
  clearTimeout(_awaitTimer);
  hideAwaitPlaceholder();
}

// ── 전송 ──────────────────────────────────────────────────────────────────────
// 시스템 알림 권한은 사용자가 /schedule 을 쓸 때 묻는다(맥락 없는 권한 요청을 피한다)
function askNotificationPermission() {
  if ('Notification' in window && Notification.permission === 'default') {
    Notification.requestPermission().catch(() => {});
  }
}

// 대화에 이미 올린 사용자 텍스트를 서버로 보내고 대기 표시로 들어간다. 음성 전사도 같은 길을 탄다.
// 에이전트가 일하는 중이면 대기 말로 보낸다. 대화에는 건네질 때(queue_delivered) 붙는다
export function sendUserText(text, attachments = []) {
  const id = newQueueId();
  const extra = attachments.length ? { attachments: attachments.map((a) => a.id) } : {};
  if (_turnBusy) {
    send({ type: 'user_message', text, id, queued: true, ...extra });
    return;
  }
  // 말풍선은 이미 붙였다. 서버가 이 말을 뒤에서 도는 작업으로 보내며 queue_delivered 로 알려 와도 다시 붙이지 않는다
  markShown(id);
  send({ type: 'user_message', text, id, ...extra });
  noteFocusCommand(text);
  beginAwaitingReply();
  if (/(^|\s)\/schedule\b/.test(text)) askNotificationPermission();
}

function attachmentLines(attachments) {
  return attachments.map((a) => `📎 ${escapeHtml(a.name)}`).join('<br>');
}

async function submitMessage() {
  const text = $input.value.trim();
  if (!text && !hasAttachments()) return;
  if (_slashVisible) return; // 팝업이 열려 있으면 keydown 이 처리한다
  $input.value = '';
  updateHighlight();
  // 올리는 중인 파일은 끝날 때까지 기다린다. 실패한 파일은 칩으로 남는다
  const attachments = await takeAttachments();
  if (!text && !attachments.length) return;
  if (!_turnBusy) {
    const body = [escapeHtml(text), attachmentLines(attachments)].filter(Boolean).join('<br>');
    appendMsg('USER', 'user', body);
  }
  sendUserText(text, attachments);
}

document.getElementById('composer').addEventListener('submit', (e) => {
  e.preventDefault();
  submitMessage();
});

// 지금 단계를 멈춘다. 한 데까지는 남고, 대기 중인 말은 서버가 바로 다음 턴으로 보낸다
function abortTurn() {
  send({ type: 'abort' });
  endAwaitingReply();
  streamEnd();
  setStatus('READY');
  HUD.setState('idle');
  setInputEnabled(true);
}

// Ctrl+K → 중단
document.addEventListener('keydown', (e) => {
  if (e.ctrlKey && e.key === 'k') {
    e.preventDefault();
    abortTurn();
  }
});

// 일하는 동안: Ctrl(Cmd)+Enter 지금 보내기, 빈 입력창에서 ↑ 되가져오기, Esc 멈추기
$input.addEventListener('keydown', (e) => {
  if (_slashVisible) return;
  if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
    e.preventDefault();
    if ($input.value.trim()) submitMessage();
    if (_turnBusy) sendNow();
  } else if (e.key === 'ArrowUp' && !$input.value && queuedCount() > 0) {
    e.preventDefault();
    takeBack();
  } else if (e.key === 'Escape' && _turnBusy) {
    e.preventDefault();
    abortTurn();
  }
});

// ── 입력 하이라이트 ───────────────────────────────────────────────────────────
function buildHighlightHtml(text) {
  let result = '';
  let lastIdx = 0;
  let m;
  CMD_HIGHLIGHT_RE.lastIndex = 0;
  while ((m = CMD_HIGHLIGHT_RE.exec(text)) !== null) {
    result += escapeHtml(text.slice(lastIdx, m.index));
    result += `<span class="slash-token">${escapeHtml(m[0])}</span>`;
    lastIdx = m.index + m[0].length;
  }
  result += escapeHtml(text.slice(lastIdx));
  return result;
}

export function updateHighlight() {
  $highlightInner.innerHTML = buildHighlightHtml($input.value);
  $highlightInner.style.transform = `translateX(-${$input.scrollLeft}px)`;
}

// ── 슬래시 명령 자동완성 ──────────────────────────────────────────────────────
function setSlashActive(idx) {
  _slashIdx = idx;
  $slashPopup.querySelectorAll('.slash-item').forEach((el, i) => {
    el.classList.toggle('active', i === idx);
  });
}

// 커서 직전 텍스트에서 /command 컨텍스트 추출. 반환: { query, slashStart, slashEnd } 또는 null
function getSlashContext() {
  const val    = $input.value;
  const cursor = $input.selectionStart ?? val.length;
  const before = val.slice(0, cursor);
  // /command 가 문장 맨앞이거나 공백 뒤에 위치할 때만 매칭
  const m = before.match(/(?:^|\s)(\/([a-zA-Z0-9_?-]*))$/);
  if (!m) return null;
  const slashStart = cursor - m[1].length;
  return { query: m[2].toLowerCase(), slashStart, slashEnd: cursor };
}

function selectSlashItem(idx) {
  const cmd = _slashFiltered[idx];
  if (!cmd) return;
  const ctx = getSlashContext();
  if (ctx) {
    // 커서 앞의 /fragment 만 /cmdname␣ 으로 교체, 뒤 텍스트는 보존
    const val      = $input.value;
    const inserted = '/' + cmd.name + ' ';
    $input.value   = val.slice(0, ctx.slashStart) + inserted + val.slice(ctx.slashEnd);
    const newPos   = ctx.slashStart + inserted.length;
    $input.setSelectionRange(newPos, newPos);
  } else {
    $input.value = '/' + cmd.name + ' ';
  }
  updateHighlight();
  hideSlashPopup();
  $input.focus();
}

function showSlashPopup(cmds) {
  _slashFiltered = cmds;
  $slashPopup.innerHTML = '<div class="slash-popup-head">SLASH COMMANDS</div>';
  cmds.forEach((cmd, i) => {
    const item = document.createElement('div');
    item.className = 'slash-item';
    item.setAttribute('role', 'option');
    item.innerHTML =
      `<span class="cmd-name">/${escapeHtml(cmd.name)}</span>` +
      `<span class="cmd-desc">${escapeHtml(cmd.description || '')}</span>`;
    item.addEventListener('mousedown', (e) => {
      e.preventDefault(); // 입력 포커스 유지
      selectSlashItem(i);
    });
    item.addEventListener('mousemove', () => setSlashActive(i));
    $slashPopup.appendChild(item);
  });
  _slashVisible = true;
  $slashPopup.classList.remove('hidden');
  setSlashActive(0);
}

function hideSlashPopup() {
  _slashVisible  = false;
  _slashIdx      = -1;
  _slashFiltered = [];
  $slashPopup.classList.add('hidden');
}

// 입력·커서 이동·클릭으로 슬래시 컨텍스트가 바뀔 때마다 팝업을 재평가
function refreshSlashPopup() {
  const ctx = getSlashContext();
  if (ctx) {
    const filtered = _slashCmds.filter(c => c.name.startsWith(ctx.query));
    if (filtered.length > 0) { showSlashPopup(filtered); return; }
  }
  hideSlashPopup();
}

$input.addEventListener('input', () => { updateHighlight(); refreshSlashPopup(); });
$input.addEventListener('keyup', (e) => {
  if (['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(e.key)) refreshSlashPopup();
});
$input.addEventListener('click', refreshSlashPopup);
$input.addEventListener('scroll', updateHighlight);

$input.addEventListener('keydown', (e) => {
  if (!_slashVisible) return;
  const n = _slashFiltered.length;
  if (n === 0) return;
  switch (e.key) {
    case 'ArrowDown': e.preventDefault(); setSlashActive((_slashIdx + 1) % n); break;
    case 'ArrowUp':   e.preventDefault(); setSlashActive((_slashIdx - 1 + n) % n); break;
    case 'Tab':
    case 'Enter':     e.preventDefault(); selectSlashItem(_slashIdx); break;
    case 'Escape':    e.preventDefault(); hideSlashPopup(); break;
  }
});

// 항목 mousedown 은 preventDefault 라 blur 가 나지 않는다. 그 외 포커스 이탈이면 닫는다.
$input.addEventListener('blur', () => { setTimeout(hideSlashPopup, 150); });
