"""docs_router: 문서 폴더의 .render/ 안 png, pdf 만 내주고, 원본 문서와 밖은 404."""

from fastapi import FastAPI
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from ash_industry.ui.web.router.docs_router import resolve_render, build_docs_router
from ash_industry.ash_config import AshSettings


def _client(tmp_path):
    settings = AshSettings()
    settings.docs.dir = str(tmp_path)
    state = MagicMock()
    state.settings = settings
    app = FastAPI()
    app.include_router(build_docs_router(state))
    return TestClient(app)


def _tree(tmp_path):
    (tmp_path / ".render" / "a").mkdir(parents=True)
    (tmp_path / ".render" / "a" / "a-1.png").write_bytes(b"\x89PNGpage")
    (tmp_path / ".render" / "a" / "a.pdf").write_bytes(b"%PDF-1.7")
    (tmp_path / ".render" / "a" / "a.html").write_text("<p>x</p>")
    (tmp_path / "a.docx").write_bytes(b"doc")
    (tmp_path / "secret.png").write_bytes(b"x")


def test_resolve_render_only_png_and_pdf_under_render(tmp_path):
    _tree(tmp_path)
    assert resolve_render(tmp_path, ".render/a/a-1.png") == (tmp_path / ".render" / "a" / "a-1.png").resolve()
    assert resolve_render(tmp_path, ".render/a/a.pdf") is not None
    for bad in (".render/a/a.html", "a.docx", "secret.png", ".render/../secret.png", ".render/a/none.png", ""):
        assert resolve_render(tmp_path, bad) is None


def test_render_file_route_serves_with_media_type_and_404s_otherwise(tmp_path):
    _tree(tmp_path)
    client = _client(tmp_path)

    png = client.get("/api/docs/files/.render/a/a-1.png")
    pdf = client.get("/api/docs/files/.render/a/a.pdf")
    source = client.get("/api/docs/files/a.docx")
    outside = client.get("/api/docs/files/.render%2F..%2Fsecret.png")

    assert png.status_code == 200 and png.headers["content-type"] == "image/png" and png.content.endswith(b"page")
    assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf"
    assert source.status_code == 404 and outside.status_code == 404
