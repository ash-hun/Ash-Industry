"""notify: sent_store 가 보낸 키를 jsonl 로 남겨 재시작 뒤에도 기억하고, 상한과 TTL 로 파일이 자라지 않는지 검증."""

import json

from ash_industry.core.notify.sent_store import SentStore


async def test_sent_store_persists_keys_across_instances(tmp_path):
    path = tmp_path / "notify_sent.jsonl"
    store = SentStore(str(path))

    await store.add("k1", 100.0)
    reopened = SentStore(str(path))

    assert await reopened.contains("k1", 101.0) is True
    assert await reopened.contains("k2", 101.0) is False
    assert json.loads(path.read_text().splitlines()[0]) == {"key": "k1", "ts": 100.0}


async def test_sent_store_memory_only_and_ttl(tmp_path):
    memory = SentStore(None, ttl_sec=10.0)

    await memory.add("k1", 100.0)

    assert await memory.contains("k1", 105.0) is True
    assert await memory.contains("k1", 111.0) is False  # TTL 이 지나면 잊는다
    assert not list(tmp_path.iterdir())


async def test_sent_store_compacts_the_file_at_twice_the_cap(tmp_path):
    path = tmp_path / "notify_sent.jsonl"
    store = SentStore(str(path), max_keys=3)

    for i in range(6):
        await store.add(f"k{i}", float(i))

    lines = [json.loads(line)["key"] for line in path.read_text().splitlines()]
    assert lines == ["k3", "k4", "k5"] and len(store) == 3
    assert await store.contains("k0", 6.0) is False and await store.contains("k5", 6.0) is True
    assert not path.with_suffix(".jsonl.tmp").exists()


async def test_sent_store_skips_broken_lines_and_compacts_on_load(tmp_path):
    path = tmp_path / "notify_sent.jsonl"
    rows = [json.dumps({"key": f"k{i}", "ts": float(i)}) for i in range(6)]
    path.write_text("\n".join([*rows[:3], "not json", *rows[3:]]) + "\n")

    store = SentStore(str(path), max_keys=3)

    assert await store.contains("k5", 6.0) is True
    assert await store.contains("k0", 6.0) is False
    assert len(path.read_text().splitlines()) == 3
