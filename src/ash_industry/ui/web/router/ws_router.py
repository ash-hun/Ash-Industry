"""[ui] /ws 라우트: 연결 하나의 수명(인증, connected 핸드셰이크, 메시지 분기, 정리)을 맡는다."""

import re
import json
import uuid
import asyncio
from typing import Any
from pathlib import Path
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from ash_industry.ui.web.ws_tasks import (
    first_feedback,
    notify_quietly,
    run_focus,
    run_prompt,
    run_reply_classify,
    run_stt,
    run_tts,
)
from ash_industry.app.upload_store import Upload, UploadStore, describe
from ash_industry.core.notify import spoken_notice_text, spoken_payload
from ash_industry.ui.web.web_auth import auth_enabled, lookup_api_user
from ash_industry.ui.web.router.agent_router import agent_summary
from ash_industry.core.focus.focus_types import parse_command
from ash_industry.memory.scope import LOCAL_USER, MemoryScope
from ash_industry.model_layer.model_types import ImageContent
from ash_industry.ui.web.session_registry import UnknownAgent
from ash_industry.voice.english import should_speak_english
from ash_industry.voice.speech_text import speech_text
from ash_industry.ui.web.web_state import WebState
from ash_industry.common.logger import get_logger
from ash_industry.voice.wake import WakeDetector

# 키 불일치로 서버가 끊을 때의 close code. 브라우저가 이 코드를 보고 키 입력을 띄운다
# 메시지 하나에 붙이는 첨부 수 상한
MAX_ATTACHMENTS = 10
WS_UNAUTHORIZED = 4401
# 정의에 없는 에이전트로 새 세션을 열려 할 때. 브라우저는 재연결하지 않고 오류를 보인다
WS_UNKNOWN_AGENT = 4404
DEFAULT_STT_SAMPLE_RATE = 16000
# 화면이 붙이는 대기 말 id. 형식이 다르면 서버가 새로 만든다
QUEUE_ID = re.compile(r"^[A-Za-z0-9-]{1,64}$")


def queue_id_of(raw: object, new_id: Any = None) -> str:
    """화면이 보낸 id 가 형식에 맞으면 그대로, 아니면 새 id. 같은 id 로 두 번 보내도 대기열에는 한 번만 담긴다."""
    if isinstance(raw, str) and QUEUE_ID.match(raw):
        return raw
    return (new_id or (lambda: uuid.uuid4().hex))()

logger = get_logger(__name__)


async def receive_frame(ws: WebSocket) -> dict[str, Any] | bytes:
    """텍스트 프레임은 JSON 메시지로, 바이너리 프레임은 웨이크워드용 PCM 으로 돌려준다. 끊기면 WebSocketDisconnect."""
    message = await ws.receive()
    if message["type"] == "websocket.disconnect":
        raise WebSocketDisconnect(message.get("code", 1000))
    data = message.get("bytes")
    if data is not None:
        return bytes(data)
    parsed: dict[str, Any] = json.loads(message.get("text") or "{}")
    return parsed


def attachments_of(store: UploadStore, raw: Any) -> list[Upload]:
    """ws 가 보낸 첨부 id 중 실제로 올라온 것만. 모르는 id 는 버린다(최대 10개)."""
    ids = raw if isinstance(raw, list) else []
    found = [store.find(str(i)) for i in ids[:MAX_ATTACHMENTS]]
    return list({u.id: u for u in found if u is not None}.values())


def images_of(store: UploadStore, uploads: list[Upload]) -> list[ImageContent]:
    images = []
    for upload in uploads:
        data = store.image_base64(upload)
        if data is not None:
            images.append(ImageContent(data=data, mime_type=upload.mime))
    return images


def build_ws_router(state: WebState) -> APIRouter:
    router = APIRouter()
    ctx = state.ctx
    settings = state.settings
    uploads = UploadStore(Path(settings.docs.dir))

    @router.websocket("/ws")
    async def websocket_endpoint(
        ws: WebSocket,
        session_id: str = Query(default="default", description="붙을 세션 id. 없으면 만든다"),
        token: str | None = Query(default=None, description="접근 키. 인증이 켜져 있을 때만 필요"),
        agent: str | None = Query(
            default=None, description="새 세션을 맡을 에이전트 id. 이미 있는 세션은 저장된 에이전트로 열린다"
        ),
    ) -> None:
        from ash_industry.ui.web.adapter import PerConnectionAdapter
        from ash_industry.ash_config import ApiUser

        # accept 뒤에 닫아야 브라우저가 close code(4401)를 읽을 수 있다. accept 전에 닫으면 403 으로만 보인다
        await ws.accept()
        user: ApiUser | None = None
        if auth_enabled(settings):
            user = lookup_api_user(settings, token)
            if user is None:
                await ws.close(code=WS_UNAUTHORIZED, reason="invalid token")
                return
        credentials = {"api_key": token} if user is not None and token is not None else {}
        try:
            session, sandbox = await state.registry.get_or_create(session_id, agent)
        except UnknownAgent as exc:
            await ws.close(code=WS_UNKNOWN_AGENT, reason=f"unknown agent: {exc}")
            return
        agent_id = state.registry.agent_of(session_id)
        profile = state.assembly.agents.builder(agent_id).profile

        adapter = PerConnectionAdapter(ws)
        broker = state.broker(session_id)
        # get_or_create 와 attach 사이에 await 를 두지 않는다. 그 틈에 세션 삭제가 연결 0개로 보고 지운다
        await broker.attach(adapter)
        sandbox.set_approval_callback(broker.request)
        unsubscribe = session.subscribe(adapter.on_agent_event)
        # 구독과 같은 자리(사이에 await 없음)에서 떠야 재생과 라이브 이벤트가 겹치지 않는다
        in_flight = state.turns.snapshot(session_id) if session.is_running else []
        # 같은 🔔 에 피드백이 두 번 와도(재전송, 키워드와 분류가 겹침) 학습은 한 번만
        feedback_ids: set[str] = set()
        voice_service = state.voice_service
        # 웨이크워드 감지기는 첫 오디오가 올 때 만든다. 만들다 실패하면 이 연결에서는 다시 시도하지 않는다
        wake_detector: WakeDetector | None = None
        wake_on = state.wake is not None

        def notify_spoken(payload: dict[str, Any] | None) -> None:
            # 같은 세션을 연 화면마다 같은 말을 읽어 알려 온다. 밖으로는 첫 번째만 보낸다
            if payload is not None and state.spoken_once.first((session_id, payload["text"])):
                asyncio.create_task(notify_quietly(ctx.notifier, payload))

        try:
            stt_browser = voice_service is None or voice_service.stt_is_browser
            await ws.send_json({
                "type": "connected",
                "boot_id": state.boot_id,
                "session_id": session._session_id,
                "agent": agent_summary(profile),
                "user": user.name if user is not None else None,
                "model": session._harness._model.model,
                "sessions": state.registry.list_ids(),
                "session_agents": state.registry.session_agents(),
                "active_agents": state.activity.active(),
                "slash_commands": [
                    {"name": name, "description": desc} for name, desc in sorted(ctx.dispatcher.commands.items())
                ] if ctx.dispatcher else [],
                "voice": {
                    # server: 브라우저가 녹음해 백엔드 STT 로 보낸다. browser: Web Speech API 가 인식까지
                    "stt_mode": "browser" if stt_browser else "server",
                    # browser 일 때 인식이 실패하면 화면이 녹음해 보내도 되는지(서버 폴백 STT 가 있는지)
                    "server_stt": voice_service is not None and voice_service.server_stt_available,
                    "stt_lang": settings.voice.stt_lang,
                    # 미리 녹음한 문구 이름. 화면은 이 이름만 /api/voice/phrases/{name} 으로 받는다
                    "phrases": sorted(state.phrases),
                    # true 면 대기 중에 16kHz PCM 을 바이너리 프레임으로 보내고 voice_wake 를 기다린다
                    "wake": wake_on,
                },
                "reply_classifier": state.reply_classifier is not None,
                # 진행 중인 턴의 이벤트. 다른 에이전트로 옮겼다 돌아온 화면이 이력 뒤에 다시 그린다
                "in_flight": in_flight,
                "approval_waiting": state.waiting_approvals(),
                # 일하는 동안 보낸 말의 대기열. 화면은 대화 아래 회색으로 보인다
                "queued": session.queued(),
                # 뒤에서 도는 턴. 화면은 작업마다 별을 띄운다(background_tasks 와 같은 모양)
                "background_tasks": state.background.running(),
            })

            # 스케줄 알림 방송 대상에 넣고, 아무도 없을 때 쌓인 알림을 먼저 보낸다
            state.live_clients.add(adapter)
            for missed in await state.notices.drain():
                await adapter.send({**missed, "missed": True})

            # 진행 중인 Focus 작업이 있으면(재시작 뒤 포함) 화면을 Focus 로 되살린다
            if state.focus is not None:
                run = await state.focus.restore(session)
                for event in run.panel_events() if run is not None else []:
                    await adapter.on_agent_event(event)

            while True:
                frame = await receive_frame(ws)
                if isinstance(frame, bytes):
                    if not wake_on or state.wake is None:
                        continue
                    if wake_detector is None:
                        try:
                            wake_detector = await asyncio.to_thread(state.wake)
                        except Exception as exc:
                            logger.warning(f"[Voice] 웨이크워드 감지기 생성 실패, 이 연결에서 끈다: {exc}")
                            wake_on = False
                            continue
                    score = wake_detector.feed(frame)
                    if score is not None:
                        # 화면이 "Yes, sir?" 를 못 읽었을 때 감지는 됐는지 가르려고 남긴다
                        logger.info(f"[Voice] wake detected score={score:.3f} session={session_id}")
                        await ws.send_json({"type": "voice_wake", "score": round(score, 3)})
                    continue
                msg = frame
                msg_type = msg.get("type", "")

                if msg_type == "user_message":
                    text = msg.get("text", "").strip()
                    attached = attachments_of(uploads, msg.get("attachments"))
                    if text or attached:
                        state.registry.touch(session_id)
                        focus_command = parse_command(text) if state.focus is not None and text else None
                        if state.focus is not None and focus_command is not None:
                            asyncio.create_task(
                                run_focus(session, adapter, state.focus, focus_command, credentials)
                            )
                            continue
                        # 슬래시 명령 인터셉트: 텍스트 어디서나 /command 를 처리하고 나머지만 LLM 으로 보낸다
                        if ctx.dispatcher is not None and text:
                            # /remember 같은 명령이 이 연결의 사용자 범위로 기억을 쓰게 한다
                            scope = MemoryScope(
                                user_id=user.name if user is not None else LOCAL_USER,
                                agent_id=agent_id,
                                session_id=session_id,
                            )
                            result = await ctx.dispatcher.dispatch(text, scope)
                            for feedback in result.feedbacks:
                                await ws.send_json({"type": "agent_start"})
                                await ws.send_json({"type": "stream_delta", "text": feedback})
                                await ws.send_json({"type": "agent_end"})
                            if result.fully_consumed:
                                continue
                            text = result.remaining_text
                        if attached:
                            # 에이전트가 경로로 파일을 열도록 메시지 끝에 붙인다. 기록에도 이 글이 남는다
                            text = f"{text.strip()}\n\n{describe(attached)}".strip()
                        if text.strip():
                            # 답하는 중이면 대기열로. 도구 결과 뒤에 같은 턴으로, 아니면 턴이 끝난 뒤 다음 턴으로 간다
                            message_id = queue_id_of(msg.get("id"))
                            if await session.enqueue(message_id, text, credentials):
                                continue
                            # 대화는 한가한데 뒤에서 작업이 돈다. 그 작업에 대한 지시면 그 작업으로 보낸다
                            if await session.steer(message_id, text):
                                continue
                            # 화면은 답하는 중이라 보고 대기 말로 보냈는데 그 사이 턴이 끝났다. 대화에 붙이라고 알린다
                            if msg.get("queued"):
                                await adapter.send({
                                    "type": "queue_delivered", "session_id": session_id,
                                    "items": [{"id": message_id, "text": text}],
                                })
                            # ponytail: 대기열과 steer 로 간 말은 첨부 안내 글만 가고 그림은 빠진다,
                            # 답하는 중에 이미지를 자주 보내면 대기열 항목에 그림을 싣는다
                            images = images_of(uploads, attached)
                            asyncio.create_task(run_prompt(session, adapter, text, credentials, images))

                elif msg_type == "approval_response":
                    broker.resolve(
                        approval_id=msg.get("id", ""),
                        approved=bool(msg.get("approved", False)),
                        always=bool(msg.get("always", False)),
                    )

                elif msg_type == "proactive_feedback":
                    # 🔔 수락/무시 → 피드백 학습기
                    if first_feedback(feedback_ids, msg.get("id")):
                        await session.record_feedback(bool(msg.get("accepted", False)))

                elif msg_type == "reply_classify":
                    asyncio.create_task(run_reply_classify(ws, state.reply_classifier, session, feedback_ids, msg))

                elif msg_type == "voice_tts_request":
                    text = speech_text(msg.get("text", ""))
                    lang = msg.get("lang", settings.voice.tts_lang)
                    # 화면이 소리 내어 읽는 말을 같은 글로 밖에도 알린다. 🔔 과 ⏰ 은 서버가 이미 보냈다
                    # 화면이 문장 조각으로 나눠 보내면 첫 조각에서 원문 전체로 한 번만
                    notice = spoken_notice_text(text, msg.get("part"), speech_text(msg.get("full_text") or ""))
                    notify_spoken(spoken_payload(notice, agent_id, str(msg.get("source") or "")))
                    # 화면이 멈춘 읽기의 늦은 응답을 버릴 수 있게 요청 id 를 그대로 돌려준다
                    request_id = msg.get("id")
                    if text and voice_service:
                        translate = state.translate_english if should_speak_english(text, agent_id) else None
                        stream = bool(msg.get("stream"))
                        fallback = settings.voice.english_fallback
                        asyncio.create_task(
                            run_tts(ws, voice_service, text, lang, request_id, translate, stream, fallback)
                        )
                    else:
                        # 음성 서비스가 없거나 읽을 글자가 없어도 답한다. 안 주면 HUD 가 '음성 처리 중' 에 멈춘다
                        await ws.send_json({"type": "voice_tts_audio", "data": "", "text": text, "id": request_id})

                elif msg_type == "voice_spoken":
                    # 녹음 문구는 화면이 바로 재생한다. 재생했다고 알려 오면 그 문장을 밖에 알린다
                    phrase = state.phrase_texts.get(str(msg.get("phrase") or ""), "")
                    notify_spoken(spoken_payload(phrase, agent_id, "phrase"))

                elif msg_type == "voice_stt_submit":
                    data = msg.get("data", "")
                    sample_rate = int(msg.get("sample_rate", DEFAULT_STT_SAMPLE_RATE))
                    if data and voice_service:
                        v = state.settings.voice
                        asyncio.create_task(run_stt(
                            ws, voice_service, data, sample_rate, agent_id,
                            command_max_sec=v.command_max_sec, command_max_chars=v.command_max_chars,
                            unclear_main=v.english_unclear,
                        ))

                elif msg_type == "abort":
                    session.abort()

                elif msg_type == "send_now":
                    await session.send_now()

                elif msg_type == "background_stop":
                    # 별에서 누른 작업 멈추기. 다른 세션의 작업일 수 있어 그 세션을 찾는다
                    target_sid, task_id = str(msg.get("session_id") or session_id), str(msg.get("task_id") or "")
                    if QUEUE_ID.match(task_id) and target_sid in state.registry.list_ids():
                        target, _ = await state.registry.get_or_create(target_sid)
                        await target.stop_background(task_id)

                elif msg_type == "queue_take":
                    # 되가져온 말은 이 화면의 입력창으로만. 대기열이 빈 것은 queue_changed 로 모든 화면이 안다
                    taken = await session.take_back()
                    await ws.send_json({"type": "queue_taken", "items": [item.to_dict() for item in taken]})

        except WebSocketDisconnect:
            pass
        finally:
            state.live_clients.discard(adapter)
            broker.detach(adapter)
            unsubscribe()

    return router
