"""turn: TurnDetach 가 정한 시간 안에 끝난 턴은 그 답을, 넘긴 턴은 선응답과 함께 떼어 내는지 검증한다."""

import asyncio

from ash_industry.core.turn import DetachSettings, Detached, TurnDetach, ack_schedule
from ash_industry.agent_layer.thought.ack_writer import FALLBACK_ACK, SEND_NOW_ACK
from ash_industry.model_layer.model_types import AssistantMessage, TextContent
from ash_industry.agent_layer.turn_channel import TurnChannel

FAST = DetachSettings(after_sec=0.05, lead_sec=0.03)


async def _sink(event) -> None:
    return None


def _reply(text: str) -> AssistantMessage:
    return AssistantMessage(content=[TextContent(text=text)])


class _Writer:
    def __init__(self, text: str | None, delay: float = 0.0) -> None:
        self.text, self.delay, self.calls = text, delay, []

    async def write(self, request: str, progress: str) -> str | None:
        self.calls.append((request, progress))
        await asyncio.sleep(self.delay)
        return self.text


def _slow(gate: asyncio.Event, text: str = "끝"):
    async def run_main(channel: TurnChannel) -> AssistantMessage:
        await gate.wait()
        return _reply(text)
    return run_main


def test_ack_schedule_starts_drafting_lead_seconds_early():
    assert ack_schedule(DetachSettings(after_sec=7.5, lead_sec=2.0)) == (5.5, 2.0)
    assert ack_schedule(DetachSettings(after_sec=1.0, lead_sec=3.0)) == (0.0, 1.0)


async def test_fast_turn_returns_its_answer_without_detaching():
    async def run_main(channel: TurnChannel) -> AssistantMessage:
        return _reply("바로 답")

    channel = TurnChannel(_sink)
    writer = _Writer("안 쓰임")
    outcome = await TurnDetach(DetachSettings(after_sec=5), writer).run(run_main, channel, "요청")
    assert isinstance(outcome, AssistantMessage) and outcome.text() == "바로 답"
    assert channel.detached is False and writer.calls == []


async def test_slow_turn_detaches_with_written_ack_and_keeps_running():
    gate = asyncio.Event()
    channel = TurnChannel(_sink)
    writer = _Writer("영상을 만드는 중이에요. 끝나면 알려 드릴게요.")
    outcome = await TurnDetach(FAST, writer).run(_slow(gate, "완성"), channel, "QKV 영상")
    assert isinstance(outcome, Detached) and outcome.ack == "영상을 만드는 중이에요. 끝나면 알려 드릴게요."
    assert channel.detached is True and writer.calls[0][0] == "QKV 영상"
    gate.set()
    assert (await outcome.task).text() == "완성"


async def test_late_or_missing_writer_falls_back_on_time():
    gate = asyncio.Event()
    late = await TurnDetach(FAST, _Writer("늦은 말", delay=1.0)).run(_slow(gate), TurnChannel(_sink), "요청")
    none = await TurnDetach(FAST, None).run(_slow(gate), TurnChannel(_sink), "요청")
    assert isinstance(late, Detached) and late.ack == FALLBACK_ACK
    assert isinstance(none, Detached) and none.ack == FALLBACK_ACK
    gate.set()


async def test_early_ack_detaches_without_waiting():
    gate = asyncio.Event()
    detach = TurnDetach(DetachSettings(after_sec=60), _Writer("안 쓰임"))
    outcome = await asyncio.wait_for(detach.run(_slow(gate), TurnChannel(_sink), "요청", early_ack="미리 본 말"), 1)
    assert isinstance(outcome, Detached) and outcome.ack == "미리 본 말"
    gate.set()


async def test_failure_before_detach_is_raised_to_caller():
    async def run_main(channel: TurnChannel) -> AssistantMessage:
        raise RuntimeError("provider down")

    try:
        await TurnDetach(FAST).run(run_main, TurnChannel(_sink), "요청")
    except RuntimeError as exc:
        assert str(exc) == "provider down"
    else:
        raise AssertionError("not raised")


async def test_send_now_request_detaches_at_once_without_waiting_for_writer():
    gate = asyncio.Event()
    channel = TurnChannel(_sink)
    writer = _Writer("안 쓰임", delay=5)
    run = asyncio.create_task(TurnDetach(DetachSettings(after_sec=60), writer).run(_slow(gate), channel, "요청"))
    await asyncio.sleep(0.01)
    channel.request_detach()
    outcome = await asyncio.wait_for(run, 1)
    assert isinstance(outcome, Detached) and outcome.ack == SEND_NOW_ACK
    gate.set()
