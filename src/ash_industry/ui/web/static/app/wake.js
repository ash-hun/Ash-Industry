// 웨이크워드 — 모드와 상관없이 기다리는 동안 마이크를 16kHz PCM 으로 서버에 흘리고, voice_wake 가 오면 듣기를 연다.
import { sendBinary } from './ws.js';
import { logActivity, SYSTEM } from './shell.js';
import { isAgentBusy } from './events.js';
import { isApprovalOpen } from './approval.js';
import { voice, isSpeechActive, cue } from './voice-ui.js';

const SAMPLE_RATE = 16000;
const WORKLET_URL = 'wake-worklet.js';

// 주변 대화로 판정된 녹음이 이어지면(회의) 웨이크워드를 쉰다. 한 번에 2분, 거듭되면 두 배씩, 최대 15분.
// 진짜 요청이 한 번 들어오면 바로 푼다
const AMBIENT_BACKOFF_MS = 2 * 60 * 1000;
const AMBIENT_BACKOFF_MAX_MS = 15 * 60 * 1000;

let _enabled = false;  // 서버가 connected.voice.wake 로 알려 준다
let _ctx = null;
let _stream = null;
let _node = null;
let _ambientStreak = 0;
let _restUntil = 0;    // 이 시각(performance.now)까지는 웨이크워드를 듣지 않는다

// 듣기, 읽기, 응답, 승인 중과 주변 대화 뒤 쉬는 동안에는 보내지 않는다. 그동안의 웨이크워드는 대화의 일부다
function waiting() {
  return _enabled && voice.state === 'idle' && !isSpeechActive() && !isAgentBusy() && !isApprovalOpen()
    && performance.now() >= _restUntil;
}

export function restAfterAmbient() {
  _ambientStreak += 1;
  const ms = Math.min(AMBIENT_BACKOFF_MAX_MS, AMBIENT_BACKOFF_MS * 2 ** (_ambientStreak - 1));
  _restUntil = performance.now() + ms;
  logActivity(`◉ wake · 주변 대화가 이어져 ${Math.round(ms / 60000)}분 쉼`, 'sys', SYSTEM);
}

export function resumeWake() {
  _ambientStreak = 0;
  _restUntil = 0;
}

document.addEventListener('voice:ambient', restAfterAmbient);
document.addEventListener('voice:heard', resumeWake);

// 자동 재생 정책에 걸려 멈춘 컨텍스트는 다음 클릭이나 키 입력에서 깨운다
function resumeOnGesture(ctx) {
  const resume = () => { if (_ctx === ctx) ctx.resume(); };
  document.addEventListener('pointerdown', resume, { once: true });
  document.addEventListener('keydown', resume, { once: true });
}

async function startCapture() {
  if (_ctx || !_enabled || !navigator.mediaDevices?.getUserMedia) return;
  const ctx = new AudioContext({ sampleRate: SAMPLE_RATE });
  _ctx = ctx;
  try {
    await ctx.audioWorklet.addModule(WORKLET_URL);
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
    });
    if (_ctx !== ctx) { stream.getTracks().forEach((t) => t.stop()); return; }  // 기다리는 사이 껐다
    _stream = stream;
    _node = new AudioWorkletNode(ctx, 'wake-capture');
    _node.port.onmessage = (e) => { if (waiting()) sendBinary(e.data); };
    ctx.createMediaStreamSource(stream).connect(_node);
    if (ctx.state === 'suspended') resumeOnGesture(ctx);
  } catch (e) {
    stopCapture();
    logActivity(`wake word off · ${e.message}`, 'err', SYSTEM);
  }
}

function stopCapture() {
  if (_node) _node.port.onmessage = null;
  _node = null;
  if (_stream) _stream.getTracks().forEach((t) => t.stop());
  _stream = null;
  if (_ctx) _ctx.close().catch(() => {});
  _ctx = null;
}

// 접속마다 서버가 알려 준다. 몇 번 불러도 같은 상태로 맞춘다
export function setWakeEnabled(on) {
  _enabled = !!on;
  if (_enabled) startCapture();
  else stopCapture();
}

// 웨이크워드를 들으면 대답 문구를 읽고 듣기를 연다. 그사이 다른 일이 시작됐으면 듣지 않는다.
// Default 에서 깨운 요청은 음성으로 시작한 요청이라 응답을 읽어 주고, 다 읽은 뒤 다시 듣지는 않는다
export async function onWake() {
  if (!waiting()) return;
  logActivity('◉ wake', '', SYSTEM);
  await cue('wake_up', { always: true });
  if (waiting()) voice.start();
}
