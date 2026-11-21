// 다른 세션의 승인 대기 — 다른 에이전트를 보는 동안 그 에이전트가 승인을 기다리면 띠를 띄우고, 누르면 그 세션으로 옮긴다.
import { agentById } from './agents.js';

const $bar = document.getElementById('approval-wait');
let _waiting = [];  // [{session_id, agent, count}] 서버가 매번 목록 전체를 보낸다

function render() {
  const current = document.body.dataset.session;
  const others = _waiting.filter((w) => w.session_id !== current && w.count > 0);
  $bar.replaceChildren();
  $bar.hidden = others.length === 0;
  for (const w of others) {
    const agent = agentById(w.agent);
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'approval-wait-item';
    // 글자는 textContent 로만 넣는다. 세션 id 와 에이전트 이름이 화면에 그대로 섞이지 않게
    btn.textContent = `⚡ ${agent ? agent.name : w.agent} 승인 대기${w.count > 1 ? ` ${w.count}건` : ''} · 이동`;
    if (agent) btn.style.setProperty('--agent-color', agent.palette.primary);
    btn.addEventListener('click', () => {
      document.dispatchEvent(new CustomEvent('session:open', { detail: w.session_id }));
    });
    $bar.appendChild(btn);
  }
}

export function setApprovalWaiting(waiting) {
  _waiting = Array.isArray(waiting) ? waiting : [];
  render();
}

// 세션을 옮기면 지금 세션의 대기는 모달로 보이므로 띠에서 뺀다
document.addEventListener('session:connected', render);
