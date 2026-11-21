"""send_now: SteerRouter 가 작은 모델 출력에서 작업 지시와 새 요청을 가르고, 실패하면 규칙으로 정하는지 검증한다."""

import pytest

from ash_industry.agent_layer.thought.steer_router import (
    STEER_ACK,
    SteerDecision,
    SteerRouter,
    build_steer_prompt,
    fallback_steer,
    parse_steer,
)
from ash_industry.model_layer.model_types import AssistantMessage, ModelConfig, TextContent
import ash_industry.agent_layer.thought.steer_router as steer_module

TASKS = [("t1", "QKV 개념설명 영상 만들어줘"), ("t2", "LH 공고 정리")]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ('{"target": "t1", "ack": "영상에서 자막을 뺄게요."}', SteerDecision("t1", "영상에서 자막을 뺄게요.")),
        ('앞말 {"target": "t2", "ack": ""} 뒷말', SteerDecision("t2", STEER_ACK)),
        ('{"target": "new", "ack": "무시"}', SteerDecision(None)),
        ('{"target": "t9", "ack": "x"}', None),
        ("형식 없음", None),
    ],
)
def test_parse_steer(raw, expected):
    assert parse_steer(raw, ["t1", "t2"]) == expected


def test_fallback_steers_only_single_task_and_prompt_lists_tasks():
    assert fallback_steer(["t1"]) == SteerDecision("t1", STEER_ACK)
    assert fallback_steer(["t1", "t2"]) == SteerDecision(None)
    prompt = build_steer_prompt("가볍게", "자막 빼줘", TASKS)
    assert "- t1: QKV 개념설명 영상 만들어줘" in prompt and "자막 빼줘" in prompt


async def test_route_uses_model_and_falls_back_on_provider_error(monkeypatch):
    async def ok(model, ctx, options=None):
        return AssistantMessage(content=[TextContent(text='{"target": "t1", "ack": "자막을 뺄게요."}')])

    async def rejected(model, ctx, options=None):
        return AssistantMessage(content=[], error_message="400")

    router = SteerRouter(ModelConfig(provider="none", model="mini"), "가볍게")
    monkeypatch.setattr(steer_module, "stream_to_message", ok)
    assert await router.route("자막 빼줘", TASKS) == SteerDecision("t1", "자막을 뺄게요.")
    monkeypatch.setattr(steer_module, "stream_to_message", rejected)
    assert await router.route("자막 빼줘", TASKS) == SteerDecision(None)
    assert await router.route("자막 빼줘", []) == SteerDecision(None)
