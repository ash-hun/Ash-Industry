// 창 닫기를 트레이로 숨기기로 바꾼다. electron 없이 시험할 수 있게 창 객체만 받는다.

// macOS 전체 화면 창을 바로 숨기면 창만 사라지고 그 전체 화면 공간이 검은 화면으로 남는다.
// 전체 화면을 먼저 풀고, 풀린 뒤에 숨긴다
function hideToTray(win) {
  if (win.isFullScreen()) {
    win.once('leave-full-screen', () => win.hide());
    win.setFullScreen(false);
    return;
  }
  win.hide();
}

module.exports = { hideToTray };
