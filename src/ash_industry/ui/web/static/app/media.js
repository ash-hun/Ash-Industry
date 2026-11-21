// 도구가 만든 결과물(영상, 음악, 이미지)을 플레이어 모달로 띄운다. 파일은 /api/creative/files/<상대 경로> 로 받는다.
// 접근 키가 있으면 <video src> 가 헤더를 못 보내므로 apiFetch 로 받아 blob URL 로 재생한다.
import { apiFetch } from './api.js';
import { logActivity } from './shell.js';

const $overlay = document.getElementById('media-overlay');
const $kind = document.getElementById('media-kind');
const $title = document.getElementById('media-title');
const $stage = document.getElementById('media-stage');
const $path = document.getElementById('media-path');
const $open = document.getElementById('media-open');
const $close = document.getElementById('media-close');

const STORE_URL = { creative: '/api/creative/files/' };
const PLAYABLE = new Set(['video', 'audio', 'image']);
let _blobUrl = null;
let _seq = 0;

function fileUrl(artifact) {
  const base = STORE_URL[artifact.store || 'creative'];
  return base ? base + artifact.path.split('/').map(encodeURIComponent).join('/') : null;
}

function clearStage() {
  for (const el of $stage.querySelectorAll('video, audio')) el.pause();
  $stage.replaceChildren();
  if (_blobUrl) { URL.revokeObjectURL(_blobUrl); _blobUrl = null; }
}

export function hideMedia() {
  $overlay.classList.add('hidden');
  clearStage();
}

// 결과물 하나를 모달에. 같은 턴에 여럿이면 영상, 음악, 이미지 순으로 하나만 띄운다
export async function showMedia(artifact) {
  const url = fileUrl(artifact);
  if (!url || !PLAYABLE.has(artifact.kind)) return;
  _lastShown = { path: artifact.path, at: Date.now() };
  const seq = ++_seq;
  $kind.textContent = artifact.kind.toUpperCase();
  $title.textContent = artifact.title || artifact.path;
  $path.textContent = artifact.path;
  $open.href = url;
  clearStage();
  $stage.appendChild(Object.assign(document.createElement('p'), { className: 'media-loading', textContent: '불러오는 중…' }));
  $overlay.classList.remove('hidden');
  let blob;
  try {
    const res = await apiFetch(url);
    if (!res.ok) throw new Error(`${res.status}`);
    blob = await res.blob();
  } catch (e) {
    if (seq !== _seq) return;
    $stage.replaceChildren(Object.assign(document.createElement('p'), { className: 'media-loading', textContent: `파일을 받지 못했어요 (${e.message})` }));
    return;
  }
  if (seq !== _seq) return;
  _blobUrl = URL.createObjectURL(blob);
  const tag = artifact.kind === 'image' ? 'img' : artifact.kind;
  const el = document.createElement(tag);
  el.src = _blobUrl;
  if (tag !== 'img') { el.controls = true; el.autoplay = true; el.playsInline = true; }
  el.className = `media-${artifact.kind}`;
  $stage.replaceChildren(el);
  logActivity(`▶ ${artifact.kind} · ${artifact.title || artifact.path}`, 'ok');
}

// 답 글에 결과 파일 경로(out/…/x.mp4)가 있으면 도구 호출 없이도 띄운다. 모델이 기억으로 답해 첨부가 안 올 때의 길
const REPLY_PATH_RE = /(?:^|[\s`"'(（\[])((?:out|cache|clips|keyframes|music|panels_clean|fx|edit)\/[^\s`"')）\]]+?\.(?:mp4|webm|mov|wav|mp3|m4a|flac|ogg|png|jpe?g|webp|gif))(?=$|[\s`"'.,)）\]])/i;
const REPEAT_MS = 60 * 1000;
let _lastShown = { path: '', at: 0 };

function kindOfPath(path) {
  const ext = path.toLowerCase().split('.').pop();
  if (['mp4', 'webm', 'mov'].includes(ext)) return 'video';
  if (['wav', 'mp3', 'm4a', 'flac', 'ogg'].includes(ext)) return 'audio';
  return 'image';
}

export function mediaPathInText(text) {
  const m = REPLY_PATH_RE.exec(text || '');
  return m ? m[1] : null;
}

export function onReplyText(text) {
  const path = mediaPathInText(text);
  if (!path) return;
  // 같은 파일을 방금 띄웠으면(도구 첨부로) 다시 띄우지 않는다
  if (_lastShown.path === path && Date.now() - _lastShown.at < REPEAT_MS) return;
  showMedia({ kind: kindOfPath(path), path, title: path.split('/').pop(), store: 'creative' });
}

// tool_execution_end 의 artifacts 에서 띄울 것 하나를 고른다
export function onToolArtifacts(artifacts) {
  if (!Array.isArray(artifacts) || !artifacts.length) return;
  const order = ['video', 'audio', 'image'];
  const pick = [...artifacts].sort((a, b) => order.indexOf(a.kind) - order.indexOf(b.kind))[0];
  if (pick && PLAYABLE.has(pick.kind)) showMedia(pick);
}

$close?.addEventListener('click', hideMedia);
$overlay?.addEventListener('click', (e) => { if (e.target === $overlay) hideMedia(); });
document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && !$overlay.classList.contains('hidden')) hideMedia(); });
