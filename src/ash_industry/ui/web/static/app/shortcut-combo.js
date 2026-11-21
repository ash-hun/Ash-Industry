// HUD 단축키 문자열(Ctrl+Shift+Enter) 읽기와 키 이벤트 맞추기. DOM 을 만지지 않는 순수 함수만 둔다.
// COMBO 는 서버 ash_config.SHORTCUT_PATTERN 과 같은 식이다. 바꾸면 둘을 같이 바꾼다
export const COMBO = /^(?:(?:Ctrl|Alt|Shift|Meta)\+){0,4}(?:[A-Za-z0-9]|F[1-9]|F1[0-2]|Enter|Escape|Space|Tab|Backspace|Delete|Home|End|PageUp|PageDown|ArrowUp|ArrowDown|ArrowLeft|ArrowRight)$/;

// 앞의 것이 먼저 맞는다. 서버가 겹치는 키를 막으니 순서는 기본값을 고르는 데만 쓴다
export const ACTIONS = ['voice_start', 'voice_stop', 'agent_prev', 'agent_next'];

export const DEFAULT_SHORTCUTS = Object.freeze({
  voice_start: 'Ctrl+Shift+Enter',
  voice_stop: 'Escape',
  agent_prev: 'Ctrl+Shift+ArrowLeft',
  agent_next: 'Ctrl+Shift+ArrowRight',
});

// 형식이 틀리면 null. Ctrl 은 macOS 에서도 Control 키다(Cmd 는 Meta)
export function parseCombo(text) {
  if (typeof text !== 'string' || !COMBO.test(text)) return null;
  const parts = text.split('+');
  const key = parts.pop();
  return {
    ctrl: parts.includes('Ctrl'),
    alt: parts.includes('Alt'),
    shift: parts.includes('Shift'),
    meta: parts.includes('Meta'),
    key,
  };
}

// 수정키 집합이 정확히 같아야 맞는다. 글자와 숫자는 물리 키(code)로도 본다. Alt 나 한글 입력 중에는 key 가 다른 글자가 된다
export function matchCombo(combo, e) {
  if (!combo) return false;
  if (!!e.ctrlKey !== combo.ctrl || !!e.altKey !== combo.alt || !!e.shiftKey !== combo.shift || !!e.metaKey !== combo.meta) {
    return false;
  }
  const k = combo.key;
  if (/^[A-Za-z]$/.test(k)) return e.code === `Key${k.toUpperCase()}` || String(e.key || '').toLowerCase() === k.toLowerCase();
  if (/^[0-9]$/.test(k)) return e.code === `Digit${k}` || e.key === k;
  if (k === 'Space') return e.code === 'Space' || e.key === ' ';
  return e.key === k;
}

// 동작마다 읽은 조합. 비었거나 틀린 값은 그 동작의 기본값으로 둔다
export function resolveShortcuts(values) {
  const src = values && typeof values === 'object' ? values : {};
  return Object.fromEntries(ACTIONS.map((a) => [a, parseCombo(src[a]) || parseCombo(DEFAULT_SHORTCUTS[a])]));
}
