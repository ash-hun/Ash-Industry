// 부팅 화면의 단계와 시간 결정. 시각은 밖에서 받아 계산만 한다(electron 없이 시험한다).

// 백엔드가 빨리 떠도 부팅 화면이 번쩍이고 사라지지 않게 최소한 이만큼 보인다
const BOOT_MIN_MS = 2000;
// "SYSTEM ONLINE" 뒤 화면이 어두워지는 시간. loading.html 의 .exit 전환 시간과 같아야 한다
const EXIT_FADE_MS = 600;
// 렌더러가 단계를 놓쳐도 앞 단계 줄을 채울 수 있게 순서를 고정한다
const STAGES = Object.freeze(['shell', 'connecting', 'online', 'exit']);
const ALL_STAGES = new Set([...STAGES, 'error']);

function isStage(value) {
  return typeof value === 'string' && ALL_STAGES.has(value);
}

// 백엔드가 응답한 뒤 몇 ms 더 머물고(holdMs), 몇 ms 동안 어두워진 뒤(fadeMs) 주소를 여는지.
// 움직임 줄이기를 켰으면 기다리지 않고 바로 넘어간다
function planExit({ shownAt, onlineAt, reducedMotion }) {
  if (reducedMotion) return { holdMs: 0, fadeMs: 0 };
  const elapsed = Math.max(0, onlineAt - shownAt);
  return { holdMs: Math.max(0, BOOT_MIN_MS - elapsed), fadeMs: EXIT_FADE_MS };
}

module.exports = { BOOT_MIN_MS, EXIT_FADE_MS, STAGES, isStage, planExit };
