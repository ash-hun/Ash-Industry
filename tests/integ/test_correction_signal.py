"""교정 신호: 🔔 답이 아닌 보통 말이 직전 답을 바로잡는 말이면 그 턴 일화를 실패로 적고, 반성이 그 말을 읽는다."""

import asyncio

from ash_industry.model_layer.model_types import AssistantMessage, TextContent, UserMessage
from ash_industry.memory.memory_service import turn_item_id
from ash_industry.core.session import AgentSession

SID = "correction-session"


class FakeClassifier:
    def __init__(self, verdict: str) -> None:
        self.verdict = verdict
        self.calls: list[tuple[str, str, str]] = []

    async def classify(self, kind, text, context="", has_always=False):  # type: ignore[no-untyped-def]
        self.calls.append((kind, text, context))
        return self.verdict


def _session(fx, classifier: FakeClassifier | None) -> AgentSession:
    return AgentSession(
        model=fx["model"], session_id=SID, security_pipeline=fx["pipeline"], plugin_runner=fx["plugin_runner"],
        memory=fx["session_memory"], tool_registry=fx["tool_registry"], skill_registry=fx["skill_registry"],
        session_repo=fx["repo"], reply_classifier=classifier,
    )


async def _open_with_answer(fx) -> None:
    await fx["repo"].create(session_id=SID)
    await fx["repo"].append(SID, UserMessage(content="목록 보여줘", timestamp=0))
    text = "앞서 찾은 레퍼런스 열 건을 다시 읽어드립니다."
    await fx["repo"].append(SID, AssistantMessage(content=[TextContent(text=text)], timestamp=1))


async def _settle(session: AgentSession) -> None:
    for _ in range(20):
        await asyncio.sleep(0)
    await asyncio.gather(*list(session._feedback_tasks), return_exceptions=True)


async def _fx(faux_model, permissive_pipeline, plugin_runner, session_memory, tool_registry, skill_registry, repo):
    return {
        "model": faux_model, "pipeline": permissive_pipeline, "plugin_runner": plugin_runner,
        "session_memory": session_memory, "tool_registry": tool_registry, "skill_registry": skill_registry,
        "repo": repo,
    }


async def test_correcting_reply_marks_the_previous_turn_failed(
    faux_model, permissive_pipeline, plugin_runner, session_memory, tool_registry, skill_registry, jsonl_repo
):
    fx = await _fx(
        faux_model, permissive_pipeline, plugin_runner, session_memory, tool_registry, skill_registry, jsonl_repo
    )
    await _open_with_answer(fx)
    classifier = FakeClassifier("correction")
    session = _session(fx, classifier)
    await session_memory.record_turn(1, "목록 보여줘", "앞서 찾은 레퍼런스 열 건", session.memory_scope)

    await session.prompt("이 얘기가 왜 나와?")
    await _settle(session)

    assert classifier.calls[0][0] == "correction" and "레퍼런스 열 건" in classifier.calls[0][2]
    turn = await session_memory.get(turn_item_id(session.memory_scope, 1))
    assert turn is not None
    assert (turn.metadata["outcome"], turn.metadata["correction"]) == ("failure", "이 얘기가 왜 나와?")


async def test_ordinary_reply_and_slash_command_leave_the_turn_alone(
    faux_model, permissive_pipeline, plugin_runner, session_memory, tool_registry, skill_registry, jsonl_repo
):
    fx = await _fx(
        faux_model, permissive_pipeline, plugin_runner, session_memory, tool_registry, skill_registry, jsonl_repo
    )
    await _open_with_answer(fx)
    classifier = FakeClassifier("other")
    session = _session(fx, classifier)
    await session_memory.record_turn(1, "목록 보여줘", "답", session.memory_scope)

    await session.prompt("/focus")
    await session.prompt("고마워")
    await _settle(session)

    assert [c[0] for c in classifier.calls] == ["correction"]
    turn = await session_memory.get(turn_item_id(session.memory_scope, 1))
    assert turn is not None and turn.metadata["outcome"] == "success"
