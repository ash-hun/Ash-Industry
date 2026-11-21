"""send_now: 루프가 도구 결과 뒤 다음 호출 전에 대기 중인 말을 같은 턴의 사용자 메시지로 붙이는지 검증한다."""

from ash_industry.agent_layer.agent_types import AgentContext, AgentLoopConfig, QueueDeliveredEvent
from tests.fixtures.agent_loop_helpers import ScriptedProvider, register, text_turn, tool_turn
from ash_industry.model_layer.model_types import TextContent, ToolResultMessage, UserMessage
from ash_industry.agent_layer.turn_inbox import QueuedMessage
from ash_industry.agent_layer.loop import run_agent_loop


async def _executor(name, tool_call_id, args):
    return ToolResultMessage(tool_call_id=tool_call_id, tool_name=name, content=[TextContent(text="ok")])


def _context(provider):
    model = register(provider)
    return AgentContext(session_id="s", messages=[UserMessage(content="영상 만들어")], tools=[], model=model)


async def test_queued_message_joins_same_turn_after_tool_result():
    provider = ScriptedProvider([tool_turn(("c1", "render", {})), text_turn("자막 없이 만들었어요")])
    queue = [[QueuedMessage("q1", "자막은 빼줘")]]
    events = []

    async def emit(event):
        events.append(event)

    ctx = _context(provider)
    drain = lambda: queue.pop() if queue else []  # noqa: E731
    result = await run_agent_loop(ctx, AgentLoopConfig(), emit, _executor, drain_queue=drain)

    assert result is not None and result.text() == "자막 없이 만들었어요"
    roles = [type(m).__name__ for m in ctx.messages]
    assert roles == ["UserMessage", "AssistantMessage", "ToolResultMessage", "UserMessage", "AssistantMessage"]
    assert ctx.messages[3].content == "자막은 빼줘"
    assert provider.calls[1].messages[-1].content == "자막은 빼줘"
    delivered = [e for e in events if isinstance(e, QueueDeliveredEvent)]
    assert len(delivered) == 1 and delivered[0].items == [{"id": "q1", "text": "자막은 빼줘"}]


async def test_without_queue_or_tools_nothing_is_added():
    provider = ScriptedProvider([text_turn("바로 답")])
    ctx = _context(provider)

    async def emit(event):
        return None

    await run_agent_loop(ctx, AgentLoopConfig(), emit, _executor, drain_queue=lambda: [QueuedMessage("q", "안 붙음")])
    assert [type(m).__name__ for m in ctx.messages] == ["UserMessage", "AssistantMessage"]
