"""workflow 의 Postgres 저장소: 가짜 asyncpg 위에서 간선과 작업의 upsert, 상한, 새 인스턴스에서 복원을 검증한다."""

import pytest
from typing import Any

from ash_industry.core.workflow.workflow_postgres_store import PostgresWorkflowStore, _row_to_edge, _row_to_job
from ash_industry.core.workflow.workflow_types import DelegationEdge, JobRecord
from ash_industry.core.workflow.workflow_store import WorkflowStore
from tests.fixtures.fake_asyncpg import install_fake_asyncpg

DSN = "postgresql://unused@localhost/none"
EDGE_COLS = ("edge_id", "kind", "source", "target", "label", "started_ms", "ended_ms", "ok", "session_id", "tokens")
JOB_COLS = (
    "job_id", "kind", "label", "runs", "running", "last_started_ms", "last_ended_ms", "last_ok", "last_error",
    "fail_streak",
)


class _Tables:
    """ash_workflow_edges(edge_id → 행, seq 포함)와 ash_workflow_jobs(job_id → 행) 흉내."""

    def __init__(self) -> None:
        self.edges: dict[str, dict[str, Any]] = {}
        self.jobs: dict[str, dict[str, Any]] = {}
        self._seq = 0

    def __call__(self, sql: str, args: tuple[Any, ...]) -> Any:
        if sql.startswith("CREATE TABLE") or sql.startswith("ALTER TABLE"):
            return "OK"
        if sql.startswith("INSERT INTO ash_workflow_edges"):
            row = dict(zip(EDGE_COLS, args, strict=True))
            self._seq += 1
            row["seq"] = self.edges[row["edge_id"]]["seq"] if row["edge_id"] in self.edges else self._seq
            self.edges[row["edge_id"]] = row
            return "INSERT 0 1"
        if sql.startswith("DELETE FROM ash_workflow_edges"):
            ordered = sorted(self.edges.values(), key=lambda r: r["seq"], reverse=True)
            for row in ordered[args[0]:]:
                del self.edges[row["edge_id"]]
            return "DELETE"
        if sql.startswith("SELECT * FROM ash_workflow_edges"):
            ordered = sorted(self.edges.values(), key=lambda r: (r["started_ms"], r["seq"]), reverse=True)
            return ordered[: args[0]]
        if sql.startswith("INSERT INTO ash_workflow_jobs"):
            row = dict(zip(JOB_COLS, args, strict=True))
            self.jobs[row["job_id"]] = row
            return "INSERT 0 1"
        if sql.startswith("SELECT * FROM ash_workflow_jobs"):
            return [self.jobs[k] for k in sorted(self.jobs)]
        raise AssertionError(sql)


@pytest.fixture
def tables(monkeypatch):
    handler = _Tables()
    install_fake_asyncpg(monkeypatch, handler)
    return handler


def _edge(eid: str, started: int, ended: int | None = None) -> DelegationEdge:
    return DelegationEdge(eid, "ask", "main", "scribe", "뉴스", started, ended, None if ended is None else True)


def test_postgres_store_is_workflow_store():
    assert issubclass(PostgresWorkflowStore, WorkflowStore)


def test_row_mappers_keep_every_column():
    edge = _row_to_edge(dict(zip(EDGE_COLS, ("e1", "subagent", "main", "x", "t", 1, 2, False, "s1", 70), strict=True)))
    job = _row_to_job(dict(zip(JOB_COLS, ("schedule:x", "schedule", "x", 3, False, 1, 2, True, "", 0), strict=True)))

    assert (edge.edge_id, edge.kind, edge.target, edge.ended_ms, edge.ok) == ("e1", "subagent", "x", 2, False)
    assert (edge.session_id, edge.tokens) == ("s1", 70)
    assert (job.job_id, job.runs, job.last_ok, job.fail_streak) == ("schedule:x", 3, True, 0)


async def test_edges_and_jobs_survive_a_new_store_instance(tables):
    store = PostgresWorkflowStore(DSN)
    await store.save_edge(_edge("e1", 10, ended=20))
    await store.save_edge(_edge("e2", 30))
    await store.save_job(JobRecord("schedule:x", "schedule", "x", runs=4, running=False, last_ok=True))

    restarted = PostgresWorkflowStore(DSN)

    assert [e.edge_id for e in await restarted.recent_edges(10)] == ["e1", "e2"]
    assert [(j.job_id, j.runs) for j in await restarted.jobs()] == [("schedule:x", 4)]


async def test_same_edge_twice_is_one_row_and_keep_trims_oldest(tables):
    store = PostgresWorkflowStore(DSN, keep=2)
    await store.save_edge(_edge("e1", 10))
    await store.save_edge(_edge("e1", 10, ended=20))
    assert len(tables.edges) == 1 and tables.edges["e1"]["ended_ms"] == 20

    await store.save_edge(_edge("e2", 30))
    await store.save_edge(_edge("e3", 40))

    assert [e.edge_id for e in await store.recent_edges(10)] == ["e2", "e3"]
