"""upload: upload_store 가 이름을 정리하고 같은 내용은 한 파일로 두며 id 로 찾고 그림 대상 이미지를 가리는지 검증."""

import pytest

from ash_industry.app.upload_store import MAX_IMAGE_BYTES, UploadStore, UploadTooLarge, describe, kind_of, safe_name


@pytest.mark.parametrize(
    ("raw", "safe"),
    [("../../etc/passwd", "passwd"), ("보고서 최종(2).hwpx", "보고서_최종_2_.hwpx"), (".env", "env"), ("", "file")],
)
def test_safe_name_strips_paths_and_unsafe_characters(raw, safe):
    assert safe_name(raw) == safe


def test_save_is_idempotent_and_find_returns_the_same_upload(tmp_path):
    store = UploadStore(tmp_path)
    first = store.save("a.png", [b"\x89PNG", b"data"], "image/png")
    again = store.save("a.png", [b"\x89PNGdata"], "image/png")

    assert first == again and store.find(first.id) == first
    assert [p.name for p in (tmp_path / "uploads").iterdir()] == [f"{first.id}-a.png"]
    assert store.image_base64(first) is not None
    assert "[첨부] a.png | 경로 uploads/" in describe([first])


def test_find_rejects_bad_ids_and_large_or_non_images_are_not_pictures(tmp_path, monkeypatch):
    store = UploadStore(tmp_path)
    doc = store.save("명단.xlsx", [b"PK"])
    big = store.save("big.png", [b"x" * (MAX_IMAGE_BYTES + 1)], "image/png")

    assert store.find("../uploads") is None and store.find("0" * 12) is None
    assert doc.kind == "document" and store.image_base64(doc) is None and store.image_base64(big) is None
    assert kind_of("video/mp4", "a.mp4") == "video" and kind_of("application/zip", "a.zip") == "other"
    monkeypatch.setattr("ash_industry.app.upload_store.MAX_BYTES", 4)
    with pytest.raises(UploadTooLarge):
        store.save("x.bin", [b"12345"])


def test_purge_removes_files_past_ttl_and_reupload_restarts_the_clock(tmp_path):
    import os

    store = UploadStore(tmp_path)
    old = store.save("old.txt", [b"old"])
    kept = store.save("kept.txt", [b"kept"])
    day_ago = 1_000_000.0 - 86_400
    for upload in (old, kept):
        os.utime(tmp_path / upload.path, (day_ago, day_ago))
    store.save("kept.txt", [b"kept"])

    now = (tmp_path / kept.path).stat().st_mtime + 60
    assert store.purge(now, 86_400) == [f"{old.id}-old.txt"]
    assert store.purge(now, 86_400) == []
    assert store.find(old.id) is None and store.find(kept.id) == kept
    assert UploadStore(tmp_path / "none").purge(now, 1) == []
