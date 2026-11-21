"""[core] 스케줄 알림 보류 큐를 PostgreSQL 테이블에 둔다(asyncpg 풀, 자연 키 upsert, 꺼내면 지운다)."""

import json
import asyncio
from typing import Any

from ash_industry.core.scheduler.notice_store import PENDING_NOTICE_MAX, Notice, PendingNoticeStore, notice_key

TABLE = "ash_pending_notices"


class PostgresPendingNoticeStore(PendingNoticeStore):
    """PostgresOpenLoopStore 와 같은 풀, 테이블 초기화 패턴. 기본 클래스의 메모리 큐는 쓰지 않는다."""

    def __init__(self, dsn: str, limit: int = PENDING_NOTICE_MAX) -> None:
        super().__init__(limit)
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
            async with self._pool.acquire() as conn:
                await conn.execute(f"""
                    CREATE TABLE IF NOT EXISTS {TABLE} (
                        notice_id  TEXT      PRIMARY KEY,
                        seq        BIGSERIAL NOT NULL,
                        payload    TEXT      NOT NULL
                    )
                """)
        return self._pool

    async def push(self, payload: Notice) -> None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                f"INSERT INTO {TABLE} (notice_id, payload) VALUES ($1, $2)"
                " ON CONFLICT (notice_id) DO UPDATE SET payload = EXCLUDED.payload",
                notice_key(payload),
                json.dumps(payload, ensure_ascii=False, default=str),
            )
            # 상한을 넘는 오래된 알림만 지운다. 상한 안이면 서브쿼리가 비어 아무것도 지우지 않는다
            await conn.execute(
                f"DELETE FROM {TABLE} WHERE seq < (SELECT seq FROM {TABLE} ORDER BY seq DESC OFFSET $1 LIMIT 1)",
                self._limit,
            )

    async def drain(self) -> list[Notice]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"WITH gone AS (DELETE FROM {TABLE} RETURNING seq, payload) SELECT payload FROM gone ORDER BY seq"
            )
        return [json.loads(r["payload"]) for r in rows]

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()
            self._pool = None
            self._loop = None
