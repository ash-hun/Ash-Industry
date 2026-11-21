// 도구가 만든 결과물(영상, 음악, 이미지, 문서 렌더)을 모달로 띄운다. 미디어는 /api/creative/files/, 문서 쪽 그림과
// PDF 는 /api/docs/files/ 로 받는다. 접근 키가 있으면 <video src> 가 헤더를 못 보내므로 apiFetch 로 받아 blob URL 로 쓴다.
import { apiFetch } from './api.js';
import { logActivity } from './shell.js';

const $overlay = document.getElementById('media-overlay');
const $kind = document.getElementById('media-kind');
const $title = document.getElementById('media-title');
const $stage = document.getElementById('media-stage');
const $path = document.getElementById('media-path');
const $open = document.getElementById('media-open');
const $close = document.getElementById('media-close');
const $pager = document.getElementById('media-pager');
const $page = document.getElementById('media-page');
const $prev = document.getElementById('media-prev');
const $next = document.getElementById('media-next');

const STORE_URL = { creative: '/api/creative/files/', docs: '/api/docs/files/' };
const PLAYABLE = new Set(['video', 'audio', 'image', 'document']);
let _blobUrl = null;
let _seq = 0;
let _doc = null;  // 띄운 문서 { title, pages, index }

function fileUrl(store, path) {
  const base = STORE_URL[store || 'creative'];
  return base ? base + path.split('/').map(encodeURIComponent).join('/') : null;
}

function clearStage() {
  for (const el of $stage.querySelectorAll('video, audio')) el.pause();
  $stage.replaceChildren();
  if (_blobUrl) { URL.revokeObjectURL(_blobUrl); _blobUrl = null; }
}

function note(text) {
  return Object.assign(document.createElement('p'), { className: 'media-loading', textContent: text });
}

export function hideMedia() {
  $overlay.classList.add('hidden');
  _doc = null;
  _seq++;
  clearStage();
}

// 파일 하나를 받아 blob URL 로. 그사이 다른 것을 띄웠으면 null
async function loadBlob(url, seq) {
  clearStage();
  $stage.appendChild(note('불러오는 중…'));
  let blob;
  try {
    const res = await apiFetch(url);
    if (!res.ok) throw new Error(`${res.status}`);
    blob = await res.blob();
  } catch (e) {
    if (seq === _seq) $stage.replaceChildren(note(`파일을 받지 못했어요 (${e.message})`));
    return null;
  }
  if (seq !== _seq) return null;
  _blobUrl = URL.createObjectURL(blob);
  return _blobUrl;
}

function openFrame(kind, title, path) {
  $kind.textContent = kind;
  $title.textContent = title || path;
  $path.textContent = path;
  $overlay.classList.remove('hidden');
}

// 결과물 하나를 모달에. 같은 턴에 여럿이면 문서, 영상, 음악, 이미지 순으로 하나만 띄운다
export async function showMedia(artifact) {
  if (!PLAYABLE.has(artifact.kind)) return;
  if (artifact.kind === 'document') { showDocument(artifact); return; }
  const url = fileUrl(artifact.store, artifact.path);
  if (!url) return;
  _lastShown = { path: artifact.path, at: Date.now() };
  _doc = null;
  $pager.classList.add('hidden');
  $stage.classList.remove('doc');
  const seq = ++_seq;
  $open.href = url;
  openFrame(artifact.kind.toUpperCase(), artifact.title, artifact.path);
  const blobUrl = await loadBlob(url, seq);
  if (!blobUrl) return;
  const tag = artifact.kind === 'image' ? 'img' : artifact.kind;
  const el = document.createElement(tag);
  el.src = blobUrl;
  if (tag !== 'img') { el.controls = true; el.autoplay = true; el.playsInline = true; }
  el.className = `media-${artifact.kind}`;
  $stage.replaceChildren(el);
  logActivity(`▶ ${artifact.kind} · ${artifact.title || artifact.path}`, 'ok');
}

// 문서 렌더: 쪽 PNG 여럿은 넘겨 보고, PDF 는 브라우저 뷰어로. 새 탭은 받은 blob 을 연다(접근 키 헤더가 필요 없게)
function showDocument(artifact) {
  const pages = Array.isArray(artifact.pages) && artifact.pages.length ? artifact.pages : [artifact.path];
  _doc = { title: artifact.title || artifact.path, pages, index: 0 };
  $stage.classList.add('doc');
  openFrame('DOC', _doc.title, pages[0]);
  showPage(0);
  logActivity(`▤ 문서 · ${_doc.title} (${pages.length}쪽)`, 'ok');
}

async function showPage(index) {
  if (!_doc) return;
  const { pages } = _doc;
  _doc.index = Math.max(0, Math.min(pages.length - 1, index));
  const path = pages[_doc.index];
  const isPdf = path.toLowerCase().endsWith('.pdf');
  $pager.classList.toggle('hidden', pages.length < 2);
  $page.textContent = `${_doc.index + 1} / ${pages.length}`;
  $prev.disabled = _doc.index === 0;
  $next.disabled = _doc.index === pages.length - 1;
  $path.textContent = path;
  const seq = ++_seq;
  $open.removeAttribute('href');
  const blobUrl = await loadBlob(fileUrl('docs', path), seq);
  if (!blobUrl) return;
  $open.href = blobUrl;
  const el = document.createElement(isPdf ? 'iframe' : 'img');
  el.src = blobUrl;
  el.className = isPdf ? 'media-pdf' : 'media-page';
  if (isPdf) el.title = _doc.title;
  else el.alt = `${_doc.title} ${_doc.index + 1}쪽`;
  $stage.replaceChildren(el);
  $stage.scrollTop = 0;
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
  const order = ['document', 'video', 'audio', 'image'];
  const pick = [...artifacts].sort((a, b) => order.indexOf(a.kind) - order.indexOf(b.kind))[0];
  if (pick && PLAYABLE.has(pick.kind)) showMedia(pick);
}

$close?.addEventListener('click', hideMedia);
$prev?.addEventListener('click', () => showPage((_doc?.index ?? 0) - 1));
$next?.addEventListener('click', () => showPage((_doc?.index ?? 0) + 1));
$overlay?.addEventListener('click', (e) => { if (e.target === $overlay) hideMedia(); });
document.addEventListener('keydown', (e) => {
  if ($overlay.classList.contains('hidden')) return;
  if (e.key === 'Escape') hideMedia();
  // 글 입력 중이 아닐 때만 화살표로 쪽을 넘긴다
  else if (_doc && !e.target.closest?.('input, textarea') && (e.key === 'ArrowLeft' || e.key === 'ArrowRight')) {
    showPage(_doc.index + (e.key === 'ArrowRight' ? 1 : -1));
  }
});
