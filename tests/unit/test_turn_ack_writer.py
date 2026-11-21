"""turn: 선응답 지시문을 자르고 모델 출력을 다듬으며, 모델이 실패하면 None 으로 알리는지 검증한다."""

import pytest

from ash_industry.agent_layer.thought.ack_writer import ACK_MAX_CHARS, AckWriter, build_ack_prompt, clean_ack
from ash_industry.model_layer.model_types import AssistantMessage, ModelConfig, TextContent
import ash_industry.agent_layer.thought.ack_writer as ack_module


def test_build_prompt_clips_inputs_and_fills_blanks():
    prompt = build_ack_prompt("", "요" * 1000, "")
    assert "(정중하고 간결함)" in prompt and "(아직 없음)" in prompt
    assert "요" * 400 in prompt and "요" * 401 not in prompt


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ('"영상을 만드는 중이에요.  끝나면 알려 드릴게요."', "영상을 만드는 중이에요. 끝나면 알려 드릴게요."),
        ("   ", ""),
    ],
)
def test_clean_ack_strips_quotes_and_spaces(raw, expected):
    assert clean_ack(raw) == expected


def test_clean_ack_cuts_long_text_at_sentence_end():
    text = "가" * 150 + ". " + "나" * 200
    cleaned = clean_ack(text)
    assert cleaned.endswith(".") and len(cleaned) <= ACK_MAX_CHARS


async def test_write_returns_clean_text_or_none_on_failure(monkeypatch):
    async def ok(model, ctx, options=None):
        return AssistantMessage(content=[TextContent(text="'뒤에서 이어 할게요.'")])

    async def boom(model, ctx, options=None):
        raise RuntimeError("timeout")

    writer = AckWriter(ModelConfig(provider="none", model="mini"), "정중함")
    monkeypatch.setattr(ack_module, "stream_to_message", ok)
    assert await writer.write("요청", "") == "뒤에서 이어 할게요."
    monkeypatch.setattr(ack_module, "stream_to_message", boom)
    assert await writer.write("요청", "") is None

    async def rejected(model, ctx, options=None):
        return AssistantMessage(content=[], error_message="max_tokens is too large")

    monkeypatch.setattr(ack_module, "stream_to_message", rejected)
    assert await writer.write("요청", "") is None
