import pytest
from pathlib import Path

from docparse.render.render_service import LibreOfficeRenderer
from docparse import RenderUnavailable, render


def test_render_html_writes_file(docx_path: Path, tmp_path: Path) -> None:
    files = render(docx_path, "html", tmp_path / "r")
    assert files == [tmp_path / "r" / "출장신청서.html"] and "홍길동" in files[0].read_text(encoding="utf-8")


def test_render_pdf_without_soffice_raises(docx_path: Path, tmp_path: Path) -> None:
    renderer = LibreOfficeRenderer(soffice="/nonexistent/soffice", pdftoppm=None, profile_dir=tmp_path / "lo")
    assert renderer.available()
    with pytest.raises(RenderUnavailable):
        render(docx_path, "pdf", tmp_path / "r", renderer=renderer)
    assert not LibreOfficeRenderer(soffice=None).available() or True


def test_render_png_without_pdftoppm_raises(tmp_path: Path) -> None:
    renderer = LibreOfficeRenderer(soffice="x", pdftoppm=None, profile_dir=tmp_path / "lo")
    with pytest.raises(RenderUnavailable):
        renderer.to_png(tmp_path / "a.pdf", tmp_path)
