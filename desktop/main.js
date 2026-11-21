// Electron 메인 프로세스: 창 하나, 트레이 상주, 전역 단축키, 마이크와 알림 권한, 백엔드 확인.
const path = require('node:path');
const {
  app, BrowserWindow, Tray, Menu, nativeImage, globalShortcut, ipcMain, session, shell, systemPreferences,
} = require('electron');

const { migrateLegacySettings } = require('./userdata_migration');
const { DesktopSettings } = require('./desktop_settings');
const { isStage, planExit } = require('./boot_sequence');
const { BackendProbe } = require('./backend_probe');
const { hideToTray } = require('./window_hide');

const ICON = path.join(__dirname, 'icons', 'icon.png');
// 메뉴 막대 아이콘은 검정과 알파만 쓴 템플릿이라 macOS 가 밝은, 어두운 막대에 맞춰 칠한다. @2x 는 같은 폴더에서 자동으로 붙는다
const TRAY_ICON = path.join(__dirname, 'icons', 'trayTemplate.png');
const LOADING = path.join(__dirname, 'loading.html');
// 백엔드가 없으면 이 간격으로 다시 본다. 앱은 백엔드를 띄우지 않는다(docker compose 나 Ion 의 몫). 뜨면 알아서 붙는다
const RETRY_MS = 5000;
// 렌더러가 요청할 수 있는 권한. 그 밖은 모두 거절한다
const ALLOWED_PERMISSIONS = new Set(['media', 'notifications', 'clipboard-sanitized-write']);
// 기본 제목 표시줄을 숨기고 HUD 헤더(높이 52px, 배경 #14161a)가 그 자리를 맡는다.
// macOS 는 신호등 버튼을 헤더 세로 가운데에, 그 밖은 창 버튼을 헤더 색으로 덧그린다
const HEADER_H = 52;
const TITLE_BAR = process.platform === 'darwin'
  ? { titleBarStyle: 'hiddenInset', trafficLightPosition: { x: 16, y: 18 } }
  : { titleBarStyle: 'hidden', titleBarOverlay: { color: '#14161a', symbolColor: '#e6e8ea', height: HEADER_H } };

// 시험과 여러 설치를 나눌 때 앱 데이터 폴더를 바꾼다. 비우면 OS 기본 위치
if (process.env.ASH_DESKTOP_DATA) app.setPath('userData', path.resolve(process.env.ASH_DESKTOP_DATA));
// productName 이 Jarvis 에서 바뀌어 userData 폴더도 바뀌었다. 직접 고른 폴더에는 옛 설정을 끌어오지 않는다
else migrateLegacySettings({ appDataDir: app.getPath('appData'), userDataDir: app.getPath('userData') });
const settingsStore = new DesktopSettings(path.join(app.getPath('userData'), 'settings.json'));
let settings = settingsStore.load();
let win = null;
let tray = null;
let quitting = false;
let connectSeq = 0;  // 주소가 바뀌면 지난 재시도 루프를 버린다
// 부팅 화면(loading.html)이 그리는 단계. 렌더러는 로드 뒤 지금 단계를 당겨 가고, 이후 바뀌면 받는다
const boot = { stage: 'shell', detail: '', reducedMotion: false };

function isBackendUrl(target) {
  try { return new URL(target).origin === settings.backendUrl; } catch { return false; }
}

function showLoading(error) {
  if (!win) return;
  win.loadFile(LOADING, error ? { query: { error } } : undefined);
}

function setBootStage(stage, detail = '') {
  boot.stage = stage;
  boot.detail = detail;
  if (win && win.webContents.getURL().startsWith('file://')) win.webContents.send('desktop:boot-stage', { stage, detail });
}

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function connectBackend() {
  const seq = ++connectSeq;
  const shownAt = Date.now();
  showLoading();
  setBootStage('connecting', settings.backendUrl);
  const probe = new BackendProbe({ url: settings.backendUrl });
  while (win && seq === connectSeq) {
    if (await probe.alive()) {
      if (!win || seq !== connectSeq) return;
      setBootStage('online', settings.backendUrl);
      const { holdMs, fadeMs } = planExit({ shownAt, onlineAt: Date.now(), reducedMotion: boot.reducedMotion });
      await wait(holdMs);
      if (!win || seq !== connectSeq) return;
      setBootStage('exit');
      await wait(fadeMs);
      if (win && seq === connectSeq) win.loadURL(settings.backendUrl);
      return;
    }
    boot.stage = 'error';
    showLoading(`백엔드(${settings.backendUrl})가 응답하지 않습니다. docker compose --profile web up -d 로 띄우면 자동으로 연결합니다.`);
    await wait(RETRY_MS);
  }
}

function showWindow() {
  if (!win) return;
  if (win.isMinimized()) win.restore();
  win.show();
  win.focus();
}

function guardPermissions() {
  const ses = session.defaultSession;
  ses.setPermissionRequestHandler((wc, permission, callback, details) => {
    const fromBackend = isBackendUrl(details.requestingUrl || wc.getURL());
    const audioOnly = permission !== 'media' || (details.mediaTypes || []).every((t) => t === 'audio');
    callback(fromBackend && ALLOWED_PERMISSIONS.has(permission) && audioOnly);
  });
  ses.setPermissionCheckHandler((_wc, permission, origin) => ALLOWED_PERMISSIONS.has(permission) && isBackendUrl(origin));
}

function createWindow() {
  win = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 380,
    minHeight: 560,
    backgroundColor: '#14161a',
    title: 'Ash Industry',
    icon: ICON,
    show: false,
    ...TITLE_BAR,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  win.once('ready-to-show', () => win.show());
  // 백엔드 밖으로는 창 안에서 이동하지 않는다. http(s) 링크만 기본 브라우저로 연다
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https?:\/\//.test(url) && !isBackendUrl(url)) shell.openExternal(url);
    return { action: 'deny' };
  });
  win.webContents.on('will-navigate', (event, url) => {
    if (!isBackendUrl(url) && !url.startsWith('file://')) event.preventDefault();
  });
  // 백엔드가 재시작되면 페이지 로드가 끊긴다. 다시 연결한다
  win.webContents.on('did-fail-load', (_e, code, _desc, url, isMainFrame) => {
    if (isMainFrame && code !== -3 && isBackendUrl(url)) connectBackend();
  });
  // 닫기는 트레이로 숨기기. 백그라운드 알림(🔔, 리마인더)을 받으려면 ws 가 열려 있어야 한다
  win.on('close', (event) => {
    if (quitting) return;
    event.preventDefault();
    hideToTray(win);
  });
  win.on('closed', () => { win = null; });
}

function triggerListen() {
  showWindow();
  win?.webContents.send('desktop:hotkey');
}

function applyHotkey() {
  globalShortcut.unregisterAll();
  if (!settings.hotkey) return true;
  try { return globalShortcut.register(settings.hotkey, triggerListen); } catch { return false; }
}

function applyLoginItem() {
  if (process.platform === 'darwin' || process.platform === 'win32') {
    app.setLoginItemSettings({ openAtLogin: settings.autoLaunch, openAsHidden: true });
  }
}

function createTray() {
  // 템플릿은 macOS 만 칠해 준다. 다른 OS 의 어두운 트레이에서는 검정이 안 보여 앱 아이콘을 줄여 쓴다
  const image = process.platform === 'darwin'
    ? nativeImage.createFromPath(TRAY_ICON)
    : nativeImage.createFromPath(ICON).resize({ width: 16, height: 16 });
  if (process.platform === 'darwin') image.setTemplateImage(true);
  tray = new Tray(image);
  tray.setToolTip('Ash Industry');
  tray.setContextMenu(Menu.buildFromTemplate([
    { label: '열기', click: showWindow },
    { label: '듣기 시작', click: triggerListen },
    { type: 'separator' },
    { label: '종료', click: () => { quitting = true; app.quit(); } },
  ]));
  tray.on('click', showWindow);
}

function fromLoadingPage(event) {
  return (event.senderFrame?.url || '').startsWith('file://');
}

function registerIpc() {
  // 부팅 화면만 부른다. 백엔드 페이지에도 같은 preload 가 열려 있어 출처를 본다
  ipcMain.handle('desktop:boot-sync', (event, hello) => {
    if (!fromLoadingPage(event)) return null;
    boot.reducedMotion = hello?.reducedMotion === true;
    return { stage: isStage(boot.stage) ? boot.stage : 'shell', detail: boot.detail };
  });
  ipcMain.handle('desktop:get-settings', () => settings);
  ipcMain.handle('desktop:set-settings', (_event, next) => {
    const prevUrl = settings.backendUrl;
    const result = settingsStore.save(next || {});
    if (!result.ok) return result;
    settings = result.settings;
    applyLoginItem();
    if (!applyHotkey()) return { ok: false, error: `단축키를 등록하지 못했습니다: ${settings.hotkey}`, settings };
    if (settings.backendUrl !== prevUrl) connectBackend();
    return { ok: true, settings };
  });
}

if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on('second-instance', showWindow);
  app.whenReady().then(async () => {
    if (process.platform === 'darwin') {
      // 패키징 전 macOS 는 창 icon 을 무시하고 Electron 기본 아이콘을 Dock 에 띄운다. 번들은 Info.plist 의 아이콘을 쓴다
      if (!app.isPackaged) app.dock?.setIcon(ICON);
      // 처음 한 번 macOS 가 마이크 권한을 묻는다. 거절하면 HUD 가 마이크 오류를 보여 준다
      await systemPreferences.askForMediaAccess('microphone').catch(() => false);
    }
    guardPermissions();
    registerIpc();
    createWindow();
    createTray();
    applyHotkey();
    applyLoginItem();
    await connectBackend();
  });
  app.on('activate', showWindow);
  app.on('before-quit', () => { quitting = true; });
  app.on('will-quit', () => globalShortcut.unregisterAll());
  // 창을 닫아도 트레이에 남는다. 종료는 트레이 메뉴나 Cmd+Q
  app.on('window-all-closed', () => {});
}
