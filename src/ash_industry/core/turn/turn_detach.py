"""[core] TurnDetach: 턴이 정한 시간을 넘기면 작은 모델이 쓴 선응답과 함께 그 턴을 대화에서 떼어 낸다."""

import asyncio
from typing import Any
from dataclasses import dataclass
from collections.abc import Callable, Coroutine

from ash_industry.agent_layer.thought.ack_writer import FALLBACK_ACK, SEND_NOW_ACK, AckWriter
from ash_industry.model_layer.model_types import AssistantMessage
from ash_industry.agent_layer.turn_channel import TurnChannel
from ash_industry.agent_layer.turn_inbox import TurnInbox

RunMain = Callable[[TurnChannel], Coroutine[Any, Any, AssistantMessage | None]]
Sleep = Callable[[float], Coroutine[Any, Any, None]]


@dataclass(frozen=True)
class DetachSettings:
    """after_sec 가 지나도 턴이 안 끝나면 떼어 낸다. 선응답은 그보다 lead_sec 먼저 쓰기 시작해 제때 낸다."""

    after_sec: float = 7.5
    lead_sec: float = 3.5


def ack_schedule(settings: DetachSettings) -> tuple[float, float]:
    """(선응답을 쓰기 시작할 때까지, 그 뒤 떼어 낼 때까지) 초. 순수 함수."""
    draft_at = max(0.0, settings.after_sec - settings.lead_sec)
    return draft_at, max(0.0, settings.after_sec - draft_at)


@dataclass
class Detached:
    """떼어 낸 턴. task 는 뒤에서 계속 돌고, channel.produced 에 그 턴의 메시지가 남는다."""

    ack: str
    task: "asyncio.Task[AssistantMessage | None]"
    channel: TurnChannel


@dataclass
class RunningTask:
    """뒤에서 도는 작업 하나. signal 을 켜면 그 작업만 다음 확인 자리에서 멈춘다."""

    task_id: str
    label: str
    channel: TurnChannel
    signal: asyncio.Event
    inbox: TurnInbox
    stopped: bool = False
    applied: int = 0  # 그 작업이 읽은 지시 수. 별에 "반영" 으로 남는다


class TurnDetach:
    """턴 하나를 돌리며 시계를 본다. 정한 시간 안에 끝나면 그 답을, 넘기면 Detached 를 돌려준다.

    early_ack 가 있으면(사고가 미리 오래 걸린다고 본 턴) 기다리지 않고 그 말로 바로 떼어 낸다.
    떼어 낸 뒤 화면에 무엇을 보이고 무엇을 남길지는 부른 쪽(세션)이 정한다.
    """

    def __init__(self, settings: DetachSettings, writer: AckWriter | None = None, sleep: Sleep = asyncio.sleep) -> None:
        self._settings = settings
        self._writer = writer
        self._sleep = sleep

    async def run(
        self, run_main: RunMain, channel: TurnChannel, request: str, early_ack: str | None = None
    ) -> AssistantMessage | None | Detached:
        task: asyncio.Task[AssistantMessage | None] = asyncio.create_task(run_main(channel))
        timer = asyncio.create_task(self._timer(channel, request, early_ack, task))
        await asyncio.wait({task, timer}, return_when=asyncio.FIRST_COMPLETED)
        if timer.done() and not timer.cancelled():
            ack = timer.result()
            if ack is not None:
                return Detached(ack=ack, task=task, channel=channel)
        else:
            timer.cancel()
        return await task

    async def _timer(
        self, channel: TurnChannel, request: str, early_ack: str | None, task: "asyncio.Task[object]"
    ) -> str | None:
        """떼어 냈으면 선응답, 그 전에 턴이 끝났으면 None. 사용자가 지금 보내기를 누르면 그 자리에서 떼어 낸다."""
        if early_ack:
            ack = early_ack
        else:
            draft_at, wait = ack_schedule(self._settings)
            if await self._wait(draft_at, channel):
                ack = SEND_NOW_ACK
            else:
                draft = asyncio.create_task(self._draft(request, channel.progress()))
                try:
                    forced = await self._wait(wait, channel)
                finally:
                    if not draft.done():
                        draft.cancel()
                # 제때 못 쓴 선응답은 기다리지 않는다. 사용자가 기다리는 시간은 after_sec 를 넘지 않는다
                written = draft.result() if draft.done() and not draft.cancelled() else None
                ack = SEND_NOW_ACK if forced else (written or FALLBACK_ACK)
        # 확인과 떼어 내기 사이에 await 가 없다. 그 사이 턴이 끝나 답이 두 번 가는 일이 없다
        if task.done() or not channel.detach():
            return None
        return ack

    async def _wait(self, seconds: float, channel: TurnChannel) -> bool:
        """seconds 를 기다린다. 그 사이 지금 보내기가 오면 바로 돌아오고 True."""
        sleep = asyncio.create_task(self._sleep(seconds))
        forced = asyncio.create_task(channel.detach_requested.wait())
        try:
            await asyncio.wait({sleep, forced}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            sleep.cancel()
            forced.cancel()
        return channel.detach_requested.is_set()

    async def _draft(self, request: str, progress: str) -> str | None:
        if self._writer is None:
            return None
        return await self._writer.write(request, progress)
