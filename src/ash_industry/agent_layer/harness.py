"""[agent_layer] 세션 이력, 작업 기억 변환, 이벤트 구독을 묶어 한 턴의 에이전트 루프를 돌리는 상태 있는 래퍼."""

import asyncio
from typing import Any
from collections.abc import Awaitable, Callable

from ash_industry.agent_layer.agent_types import AgentContext, AgentEndEvent, AgentEvent, AgentLoopConfig
from ash_industry.model_layer.model_types import AssistantMessage, ModelConfig, Tool, ToolResultMessage
from ash_industry.agent_layer.session.session_protocol import SessionRepo
from ash_industry.agent_layer.loop import AgentEventSink, run_agent_loop
from ash_industry.agent_layer.turn_inbox import QueuedMessage, TurnInbox
from ash_industry.agent_layer.turn_channel import TurnChannel
from ash_industry.memory.memory_service import MemoryService


class AgentHarness:
    """
    Agent 실행의 stateful 래퍼.
    작업 기억 변환, 세션 영속성, 이벤트 구독 관리.
    Pi: AgentHarness 패턴.
    """

    def __init__(
        self,
        model: ModelConfig,
        session_id: str,
        session_repo: SessionRepo,
        memory: MemoryService | None = None,
        system_prompt: str | None = None,
        tools: list[Tool] | None = None,
        loop_config: AgentLoopConfig | None = None,
        agent_name: str | None = None,
        memory_agent: str | None = None,
    ) -> None:
        self._model = model
        self._session_id = session_id
        self._memory = memory
        self._session_repo = session_repo
        self._system_prompt = system_prompt
        self._tools: list[Tool] = tools or []
        self._loop_config = loop_config or AgentLoopConfig()
        self._listeners: list[AgentEventSink] = []
        self._signal = asyncio.Event()
        self._running = False
        self._agent_name: str | None = agent_name
        # 기억을 읽고 쓰는 에이전트 id. 기능 담당 sub-agent 는 부모 에이전트의 기억을 쓴다. None 이면 자기 이름
        self._memory_agent: str | None = memory_agent

    def subscribe(self, listener: AgentEventSink) -> Callable[[], None]:
        self._listeners.append(listener)
        def unsubscribe() -> None:
            self._listeners.remove(listener)
        return unsubscribe

    async def _emit(self, event: AgentEvent) -> None:
        await asyncio.gather(*[fn(event) for fn in self._listeners], return_exceptions=True)

    async def emit_event(self, event: AgentEvent) -> None:
        """루프 외부(예: session의 inner thought)에서 구독자에게 이벤트를 보낸다."""
        await self._emit(event)

    async def run(
        self,
        user_input: str,
        tool_executor: Callable[[str, str, dict[str, Any]], Awaitable[ToolResultMessage]] | None = None,
        extra_context: dict[str, Any] | None = None,
        channel: TurnChannel | None = None,
        inbox: TurnInbox | None = None,
    ) -> AssistantMessage | None:
        """channel 을 주면 이벤트가 그 길로 간다. 턴을 뒤로 넘겼으면(channel.detached) 루프가 만든 메시지를
        대화 기록에 남기지 않고 channel.produced 에 둔다. 넘긴 뒤 이 세션에 다른 턴이 먼저 끝날 수 있어서다."""
        from ash_industry.model_layer.model_types import UserMessage

        self._running = True
        # 프로바이더나 저장소가 던져도 실행 중 표시는 풀린다. 남으면 is_running 이 영원히 True 다
        try:
            self._signal.clear()

            history = await self._session_repo.get_messages(self._session_id)
            new_user_msg = UserMessage(content=user_input)
            history.append(new_user_msg)
            await self._session_repo.append(self._session_id, new_user_msg)
            if channel is not None:
                channel.user_saved.set()

            mem_context: dict[str, Any] = {
                "session_id": self._session_id,
                # 메모리 범위: 어느 에이전트가 읽고 쓰는가. 기능 담당은 부모의 것을 쓴다
                "agent_id": self._memory_agent or self._agent_name or "main",
                **(extra_context or {}),
            }
            messages = await self._memory.observe(history, mem_context) if self._memory else history

            agent_context = AgentContext(
                session_id=self._session_id,
                messages=messages,
                tools=self._tools,
                model=self._model,
                system_prompt=self._system_prompt,
                metadata=extra_context or {},
            )

            n_before = len(agent_context.messages)
            overflows = 0

            async def emit(event: AgentEvent) -> None:
                nonlocal overflows
                if isinstance(event, AgentEndEvent):
                    overflows = event.overflows
                await (channel.emit(event) if channel is not None else self._emit(event))

            result = await run_agent_loop(
                context=agent_context,
                config=self._loop_config,
                emit=emit,
                tool_executor=tool_executor,
                signal=self._signal,
                agent_name=self._agent_name,
                drain_queue=self._drainer(channel, inbox),
            )
            if channel is not None:
                channel.finish()

            # 루프가 쌓은 메시지(assistant tool_use → tool_result → ... → 최종 assistant)를 전부 남긴다.
            # 최종 메시지만 남기면 세션 재개 시 provider가 tool_use/tool_result 짝 불일치로 거부한다.
            produced = agent_context.messages[n_before:]
            if channel is not None and channel.detached:
                channel.produced = produced
            else:
                for msg in produced:
                    await self._session_repo.append(self._session_id, msg)
            if self._memory is not None:
                # 떠올린 기억 중 답에 쓰인 것만 강해진다. 턴 일화의 작업 종류와 성패, 넘침도 여기서 정한다
                calls = [c for m in produced if isinstance(m, AssistantMessage) for c in m.tool_calls()]
                errors = {m.tool_call_id for m in produced if isinstance(m, ToolResultMessage) and m.is_error}
                failed = result is None or result.error_message is not None or bool(errors)
                await self._memory.reinforce(
                    result.text() if result is not None else "", mem_context, tools=[c.name for c in calls],
                    failed=failed, steps=[(c.name, dict(c.arguments)) for c in calls if c.id not in errors],
                    overflow=overflows > 0,
                )

            return result
        finally:
            # 뒤로 넘긴 턴은 detach_foreground 에서 이미 내려놓았다. 그 사이 시작한 다음 턴의 표시를 지우지 않는다
            if channel is None or not channel.detached:
                self._running = False

    @staticmethod
    def _drainer(channel: TurnChannel | None, inbox: TurnInbox | None) -> "Callable[[], list[QueuedMessage]] | None":
        """대화 중인 턴은 세션 대기열에서, 뒤로 넘긴 턴은 그 작업의 대기열에서 꺼낸다.

        뒤로 넘긴 뒤 세션 대기열에 쌓이는 말은 화면에 남은 대화(다음 턴)의 것이라 건드리지 않는다.
        """
        if inbox is None:
            return None

        def drain() -> list[QueuedMessage]:
            if channel is not None and channel.detached:
                return channel.background_inbox.take_all() if channel.background_inbox is not None else []
            return inbox.take_all()

        return drain

    def detach_foreground(self) -> asyncio.Event:
        """도는 턴을 뒤로 넘겼다. 다음 턴이 쓸 중단 신호를 새로 두어, 다음 턴의 중단이 넘긴 턴까지 끊지 않게 한다.

        넘긴 턴이 쥐고 있는 옛 신호를 돌려준다. 그 작업만 멈출 때 쓴다.
        """
        background_signal, self._signal = self._signal, asyncio.Event()
        self._running = False
        return background_signal

    def abort(self) -> None:
        self._signal.set()

    @property
    def is_running(self) -> bool:
        return self._running
