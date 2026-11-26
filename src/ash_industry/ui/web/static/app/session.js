// 세션 — 목록, 전환·분기·생성, 웹소켓 연결과 재연결, 접속 직후 화면 채우기.
import { apiFetch, getToken, askForToken } from './api.js';
import { openSocket } from './ws.js';
import { escapeHtml } from './markdown.js';
import { setStatus, setLinkState, logActivity, showQuote, renderActivity, SYSTEM } from './shell.js';
import { appendMsg, appendHistory, resetMessages } from './messages.js';
import { resetFocus } from './focus.js';
import { setModel, resetUsage } from './usage.js';
import { hideArtifact } from './artifact.js';
import { setInputEnabled, setSlashCommands, setTurnBusy } from './composer.js';
import { setQueue } from './queue.js';
import { fetchAgenda } from './agenda.js';
import { fetchTools, setToolsSession } from './tools.js';
import { voice, cue } from './voice-ui.js';
import { setPhrases } from './phrases.js';
import { setWakeEnabled } from './wake.js';
import { handleMessage, resetAgentStack, resetBackgroundThought } from './events.js';
import { setReplyClassifier } from './reply.js';
import { applyBrand, AGENT_ID } from './brand.js';
import { renderAgentNav, setAgentSwitcher, setUnreadAgents } from './agent-nav.js';
import { loadAgents, agentById, isTeam, setActiveAgents } from './agents.js';
import { setApprovalWaiting } from './approval-wait.js';
import { setBackgroundTasks } from './task-stars.js';

const $list         = document.getElementById('session-list');
const $count        = document.getElementById('session-count');
const $idLabel      = document.getElementById('session-id-label');
const $sysModel     = document.getElementById('sys-model');
const $connBanner   = document.getElementById('connection-banner');

const RECONNECT_MIN_MS = 1000;
const RECONNECT_MAX_MS = 10000;
const WS_UNAUTHORIZED = 4401;  // 서버가 키 불일치로 끊을 때 쓰는 close code
const WS_UNKNOWN_AGENT = 4404; // 세션의 에이전트가 정의에 없을 때. 다시 붙어도 같은 답이라 재시도하지 않는다
const FALLBACK_SESSION_ID = 'default';

let _currentSessionId = 'default';
let _bootId = null;  // 처음 붙은 백엔드의 기동 표식
let _reconnectDelay = RECONNECT_MIN_MS;
// 세션 id → 에이전트 id. connected 와 /api/sessions 가 채운다
let _sessionAgents = {};
// 붙는 중에 온 라이브 이벤트. 이력과 진행 중인 턴을 다 그린 뒤 흘려 순서를 지킨다. null 이면 바로 처리한다
let _held = null;
let _historyDone = Promise.resolve();
// connect 를 부를 때마다 하나씩 는다. 같은 세션에 다시 붙어도 앞 연결의 재생이 새 연결을 건드리지 않게 가른다
let _linkGen = 0;
// 보고 있지 않을 때 먼저 건넨 말이나 뒤에서 끝난 답이 온 세션. 그 세션에 붙으면 지운다
const _unread = new Set();
let _lastSessions = [];

function unreadAgents() {
  return [..._unread].map((sid) => _sessionAgents[sid] || 'main');
}

// SESSIONS 는 지금 보는 에이전트의 세션만. 다른 에이전트의 세션은 그 에이전트로 넘어가면 보인다
function renderSessions(sessions, sessionAgents) {
  if (sessionAgents) _sessionAgents = sessionAgents;
  _lastSessions = sessions;
  const shown = sessions.filter((sid) => sid === _currentSessionId || (_sessionAgents[sid] || 'main') === AGENT_ID);
  $list.innerHTML = '';
  $count.textContent = String(shown.length).padStart(2, '0');
  for (const sid of shown) {
    const isActive = sid === _currentSessionId;
    const div = document.createElement('div');
    div.className = `session${isActive ? ' active' : ''}${_unread.has(sid) ? ' unread' : ''}`;
    // 세션 앞 표식은 그 세션 에이전트의 색
    const agent = agentById(_sessionAgents[sid] || 'main');
    if (agent && isTeam()) {
      div.style.setProperty('--agent-color', agent.palette.primary);
      div.dataset.agent = agent.id;
      div.title = agent.name;
    }
    div.innerHTML = `
      <span class="marker"></span>
      <span class="title">${escapeHtml(sid)}</span>
      <span class="meta">${isActive ? 'NOW' : ''}</span>
      ${isActive ? '<button class="fork-btn" title="Fork session">⑂</button>'
                 : '<button class="fork-btn delete-btn" title="세션 삭제">✕</button>'}`;
    div.querySelector('.title')?.addEventListener('click', () => { if (!isActive) connect(sid); });
    // 보고 있는 세션은 못 지운다. 지우려면 다른 세션으로 옮긴 뒤.
    div.querySelector('.delete-btn')?.addEventListener('click', async (e) => {
      e.stopPropagation();
      if (!confirm(`세션 "${sid}" 과 그 대화를 지웁니다. 되돌릴 수 없습니다.`)) return;
      const res = await apiFetch(`/api/sessions/${encodeURIComponent(sid)}`, { method: 'DELETE' });
      if (!res.ok) { logActivity(`세션 삭제 실패 · ${sid} · ${res.status}`, 'err'); return; }
      logActivity(`세션 삭제 · ${sid}`);
      const body = await (await apiFetch('/api/sessions')).json();
      renderSessions(body.sessions, body.agents);
    });
    if (isActive) {
      div.querySelector('.fork-btn')?.addEventListener('click', async (e) => {
        e.stopPropagation();
        const res = await apiFetch(`/api/sessions/${encodeURIComponent(sid)}/branch`, { method: 'POST' });
        const { session_id } = await res.json();
        connect(session_id);
      });
    }
    $list.appendChild(div);
  }
}

// 에이전트끼리 대화하면 서버에 대화 세션(peer-…)이 새로 생긴다. 일하는 에이전트가 바뀔 때 목록을 다시 받는다
window.addEventListener('ash:activity', async () => {
  try {
    const res = await apiFetch('/api/sessions');
    if (!res.ok) return;
    const body = await res.json();
    renderSessions(body.sessions, body.agents);
  } catch { /* 목록은 다음 접속 때 맞춰진다 */ }
});

// 다른 세션에 말이 왔다(먼저 건넨 말, 뒤에서 끝난 답). 대화는 그 세션 기록에 남아 있어 옮겨 가면 보인다.
// 여기서는 놓치지 않게 알리기만 한다: 어느 화면에서나 보이는 활동 줄, 세션 목록과 에이전트 화살표의 점
window.addEventListener('ash:session-message', (e) => {
  const msg = e.detail || {};
  const sid = msg.session_id;
  if (!sid || sid === _currentSessionId) return;
  if (msg.agent) _sessionAgents[sid] = msg.agent;
  _unread.add(sid);
  const name = agentById(msg.agent || 'main')?.name || msg.agent || sid;
  const text = (msg.text || '').trim().split('\n')[0];
  logActivity(`🔔 ${name} · ${text}`, 'proactive', SYSTEM);
  setUnreadAgents(unreadAgents());
  renderSessions(_lastSessions.includes(sid) ? _lastSessions : [..._lastSessions, sid]);
});

// 새 세션은 지금 보고 있는 에이전트의 것
async function createSession(agentId) {
  const res = await apiFetch('/api/sessions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ agent: agentId }),
  });
  if (!res.ok) { logActivity(`세션 생성 실패 · ${agentId} · ${res.status}`, 'err', agentId); return null; }
  return (await res.json()).session_id;
}

document.getElementById('new-session-btn').addEventListener('click', async () => {
  const sid = await createSession(AGENT_ID);
  if (sid) connect(sid);
});

// 에이전트끼리의 대화 세션(peer-부른쪽-받는쪽). 사용자가 직접 말을 거는 세션이 아니다
const PEER_PREFIX = 'peer-';

// 에이전트 전환: 그 에이전트의 열린 세션(대화 세션 제외)이 있으면 안 읽은 것, 없으면 가장 위의 것으로, 없으면 새로 만든다.
// 옮겼으면 true. 구체 밀기 애니메이션(agent-nav.js)이 옮기지 못한 경우를 되돌린다
async function switchAgent(agentId) {
  if (agentId === AGENT_ID) return false;
  // 안 읽은 말이 온 세션이 있으면 그쪽으로 간다
  const own = Object.keys(_sessionAgents).filter((s) => _sessionAgents[s] === agentId && !s.startsWith(PEER_PREFIX));
  const sid = own.find((s) => _unread.has(s)) || own[0] || await createSession(agentId);
  if (!sid) return false;
  connect(sid);
  return true;
}
setAgentSwitcher(switchAgent);

async function fetchAndRenderHistory(sessionId) {
  try {
    const res = await apiFetch(`/api/sessions/${encodeURIComponent(sessionId)}/messages`);
    if (!res.ok) return;
    if (_currentSessionId !== sessionId) return;  // 받는 사이 세션이 바뀌었으면 버린다
    const { messages } = await res.json();
    if (_currentSessionId !== sessionId) return;
    if (messages && messages.length) appendHistory(messages);
  } catch (e) {
    console.error('history fetch failed:', e);
  }
}

function resetChatUI() {
  resetFocus();
  resetMessages();
  resetAgentStack();
  setTurnBusy(false);
  setQueue([]);
  setInputEnabled(false);
  resetUsage();
  hideArtifact();
}

let _connectedOnce = false;  // 첫 접속의 에이전트는 전환이 아니다

// 서버의 첫 메시지 — 세션·모델·도구·슬래시 명령을 받아 화면을 채운다.
async function onConnected(msg) {
  // 백엔드가 다시 떴으면(기동 표식이 바뀜) 화면의 JS 와 CSS 가 옛것일 수 있다. 한 번 새로 고쳐 맞춘다
  if (msg.boot_id && _bootId && msg.boot_id !== _bootId) {
    logActivity('backend restarted · 화면 새로 고침', 'sys', SYSTEM);
    location.reload();
    return;
  }
  if (msg.boot_id) _bootId = msg.boot_id;
  await loadAgents();
  if (msg.voice) setPhrases(msg.voice.phrases);
  // 세션 에이전트의 이름과 색으로 화면을 바꾼다. 바뀌었으면 명언도 그 에이전트 것으로
  if (applyBrand(msg.agent)) {
    showQuote();
    if (_connectedOnce) cue(`persona_${msg.agent.main ? 'main' : msg.agent.id}`);
  }
  _connectedOnce = true;
  // ACTIVITY 를 이 에이전트의 줄로 다시 그린다. AGENDA 와 SESSIONS 는 아래에서 이 에이전트로 거른다
  renderActivity();
  renderAgentNav();
  setActiveAgents(msg.active_agents || []);
  const sid = msg.session_id || '—';
  const model = msg.model || '—';
  setModel(model);
  $idLabel.textContent = sid;
  $sysModel.textContent = model;
  $sysModel.title = model;
  logActivity(`session ${sid} linked`, 'ok');
  fetchAgenda();
  setToolsSession(msg.session_id);
  fetchTools();
  if (msg.sessions) renderSessions(msg.sessions, msg.session_agents);
  if (msg.slash_commands) setSlashCommands(msg.slash_commands);
  if (msg.voice && msg.voice.stt_mode) voice.setSttMode(msg.voice.stt_mode);
  voice.setServerSttAvailable(!!(msg.voice && msg.voice.server_stt));
  setWakeEnabled(!!(msg.voice && msg.voice.wake));
  setReplyClassifier(msg.reply_classifier);
  setApprovalWaiting(msg.approval_waiting);
  setBackgroundTasks(msg.background_tasks);
  setQueue(msg.queued);
  setStatus('READY');
  setLinkState(true);
  setInputEnabled(true);
  // 다른 세션(또는 끊기기 전)의 사고가 끝났는지는 알 수 없다
  resetBackgroundThought();
  HUD.setState('idle');
}

// 다른 에이전트로 옮겼다 돌아오면 그 사이 진행된 턴을 이력 뒤에 다시 그리고, 기다리던 라이브 이벤트를 잇는다
async function replayInFlight(gen, events) {
  await _historyDone;
  if (gen !== _linkGen) return;  // 기다리는 사이 다시 붙었으면 새 연결이 맡는다
  // 다시 그린 agent_start 가 이 화면을 "일하는 중" 으로 둔다. 그동안 보낸 말은 대기열로 간다
  for (const ev of events) handleMessage(ev, { replay: true });
  const held = _held || [];
  _held = null;
  for (const m of held) handleMessage(m);
}

export function connect(sessionId = _currentSessionId) {
  _currentSessionId = sessionId;
  _unread.delete(sessionId);
  setUnreadAgents(unreadAgents());
  // 지금 세션을 다른 모듈(workflow 의 지도)이 import 없이 읽고, 바뀜을 듣는다
  document.body.dataset.session = sessionId;
  document.dispatchEvent(new CustomEvent('session:connected', { detail: sessionId }));
  resetChatUI();
  const gen = ++_linkGen;
  _held = [];
  _historyDone = fetchAndRenderHistory(sessionId).then(() => {
    if (_currentSessionId === sessionId) {
      appendMsg('SYS', 'sys', `— SESSION · ${new Date().toLocaleTimeString('ko-KR', { hour12: false })} · ${escapeHtml(sessionId)} —`);
    }
  });

  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  const tokenQs = getToken() ? `&token=${encodeURIComponent(getToken())}` : '';
  openSocket(`${proto}://${location.host}/ws?session_id=${encodeURIComponent(sessionId)}${tokenQs}`, {
    onOpen() {
      $connBanner.classList.add('hidden');
      _reconnectDelay = RECONNECT_MIN_MS;
    },
    onClose(ev) {
      setInputEnabled(false);
      setLinkState(false);
      if (ev.code === WS_UNAUTHORIZED) {
        // 키 불일치 — 재시도 루프 대신 키를 묻고 바로 다시 연결한다
        askForToken().then((ok) => {
          if (ok) location.reload();
          else { $connBanner.classList.remove('hidden'); logActivity('접근 키 없음', 'err', SYSTEM); }
        });
        return;
      }
      if (ev.code === WS_UNKNOWN_AGENT) {
        logActivity(`에이전트 없음 · ${sessionId} · ${ev.reason || 'unknown agent'}`, 'err', SYSTEM);
        // 기본 세션으로 한 번만 옮긴다. 기본 세션마저 4404 면 배너만 남기고 멈춘다
        if (sessionId !== FALLBACK_SESSION_ID) connect(FALLBACK_SESSION_ID);
        else $connBanner.classList.remove('hidden');
        return;
      }
      $connBanner.classList.remove('hidden');
      logActivity('link lost — retrying', 'err', SYSTEM);
      setTimeout(() => connect(_currentSessionId), _reconnectDelay);
      _reconnectDelay = Math.min(_reconnectDelay * 2, RECONNECT_MAX_MS);
    },
    onMessage(msg) {
      // 화면 채우기가 실패해도 붙잡아 둔 이벤트는 흘려야 화면이 멈추지 않는다
      if (msg.type === 'connected') {
        onConnected(msg)
          .catch((e) => console.error('connected handling failed:', e))
          .finally(() => replayInFlight(gen, msg.in_flight || []));
      } else if (_held) _held.push(msg);
      else handleMessage(msg);
    },
  });
}

// 다른 모듈이 세션을 열 때(지도의 위임 카드 클릭). import 순환을 피해 이벤트로 받는다
document.addEventListener('session:open', (e) => {
  const sid = typeof e.detail === 'string' ? e.detail : '';
  if (sid && sid !== _currentSessionId) connect(sid);
});
