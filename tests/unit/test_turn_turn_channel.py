"""turn: TurnChannel 이 떼어 내기 전에는 화면으로 보내고, 뗀 뒤와 턴이 끝난 뒤의 규칙을 지키는지 검증한다."""

from ash_industry.agent_layer.agent_types import (
    AgentEndEvent,
    AgentStartEvent,
    MessageUpdateEvent,
    ToolExecutionEndEvent,
    ToolExecutionStartEvent,
)
from ash_industry.agent_layer.turn_channel import PROGRESS_TEXT_CHARS, TurnChannel


def _channel():
    seen = []

    async def sink(event):
        seen.append(event.type)

    return TurnChannel(sink), seen


async def test_forwards_until_detached_and_records_progress():
    channel, seen = _channel()
    await channel.emit(AgentStartEvent(session_id="s", prompt=""))
    await channel.emit(ToolExecutionStartEvent(tool_call_id="t", tool_name="render_explainer", args={}))
    await channel.emit(MessageUpdateEvent(text_delta="장면을 쓰는 중"))
    assert channel.detach() is True and channel.detach() is False
    await channel.emit(MessageUpdateEvent(text_delta="뗀 뒤의 글"))
    assert seen == ["agent_start", "tool_execution_start", "message_update"]
    assert channel.progress() == "부른 도구: render_explainer\n지금까지 한 말: 장면을 쓰는 중"


async def test_cannot_detach_after_root_end_or_finish():
    channel, _ = _channel()
    await channel.emit(AgentStartEvent(session_id="s", prompt=""))
    await channel.emit(AgentStartEvent(session_id="s", prompt="", agent_name="sub"))
    await channel.emit(AgentEndEvent(session_id="s", agent_name="sub"))
    assert channel.detach() is True  # 하위 에이전트의 끝은 턴의 끝이 아니다

    ended, _ = _channel()
    await ended.emit(AgentStartEvent(session_id="s", prompt=""))
    await ended.emit(AgentEndEvent(session_id="s"))
    assert ended.detach() is False

    finished, _ = _channel()
    finished.finish()
    assert finished.detach() is False


def test_progress_is_empty_without_activity_and_clipped():
    channel, _ = _channel()
    assert channel.progress() == ""
    channel.streamed_text = "가" * (PROGRESS_TEXT_CHARS + 50)
    assert len(channel.progress()) == len("지금까지 한 말: ") + PROGRESS_TEXT_CHARS


async def test_counts_running_tools_even_after_detach():
    channel, _ = _channel()
    await channel.emit(ToolExecutionStartEvent(tool_call_id="t", tool_name="render", args={}))
    assert channel.tools_running == 1
    channel.detach()
    await channel.emit(ToolExecutionEndEvent(tool_call_id="t", tool_name="render", result=None, is_error=False))
    assert channel.tools_running == 0
