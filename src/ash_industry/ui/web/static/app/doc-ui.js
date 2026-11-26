// 문서 편집 보기와 양식 등록 창이 같이 쓰는 요소 만들기와 /api/docs/* 호출.
import { apiFetch } from './api.js';

export function el(tag, props = {}, ...children) {
  const node = Object.assign(document.createElement(tag), props);
  for (const child of children) if (child != null) node.append(child);
  return node;
}

export function button(label, onClick, extra = {}) {
  return el('button', { type: 'button', className: 'art-btn', textContent: label, onclick: onClick, ...extra });
}

export async function callApi(url, opts = {}) {
  const res = await apiFetch(url, opts);
  const body = await res.json().catch(() => ({}));
  return { ok: res.ok, status: res.status, body };
}

export function postJson(url, data) {
  return callApi(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
}

export function errorLines(body, status) {
  const lines = [body.error || `요청 실패 (${status})`];
  for (const issue of body.issues || []) lines.push(`· ${issue}`);
  return lines;
}
