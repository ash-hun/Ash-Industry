"""openloop 의 PostgresOpenLoopStore: 기본 클래스 상속, DB 없이 모르는 상태 거절, 행 변환, 임베딩 열 저장을 검증한다."""

from typing import Any

from ash_industry.agent_layer.openloop import OpenLoop, OpenLoopStore, PostgresOpenLoopStore
from ash_industry.agent_layer.openloop.postgres_store import _row_to_loop
from tests.fixtures.fake_asyncpg import install_fake_asyncpg

DSN = "postgresql://unused@localhost/none"  # 연결하지 않는다


def test_postgres_store_is_open_loop_store():
    assert issubclass(PostgresOpenLoopStore, OpenLoopStore)


async def test_update_status_rejects_unknown_status_without_db():
    assert await PostgresOpenLoopStore(DSN).update_status("x", "bogus") is False


def test_row_to_loop_maps_columns():
    row = {
        "id": "r1", "description": "전화하기", "status": "done", "origin_session": None,
        "due_ms": 5, "created_at": 1, "updated_at": 2, "agent_id": "scribe",
        "embedding": (0.5, 0.5), "embedding_model": "bge-m3",
    }

    loop = _row_to_loop(row)
    bare = _row_to_loop({**row, "embedding": None, "embedding_model": ""})

    assert (loop.id, loop.description, loop.status, loop.origin_session) == ("r1", "전화하기", "done", None)
    assert loop.agent_id == "scribe"
    assert (loop.due_ms, loop.created_at, loop.updated_at) == (5, 1, 2)
    assert (loop.embedding, loop.embedding_model) == ([0.5, 0.5], "bge-m3")
    assert (bare.embedding, bare.embedding_model) == (None, "")


COLS = (
    "id", "description", "status", "origin_session", "due_ms", "created_at", "updated_at", "agent_id", "embedding",
    "embedding_model",
)


class _Table:
    """ash_open_loops 흉내. id → 행. 상태 UPDATE 와 조회 조건은 이 테스트가 안 쓴다."""

    def __init__(self) -> None:
        self.rows: dict[str, dict[str, Any]] = {}

    def __call__(self, sql: str, args: tuple[Any, ...]) -> Any:
        if sql.startswith(("CREATE", "ALTER")):
            return "OK"
        if sql.startswith("INSERT"):
            row = dict(zip(COLS, args, strict=True))
            self.rows[row["id"]] = row
            return "INSERT 0 1"
        if sql.startswith("SELECT * FROM ash_open_loops WHERE id = $1"):
            return [self.rows[args[0]]] if args[0] in self.rows else []
        raise AssertionError(sql)


async def test_add_round_trips_embedding_and_survives_a_new_store_instance(monkeypatch):
    table = _Table()
    install_fake_asyncpg(monkeypatch, table)
    loop = OpenLoop(id="e1", description="회의 준비", embedding=[0.1, 0.9], embedding_model="table")
    await PostgresOpenLoopStore(DSN).add(loop)
    await PostgresOpenLoopStore(DSN).add(loop)

    got = await PostgresOpenLoopStore(DSN).get("e1")

    assert len(table.rows) == 1
    assert got is not None and (got.embedding, got.embedding_model) == ([0.1, 0.9], "table")
