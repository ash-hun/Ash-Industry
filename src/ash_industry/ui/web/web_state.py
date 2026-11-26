"""[ui] WebState: Web HUD 라우터들이 같이 보는 실행 상태(조립 결과, 세션, 승인 브로커, 열린 연결, 놓친 알림)."""

import time
from pathlib import Path
from datetime import datetime
from typing import TYPE_CHECKING
from collections.abc import Callable

from ash_industry.core.workflow.workflow_tracker import MAX_EDGES, WorkflowTracker
from ash_industry.core.notify.dedupe import SPOKEN_DEDUPE_SEC, RecentOnce
from ash_industry.core.scheduler.notice_store import PendingNoticeStore
from ash_industry.voice.phrases import load_phrase_texts, load_phrases
from ash_industry.voice.english import Translate, make_llm_translator
from ash_industry.core.workflow.workflow_store import WorkflowStore
from ash_industry.ui.web.background_board import BackgroundBoard
from ash_industry.ui.web.session_registry import SessionRegistry
from ash_industry.core.workflow.workflow_types import JobRecord
from ash_industry.core.platform.loop_lag import LoopLagMonitor
from ash_industry.ui.web.agent_activity import AgentActivity
from ash_industry.ui.web.approvals import SessionApprovals
from ash_industry.ui.web.session_relay import SessionRelay
from ash_industry.core.workflow.job_board import JobBoard
from ash_industry.ui.web.turn_replay import TurnReplay
from ash_industry.common.logger import get_logger

if TYPE_CHECKING:
    from ash_industry.core.platform.metrics_service import PlatformMetricsService
    from ash_industry.agent_layer.thought.reply import ReplyClassifier
    from ash_industry.core.focus.focus_service import FocusService
    from ash_industry.ui.web.adapter import PerConnectionAdapter
    from ash_industry.voice.voice_service import VoiceService
    from ash_industry.app.app_assembly import AppAssembly
    from ash_industry.app.app_context import AppContext
    from ash_industry.core.session import AgentSession
    from ash_industry.voice.wake import WakeDetector
    from ash_industry.ash_config import AshSettings

logger = get_logger(__name__)

WORKFLOW_EVENT = "workflow_changed"
JOB_EVENT = "job_changed"


def _now_ms() -> int:
    return int(time.time() * 1000)


async def _focus_outside_ws(_args: str) -> str:
    return "[Focus] Web HUD 에서만 쓸 수 있습니다."


# 승인 대기 목록 전체를 보낸다. 같은 목록이 두 번 와도 화면 결과가 같다
APPROVAL_WAITING_EVENT = "approval_waiting"


class WebState:
    """create_app 이 하나 만들어 모든 라우터에 넘긴다. 연결은 프로세스 메모리에만 있다."""

    def __init__(self, assembly: "AppAssembly") -> None:
        self.assembly = assembly
        # 이 프로세스의 기동 표식. 화면은 재접속 때 값이 바뀌었으면(백엔드 재기동) 새 정적 파일을 받게 새로 고친다
        self.boot_id = int(time.time() * 1000)
        self.registry = SessionRegistry(assembly.ctx, assembly.services, assembly.agents)
        # 세션별 승인 브로커. 같은 세션의 모든 연결이 모달을 받고 먼저 온 답을 쓴다
        self.approvals: dict[str, SessionApprovals] = {}
        self.live_clients: set[PerConnectionAdapter] = set()
        # 열린 HUD 가 없을 때 쌓아 두는 스케줄 알림. 스케줄러가 없으면 메모리 큐(비어 있을 뿐이다)
        self.notices: PendingNoticeStore = assembly.ctx.notice_store or PendingNoticeStore()
        self.voice_service: VoiceService | None = None
        # main 의 한국어 답을 소리로만 영어로 옮긴다. 영어 TTS 가 없으면 옮겨도 main 목소리가 아니라 끈다
        self.translate_english: Translate | None = None
        self.rebuild_voice()
        # 미리 녹음한 읽기 문구. 이름은 connected 로 화면에 알리고 wav 는 /api/voice/phrases 가 내준다
        self.phrases: dict[str, Path] = load_phrases(self.settings.voice.phrases_dir)
        # 화면이 녹음 문구를 재생하면 그 문장을 밖(디스코드 등)에 알린다
        self.phrase_texts: dict[str, str] = load_phrase_texts(self.settings.voice.phrases_dir)
        # 같은 세션을 연 화면들이 읽었다고 알려 온 같은 말은 한 번만 밖에 보낸다. 재시작하면 잊는다
        self.spoken_once = RecentOnce(SPOKEN_DEDUPE_SEC, time.monotonic)
        # 연결마다 웨이크워드 감지기를 하나씩 만든다. 꺼져 있거나 준비가 안 되면 None
        self.wake: Callable[[], WakeDetector] | None = self._build_wake_factory()
        self.focus: FocusService | None = None
        self.rebuild_focus()
        # 🔔 짧은 답과 음성 승인 답 분류기. 사고가 꺼져 있으면 None 이고 화면은 키워드만 쓴다
        self.reply_classifier: ReplyClassifier | None = assembly.profile.reply_classifier()
        # 어느 에이전트가 일하는지. 둘 이상이면 HUD 구체가 색을 섞는다
        self.activity = AgentActivity(self.broadcast_live)
        self.registry.on_open(self.activity.watch)
        # 화면을 옮겨도 놓치면 안 되는 것(결과물, 다른 세션의 먼저 건넨 말과 뒤에서 끝난 답). 열린 HUD 전부에 보낸다
        self.relay = SessionRelay(self.broadcast_live)
        self.registry.on_open(self.relay.watch)
        # 진행 중인 턴. 다른 에이전트로 옮겼다 돌아온 화면이 이것으로 진행 상황을 되살린다
        self.turns = TurnReplay()
        self.registry.on_open(self.turns.watch)
        # Workflow 화면: 에이전트 사이 위임과 백그라운드 작업 실행. 바뀔 때마다 열린 HUD 전부에 보내고 저장소에 적는다
        self.workflow_store: WorkflowStore = assembly.ctx.workflow_store or WorkflowStore()
        self.workflow = WorkflowTracker(_now_ms)
        self.jobs = JobBoard(_now_ms, self._on_job_change)
        # 뒤로 넘긴 턴. FLOW 작업 기록에 남기고, 열린 HUD 는 작업마다 별을 띄운다
        self.background = BackgroundBoard(self.broadcast_live, self.jobs)
        self.registry.on_open(self.background.watch)
        # Ion 가 밖에서 읽는 지표. 루프 지연은 기동 때 재기 시작한다
        self.loop_lag = LoopLagMonitor()
        self.platform_metrics = self._build_platform_metrics()
        self.registry.on_open(self._watch_workflow)
        # 에이전트끼리 묻는 도구가 받는 쪽 세션을 이 화면의 세션 목록에 열게 한다
        from ash_industry.app.agent_conversation import ASK_AGENT_TOOL, AskAgentTool

        ask_tool = assembly.ctx.tool_registry.get(ASK_AGENT_TOOL)
        if isinstance(ask_tool, AskAgentTool):
            ask_tool.set_opener(self.open_peer_session)

    @property
    def ctx(self) -> "AppContext":
        return self.assembly.ctx

    @property
    def settings(self) -> "AshSettings":
        return self.assembly.ctx.settings

    def _build_platform_metrics(self) -> "PlatformMetricsService":
        """에이전트별 작업 지표와 프로세스 지표. 스케줄 작업의 에이전트는 지금 등록된 작업 목록에서 찾는다."""
        from ash_industry.core.platform.metrics_service import PlatformMetricsService, schedule_agent_of

        def agent_of(job_id: str) -> str | None:
            scheduler = self.ctx.scheduler
            tasks = {t.name: t.agent for t in scheduler.list_tasks()} if scheduler is not None else {}
            return schedule_agent_of(tasks)(job_id)

        def scheduled() -> set[str]:
            scheduler = self.ctx.scheduler
            return {t.agent for t in scheduler.list_tasks() if t.enabled} if scheduler is not None else set()

        def names() -> dict[str, str]:
            return {p.agent_id: p.name for p in self.assembly.agents.profiles()}

        def due() -> dict[str, int]:
            # 에이전트마다 켜진 스케줄 중 가장 최근에 지난 예정 시각. 스케줄이 없으면 빠진다
            scheduler = self.ctx.scheduler
            if scheduler is None:
                return {}
            from ash_industry.core.scheduler.scheduler_service import SchedulerService

            now, out = datetime.now(), dict[str, int]()
            for task in scheduler.list_tasks():
                prev = SchedulerService.prev_run(task, now)
                if prev is not None:
                    ms = int(prev.timestamp() * 1000)
                    out[task.agent] = max(out.get(task.agent, ms), ms)
            return out

        return PlatformMetricsService(
            records=self.jobs.records,
            agent_of=agent_of,
            agents=self.assembly.agents.ids,
            sessions=self.registry.session_agents,
            scheduled=scheduled,
            names=names,
            due=due,
            loop_lag=self.loop_lag,
        )

    async def last_active(self) -> dict[str, int]:
        """에이전트별 마지막 세션 갱신 시각(epoch ms). Ion 의 상태 화면이 보여 준다. 저장소가 없으면 빈 것."""
        try:
            metas = await self.ctx.session_repo.list()
        except Exception:  # 세션 저장소가 잠시 못 답해도 지표는 낸다
            return {}
        latest: dict[str, int] = {}
        for m in metas:
            if m.updated_at > latest.get(m.agent_id, 0):
                latest[m.agent_id] = m.updated_at
        return latest

    def rebuild_voice(self) -> None:
        """음성 설정대로 프로바이더와 영어 번역기를 (다시) 만든다. 설정 화면이 고친 뒤에도 부른다.

        whisper 는 만들 때 모델을 적재하므로 기동 뒤에는 스레드에서 부른다. 열린 연결은 다음 접속부터 새것을 쓴다.
        """
        self.voice_service = self._build_voice_service()
        self.translate_english = None
        if self.settings.voice.speak_english and self.voice_service is not None and self.voice_service.has_english_tts:
            self.translate_english = make_llm_translator(
                self.assembly.services.model_config, self.settings.voice.english_style
            )

    def rebuild_focus(self) -> None:
        """focus.enabled 대로 서비스를 만들거나 내려놓는다. 끌 때 진행 중인 작업은 들고 있는 쪽이 끝까지 돌린다."""
        self.focus = self._build_focus_service()
        dispatcher = self.assembly.ctx.dispatcher
        if self.focus is not None and dispatcher is not None:
            # 실행은 ws 가 디스패처보다 먼저 가로챈다. 여기 등록은 입력창의 명령 목록에 보이게 하려는 것(덮어써서 멱등)
            dispatcher.register("focus", _focus_outside_ws, "<작업> Focus 모드 시작 | stop 종료 | 현황")

    def _build_focus_service(self) -> "FocusService | None":
        """Focus 모드 서비스. 시각과 작업 id 는 여기(경계)에서 만들어 넣는다."""
        cfg = self.settings.focus
        if not cfg.enabled:
            return None
        import uuid
        from datetime import datetime

        from ash_industry.core.multi_agent.factory import AgentDefinition, AgentMemoryPolicy
        from ash_industry.core.focus.prompts import REFERENCE_TOOLS, SYSTEM_PROMPTS
        from ash_industry.core.focus.focus_service import FocusService
        from ash_industry.app.subagent_builder import SubagentBuilder
        from ash_industry.core.focus.focus_store import FocusStore

        ctx, services = self.assembly.ctx, self.assembly.services
        builder = SubagentBuilder(ctx, services, ctx.tool_registry)

        async def make_agent(role: str, session_id: str) -> "AgentSession":
            definition = AgentDefinition(
                name=f"focus-{role}",
                description=f"Focus 모드 {role} 담당",
                system_prompt=SYSTEM_PROMPTS[role],
                tools=REFERENCE_TOOLS if role == "reference" else [],
                tools_only=True,
                model_override=cfg.model or None,
                # 영역 일꾼은 요청에 든 작업과 지시만 본다. 장기 기억의 사용자 프로필이 짧은 지시를 엉뚱한 쪽으로 끌었다
                memory=AgentMemoryPolicy(ltm=False),
            )
            await ctx.session_repo.create(session_id=session_id)
            return builder.build_session(definition, session_id)

        return FocusService(
            store=FocusStore(cfg.dir),
            make_agent=make_agent,
            clock=time.time,
            new_id=lambda: f"{datetime.now():%Y%m%d}-{uuid.uuid4().hex[:6]}",
            ready_timeout_sec=cfg.ready_timeout_sec,
        )

    def _build_voice_service(self) -> "VoiceService | None":
        """음성 프로바이더를 설정대로 만든다. 선택 의존성이 없으면 None(브라우저 음성만)."""
        try:
            from ash_industry.voice.voice_service import VoiceService

            v = self.settings.voice
            return VoiceService.from_config(
                stt_provider=v.stt_provider,
                tts_provider=v.tts_provider,
                stt_options=v.stt_options(),
                tts_options=v.tts_options(),
                english_tts_provider=v.english_tts_provider,
                english_tts_options=v.english_tts_options(),
                stt_fallback=v.stt_fallback,
                stt_fallback_options=v.stt_fallback_options(),
            )
        except Exception as exc:
            logger.warning(f"[Voice] 서버 음성 비활성화, 브라우저 음성만 쓴다 (초기화 실패): {exc}")
            return None

    def _build_wake_factory(self) -> "Callable[[], WakeDetector] | None":
        """설정과 모델 파일, 선택 의존성을 기동 때 한 번 확인한다. 하나라도 없으면 웨이크워드를 끈다."""
        v = self.settings.voice
        if not v.wake_model_dir:
            return None
        from ash_industry.voice.wake import WakeDetector, missing_wake_files, openwakeword_scorer

        missing = missing_wake_files(v.wake_model_dir, v.wake_model_file)
        try:
            import openwakeword  # noqa: F401
        except ImportError:
            missing.append("openwakeword(uv sync --extra wake)")
        if missing:
            logger.warning(f"[Voice] 웨이크워드 비활성화, 없는 것: {', '.join(missing)}")
            return None
        return lambda: WakeDetector(openwakeword_scorer(v.wake_model_dir, v.wake_model_file), v.wake_threshold)

    def broker(self, session_id: str) -> SessionApprovals:
        """세션의 승인 브로커. 없으면 만든다."""
        broker = self.approvals.get(session_id)
        if broker is None:
            async def on_waiting(_count: int) -> None:
                await self.broadcast_live({"type": APPROVAL_WAITING_EVENT, "waiting": self.waiting_approvals()})

            broker = self.approvals[session_id] = SessionApprovals(on_waiting=on_waiting)
        return broker

    def waiting_approvals(self) -> list[dict[str, object]]:
        """승인을 기다리는 세션과 그 에이전트. 다른 세션을 보는 화면이 이것으로 알림을 띄운다."""
        return [
            {"session_id": sid, "agent": self.registry.agent_of(sid), "count": len(broker.pending_ids)}
            for sid, broker in self.approvals.items() if broker.pending_ids
        ]

    async def open_peer_session(
        self, agent_id: str, session_id: str, caller_session_id: str | None
    ) -> "AgentSession":
        """다른 에이전트가 부른 대화 세션. 받는 쪽 도구의 승인 요청은 부른 세션의 화면으로 보낸다."""
        session, sandbox = await self.registry.get_or_create(session_id, agent_id, peer=True)
        if caller_session_id is not None:
            sandbox.set_approval_callback(self.broker(caller_session_id).request)
        return session

    async def converse(self, agent_id: str, text: str) -> bool:
        """스케줄 결과를 그 에이전트와 최근 대화한 세션에 에이전트의 말로 건넨다. 건넸으면 True.

        열린 대화가 없어도(재시작 뒤, 한동안 말이 없을 때) 저장된 마지막 대화에 건넨다.
        알림 제목 대신 에이전트의 말로 온다.
        """
        session = await self.registry.conversation_of(agent_id)
        return await session.say(text)

    def _watch_workflow(self, session_id: str, agent_id: str, session: "AgentSession") -> None:
        async def on_event(event: object) -> None:
            edge = self.workflow.observe(session_id, agent_id, event)
            if edge is None:
                return
            await self.broadcast_live({"type": WORKFLOW_EVENT, "edge": edge.to_dict()})
            try:
                await self.workflow_store.save_edge(edge)
            except Exception as exc:  # 저장소가 못 받아도 위임은 계속된다
                logger.info(f"[Workflow] edge not saved: {exc!r}")

        session.subscribe(on_event)

    async def _on_job_change(self, record: JobRecord) -> None:
        await self.broadcast_live({"type": JOB_EVENT, "job": record.to_dict()})
        await self.workflow_store.save_job(record)  # JobBoard 가 예외를 삼켜 작업은 계속된다

    async def restore_workflow(self) -> None:
        """저장소의 최근 위임과 작업 기록을 되살린다. 기동 때 한 번, 저장소가 못 답하면 빈 채로 간다."""
        try:
            self.workflow.load(await self.workflow_store.recent_edges(MAX_EDGES))
            self.jobs.load(await self.workflow_store.jobs())
        except Exception as exc:
            logger.warning(f"[Workflow] history not restored: {exc!r}")

    async def broadcast_live(self, payload: dict[str, object]) -> None:
        """열린 HUD 에만 보낸다. 지금 상태를 알리는 것이라 아무도 없으면 버린다."""
        for adapter in list(self.live_clients):
            await adapter.send(payload)

    async def broadcast_notice(self, payload: dict[str, object]) -> None:
        """스케줄 실행 결과를 열린 HUD 전부에 보낸다. 열린 HUD 가 없으면 다음 접속 때 missed 로 보낸다."""
        if not self.live_clients:
            await self.notices.push(payload)
            return
        for adapter in list(self.live_clients):
            await adapter.send(payload)
