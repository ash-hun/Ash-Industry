const test = require('node:test');
const assert = require('node:assert/strict');

const { BOOT_MIN_MS, EXIT_FADE_MS, STAGES, isStage, planExit } = require('../boot_sequence');

test('planExit holds a fast backend until the minimum display time', () => {
  assert.deepEqual(planExit({ shownAt: 1000, onlineAt: 1300, reducedMotion: false }), { holdMs: BOOT_MIN_MS - 300, fadeMs: EXIT_FADE_MS });
});

test('planExit does not hold a slow backend and skips everything with reduced motion', () => {
  assert.deepEqual(planExit({ shownAt: 0, onlineAt: BOOT_MIN_MS + 5000, reducedMotion: false }), { holdMs: 0, fadeMs: EXIT_FADE_MS });
  assert.deepEqual(planExit({ shownAt: 0, onlineAt: 10, reducedMotion: true }), { holdMs: 0, fadeMs: 0 });
  assert.deepEqual(planExit({ shownAt: 500, onlineAt: 100, reducedMotion: false }), { holdMs: BOOT_MIN_MS, fadeMs: EXIT_FADE_MS });
});

test('isStage accepts known stages only', () => {
  for (const stage of [...STAGES, 'error']) assert.equal(isStage(stage), true);
  assert.equal(isStage('ready'), false);
  assert.equal(isStage(undefined), false);
});
