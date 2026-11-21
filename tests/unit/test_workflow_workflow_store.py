"""workflow 의 메모리 저장소: 간선과 작업의 upsert, 최근 N 개 읽기, 상한을 검증한다."""

from ash_industry.core.workflow.workflow_types import DelegationEdge, JobRecord
from ash_industry.core.workflow.workflow_store import WorkflowStore


def _edge(eid: str, started: int, ended: int | None = None) -> DelegationEdge:
    return DelegationEdge(eid, "ask", "main", "scribe", "뉴스", started, ended, None if ended is None else True)


async def test_recent_edges_returns_newest_limit_in_start_order():
    store = WorkflowStore()
    for i in (3, 1, 2):
        await store.save_edge(_edge(f"e{i}", i * 10))

    assert [e.edge_id for e in await store.recent_edges(2)] == ["e2", "e3"]
    assert await store.recent_edges(0) == []


async def test_save_edge_twice_keeps_one_and_keep_drops_oldest():
    store = WorkflowStore(keep=2)
    await store.save_edge(_edge("e1", 10))
    await store.save_edge(_edge("e1", 10, ended=20))
    assert [e.ended_ms for e in await store.recent_edges(10)] == [20]

    await store.save_edge(_edge("e2", 30))
    await store.save_edge(_edge("e3", 40))

    assert [e.edge_id for e in await store.recent_edges(10)] == ["e2", "e3"]


async def test_save_job_upserts_by_job_id_and_lists_sorted():
    store = WorkflowStore()
    await store.save_job(JobRecord("schedule:b", "schedule", "b", runs=1, running=True))
    await store.save_job(JobRecord("schedule:a", "schedule", "a", runs=1, running=False))
    await store.save_job(JobRecord("schedule:b", "schedule", "b", runs=1, running=False, last_ok=True))

    jobs = await store.jobs()

    assert [(j.job_id, j.running, j.last_ok) for j in jobs] == [
        ("schedule:a", False, None), ("schedule:b", False, True),
    ]
