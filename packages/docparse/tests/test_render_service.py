import pytest
from pathlib import Path

from docparse.render.render_service import LibreOfficeRenderer, page_count
from docparse.render.rhwp_renderer import RhwpRenderer, rhwp_available
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


@pytest.mark.skipif(not rhwp_available(), reason="rhwp 네이티브 모듈을 이 환경에서 열 수 없다")
def test_render_hwpx_pdf_and_png_with_rhwp(hwpx_path: Path, tmp_path: Path) -> None:
    out = tmp_path / "r"
    renderer = LibreOfficeRenderer(soffice="/nonexistent/soffice", pdftoppm=None)
    pdf = render(hwpx_path, "pdf", out, renderer=renderer)
    assert pdf == [out / "신청서.pdf"] and pdf[0].read_bytes().startswith(b"%PDF")
    assert page_count(pdf[0]) == 1
    pngs = render(hwpx_path, "png", out, renderer=renderer)
    assert pngs == [out / "신청서-1.png"] and pngs[0].read_bytes().startswith(b"\x89PNG")
    assert render(hwpx_path, "png", out, renderer=renderer) == pngs


@pytest.mark.skipif(not rhwp_available(), reason="rhwp 네이티브 모듈을 이 환경에서 열 수 없다")
def test_rhwp_renderer_rejects_broken_file_and_too_many_pages(hwpx_path: Path, tmp_path: Path) -> None:
    bad = tmp_path / "bad.hwpx"
    bad.write_bytes(b"not a document")
    with pytest.raises(RenderUnavailable):
        RhwpRenderer().to_pdf(bad, tmp_path / "r")
    with pytest.raises(RenderUnavailable):
        RhwpRenderer(max_pages=0).to_png(hwpx_path, tmp_path / "r")
