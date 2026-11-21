const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const { migrateLegacySettings, pickLegacySettings } = require('../userdata_migration');

function appData() {
  return fs.mkdtempSync(path.join(os.tmpdir(), 'ash-industry-appdata-'));
}

function write(file, text) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, text);
}

test('copies legacy Jarvis settings once and never overwrites', () => {
  const root = appData();
  const userDataDir = path.join(root, 'Ash Industry');
  write(path.join(root, 'Jarvis', 'settings.json'), '{"autoLaunch":true}');
  write(path.join(root, 'jarvis-desktop', 'settings.json'), '{"autoLaunch":false}');

  const first = migrateLegacySettings({ appDataDir: root, userDataDir });
  assert.equal(first.copied, true);
  assert.equal(first.from, path.join(root, 'Jarvis', 'settings.json'));
  assert.equal(fs.readFileSync(path.join(userDataDir, 'settings.json'), 'utf8'), '{"autoLaunch":true}');

  write(path.join(root, 'Jarvis', 'settings.json'), '{"autoLaunch":false}');
  assert.deepEqual(migrateLegacySettings({ appDataDir: root, userDataDir }), { copied: false });
  assert.equal(fs.readFileSync(path.join(userDataDir, 'settings.json'), 'utf8'), '{"autoLaunch":true}');
});

test('does nothing without legacy settings or when the legacy dir is userData itself', () => {
  const root = appData();
  assert.deepEqual(migrateLegacySettings({ appDataDir: root, userDataDir: path.join(root, 'Ash Industry') }), { copied: false });
  assert.equal(fs.existsSync(path.join(root, 'Ash Industry')), false);
  const exists = (p) => p === path.join(root, 'Jarvis', 'settings.json');
  assert.equal(pickLegacySettings({ appDataDir: root, userDataDir: path.join(root, 'Jarvis'), exists }), null);
});

test('reports a copy failure instead of throwing', () => {
  const root = appData();
  write(path.join(root, 'jarvis-desktop', 'settings.json'), '{}');
  const brokenFs = { ...fs, copyFileSync: () => { throw new Error('EACCES'); } };
  const result = migrateLegacySettings({ appDataDir: root, userDataDir: path.join(root, 'new'), fs: brokenFs });
  assert.deepEqual(result, { copied: false, error: 'EACCES' });
});
