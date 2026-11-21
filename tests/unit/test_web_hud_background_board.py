"""web_hud: BackgroundBoard 가 뒤로 넘긴 턴을 모아 FLOW 작업 기록에 남기고 바뀔 때만 목록 전체를 알리는지 검증한다."""

from ash_industry.ui.web.background_board import BACKGROUND_EVENT, BackgroundBoard, job_id_of
from ash_industry.agent_layer.agent_types import BackgroundTaskEvent
from ash_industry.core.workflow.job_board import JobBoard


def _event(state: str, ok: bool = True) -> BackgroundTaskEvent:
    return BackgroundTaskEvent(session_id="s1", task_id="t1", label="QKV 영상", state=state, ok=ok)


class _Session:
    def __init__(self):
        self.listeners = []

    def subscribe(self, fn):
        self.listeners.append(fn)
        return lambda: None

    async def emit(self, event):
        for fn in self.listeners:
            await fn(event)


def test_apply_is_idempotent_and_keeps_start_order():
    board = BackgroundBoard(broadcast=None, jobs=JobBoard(lambda: 0))
    assert board.apply("studio", _event("started")) is True
    assert board.apply("studio", _event("started")) is False
    expected = {"task_id": "t1", "session_id": "s1", "agent": "studio", "label": "QKV 영상", "pending": 0, "applied": 0}
    assert board.running() == [expected]
    updated = BackgroundTaskEvent(session_id="s1", task_id="t1", label="QKV 영상", state="updated", pending=1)
    assert board.apply("studio", updated) is True and board.apply("studio", updated) is False
    assert board.running()[0]["pending"] == 1
    read = BackgroundTaskEvent(session_id="s1", task_id="t1", label="QKV 영상", state="updated", applied=1)
    assert board.apply("studio", read) is True
    assert (board.running()[0]["pending"], board.running()[0]["applied"]) == (0, 1)
    assert board.apply("studio", _event("finished")) is True
    assert board.apply("studio", _event("finished")) is False
    assert board.running() == []


async def test_watch_records_job_and_broadcasts_changes_only():
    sent = []

    async def broadcast(payload):
        sent.append(payload)

    jobs = JobBoard(lambda: 1)
    board = BackgroundBoard(broadcast, jobs)
    session = _Session()
    board.watch("s1", "studio", session)

    await session.emit(_event("started"))
    await session.emit(_event("started"))
    assert jobs.records()[0].running and jobs.records()[0].job_id == job_id_of("t1")
    await session.emit(_event("finished", ok=False))

    assert [p["type"] for p in sent] == [BACKGROUND_EVENT, BACKGROUND_EVENT]
    assert sent[0]["tasks"][0]["agent"] == "studio" and sent[0]["done"] is None
    assert sent[1] == {"type": BACKGROUND_EVENT, "tasks": [], "done": {"task_id": "t1", "ok": False, "stopped": False}}
    assert jobs.records()[0].last_ok is False
