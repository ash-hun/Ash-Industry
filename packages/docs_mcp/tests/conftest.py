"""docs MCP 테스트: 임시 문서 폴더에 작은 DOCX 하나."""

import pytest
from pathlib import Path
from datetime import datetime
from docx import Document as new_docx

from docs_mcp.docs_server import DocsService
from docs_mcp.docs_paths import DocsPaths


@pytest.fixture
def root(tmp_path: Path) -> Path:
    docs = tmp_path / "documents"
    (docs / "sub").mkdir(parents=True)
    doc = new_docx()
    doc.add_paragraph("제목")
    doc.add_paragraph("본문 {{이름}}")
    doc.save(str(docs / "sub" / "a.docx"))
    (docs / "memo.txt").write_text("x")
    (docs / ".render").mkdir()
    (docs / ".render" / "b.docx").write_bytes(b"")
    return docs


class FakeRenderer:
    """LibreOffice, pdftoppm 대신 빈 파일을 쓴다. 쓰기 도구의 미리보기 경로만 본다."""

    def to_pdf(self, path: Path, out_dir: Path) -> Path:
        target = out_dir / f"{path.stem}.pdf"
        target.write_bytes(b"%PDF")
        return target

    def to_png(self, pdf: Path, out_dir: Path) -> list[Path]:
        target = out_dir / f"{pdf.stem}-1.png"
        target.write_bytes(b"png")
        return [target]


@pytest.fixture
def service(root: Path) -> DocsService:
    clock = iter([datetime(2026, 11, 16, 9, 0, 0), datetime(2026, 11, 16, 9, 0, 1)])
    return DocsService(DocsPaths(root), clock=lambda: next(clock), renderer=FakeRenderer())
