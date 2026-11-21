"""main 과 Scribe 가 서로 묻고 답하는 대화를 각본대로 흉내 내는 테스트용 프로바이더."""

import json
import asyncio
from collections.abc import AsyncIterator

from ash_industry.model_layer.model_types import (
    LLMContext,
    ModelConfig,
    StopEvent,
    StreamEvent,
    StreamOptions,
    TextDeltaEvent,
    ToolCallDeltaEvent,
    ToolResultMessage,
    Usage,
    UserMessage,
)
from ash_industry.ash_config import BrandConfig

SCRIBE_MARK = "스크라이브"


def _text(message: UserMessage) -> str:
    content = message.content
    return content if isinstance(content, str) else "".join(getattr(c, "text", "") for c in content)


class TeamProvider:
    """시스템 프롬프트에 '스크라이브'가 있으면 Scribe, 없으면 main 으로 행동한다.

    - main 이 "스크라이브에게" 를 받으면 ask_agent(scribe) 를 부른다
    - Scribe 가 main 의 요청을 받으면 사용자 관심 분야를 ask_agent(main) 로 되묻는다
    - main 이 Scribe 의 요청을 받으면 바로 답한다
    - 도구 결과를 받으면 그 결과를 정리해 답한다
    step_delay 만큼 쉬어 두 에이전트가 동시에 일하는 구간을 만든다
    """

    provider_name = "team"

    def __init__(self, step_delay: float = 0.05) -> None:
        self.step_delay = step_delay
        self.calls: list[tuple[str, str]] = []

    def supports_thinking(self) -> bool:
        return False

    def supports_images(self) -> bool:
        return False

    async def stream(
        self, model: ModelConfig, context: LLMContext, options: StreamOptions | None = None
    ) -> AsyncIterator[StreamEvent]:
        await asyncio.sleep(self.step_delay)
        scribe = SCRIBE_MARK in (context.system_prompt or "")
        who = "scribe" if scribe else "main"
        last = context.messages[-1]
        if isinstance(last, ToolResultMessage):
            result = "".join(getattr(c, "text", "") for c in last.content)
            self.calls.append((who, "summarize"))
            yield TextDeltaEvent(delta=f"정리: {result}")
            yield StopEvent(reason="stop", usage=Usage(input=1, output=1))
            return
        text = _text(last) if isinstance(last, UserMessage) else ""
        if not scribe and "스크라이브에게" in text:
            self.calls.append((who, "ask scribe"))
            yield _tool_call("main-ask", "scribe", "AI 뉴스 3개를 찾아 줘")
        elif scribe and text.startswith(f"[{BrandConfig().name}"):
            self.calls.append((who, "ask main back"))
            yield _tool_call("scribe-ask", "main", "사용자가 관심 있는 분야가 뭐야?")
        elif not scribe and text.startswith("[S.C.R.I.B.E."):
            self.calls.append((who, "answer scribe"))
            yield TextDeltaEvent(delta="AI 반도체")
            yield StopEvent(reason="stop", usage=Usage(input=1, output=1))
            return
        else:
            self.calls.append((who, "plain"))
            yield TextDeltaEvent(delta="네")
            yield StopEvent(reason="stop", usage=Usage(input=1, output=1))
            return
        yield StopEvent(reason="tool_use", usage=Usage(input=1, output=1))


def _tool_call(call_id: str, agent: str, message: str) -> ToolCallDeltaEvent:
    return ToolCallDeltaEvent(
        id=call_id, name="ask_agent", arguments_delta=json.dumps({"agent": agent, "message": message})
    )
