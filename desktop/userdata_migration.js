// 앱 이름이 바뀌어 옮겨 간 userData 로 옛 데스크톱 설정 파일을 한 번만 복사한다. fs 와 경로는 주입한다.
const nodeFs = require('node:fs');
const path = require('node:path');

// 옛 번들(productName)과 옛 개발 실행(package name)의 userData 폴더 이름. 앞의 것이 우선이다
const LEGACY_APP_NAMES = Object.freeze(['Jarvis', 'jarvis-desktop']);
const SETTINGS_FILE = 'settings.json';

// 복사할 원본을 고른다. 새 위치에 이미 파일이 있으면 아무것도 하지 않는다
function pickLegacySettings({ appDataDir, userDataDir, exists, legacyNames = LEGACY_APP_NAMES, file = SETTINGS_FILE }) {
  const target = path.join(userDataDir, file);
  if (exists(target)) return null;
  for (const name of legacyNames) {
    const dir = path.join(appDataDir, name);
    if (path.resolve(dir) === path.resolve(userDataDir)) continue;
    const source = path.join(dir, file);
    if (exists(source)) return { source, target };
  }
  return null;
}

// 덮어쓰지 않는다(COPYFILE_EXCL). 두 번째 실행은 새 파일이 있으니 그대로 지나간다
function migrateLegacySettings({ appDataDir, userDataDir, fs = nodeFs, legacyNames = LEGACY_APP_NAMES }) {
  const plan = pickLegacySettings({ appDataDir, userDataDir, legacyNames, exists: (p) => fs.existsSync(p) });
  if (!plan) return { copied: false };
  try {
    fs.mkdirSync(path.dirname(plan.target), { recursive: true });
    fs.copyFileSync(plan.source, plan.target, nodeFs.constants.COPYFILE_EXCL);
  } catch (error) {
    return { copied: false, error: String(error && error.message ? error.message : error) };
  }
  return { copied: true, from: plan.source };
}

module.exports = { LEGACY_APP_NAMES, migrateLegacySettings, pickLegacySettings };
