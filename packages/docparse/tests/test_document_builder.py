"""[test] 새 문서 만들기: 형식별로 쓴 내용을 다시 읽어 확인하고, 맞지 않는 내용과 있는 파일은 거절한다."""

import pytest
from pathlib import Path
from pptx import Presentation
from openpyxl import load_workbook

from docparse import Block, DocumentSpec, SheetSpec, SlideSpec, create, inspect


def test_docx_blocks_round_trip(tmp_path: Path) -> None:
    spec = DocumentSpec(title="주간 보고", blocks=[
        Block(type="heading", text="요약", level=1),
        Block(type="paragraph", text="이번 주는 배포를 마쳤다."),
        Block(type="bullets", items=["문서 창", "레이아웃 저장"]),
        Block(type="table", rows=[["항목", "상태"], ["배포", "완료"]]),
    ])
    doc = inspect(create(spec, tmp_path / "out" / "보고.docx"))
    texts = [p.text for p in doc.paragraphs]
    assert texts == ["주간 보고", "요약", "이번 주는 배포를 마쳤다.", "문서 창", "레이아웃 저장"]
    assert doc.paragraphs[3].style == "List Bullet"
    assert [c.text for c in doc.tables[0].cells] == ["항목", "상태", "배포", "완료"]


def test_pptx_cover_bullets_table_and_notes(tmp_path: Path) -> None:
    spec = DocumentSpec(slides=[
        SlideSpec(title="사업 계획", subtitle="2026 하반기"),
        SlideSpec(title="목표", bullets=["매출 두 배", "팀 확장"], notes="천천히 말한다"),
        SlideSpec(title="일정", table=[["단계", "기간"], ["준비", "12월"]]),
    ])
    out = create(spec, tmp_path / "계획.pptx")
    doc = inspect(out)
    assert doc.meta == {"slides": "3"}
    assert [p.text for p in doc.paragraphs] == [
        "사업 계획", "2026 하반기", "목표", "매출 두 배", "팀 확장", "천천히 말한다", "일정",
    ]
    assert [p.id for p in doc.paragraphs if not p.editable] == ["s1np0"]
    assert [c.text for c in doc.tables[0].cells] == ["단계", "기간", "준비", "12월"]
    assert Presentation(str(out)).slides[1].notes_slide.notes_text_frame.text == "천천히 말한다"


def test_xlsx_sheets_keep_value_types(tmp_path: Path) -> None:
    spec = DocumentSpec(sheets=[
        SheetSpec(name="예산", rows=[["항목", "금액"], ["출장", 150000], ["합계", None]]),
        SheetSpec(name="메모", rows=[["확정", True]]),
    ])
    wb = load_workbook(create(spec, tmp_path / "예산.xlsx"))
    assert wb.sheetnames == ["예산", "메모"]
    assert wb["예산"]["B2"].value == 150000 and wb["메모"]["B1"].value is True


@pytest.mark.parametrize(("name", "spec", "issue"), [
    ("a.hwpx", DocumentSpec(title="x"), "새로 만들 수 있는 형식"),
    ("a.docx", DocumentSpec(slides=[SlideSpec(title="x")]), "slides 를 쓰지 않는다"),
    ("a.pptx", DocumentSpec(), "slides 가 없다"),
    ("a.pptx", DocumentSpec(slides=[SlideSpec(title="x", bullets=["a"], table=[["b"]])]), "함께 넣지 않는다"),
    ("a.docx", DocumentSpec(blocks=[Block(type="bullets")]), "items 가 없다"),
    ("a.xlsx", DocumentSpec(sheets=[SheetSpec(name="s"), SheetSpec(name="s")]), "시트 이름이 겹친다"),
])
def test_mismatched_spec_is_refused_without_file(tmp_path: Path, name: str, spec: DocumentSpec, issue: str) -> None:
    with pytest.raises(ValueError, match=issue):
        create(spec, tmp_path / name)
    assert not (tmp_path / name).exists()


def test_existing_file_is_not_overwritten(tmp_path: Path) -> None:
    target = tmp_path / "a.docx"
    target.write_bytes(b"keep")
    with pytest.raises(FileExistsError):
        create(DocumentSpec(title="x"), target)
    assert target.read_bytes() == b"keep"


def test_failed_write_leaves_no_file(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        create(DocumentSpec(sheets=[SheetSpec(name="a/b")]), tmp_path / "a.xlsx")
    assert not (tmp_path / "a.xlsx").exists()
