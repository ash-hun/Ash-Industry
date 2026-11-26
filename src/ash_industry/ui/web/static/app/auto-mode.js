// auto mode — 지금 보는 에이전트의 승인 자동 허용을 입력 독의 AUTO 로, SET 의 목록으로 켜고 끈다.
import { apiFetch } from './api.js';
import { AGENT_ID } from './brand.js';

const $toggle = document.getElementById('auto-btn');
const $list   = document.getElementById('auto-list');

let _agents = [];  // [{id, name, enabled}]

function paint() {
  const me = _agents.find((a) => a.id === AGENT_ID);
  if ($toggle) {
    $toggle.hidden = !me;
    $toggle.classList.toggle('on', Boolean(me?.enabled));
    $toggle.setAttribute('aria-pressed', me?.enabled ? 'true' : 'false');
    $toggle.title = me?.enabled
      ? `${me.name} auto mode 켜짐: 승인을 묻지 않고 실행합니다(위험 명령, 정책 deny 는 막힘)`
      : 'auto mode 꺼짐: 쓰기 도구는 실행 전에 승인을 묻습니다';
  }
  if ($list) {
    $list.replaceChildren(..._agents.map((a) => {
      const label = document.createElement('label');
      label.className = 'auto-row';
      const box = document.createElement('input');
      box.type = 'checkbox';
      box.checked = a.enabled;
      box.addEventListener('change', () => setAuto(a.id, box.checked));
      const name = document.createElement('span');
      name.textContent = `${a.name} (${a.id})`;
      label.append(box, name);
      return label;
    }));
  }
}

export async function loadAuto() {
  try {
    const res = await apiFetch('/api/auto-approve');
    if (!res.ok) return;
    _agents = (await res.json()).agents || [];
    paint();
  } catch { /* 백엔드가 없으면 토글을 숨긴 채 둔다 */ }
}

async function setAuto(agent, enabled) {
  try {
    const res = await apiFetch(`/api/auto-approve/${encodeURIComponent(agent)}`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ enabled }),
    });
    if (res.ok) _agents = (await res.json()).agents || _agents;
  } finally {
    paint();
  }
}

$toggle?.addEventListener('click', () => {
  const me = _agents.find((a) => a.id === AGENT_ID);
  if (me) setAuto(me.id, !me.enabled);
});
// 에이전트를 넘기면 그 에이전트의 상태로 다시 그린다
window.addEventListener('ash:palette', paint);
loadAuto();
