import pytest
from pathlib import Path

from docs_mcp.template_store import TemplateStore, TemplateConflict, source_hash, fill_id_for
from docparse import TemplateSchema


def _schema(digest: str) -> TemplateSchema:
    return TemplateSchema.model_validate({
        "template_id": "출장신청서-v1", "format": "docx", "kind": "placeholder", "source_hash": digest,
        "origin": "a.docx", "fields": [{"name": "이름", "locator": {"kind": "placeholder", "token": "{{이름}}"}}],
    })


def test_register_twice_returns_existing_and_copies_source(tmp_path: Path) -> None:
    source = tmp_path / "a.docx"
    source.write_bytes(b"one")
    store = TemplateStore(tmp_path / ".templates")
    schema = _schema(source_hash(source))
    assert store.register(schema, source) == (schema, True)
    assert store.register(schema, source) == (schema, False)
    assert store.source(schema).read_bytes() == b"one" and store.list_all() == [schema]
    stored = tmp_path / ".templates" / "출장신청서-v1"
    assert sorted(p.name for p in stored.iterdir()) == ["schema.json", "source.docx"]


def test_register_changed_source_asks_for_new_id(tmp_path: Path) -> None:
    source = tmp_path / "a.docx"
    source.write_bytes(b"one")
    store = TemplateStore(tmp_path / ".templates")
    store.register(_schema(source_hash(source)), source)
    source.write_bytes(b"two")
    with pytest.raises(TemplateConflict, match="새 버전 id"):
        store.register(_schema(source_hash(source)), source)
    assert store.source(_schema("x")).read_bytes() == b"one"


def test_fill_record_is_written_once(tmp_path: Path) -> None:
    store = TemplateStore(tmp_path)
    assert store.put_fill("a-v1", "f1", {"path": "first"}) == {"path": "first"}
    assert store.put_fill("a-v1", "f1", {"path": "second"}) == {"path": "first"}
    assert store.get_fill("a-v1", "f2") is None


def test_fill_id_ignores_key_order_and_rejects_bad_ids(tmp_path: Path) -> None:
    assert fill_id_for("a", "h", {"x": 1, "y": "가"}) == fill_id_for("a", "h", {"y": "가", "x": 1})
    assert fill_id_for("a", "h", {"x": 1}) != fill_id_for("a", "h2", {"x": 1})
    store = TemplateStore(tmp_path)
    with pytest.raises(ValueError):
        store.get("../x")
    assert store.list_all() == [] and store.get("없음") is None
