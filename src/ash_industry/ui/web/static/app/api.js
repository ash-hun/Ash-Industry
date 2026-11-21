// REST 호출과 접근 키. 서버에 ASH_SECURITY__API_KEYS 가 설정돼 있으면 /ws 와 /api 가 키를 요구한다.
// 키는 이 브라우저에만 저장되는 편의 값이라 localStorage 에 둔다. 401 이나 4401 이 오면 입력 창으로 묻는다.
import { askTokenDialog } from './token-dialog.js';

const TOKEN_KEY = 'ash_token';

export function getToken() { try { return localStorage.getItem(TOKEN_KEY) || ''; } catch { return ''; } }
function setToken(t) { try { localStorage.setItem(TOKEN_KEY, t); } catch { /* 무시 */ } }

export async function apiFetch(path, opts = {}) {
  const headers = { ...(opts.headers || {}) };
  const t = getToken();
  if (t) headers['Authorization'] = `Bearer ${t}`;
  const res = await fetch(path, { ...opts, headers });
  // 키가 없거나 틀리면 묻고, 저장하면 새로 불러 모든 화면이 새 키로 다시 받게 한다
  if (res.status === 401) askForToken().then((ok) => { if (ok) location.reload(); });
  return res;
}

export async function askForToken() {
  const t = await askTokenDialog();
  if (!t) return false;
  setToken(t);
  return true;
}
