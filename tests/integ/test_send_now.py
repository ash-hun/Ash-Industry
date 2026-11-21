"""send_now 기능: 일하는 동안 보낸 말은 도구 결과 뒤 같은 턴, 끝나면 다음 턴으로 간다. 지금 보내기와 되가져오기."""

import asyncio
from typing import Any
from collections.abc import AsyncIterator

from ash_industry.model_layer.model_types import LLMContext, ModelConfig, StreamEvent, StreamOptions, TextDeltaEvent
from tests.fixtures.agent_loop_helpers import ScriptedProvider, register, text_turn, tool_turn
from ash_industry.model_layer.model_types import TextContent, ToolResultMessage, UserMessage
from ash_industry.agent_layer.agent_types import QueueChangedEvent, QueueDeliveredEvent
from ash_industry.agent_layer.thought.ack_writer import SEND_NOW_ACK
from ash_industry.core.turn import DetachSettings, TurnDetach
from ash_industry.core.session import AgentSession

SID = "sendnow"


class GatedTool:
    """gate 가 열릴 때까지 도는 도구. 오래 걸리는 렌더를 흉내 낸다."""

    name = "render"
    description = "오래 걸리는 렌더"
    parameters: dict = {"type": "object", "properties": {}}
    execution_mode = "parallel"

    def __init__(self) -> None:
        self.gate = asyncio.Event()
        self.started = asyncio.Event()

    async def execute(self, tool_call_id, params, signal=None):
        self.started.set()
        await self.gate.wait()
        return ToolResultMessage(tool_call_id=tool_call_id, tool_name=self.name, content=[TextContent(text="렌더 끝")])


class SlowTextProvider(ScriptedProvider):
    """첫 호출은 글을 조금 흘린 뒤 gate 가 열리거나 중단될 때까지 멈춘다."""

    def __init__(self, turns: list[list[StreamEvent]]) -> None:
        super().__init__(turns)
        self.gate = asyncio.Event()
        self.streaming = asyncio.Event()

    async def stream(
        self, model: ModelConfig, context: LLMContext, options: StreamOptions | None = None
    ) -> AsyncIterator[StreamEvent]:
        self.calls.append(context)
        index = len(self.calls) - 1
        if index == 0:
            yield TextDeltaEvent(delta="설명을 쓰는 중")
            self.streaming.set()
            await self.gate.wait()
        for event in self._turns[min(index, len(self._turns) - 1)]:
            yield event


def _session(provider: Any, fx: dict[str, Any], tool: Any = None) -> AgentSession:
    if tool is not None:
        fx["tools"].register(tool)
    return AgentSession(
        model=register(provider),
        session_id=SID,
        security_pipeline=fx["pipeline"],
        plugin_runner=fx["plugin_runner"],
        memory=fx["memory"],
        tool_registry=fx["tools"],
        skill_registry=fx["skills"],
        session_repo=fx["repo"],
        turn_detach=TurnDetach(DetachSettings(after_sec=60)),
        new_task_id=lambda: "task-1",
    )


def _fx(permissive_pipeline, plugin_runner, session_memory, tool_registry, skill_registry, jsonl_repo):
    return {"pipeline": permissive_pipeline, "plugin_runner": plugin_runner, "memory": session_memory,
            "tools": tool_registry, "skills": skill_registry, "repo": jsonl_repo}


def _record(session: AgentSession) -> list[Any]:
    events: list[Any] = []

    async def sink(event: Any) -> None:
        events.append(event)

    session.subscribe(sink)
    return events


def _texts(history: list[Any]) -> list[str]:
    return [m.content if isinstance(m, UserMessage) else (m.text() if hasattr(m, "text") else "tool") for m in history]


async def _until(cond) -> None:
    for _ in range(300):
        if cond():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("timed out")


async def test_message_sent_during_tool_joins_same_turn(
    permissive_pipeline, plugin_runner, session_memory, tool_registry, skill_registry, jsonl_repo
) -> None:
    fx = _fx(permissive_pipeline, plugin_runner, session_memory, tool_registry, skill_registry, jsonl_repo)
    await jsonl_repo.create(session_id=SID)
    tool = GatedTool()
    provider = ScriptedProvider([tool_turn(("c1", "render", {})), text_turn("자막 없이 만들었어요")])
    session = _session(provider, fx, tool)
    events = _record(session)

    turn = asyncio.create_task(session.prompt("영상 만들어", detach=True))
    await tool.started.wait()
    assert await session.enqueue("q1", "자막은 빼줘") is True
    assert session.queued() == [{"id": "q1", "text": "자막은 빼줘"}]
    tool.gate.set()
    result = await asyncio.wait_for(turn, 2)

    assert result is not None and result.text() == "자막 없이 만들었어요"
    assert provider.calls[1].messages[-1].content == "자막은 빼줘"
    assert [e.items for e in events if isinstance(e, QueueDeliveredEvent)] == [[{"id": "q1", "text": "자막은 빼줘"}]]
    assert any(isinstance(e, QueueChangedEvent) and e.items for e in events)
    history = await jsonl_repo.get_messages(SID)
    assert _texts(history)[-2:] == ["자막은 빼줘", "자막 없이 만들었어요"]


async def test_idle_session_does_not_queue_and_leftovers_become_next_turn(
    permissive_pipeline, plugin_runner, session_memory, tool_registry, skill_registry, jsonl_repo
) -> None:
    fx = _fx(permissive_pipeline, plugin_runner, session_memory, tool_registry, skill_registry, jsonl_repo)
    await jsonl_repo.create(session_id=SID)
    provider = SlowTextProvider([text_turn(" 끝"), text_turn("1분으로 줄였어요")])
    session = _session(provider, fx)
    assert await session.enqueue("idle", "한가할 때") is False

    turn = asyncio.create_task(session.prompt("설명해줘", detach=True))
    await provider.streaming.wait()
    await session.enqueue("q1", "1분으로 줄여줘")
    provider.gate.set()
    await asyncio.wait_for(turn, 2)
    await _until(lambda: len(provider.calls) >= 2 and not session.is_running)
    await _until(lambda: len(session.queued()) == 0 and not session.is_running)

    history = await jsonl_repo.get_messages(SID)
    assert _texts(history) == ["설명해줘", "설명을 쓰는 중 끝", "1분으로 줄여줘", "1분으로 줄였어요"]


async def test_send_now_during_tool_detaches_and_answers_queued_message(
    permissive_pipeline, plugin_runner, session_memory, tool_registry, skill_registry, jsonl_repo
) -> None:
    fx = _fx(permissive_pipeline, plugin_runner, session_memory, tool_registry, skill_registry, jsonl_repo)
    await jsonl_repo.create(session_id=SID)
    tool = GatedTool()
    provider = ScriptedProvider(
        [tool_turn(("c1", "render", {})), text_turn("지금 날씨는 맑아요"), text_turn("렌더 마쳤어요")]
    )
    session = _session(provider, fx, tool)

    turn = asyncio.create_task(session.prompt("영상 만들어", detach=True))
    await tool.started.wait()
    await session.enqueue("q1", "날씨 알려줘")
    await session.send_now()
    acked = await asyncio.wait_for(turn, 2)
    assert acked is not None and acked.text() == SEND_NOW_ACK
    await _until(lambda: len(provider.calls) >= 2 and not session.is_running)

    history = await jsonl_repo.get_messages(SID)
    assert _texts(history)[:4] == ["영상 만들어", SEND_NOW_ACK, "날씨 알려줘", "지금 날씨는 맑아요"]
    tool.gate.set()


async def test_send_now_while_writing_stops_step_and_take_back_empties_queue(
    permissive_pipeline, plugin_runner, session_memory, tool_registry, skill_registry, jsonl_repo
) -> None:
    fx = _fx(permissive_pipeline, plugin_runner, session_memory, tool_registry, skill_registry, jsonl_repo)
    await jsonl_repo.create(session_id=SID)
    provider = SlowTextProvider([text_turn(" 안 옴"), text_turn("짧게 말할게요")])
    session = _session(provider, fx)

    turn = asyncio.create_task(session.prompt("길게 설명해줘", detach=True))
    await provider.streaming.wait()
    await session.enqueue("q1", "취소")
    assert [i.text for i in await session.take_back()] == ["취소"] and session.queued() == []
    await session.enqueue("q2", "짧게 해줘")
    await session.send_now()
    provider.gate.set()
    await asyncio.wait_for(turn, 2)
    await _until(lambda: len(provider.calls) >= 2 and not session.is_running)

    history = await jsonl_repo.get_messages(SID)
    assert _texts(history)[-2:] == ["짧게 해줘", "짧게 말할게요"]
    assert "취소" not in _texts(history)


class _Router:
    def __init__(self, target: str | None) -> None:
        self.target = target

    async def route(self, message, tasks):
        from ash_industry.agent_layer.thought.steer_router import SteerDecision

        return SteerDecision(self.target, "진행 중인 영상에 반영할게요.") if self.target else SteerDecision(None)


def _detaching_session(provider: Any, fx: dict[str, Any], tool: Any, router: Any) -> AgentSession:
    fx["tools"].register(tool)
    return AgentSession(
        model=register(provider),
        session_id=SID,
        security_pipeline=fx["pipeline"],
        plugin_runner=fx["plugin_runner"],
        memory=fx["memory"],
        tool_registry=fx["tools"],
        skill_registry=fx["skills"],
        session_repo=fx["repo"],
        turn_detach=TurnDetach(DetachSettings(after_sec=0.05, lead_sec=0.02)),
        new_task_id=lambda: "task-1",
        steer_router=router,
    )


async def test_instruction_after_detach_reaches_background_turn(
    permissive_pipeline, plugin_runner, session_memory, tool_registry, skill_registry, jsonl_repo
) -> None:
    from ash_industry.agent_layer.agent_types import BackgroundTaskEvent, ProactiveMessageEvent

    fx = _fx(permissive_pipeline, plugin_runner, session_memory, tool_registry, skill_registry, jsonl_repo)
    await jsonl_repo.create(session_id=SID)
    tool = GatedTool()
    provider = ScriptedProvider([tool_turn(("c1", "render", {})), text_turn("자막 없이 만들었어요")])
    session = _detaching_session(provider, fx, tool, _Router("task-1"))
    events = _record(session)

    await asyncio.wait_for(session.prompt("영상 만들어", detach=True), 2)
    assert session.running_tasks() == ["task-1"]
    assert await session.steer("q1", "자막은 빼야 해") is True
    assert any(isinstance(e, ProactiveMessageEvent) and e.kind == "filler" for e in events)
    tool.gate.set()
    await _until(lambda: any(isinstance(e, BackgroundTaskEvent) and e.state == "finished" for e in events))

    assert provider.calls[1].messages[-1].content == "자막은 빼야 해"
    history = await jsonl_repo.get_messages(SID)
    assert _texts(history)[-2:] == ["자막은 빼야 해", "자막 없이 만들었어요"]
    counts = [(e.pending, e.applied) for e in events if isinstance(e, BackgroundTaskEvent) and e.state == "updated"]
    assert counts == [(1, 0), (0, 1)]


async def test_new_request_while_background_runs_is_not_steered(
    permissive_pipeline, plugin_runner, session_memory, tool_registry, skill_registry, jsonl_repo
) -> None:
    fx = _fx(permissive_pipeline, plugin_runner, session_memory, tool_registry, skill_registry, jsonl_repo)
    await jsonl_repo.create(session_id=SID)
    tool = GatedTool()
    provider = ScriptedProvider([tool_turn(("c1", "render", {})), text_turn("끝")])
    session = _detaching_session(provider, fx, tool, _Router(None))

    await asyncio.wait_for(session.prompt("영상 만들어", detach=True), 2)
    assert await session.steer("q1", "날씨 알려줘") is False
    tool.gate.set()


async def test_stop_background_ends_only_that_task(
    permissive_pipeline, plugin_runner, session_memory, tool_registry, skill_registry, jsonl_repo
) -> None:
    from ash_industry.agent_layer.agent_types import BackgroundTaskEvent

    fx = _fx(permissive_pipeline, plugin_runner, session_memory, tool_registry, skill_registry, jsonl_repo)
    await jsonl_repo.create(session_id=SID)
    tool = GatedTool()
    provider = ScriptedProvider([tool_turn(("c1", "render", {})), text_turn("다음 단계")])
    session = _detaching_session(provider, fx, tool, _Router("task-1"))
    events = _record(session)

    await asyncio.wait_for(session.prompt("영상 만들어", detach=True), 2)
    await session.steer("q1", "자막도 빼고")
    assert await session.stop_background("task-1") is True
    assert await session.stop_background("nope") is False
    tool.gate.set()
    await _until(lambda: any(isinstance(e, BackgroundTaskEvent) and e.state == "finished" for e in events))

    finished = next(e for e in events if isinstance(e, BackgroundTaskEvent) and e.state == "finished")
    assert finished.stopped is True and session.running_tasks() == []
    history = await jsonl_repo.get_messages(SID)
    assert "작업을 멈췄어요." in _texts(history)
    # 멈춘 작업이 읽지 못한 지시는 버리지 않고 대화의 다음 턴이 된다
    await _until(lambda: "자막도 빼고" in [c.messages[-1].content for c in provider.calls if c.messages])
