// 렌더러(HUD 페이지와 부팅 화면)에 window.ashDesktop 만 연다. Node 와 ipcRenderer 자체는 넘기지 않는다.
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('ashDesktop', {
  platform: process.platform,
  getSettings: () => ipcRenderer.invoke('desktop:get-settings'),
  setSettings: (next) => ipcRenderer.invoke('desktop:set-settings', next),
  onHotkey: (callback) => {
    ipcRenderer.on('desktop:hotkey', () => callback());
  },
  // 부팅 화면 전용. 메인은 부팅 화면(file://)이 아닌 곳의 동기화 요청에 null 을 돌려준다
  syncBoot: (hello) => ipcRenderer.invoke('desktop:boot-sync', { reducedMotion: hello?.reducedMotion === true }),
  onBootStage: (callback) => {
    ipcRenderer.on('desktop:boot-stage', (_event, payload) => callback({ stage: String(payload?.stage || ''), detail: String(payload?.detail || '') }));
  },
});
