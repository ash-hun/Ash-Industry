// 뒤에서 도는 작업의 별 — 오래 걸려 뒤로 넘긴 턴마다 리액터 위와 좌우(구체 바깥, 좌우 카드 안쪽)에 반짝이는 별 하나.
import { agentById } from './agents.js';
import { send } from './ws.js';
import { askConfirm } from './confirm-dialog.js';

const $reactor = document.querySelector('.reactor');
const $wrap = document.querySelector('.sphere-wrap');
const $layer = document.getElementById('task-stars');

const RING_GAP = 1.06;   // 구체 반지름 대비 별이 시작하는 거리. 링에 겹치지 않게
const EDGE_PX = 16;      // 가운데 열 가장자리에서 띄우는 거리
const MIN_BAND_PX = 18;  // 이보다 좁은 방향에는 별을 두지 않는다
const GOLDEN = 2.399963; // 자리가 겹치면 이 각도씩 돌려 다음 자리를 본다
const DONE_MS = 900;
const LOW_LIMIT = 0.9;    // 별이 내려갈 수 있는 가장 낮은 자리(구체 반지름 대비, 가운데 아래쪽). 그 밑은 상태 표시와 캡션
const NOTE_MAX_PX = 220;  // 별 옆 메시지의 최대 폭. 남은 자리가 더 좁으면 그만큼 줄인다
const NOTE_GAP_PX = 24;   // 별 중심에서 메시지까지와 가장자리 여유를 합친 거리

let _tasks = [];  // [{task_id, session_id, agent, label}] 서버가 매번 목록 전체를 보낸다

// 작업 id 로 정한 0~1 두 값. 새로 고쳐도 같은 별은 같은 자리에 뜬다
function seeds(id) {
  let h = 2166136261;
  for (const ch of id) { h ^= ch.charCodeAt(0); h = Math.imul(h, 16777619); }
  const a = (h >>> 0) / 4294967296;
  const b = (Math.imul(h ^ (h >>> 15), 2246822507) >>> 0) / 4294967296;
  return [a, b];
}

// 리액터 가운데 열 안에서 그 방향으로 갈 수 있는 거리
function reach(cx, cy, w, h, angle) {
  const dx = Math.cos(angle), dy = Math.sin(angle);
  const limits = [];
  if (dx > 0) limits.push((w - EDGE_PX - cx) / dx);
  if (dx < 0) limits.push((EDGE_PX - cx) / dx);
  if (dy > 0) limits.push((h - EDGE_PX - cy) / dy);
  if (dy < 0) limits.push((EDGE_PX - cy) / dy);
  return Math.min(...limits);
}

// 별 옆 메시지는 가운데 열 안에서 자리가 더 넓은 쪽으로 펴고, 남은 자리만큼만 늘린다. 옆 카드 밑으로 잘리지 않게
function fitNote(star, x, width) {
  const right = width - x - NOTE_GAP_PX;
  const left = x - NOTE_GAP_PX;
  star.dataset.side = right >= left ? 'right' : 'left';
  star.style.setProperty('--note-max', `${Math.max(60, Math.min(NOTE_MAX_PX, Math.max(right, left)))}px`);
}

function place(star, id) {
  const box = $reactor.getBoundingClientRect();
  const sphere = $wrap.getBoundingClientRect();
  const cx = sphere.left - box.left + sphere.width / 2;
  const cy = sphere.top - box.top + sphere.height / 2;
  const inner = (sphere.width / 2) * RING_GAP;
  const [a, b] = seeds(id);
  for (let i = 0; i < 12; i += 1) {
    const angle = (a * Math.PI * 2) + i * GOLDEN;
    const outer = reach(cx, cy, box.width, box.height, angle);
    if (outer - inner < MIN_BAND_PX) continue;
    const r = inner + b * (outer - inner);
    // 구체 아래는 상태 표시와 캡션(답이 읽히는 줄) 자리라 비운다. 캡션 폭은 글에 따라 바뀌어 띠 전체를 뺀다
    if (Math.sin(angle) * r > (sphere.height / 2) * LOW_LIMIT) continue;
    const x = cx + Math.cos(angle) * r;
    star.style.left = `${x}px`;
    star.style.top = `${cy + Math.sin(angle) * r}px`;
    fitNote(star, x, box.width);
    return;
  }
  // 둘 자리가 없으면(아주 좁은 화면) 구체 위 가장자리에 둔다
  star.style.left = `${cx}px`;
  star.style.top = `${Math.max(EDGE_PX, cy - inner)}px`;
  fitNote(star, cx, box.width);
}

function starFor(task) {
  const agent = agentById(task.agent);
  const name = agent ? agent.name : task.agent;
  // 별 하나: 반짝이는 단추(누르면 그 대화로)와, 마우스를 올리면 뜨는 메시지(맡긴 일, 대기 지시 수, 멈추기)
  const star = document.createElement('div');
  star.className = 'task-star';
  star.dataset.task = task.task_id;
  const [, b] = seeds(task.task_id);
  star.style.setProperty('--twinkle-delay', `${(b * -2.4).toFixed(2)}s`);
  if (agent) star.style.setProperty('--agent-color', agent.palette.primary);
  const hit = document.createElement('button');
  hit.type = 'button';
  hit.className = 'task-star-hit';
  hit.setAttribute('aria-label', `${name} 작업 중: ${task.label}. 눌러서 그 대화로 이동`);
  hit.appendChild(Object.assign(document.createElement('span'), { className: 'spark' }));
  hit.addEventListener('click', () => {
    document.dispatchEvent(new CustomEvent('session:open', { detail: task.session_id }));
  });
  // 맡긴 작업은 사용자 요청에서 왔으므로 textContent 로만 넣는다
  const note = document.createElement('div');
  note.className = 'task-star-note';
  const text = document.createElement('span');
  text.className = 'txt';
  const stop = document.createElement('button');
  stop.type = 'button';
  stop.className = 'task-stop';
  stop.textContent = '멈추기';
  stop.addEventListener('click', async (e) => {
    e.stopPropagation();
    const yes = await askConfirm({
      title: '⏹ 작업 멈추기',
      message: `${name} 의 작업 "${task.label}" 을 멈출까요? 하던 데까지는 대화에 남습니다.`,
      ok: '멈추기',
      cancel: '계속',
    });
    if (!yes) return;
    stop.disabled = true;
    stop.textContent = '멈추는 중';
    send({ type: 'background_stop', task_id: task.task_id, session_id: task.session_id });
  });
  note.append(text, stop);
  star.append(hit, note);
  setNote(star, task);
  place(star, task.task_id);
  return star;
}

// 메시지 글: 에이전트 · 맡긴 일, 그 작업이 아직 읽지 않은 지시(대기)와 읽어 반영한 지시(반영)의 수
function setNote(star, task) {
  const agent = agentById(task.agent);
  const pending = Number(task.pending) || 0;
  const applied = Number(task.applied) || 0;
  const counts = [pending && `지시 ${pending}건 대기`, applied && `지시 ${applied}건 반영`].filter(Boolean);
  star.querySelector('.task-star-note .txt').textContent =
    [`${agent ? agent.name : task.agent} · ${task.label}`, ...counts].join(' · ');
  star.classList.toggle('pending', pending > 0);
  star.classList.toggle('applied', pending === 0 && applied > 0);
}

function render(done) {
  const keep = new Set(_tasks.map((t) => t.task_id));
  for (const star of [...$layer.children]) {
    if (keep.has(star.dataset.task) || star.classList.contains('done')) continue;
    // 끝난 별은 한 번 밝아졌다 사라진다. 실패면 붉게, 사용자가 멈췄으면 밝아지지 않고 흐려진다
    const mine = done && done.task_id === star.dataset.task;
    star.classList.add('done');
    if (mine && done.stopped) star.classList.add('stopped');
    else if (mine && !done.ok) star.classList.add('failed');
    setTimeout(() => star.remove(), DONE_MS);
  }
  const shown = new Map([...$layer.children].map((s) => [s.dataset.task, s]));
  for (const task of _tasks) {
    const star = shown.get(task.task_id);
    if (star) setNote(star, task);
    else $layer.appendChild(starFor(task));
  }
}

export function setBackgroundTasks(tasks, done = null) {
  _tasks = Array.isArray(tasks) ? tasks : [];
  render(done);
}

// 창 크기나 Focus 열 전환으로 리액터가 바뀌면 자리를 다시 잡는다
new ResizeObserver(() => {
  for (const star of $layer.children) place(star, star.dataset.task);
}).observe($reactor);
