"""[app] AppContext: 화면(TUI, Web)이 기동 뒤 붙잡고 쓰는 앱 단위 인프라 묶음."""

from typing import TYPE_CHECKING
from dataclasses import dataclass, field
from collections.abc import Awaitable, Callable

if TYPE_CHECKING:
    from ash_industry.core.proactive.triggers import ActivityClock, ExternalTrigger, ReflectionTrigger
    from ash_industry.core.external import ExternalEventInbox, ExternalEventPoller
    from ash_industry.core.scheduler.scheduler_service import SchedulerService
    from ash_industry.agent_layer.session.session_protocol import SessionRepo
    from ash_industry.core.scheduler.notice_store import PendingNoticeStore
    from ash_industry.core.slash.dispatcher import SlashCommandDispatcher
    from ash_industry.core.workflow.workflow_store import WorkflowStore
    from ash_industry.core.policy.auto_approve import AutoApproveStore
    from ash_industry.core.procedures.learner import ProcedureLearner
    from ash_industry.core.proactive.feedback import FeedbackLearner
    from ash_industry.app.extension_watcher import ExtensionWatcher
    from ash_industry.core.tools.tools_registry import ToolRegistry
    from ash_industry.app.extension_loader import ExtensionCommand
    from ash_industry.memory.memory_service import MemoryService
    from ash_industry.core.notify.webpush import PushStore
    from ash_industry.core.policy.mcp_gate import McpGate
    from ash_industry.core.session import AgentSession
    from ash_industry.ash_config import AshSettings
    from ash_industry.core.notify import Notify


@dataclass
class AppContext:
    """기동 때 한 번 만들고 화면이 끝날 때까지 들고 있는 인프라. 세션마다 달라지는 것은 담지 않는다."""

    session_repo: "SessionRepo"
    tool_registry: "ToolRegistry"
    settings: "AshSettings"
    # Ctrl+N 새 세션, Ctrl+F 분기 팩토리. TUI 진입점이 주입한다
    session_factory: "Callable[[], Awaitable[AgentSession]] | None" = field(default=None)
    branch_factory: "Callable[[str], Awaitable[AgentSession]] | None" = field(default=None)
    scheduler: "SchedulerService | None" = field(default=None)
    dispatcher: "SlashCommandDispatcher | None" = field(default=None)
    # 활동 시계, 성찰 트리거, 피드백 학습기: 앱에 하나
    activity_clock: "ActivityClock | None" = field(default=None)
    reflection_trigger: "ReflectionTrigger | None" = field(default=None)
    # 외부 이벤트로 성찰을 깨우는 트리거. 설정을 고쳐 reflection_trigger 를 다시 만들 때 같이 섞는다
    external_trigger: "ExternalTrigger | None" = field(default=None)
    feedback_learner: "FeedbackLearner | None" = field(default=None)
    # 외부 이벤트 소스가 없으면 둘 다 None
    external_inbox: "ExternalEventInbox | None" = field(default=None)
    external_poller: "ExternalEventPoller | None" = field(default=None)
    # plugin.watch_files 가 꺼져 있거나 지켜볼 디렉터리가 없으면 None
    extension_watcher: "ExtensionWatcher | None" = field(default=None)
    # idle 공고화와 종료 요약이 쓴다
    memory: "MemoryService | None" = field(default=None)
    # 스케줄 결과와 proactive 발화를 받는 외부 채널(슬랙 등). 설정이 없으면 None
    notifier: "Notify | None" = field(default=None)
    # 앱 Web Push 구독 저장소. VAPID 키와 Postgres 가 있을 때만 있다
    push_store: "PushStore | None" = field(default=None)
    # 열린 화면이 없을 때 쌓는 스케줄 알림. 스케줄러가 없으면 None 이고 Web 은 메모리 큐를 대신 쓴다
    notice_store: "PendingNoticeStore | None" = field(default=None)
    # Workflow 화면의 위임 간선과 작업 실행 기록. 설정이 postgres 면 재시작해도 이어진다
    workflow_store: "WorkflowStore | None" = field(default=None)
    # 세션 종료 때 다단계 작업을 절차 초안으로 남긴다. 꺼져 있으면 None
    procedure_learner: "ProcedureLearner | None" = field(default=None)
    # 정의의 tools 에 이름을 적은 에이전트만 쓰는 도구(확장이 등록). 앱 레지스트리에 없어 main 에게는 안 보인다
    agent_tools: "ToolRegistry | None" = field(default=None)
    # 확장이 등록한 슬래시 명령. 디스패처를 만든 뒤 붙인다
    extension_commands: list["ExtensionCommand"] = field(default_factory=list)
    # MCP 도구 정책 문. mcp_servers 가 있을 때만 만든다
    mcp_gate: "McpGate | None" = field(default=None)
    # 에이전트별 auto mode. web 세션의 sandbox 가 매번 읽는다
    auto_approve: "AutoApproveStore | None" = field(default=None)
