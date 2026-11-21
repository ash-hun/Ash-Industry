"""[agent_layer] TurnChannel: 한 턴의 이벤트를 대화 화면으로 보내다가, 턴을 뒤로 넘기면 화면에서 떼어 낸다."""

import asyncio
from collections.abc import Awaitable, Callable

from ash_industry.agent_layer.agent_types import (
    AgentEndEvent,
    AgentEvent,
    AgentStartEvent,
    MessageUpdateEvent,
    QueueDeliveredEvent,
    ToolExecutionEndEvent,
    ToolExecutionStartEvent,
)
from ash_industry.agent_layer.turn_inbox import TurnInbox
from ash_industry.model_layer.model_types import Message

AgentEventSink = Callable[[AgentEvent], Awaitable[None]]
# 선응답을 쓸 작은 모델에 보여 줄 진행 상황의 길이. 길면 선응답이 진행 보고가 된다
PROGRESS_TEXT_CHARS = 300


class TurnChannel:
    """턴 하나의 이벤트 길. 떼어 내기 전에는 대화 화면으로 보내고, 뗀 뒤의 이벤트는 화면에 보내지 않는다.

    떼어 낸 턴의 메시지는 대화 기록에 바로 남기지 않고 produced 에 들고 있다가, 세션이 답과 함께 남긴다.
    """

    def __init__(self, foreground: AgentEventSink) -> None:
        self._foreground = foreground
        self._depth = 0
        self._ended = False
        self.detached = False
        # 지금까지 화면에 흘린 답 글과 부른 도구. 선응답이 "무엇을 하는 중인지" 를 말할 근거다
        self.streamed_text = ""
        self.tools: list[str] = []
        self.produced: list[Message] | None = None
        # 이 턴의 사용자 말이 기록에 남았다. 선응답은 그 뒤에 남아야 기록이 사용자 말, 답 순서가 된다
        self.user_saved = asyncio.Event()
        # 지금 도는 도구 수. 사용자가 지금 보내기를 누르면 도구 실행 중인 턴은 떼어 내고, 글만 쓰는 턴은 멈춘다
        self.tools_running = 0
        # 사용자가 지금 보내기를 눌렀다. 시계를 기다리지 않고 떼어 낸다
        self.detach_requested = asyncio.Event()
        # 뒤로 넘긴 뒤 이 작업에 보낸 말. 대화 중 대기열과 같은 자리(도구 결과 뒤)에서 꺼낸다
        self.background_inbox: TurnInbox | None = None
        # 뒤로 넘긴 뒤에도 화면에 알릴 이벤트(그 작업에 보낸 말을 건넸다). 세션이 별 표시를 고친다
        self.background_sink: AgentEventSink | None = None

    async def emit(self, event: AgentEvent) -> None:
        if isinstance(event, ToolExecutionStartEvent):
            self.tools_running += 1
        elif isinstance(event, ToolExecutionEndEvent):
            self.tools_running = max(0, self.tools_running - 1)
        if isinstance(event, AgentStartEvent):
            self._depth += 1
        elif isinstance(event, AgentEndEvent):
            self._depth -= 1
            # 루트 턴이 끝났다고 화면에 알리는 순간부터는 떼어 낼 수 없다. 같은 턴의 끝이 두 번 가지 않게
            if self._depth == 0:
                self._ended = True
        if self.detached:
            if isinstance(event, QueueDeliveredEvent) and self.background_sink is not None:
                await self.background_sink(event)
            return
        if isinstance(event, MessageUpdateEvent) and event.text_delta:
            self.streamed_text += event.text_delta
        elif isinstance(event, ToolExecutionStartEvent):
            self.tools.append(event.tool_name)
        await self._foreground(event)

    def detach(self) -> bool:
        """떼어 냈으면 True. 이미 뗐거나 턴이 끝났으면 False 이고 아무것도 바꾸지 않는다."""
        if self.detached or self._ended:
            return False
        self.detached = True
        return True

    def request_detach(self) -> None:
        """시계를 기다리지 않고 떼어 내 달라고 TurnDetach 에 알린다. 이미 끝난 턴이면 TurnDetach 가 무시한다."""
        self.detach_requested.set()

    def finish(self) -> None:
        """루프가 돌아왔다. 이 뒤로는 떼어 낼 수 없다."""
        self._ended = True

    def progress(self) -> str:
        """작은 모델에 보여 줄 진행 상황 한 덩이. 부른 도구 이름과 화면에 흘린 글의 앞부분."""
        parts = []
        if self.tools:
            parts.append("부른 도구: " + ", ".join(dict.fromkeys(self.tools)))
        if self.streamed_text.strip():
            parts.append("지금까지 한 말: " + self.streamed_text.strip()[:PROGRESS_TEXT_CHARS])
        return "\n".join(parts)
