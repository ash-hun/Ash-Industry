"""scheduler 의 Postgres 알림 보류 큐: 가짜 asyncpg 위에서 upsert, 상한, 꺼내면 지우기, 재시작 뒤 복원을 검증한다."""

import json
import pytest
from typing import Any

from ash_industry.core.scheduler.notice_postgres_store import PostgresPendingNoticeStore
from ash_industry.core.scheduler.notice_store import PendingNoticeStore
from tests.fixtures.fake_asyncpg import install_fake_asyncpg

DSN = "postgresql://unused@localhost/none"


class _Table:
    """ash_pending_notices 흉내. notice_id → (seq, payload)."""

    def __init__(self) -> None:
        self.rows: dict[str, tuple[int, str]] = {}
        self._seq = 0

    def __call__(self, sql: str, args: tuple[Any, ...]) -> Any:
        if sql.startswith("CREATE TABLE"):
            return "CREATE TABLE"
        if sql.startswith("INSERT"):
            notice_id, payload = args
            seq = self.rows[notice_id][0] if notice_id in self.rows else self._next()
            self.rows[notice_id] = (seq, payload)
            return "INSERT 0 1"
        if sql.startswith("DELETE"):
            keep = args[0]
            ordered = sorted(self.rows.items(), key=lambda kv: kv[1][0], reverse=True)
            for key, _ in ordered[keep:]:
                del self.rows[key]
            return "DELETE"
        if sql.startswith("WITH gone"):
            ordered = sorted(self.rows.values())
            self.rows.clear()
            return [{"payload": payload} for _, payload in ordered]
        raise AssertionError(sql)

    def _next(self) -> int:
        self._seq += 1
        return self._seq


@pytest.fixture
def table(monkeypatch):
    handler = _Table()
    install_fake_asyncpg(monkeypatch, handler)
    return handler


def _notice(nid: str, text: str = "물 마시기") -> dict[str, Any]:
    return {"type": "reminder", "id": nid, "name": "water", "text": text}


def test_postgres_store_is_pending_notice_store():
    assert issubclass(PostgresPendingNoticeStore, PendingNoticeStore)


async def test_push_then_drain_round_trips_payload_in_order(table):
    store = PostgresPendingNoticeStore(DSN)
    await store.push(_notice("n1"))
    await store.push(_notice("n2", "스트레칭"))

    drained = await store.drain()

    assert [n["id"] for n in drained] == ["n1", "n2"] and drained[1]["text"] == "스트레칭"
    assert await store.drain() == [] and table.rows == {}


async def test_notices_survive_a_new_store_instance(table):
    await PostgresPendingNoticeStore(DSN).push(_notice("n1"))

    restarted = PostgresPendingNoticeStore(DSN)

    assert [n["id"] for n in await restarted.drain()] == ["n1"]


async def test_same_notice_twice_is_one_row_and_limit_trims_oldest(table):
    store = PostgresPendingNoticeStore(DSN, limit=2)
    await store.push(_notice("n1"))
    await store.push(_notice("n1", "다시"))
    assert len(table.rows) == 1 and json.loads(table.rows["n1"][1])["text"] == "다시"

    await store.push(_notice("n2"))
    await store.push(_notice("n3"))

    assert [n["id"] for n in await store.drain()] == ["n2", "n3"]
