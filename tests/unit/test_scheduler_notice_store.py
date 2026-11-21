"""scheduler 의 알림 보류 큐: 메모리 큐의 보류, 자연 키 중복 제거, 상한, 비우기를 검증한다."""

from ash_industry.core.scheduler.notice_store import PendingNoticeStore, notice_key


def _notice(nid: str, text: str = "물 마시기") -> dict[str, object]:
    return {"type": "reminder", "id": nid, "name": "water", "text": text, "fired_at": "2026-01-01T09:00:00"}


def test_notice_key_prefers_id_then_name_and_fired_at():
    assert notice_key(_notice("n1")) == "n1"
    assert notice_key({"name": "water", "fired_at": "t"}) == "water@t"


async def test_push_then_drain_returns_oldest_first_and_empties():
    store = PendingNoticeStore()
    await store.push(_notice("n1"))
    await store.push(_notice("n2"))

    assert [n["id"] for n in await store.drain()] == ["n1", "n2"]
    assert await store.drain() == []


async def test_push_same_notice_twice_keeps_one_and_limit_drops_oldest():
    store = PendingNoticeStore(limit=2)
    await store.push(_notice("n1"))
    await store.push(_notice("n1", "다시"))
    assert [n["text"] for n in await store.drain()] == ["다시"]

    for nid in ("a", "b", "c"):
        await store.push(_notice(nid))
    assert [n["id"] for n in await store.drain()] == ["b", "c"]
