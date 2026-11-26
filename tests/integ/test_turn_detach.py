"""turn_detach 기능: 오래 걸리는 턴은 선응답으로 닫히고, 그동안 다음 말을 받고, 끝난 답이 기록과 화면에 온다."""

import asyncio
import threading
from typing import Any
from collections.abc import AsyncIterator

from ash_industry.agent_layer.agent_types import AgentEndEvent, BackgroundTaskEvent, ProactiveMessageEvent
from ash_industry.model_layer.model_types import AssistantMessage, LLMContext, ModelConfig, UserMessage
from tests.fixtures.web_hud_helpers import scripted_env, use_provider, web_assembly, web_client
from tests.fixtures.agent_loop_helpers import ScriptedProvider, register, text_turn, tool_turn
from ash_industry.model_layer.model_types import Artifact, TextContent, ToolResultMessage
from ash_industry.model_layer.model_types import StreamEvent, StreamOptions
from ash_industry.core.tools.tools_registry import AshTool, ToolContext
from ash_industry.agent_layer.thought.ack_writer import FALLBACK_ACK
from ash_industry.agent_layer.agent_types import ArtifactsEvent
from ash_industry.core.turn import DetachSettings, TurnDetach
from ash_industry.core.session import AgentSession

SID = "detach"
ACK = "QKV 영상을 만드는 중이에요. 끝나면 알려 드릴게요."


class GatedProvider(ScriptedProvider):
    """첫 호출은 gate 가 열릴 때까지 기다린다. 오래 걸리는 코어 모델 호출을 흉내 낸다."""

    def __init__(self, turns: list[list[StreamEvent]]) -> None:
        super().__init__(turns)
        self.gate = asyncio.Event()

    async def stream(
        self, model: ModelConfig, context: LLMContext, options: StreamOptions | None = None
    ) -> AsyncIterator[StreamEvent]:
        self.calls.append(context)
        index = len(self.calls) - 1
        if index == 0:
            await self.gate.wait()
        for event in self._turns[min(index, len(self._turns) - 1)]:
            yield event


class _Render(AshTool):
    """문서를 그려 첨부 하나를 돌려주는 도구. 맡긴 에이전트가 렌더한 결과를 흉내 낸다."""

    name = "render_document"
    description = "x"
    parameters = {"type": "object", "properties": {}}

    async def execute(self, tool_call_id: str, params: dict[str, Any], signal: asyncio.Event | None = None,
                      context: ToolContext | None = None) -> ToolResultMessage:
        result = ToolResultMessage(tool_call_id=tool_call_id, tool_name=self.name, content=[TextContent(text="ok")])
        page = ".render/a/a-1.png"
        result.artifacts = [Artifact(kind="document", path=page, store="docs", pages=[page])]
        return result


class _Writer:
    async def write(self, request: str, progress: str) -> str | None:
        return ACK


def _session(provider: Any, fx: dict[str, Any]) -> AgentSession:
    return AgentSession(
        model=register(provider),
        session_id=SID,
        security_pipeline=fx["pipeline"],
        plugin_runner=fx["plugin_runner"],
        memory=fx["memory"],
        tool_registry=fx["tools"],
        skill_registry=fx["skills"],
        session_repo=fx["repo"],
        turn_detach=TurnDetach(DetachSettings(after_sec=0.1, lead_sec=0.05), _Writer()),
        new_task_id=lambda: "task-1",
    )


async def _until(cond) -> None:
    for _ in range(300):
        if cond():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("timed out")


async def test_long_turn_acks_frees_session_and_delivers_answer(
    permissive_pipeline, plugin_runner, session_memory, tool_registry, skill_registry, jsonl_repo
) -> None:
    fx = {"pipeline": permissive_pipeline, "plugin_runner": plugin_runner, "memory": session_memory,
          "tools": tool_registry, "skills": skill_registry, "repo": jsonl_repo}
    await jsonl_repo.create(session_id=SID)
    provider = GatedProvider([text_turn("영상 완성: out/qkv.mp4"), text_turn("트랜스포머는 주의 메커니즘이에요")])
    session = _session(provider, fx)
    events: list[Any] = []

    async def sink(event: Any) -> None:
        events.append(event)

    session.subscribe(sink)

    acked = await asyncio.wait_for(session.prompt("transformer QKV 개념설명 영상 만들어봐", detach=True), 2)
    assert acked is not None and acked.text() == ACK
    ends = [e for e in events if isinstance(e, AgentEndEvent)]
    assert len(ends) == 1 and ends[0].final_message.text() == ACK
    assert not session.is_running
    # 선응답은 이미 한 말이다. 성찰이 같은 말을 먼저 건넬 거리로 다시 고르면 막힌다
    assert ACK in session._recent_proactive

    # 뒤에서 도는 동안 같은 에이전트와 계속 말한다
    reply = await asyncio.wait_for(session.prompt("트랜스포머가 뭐야?", detach=True), 2)
    assert reply is not None and reply.text() == "트랜스포머는 주의 메커니즘이에요"

    provider.gate.set()
    await _until(lambda: any(isinstance(e, ProactiveMessageEvent) and e.kind == "answer" for e in events))
    answer = next(e for e in events if isinstance(e, ProactiveMessageEvent) and e.kind == "answer")
    assert answer.text == "영상 완성: out/qkv.mp4"
    states = [(e.state, e.ok) for e in events if isinstance(e, BackgroundTaskEvent)]
    assert states == [("started", True), ("finished", True)]
    assert [e.task_id for e in events if isinstance(e, BackgroundTaskEvent)] == ["task-1", "task-1"]

    history = await jsonl_repo.get_messages(SID)
    shown = [m.content if isinstance(m, UserMessage) else m.text() for m in history]
    assert shown == [
        "transformer QKV 개념설명 영상 만들어봐", ACK,
        "트랜스포머가 뭐야?", "트랜스포머는 주의 메커니즘이에요",
        "영상 완성: out/qkv.mp4",
    ]
    assert all(isinstance(m, AssistantMessage) for m in history[1::2][:2])


async def test_short_turn_is_answered_in_place(
    permissive_pipeline, plugin_runner, session_memory, tool_registry, skill_registry, jsonl_repo
) -> None:
    fx = {"pipeline": permissive_pipeline, "plugin_runner": plugin_runner, "memory": session_memory,
          "tools": tool_registry, "skills": skill_registry, "repo": jsonl_repo}
    await jsonl_repo.create(session_id=SID)
    provider = ScriptedProvider([text_turn("바로 답")])
    session = _session(provider, fx)

    reply = await session.prompt("안녕", detach=True)

    assert reply is not None and reply.text() == "바로 답"
    history = await jsonl_repo.get_messages(SID)
    assert [m.content if isinstance(m, UserMessage) else m.text() for m in history] == ["안녕", "바로 답"]


class ThreadGatedProvider(ScriptedProvider):
    """첫 호출은 다른 스레드(TestClient)가 문을 열 때까지 기다린다."""

    def __init__(self, turns: list[list[StreamEvent]]) -> None:
        super().__init__(turns)
        self.gate = threading.Event()

    async def stream(
        self, model: ModelConfig, context: LLMContext, options: StreamOptions | None = None
    ) -> AsyncIterator[StreamEvent]:
        self.calls.append(context)
        index = len(self.calls) - 1
        while index == 0 and not self.gate.is_set():
            await asyncio.sleep(0.01)
        for event in self._turns[min(index, len(self._turns) - 1)]:
            yield event


def _receive_until(ws: Any, kind: str) -> list[dict[str, Any]]:
    seen = []
    while True:
        msg = ws.receive_json()
        seen.append(msg)
        if msg["type"] == kind:
            return seen


def test_hud_gets_ack_star_and_answer(monkeypatch, tmp_path) -> None:
    provider = ThreadGatedProvider([text_turn("영상 완성"), text_turn("요약")])
    for _ in use_provider(provider):
        env = {**scripted_env(provider.provider_name, tmp_path), "PROACTIVE__DETACH_AFTER_SEC": "0.2"}
        with web_client(web_assembly(monkeypatch, tmp_path, **env)) as client:
            with client.websocket_connect("/ws?session_id=alpha") as ws:
                hello = ws.receive_json()
                ws.send_json({"type": "user_message", "text": "영상 만들어줘"})
                ack_end = _receive_until(ws, "agent_end")[-1]
                started = _receive_until(ws, "background_tasks")[-1]
                provider.gate.set()
                answer = next(m for m in _receive_until(ws, "proactive_message") if m["type"] == "proactive_message")
                finished = _receive_until(ws, "background_tasks")[-1]

    assert hello["background_tasks"] == []
    assert ack_end["final_message"]["content"][0]["text"] == FALLBACK_ACK
    assert [(t["session_id"], t["agent"]) for t in started["tasks"]] == [("alpha", "main")]
    assert (answer["kind"], answer["text"]) == ("answer", "영상 완성")
    assert finished["tasks"] == [] and finished["done"]["ok"] is True


async def test_detached_turn_sends_tool_artifacts_to_screen(
    permissive_pipeline, plugin_runner, session_memory, tool_registry, skill_registry, jsonl_repo
) -> None:
    fx = {"pipeline": permissive_pipeline, "plugin_runner": plugin_runner, "memory": session_memory,
          "tools": tool_registry, "skills": skill_registry, "repo": jsonl_repo}
    tool_registry.register(_Render())
    await jsonl_repo.create(session_id=SID)
    provider = GatedProvider([tool_turn(("c1", "render_document", {})), text_turn("문서를 띄웠어요")])
    session = _session(provider, fx)
    events: list[Any] = []

    async def sink(event: Any) -> None:
        events.append(event)

    session.subscribe(sink)
    acked = await asyncio.wait_for(session.prompt("발표 자료 만들어줘", detach=True), 2)
    assert acked is not None and acked.text() == ACK

    provider.gate.set()
    await _until(lambda: any(isinstance(e, ProactiveMessageEvent) and e.kind == "answer" for e in events))
    shown = [e for e in events if isinstance(e, ArtifactsEvent)]
    assert len(shown) == 1 and shown[0].session_id == SID and shown[0].tool_name == "render_document"
    assert [a.pages for a in shown[0].artifacts] == [[".render/a/a-1.png"]]
