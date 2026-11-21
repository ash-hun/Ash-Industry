"""[ui] BackgroundBoard: 세션들이 뒤로 넘긴 턴을 모아 FLOW 작업 기록과 열린 HUD 의 별 표시에 알린다."""

from typing import TYPE_CHECKING
from collections.abc import Awaitable, Callable

from ash_industry.agent_layer.agent_types import BackgroundTaskEvent

if TYPE_CHECKING:
    from ash_industry.core.workflow.job_board import JobBoard
    from ash_industry.core.session import AgentSession

BACKGROUND_EVENT = "background_tasks"

Broadcast = Callable[[dict[str, object]], Awaitable[None]]


def job_id_of(task_id: str) -> str:
    return f"background:{task_id}"


class BackgroundBoard:
    """task_id → 도는 작업. 바뀔 때마다 목록 전체를 보내 화면이 받은 것으로 덮어쓰게 한다.

    프로세스 메모리라 재시작하면 비고, 그때 돌던 작업은 JobBoard 가 멈춘 것으로 적는다.
    """

    def __init__(self, broadcast: Broadcast, jobs: "JobBoard") -> None:
        self._broadcast = broadcast
        self._jobs = jobs
        self._running: dict[str, dict[str, object]] = {}

    def running(self) -> list[dict[str, object]]:
        """시작한 순서. 같은 상태면 같은 목록이다."""
        return list(self._running.values())

    def apply(self, agent_id: str, event: BackgroundTaskEvent) -> bool:
        """작업 하나의 상태를 반영하고 목록이 바뀌었는지 돌려준다. 같은 이벤트를 두 번 줘도 결과가 같다."""
        if event.state == "started":
            if event.task_id in self._running:
                return False
            self._running[event.task_id] = {
                "task_id": event.task_id, "session_id": event.session_id, "agent": agent_id, "label": event.label,
                "pending": 0, "applied": 0,
            }
            return True
        if event.state == "updated":
            current = self._running.get(event.task_id)
            if current is None or (current["pending"], current["applied"]) == (event.pending, event.applied):
                return False
            current["pending"], current["applied"] = event.pending, event.applied
            return True
        return self._running.pop(event.task_id, None) is not None

    def watch(self, session_id: str, agent_id: str, session: "AgentSession") -> None:
        """세션 이벤트를 구독한다. SessionRegistry 가 세션을 처음 열 때 한 번 부른다."""

        async def on_event(event: object) -> None:
            if not isinstance(event, BackgroundTaskEvent) or not self.apply(agent_id, event):
                return
            job_id = job_id_of(event.task_id)
            if event.state == "started":
                await self._jobs.start(job_id, "background", event.label)
            elif event.state == "finished":
                await self._jobs.finish(job_id, event.ok, event.error)
            done = None
            if event.state == "finished":
                done = {"task_id": event.task_id, "ok": event.ok, "stopped": event.stopped}
            await self._broadcast({"type": BACKGROUND_EVENT, "tasks": self.running(), "done": done})

        session.subscribe(on_event)
