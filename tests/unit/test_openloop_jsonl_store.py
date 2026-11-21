"""openloop: JSONL 저장소가 추가, 상태, 기한, 에이전트, 임베딩을 남겨 재로드 뒤 되살리고 바뀔 때만 덧붙이는지 본다."""

import json

from ash_industry.agent_layer.openloop import JsonlOpenLoopStore, OpenLoop, OpenLoopStore
from ash_industry.model_layer.embeddings import Embedder


class _CountingEmbedder(Embedder):
    """문구마다 서로 직교하는 축을 돌려주고 부른 문구를 센다."""

    model = "table"
    dimensions = 3
    table = {"참석자 목록 확정": [1.0, 0.0, 0.0], "배포 결과 공유": [0.0, 1.0, 0.0]}

    def __init__(self) -> None:
        self.texts: list[str] = []

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.texts += texts
        return [self.table.get(t, [0.0, 0.0, 1.0]) for t in texts]


def test_jsonl_store_is_open_loop_store(tmp_path):
    assert isinstance(JsonlOpenLoopStore(path=str(tmp_path / "openloops.jsonl")), OpenLoopStore)


async def test_add_persists_across_reload(tmp_path):
    path = str(tmp_path / "openloops.jsonl")
    await JsonlOpenLoopStore(path=path).add(OpenLoop(description="배포 결과 공유", origin_session="s1"))

    loops = await JsonlOpenLoopStore(path=path).list_open(session_id="s1")

    assert len(loops) == 1
    assert loops[0].description == "배포 결과 공유"


async def test_status_update_persists_via_replay(tmp_path):
    path = str(tmp_path / "openloops.jsonl")
    s1 = JsonlOpenLoopStore(path=path)
    lid = await s1.add(OpenLoop(description="작업 A"))
    await s1.update_status(lid, "done")

    s2 = JsonlOpenLoopStore(path=path)

    got = await s2.get(lid)
    assert got is not None and got.status == "done"
    assert await s2.list_open() == []


async def test_add_unique_dedups_across_reload(tmp_path):
    path = str(tmp_path / "openloops.jsonl")
    await JsonlOpenLoopStore(path=path).add_unique(OpenLoop(description="같은 약속", origin_session="s1"))
    s2 = JsonlOpenLoopStore(path=path)

    dup = await s2.add_unique(OpenLoop(description="같은  약속", origin_session="s1"))

    assert dup is None
    assert len(await s2.all()) == 1


async def test_missing_file_is_empty(tmp_path):
    store = JsonlOpenLoopStore(path=str(tmp_path / "nope.jsonl"))

    assert await store.list_open() == []
    assert await store.all() == []


async def test_update_status_rejects_unknown_status_and_id(tmp_path):
    store = JsonlOpenLoopStore(path=str(tmp_path / "openloops.jsonl"))
    lid = await store.add(OpenLoop(description="x"))

    assert await store.update_status(lid, "bogus") is False
    assert await store.update_status("missing", "done") is False
    assert await store.update_status(lid, "dismissed") is True


async def test_due_update_and_expired_survive_reload(tmp_path):
    path = str(tmp_path / "openloops.jsonl")
    s1 = JsonlOpenLoopStore(path=path)
    first = await s1.add_unique(OpenLoop(description="배포 결과 공유 회의 준비", origin_session="s"))
    paraphrase = OpenLoop(description="배포 결과 공유 회의 준비 및 진행", due_ms=1000, origin_session="s")
    assert await s1.add_unique(paraphrase) == first
    other = await s1.add(OpenLoop(description="리뷰 답변", origin_session="s"))
    assert await s1.update_status(other, "expired")

    s2 = JsonlOpenLoopStore(path=path)

    assert [(x.id, x.due_ms) for x in await s2.list_open()] == [(first, 1000)]
    assert (await s2.get(other)).status == "expired"


async def test_agent_survives_reload_and_old_rows_are_main(tmp_path):
    path = tmp_path / "loops.jsonl"
    old = {"id": "old", "description": "옛 약속", "status": "open", "created_at": 1, "updated_at": 1}
    path.write_text(json.dumps(old) + "\n")
    await JsonlOpenLoopStore(path=str(path)).add(OpenLoop(description="뉴스 정리", agent_id="scribe"))

    reloaded = {lp.description: lp.agent_id for lp in await JsonlOpenLoopStore(path=str(path)).all()}

    assert reloaded == {"옛 약속": "main", "뉴스 정리": "scribe"}


async def test_jsonl_update_status_appends_once_per_change(tmp_path):
    path = tmp_path / "loops.jsonl"
    store = JsonlOpenLoopStore(path=str(path))
    await store.add(OpenLoop(id="x", description="약속"))

    assert await store.update_status("x", "done") is True
    assert await store.update_status("x", "bogus") is False
    assert await store.update_status("missing", "done") is False

    assert len(path.read_text(encoding="utf-8").splitlines()) == 2


async def test_vectors_survive_reload_so_a_new_process_does_not_reembed(tmp_path):
    path = tmp_path / "openloops.jsonl"
    first = _CountingEmbedder()
    s1 = JsonlOpenLoopStore(path=str(path), embedder=first)
    await s1.add_unique(OpenLoop(description="참석자 목록 확정", origin_session="s"))
    await s1.add_unique(OpenLoop(description="배포 결과 공유", origin_session="s"))
    lines_after_first = path.read_text().count("\n")
    assert await s1.add_unique(OpenLoop(description="배포 결과 공유", origin_session="s")) is None
    assert path.read_text().count("\n") == lines_after_first

    second = _CountingEmbedder()
    s2 = JsonlOpenLoopStore(path=str(path), embedder=second)
    assert await s2.add_unique(OpenLoop(description="배포 결과 공유", origin_session="s")) is None

    assert sorted(first.texts) == ["배포 결과 공유", "참석자 목록 확정"]
    assert second.texts == []
    assert {x.embedding_model for x in await s2.all()} == {"table"}
    assert all(x.embedding in _CountingEmbedder.table.values() for x in await s2.all())
