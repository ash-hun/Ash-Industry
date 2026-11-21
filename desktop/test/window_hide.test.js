const test = require('node:test');
const assert = require('node:assert/strict');

const { hideToTray } = require('../window_hide');

function fakeWindow(fullScreen) {
  const calls = [];
  const handlers = {};
  return {
    calls,
    isFullScreen: () => fullScreen,
    setFullScreen: (on) => { calls.push(`fullscreen:${on}`); fullScreen = on; },
    once: (event, fn) => { handlers[event] = fn; },
    hide: () => calls.push('hide'),
    emit: (event) => handlers[event]?.(),
  };
}

test('hides a normal window right away', () => {
  const win = fakeWindow(false);
  hideToTray(win);
  assert.deepEqual(win.calls, ['hide']);
});

test('leaves full screen before hiding so no black space is left', () => {
  const win = fakeWindow(true);
  hideToTray(win);
  assert.deepEqual(win.calls, ['fullscreen:false']);
  win.emit('leave-full-screen');
  assert.deepEqual(win.calls, ['fullscreen:false', 'hide']);
});
