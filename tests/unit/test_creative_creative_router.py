"""creative_router: 워크스페이스 안 미디어 파일만 내주고, 밖이거나 미디어가 아니면 404."""

from fastapi import FastAPI
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from ash_industry.ui.web.router.creative_router import build_creative_router, resolve_media
from ash_industry.ash_config import AshSettings


def _client(tmp_path):
    settings = AshSettings()
    settings.creative.dir = str(tmp_path)
    state = MagicMock()
    state.settings = settings
    app = FastAPI()
    app.include_router(build_creative_router(state))
    return TestClient(app)


def test_resolve_media_keeps_to_media_inside_the_root(tmp_path):
    (tmp_path / "out").mkdir()
    (tmp_path / "out" / "a.mp4").write_bytes(b"x")
    (tmp_path / "out" / "a.json").write_text("{}")
    assert resolve_media(tmp_path, "out/a.mp4") == (tmp_path / "out" / "a.mp4").resolve()
    for bad in ("out/a.json", "../a.mp4", "/out/a.mp4", "~/a.mp4", "out/missing.mp4", ""):
        assert resolve_media(tmp_path, bad) is None


def test_media_file_route_serves_with_media_type_and_404s_otherwise(tmp_path):
    (tmp_path / "out" / "manim").mkdir(parents=True)
    (tmp_path / "out" / "manim" / "Hello.mp4").write_bytes(b"\x00\x00movie")
    client = _client(tmp_path)

    ok = client.get("/api/creative/files/out/manim/Hello.mp4")
    missing = client.get("/api/creative/files/out/manim/Nope.mp4")
    outside = client.get("/api/creative/files/..%2Fsecret.mp4")

    assert ok.status_code == 200 and ok.headers["content-type"].startswith("video/mp4")
    assert ok.content.endswith(b"movie")
    assert missing.status_code == 404 and outside.status_code == 404
