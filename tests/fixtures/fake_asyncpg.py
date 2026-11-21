"""asyncpg 흉내. SQL 과 인자를 테스트가 넘긴 핸들러에 그대로 건네고, 핸들러가 행이나 상태 문자열을 돌려준다."""

import sys
import types
from typing import Any
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator, Callable

Handler = Callable[[str, tuple[Any, ...]], Any]


class FakeConn:
    def __init__(self, handler: Handler) -> None:
        self._handler = handler

    async def execute(self, sql: str, *args: Any) -> str:
        result = self._handler(" ".join(sql.split()), args)
        return result if isinstance(result, str) else "OK"

    async def fetch(self, sql: str, *args: Any) -> list[dict[str, Any]]:
        return list(self._handler(" ".join(sql.split()), args) or [])

    async def fetchrow(self, sql: str, *args: Any) -> dict[str, Any] | None:
        rows = await self.fetch(sql, *args)
        return rows[0] if rows else None


class FakePool:
    def __init__(self, handler: Handler) -> None:
        self._handler = handler
        self.closed = False

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[FakeConn]:
        yield FakeConn(self._handler)

    async def close(self) -> None:
        self.closed = True


def install_fake_asyncpg(monkeypatch: Any, handler: Handler) -> list[str]:
    """sys.modules 의 asyncpg 를 가짜로 바꾼다. 돌려주는 목록에 create_pool 이 받은 DSN 이 쌓인다."""
    dsns: list[str] = []

    async def create_pool(dsn: str) -> FakePool:
        dsns.append(dsn)
        return FakePool(handler)

    module = types.ModuleType("asyncpg")
    module.create_pool = create_pool  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "asyncpg", module)
    return dsns
