"""[core] 위임 간선과 작업 실행 기록을 PostgreSQL 테이블에 영속한다(asyncpg 풀, id 로 upsert)."""

import asyncio
from typing import Any, cast

from ash_industry.core.workflow.workflow_types import DelegationEdge, DelegationKind, JobKind, JobRecord
from ash_industry.core.workflow.workflow_store import EDGE_KEEP, WorkflowStore

EDGES_TABLE = "ash_workflow_edges"
JOBS_TABLE = "ash_workflow_jobs"


class PostgresWorkflowStore(WorkflowStore):
    """PostgresOpenLoopStore 와 같은 풀, 테이블 초기화 패턴. 기본 클래스의 메모리 저장은 쓰지 않는다."""

    def __init__(self, dsn: str, keep: int = EDGE_KEEP) -> None:
        super().__init__(keep)
        self._dsn = dsn
        # asyncpg 는 타입 스텁이 없어 풀과 레코드를 Any 로 다룬다
        self._pool: Any = None
        self._loop: asyncio.AbstractEventLoop | None = None

    async def _get_pool(self) -> Any:
        import asyncpg

        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None
        if self._pool is None or self._loop is not current_loop:
            self._pool = await asyncpg.create_pool(self._dsn)
            self._loop = current_loop
            await self._ensure_tables()
        return self._pool

    async def _ensure_tables(self) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {EDGES_TABLE} (
                    edge_id     TEXT      PRIMARY KEY,
                    seq         BIGSERIAL NOT NULL,
                    kind        TEXT      NOT NULL,
                    source      TEXT      NOT NULL,
                    target      TEXT      NOT NULL,
                    label       TEXT      NOT NULL,
                    started_ms  BIGINT    NOT NULL,
                    ended_ms    BIGINT,
                    ok          BOOLEAN,
                    session_id  TEXT      NOT NULL DEFAULT '',
                    tokens      BIGINT
                )
            """)
            # 지도 열은 뒤에 생겼다. 옛 테이블에는 더하고, 이미 있으면 그대로다
            await conn.execute(
                f"ALTER TABLE {EDGES_TABLE} ADD COLUMN IF NOT EXISTS session_id TEXT NOT NULL DEFAULT '', "
                "ADD COLUMN IF NOT EXISTS tokens BIGINT"
            )
            await conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {JOBS_TABLE} (
                    job_id           TEXT    PRIMARY KEY,
                    kind             TEXT    NOT NULL,
                    label            TEXT    NOT NULL,
                    runs             INTEGER NOT NULL,
                    running          BOOLEAN NOT NULL,
                    last_started_ms  BIGINT,
                    last_ended_ms    BIGINT,
                    last_ok          BOOLEAN,
                    last_error       TEXT    NOT NULL DEFAULT '',
                    fail_streak      INTEGER NOT NULL DEFAULT 0
                )
            """)

    async def save_edge(self, edge: DelegationEdge) -> None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                f"""
                INSERT INTO {EDGES_TABLE}
                    (edge_id, kind, source, target, label, started_ms, ended_ms, ok, session_id, tokens)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                ON CONFLICT (edge_id) DO UPDATE SET
                    kind = EXCLUDED.kind, source = EXCLUDED.source, target = EXCLUDED.target,
                    label = EXCLUDED.label, started_ms = EXCLUDED.started_ms,
                    ended_ms = EXCLUDED.ended_ms, ok = EXCLUDED.ok,
                    session_id = EXCLUDED.session_id, tokens = EXCLUDED.tokens
                """,
                edge.edge_id, edge.kind, edge.source, edge.target, edge.label, edge.started_ms, edge.ended_ms, edge.ok,
                edge.session_id, edge.tokens,
            )
            # 상한을 넘는 오래된 간선만 지운다. 상한 안이면 서브쿼리가 비어 아무것도 지우지 않는다
            await conn.execute(
                f"DELETE FROM {EDGES_TABLE} WHERE seq < "
                f"(SELECT seq FROM {EDGES_TABLE} ORDER BY seq DESC OFFSET $1 LIMIT 1)",
                self._keep,
            )

    async def recent_edges(self, limit: int) -> list[DelegationEdge]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT * FROM {EDGES_TABLE} ORDER BY started_ms DESC, seq DESC LIMIT $1", max(limit, 0)
            )
        return [_row_to_edge(r) for r in reversed(rows)]

    async def save_job(self, record: JobRecord) -> None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                f"""
                INSERT INTO {JOBS_TABLE}
                    (job_id, kind, label, runs, running, last_started_ms, last_ended_ms, last_ok, last_error,
                     fail_streak)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                ON CONFLICT (job_id) DO UPDATE SET
                    kind = EXCLUDED.kind, label = EXCLUDED.label, runs = EXCLUDED.runs,
                    running = EXCLUDED.running, last_started_ms = EXCLUDED.last_started_ms,
                    last_ended_ms = EXCLUDED.last_ended_ms, last_ok = EXCLUDED.last_ok,
                    last_error = EXCLUDED.last_error, fail_streak = EXCLUDED.fail_streak
                """,
                record.job_id, record.kind, record.label, record.runs, record.running, record.last_started_ms,
                record.last_ended_ms, record.last_ok, record.last_error, record.fail_streak,
            )

    async def jobs(self) -> list[JobRecord]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(f"SELECT * FROM {JOBS_TABLE} ORDER BY job_id")
        return [_row_to_job(r) for r in rows]

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()
            self._pool = None
            self._loop = None


def _row_to_edge(row: Any) -> DelegationEdge:
    return DelegationEdge(
        edge_id=row["edge_id"],
        kind=cast(DelegationKind, row["kind"]),
        source=row["source"],
        target=row["target"],
        label=row["label"],
        started_ms=row["started_ms"],
        ended_ms=row["ended_ms"],
        ok=row["ok"],
        session_id=row["session_id"] or "",
        tokens=row["tokens"],
    )


def _row_to_job(row: Any) -> JobRecord:
    return JobRecord(
        job_id=row["job_id"],
        kind=cast(JobKind, row["kind"]),
        label=row["label"],
        runs=row["runs"],
        running=row["running"],
        last_started_ms=row["last_started_ms"],
        last_ended_ms=row["last_ended_ms"],
        last_ok=row["last_ok"],
        last_error=row["last_error"],
        fail_streak=row["fail_streak"],
    )
