"""[test] 빈 양식 필드 탐지: 표 오른쪽과 아래 빈 칸, 본문 기준 글, XLSX 빈 칸, 형식과 이름 추측."""

import unicodedata
from pathlib import Path
from openpyxl import Workbook
from docx import Document as new_docx

from docparse import Document, FormField, Paragraph, inspect, detect_fields, suggest_template_id
from docparse.template.field_detect import field_name, guess_type


def _summary(doc: Document) -> list[tuple[str, str, dict[str, object], str, str]]:
    return [(c.name, c.type, c.locator.model_dump(), c.rule, c.confidence) for c in detect_fields(doc)]


def _table_docx(tmp_path: Path, rows: list[list[str]]) -> Document:
    doc = new_docx()
    table = doc.add_table(rows=len(rows), cols=len(rows[0]))
    for r, row in enumerate(rows):
        for c, text in enumerate(row):
            table.cell(r, c).text = text
    path = tmp_path / "표.docx"
    doc.save(str(path))
    return inspect(path)


def _body(*texts: str) -> Document:
    paragraphs = tuple(Paragraph(id=f"p{i}", text=t) for i, t in enumerate(texts))
    return Document(path="a", format="docx", paragraphs=paragraphs)


def test_table_right_blank_cells(tmp_path: Path) -> None:
    long_label = "출장 중 있었던 일을 자세히 적어 주시기 바랍니다."
    doc = _table_docx(tmp_path, [["성명", ""], ["신청 금액", " "], [long_label, ""]])
    assert _summary(doc) == [
        ("성명", "text", {"kind": "table_cell", "table": 0, "row": 0, "col": 1}, "table_right", "high"),
        ("신청금액", "number", {"kind": "table_cell", "table": 0, "row": 1, "col": 1}, "table_right", "high"),
        (field_name(long_label), "text", {"kind": "table_cell", "table": 0, "row": 2, "col": 1},
         "table_right", "low"),
    ]
    assert detect_fields(doc) == detect_fields(doc)


def test_table_right_filled_or_placeholder_is_skipped(form_docx_path: Path, tmp_path: Path) -> None:
    assert _summary(_table_docx(tmp_path, [["성명", "홍길동"]])) == []
    assert [(c.name, c.locator.model_dump()) for c in detect_fields(inspect(form_docx_path))] == [
        ("금액", {"kind": "table_cell", "table": 0, "row": 1, "col": 1}),
    ]


def test_table_below_header_row(tmp_path: Path) -> None:
    doc = _table_docx(tmp_path, [["성명", "신청 일자"], ["", ""]])
    assert _summary(doc) == [
        ("성명", "text", {"kind": "table_cell", "table": 0, "row": 1, "col": 0}, "table_below", "low"),
        ("신청일자", "date", {"kind": "table_cell", "table": 0, "row": 1, "col": 1}, "table_below", "low"),
    ]


def test_table_below_filled_gives_nothing(tmp_path: Path) -> None:
    assert _summary(_table_docx(tmp_path, [["성명", "소속"], ["홍길동", "총무팀"]])) == []


def test_merged_cells_are_not_duplicated(tmp_path: Path) -> None:
    doc = new_docx()
    wide = doc.add_table(rows=1, cols=3)
    wide.cell(0, 0).merge(wide.cell(0, 1)).text = "성명"
    tall = doc.add_table(rows=2, cols=2)
    tall.cell(0, 0).merge(tall.cell(1, 0)).text = "주소"
    path = tmp_path / "병합.docx"
    doc.save(str(path))
    assert [(c.name, c.locator.model_dump()) for c in detect_fields(inspect(path))] == [
        ("성명", {"kind": "table_cell", "table": 0, "row": 0, "col": 2}),
        ("주소", {"kind": "table_cell", "table": 1, "row": 0, "col": 1}),
    ]


def test_hwpx_anchor_and_merged_table(hwpx_path: Path) -> None:
    assert [(c.name, c.type, c.locator.model_dump()) for c in detect_fields(inspect(hwpx_path))] == [
        ("성명", "text", {"kind": "anchor_text", "after": "성명:"}),
        ("금액", "number", {"kind": "table_cell", "table": 0, "row": 1, "col": 1}),
        ("비고", "long_text", {"kind": "table_cell", "table": 1, "row": 0, "col": 1}),
    ]


def test_anchor_text_blank_underscores_and_full_width_colon() -> None:
    doc = _body("성명:", "", "  연락처 ： ____", "생년월일: ＿＿ ")
    assert [(c.name, c.type, c.locator.model_dump()) for c in detect_fields(doc)] == [
        ("성명", "text", {"kind": "anchor_text", "after": "성명:"}),
        ("연락처", "text", {"kind": "anchor_text", "after": "연락처 ："}),
        ("생년월일", "date", {"kind": "anchor_text", "after": "생년월일:"}),
    ]


def test_anchor_text_skips_unsafe_paragraphs() -> None:
    doc = _body("대표자 성명: 홍길동", "성명:", "소속:", "비고: {{비고}}", "참고:")
    assert detect_fields(doc) == []


def test_sheet_right_blank_cell(xlsx_path: Path) -> None:
    assert _summary(inspect(xlsx_path)) == [
        ("금액", "number", {"kind": "sheet_cell", "sheet": "경비", "cell": "C1"}, "sheet_right", "high"),
        ("비고", "long_text", {"kind": "sheet_cell", "sheet": "경비", "cell": "C5"}, "sheet_right", "high"),
    ]


def test_sheet_uses_blank_merge_and_skips_covered(tmp_path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "신청"
    ws["A1"] = "성명"
    ws.merge_cells("B1:C1")
    ws["A2"] = "주소"
    ws["A3"] = "연락처"
    ws.merge_cells("B2:B3")
    ws["B2"] = 12345
    path = tmp_path / "병합.xlsx"
    wb.save(str(path))
    assert [(c.name, c.locator.model_dump()) for c in detect_fields(inspect(path))] == [
        ("성명", {"kind": "sheet_cell", "sheet": "신청", "cell": "B1"}),
    ]


def test_table_right_and_below_follow_merge_span(tmp_path: Path) -> None:
    doc = new_docx()
    table = doc.add_table(rows=3, cols=3)
    table.cell(0, 0).merge(table.cell(0, 1)).text = "성명"
    table.cell(1, 0).merge(table.cell(2, 0)).text = "주소"
    table.cell(1, 1).text = "도로명"
    table.cell(1, 2).text = "서울"
    table.cell(2, 2).text = "확인"
    path = tmp_path / "병합.docx"
    doc.save(str(path))
    cells = {c.id: c for c in inspect(path).tables[0].cells}
    assert (cells["t0r0c0"].col_span, cells["t0r1c0"].row_span) == (2, 2)
    assert [(c.name, c.locator.model_dump(), c.rule) for c in detect_fields(inspect(path))] == [
        ("성명", {"kind": "table_cell", "table": 0, "row": 0, "col": 2}, "table_right"),
        ("도로명", {"kind": "table_cell", "table": 0, "row": 2, "col": 1}, "table_below"),
    ]


def test_sheet_skips_filled_placeholder_and_numbers(form_xlsx_path: Path) -> None:
    assert [(c.name, c.locator.model_dump()) for c in detect_fields(inspect(form_xlsx_path))] == [
        ("금액", {"kind": "sheet_cell", "sheet": "신청", "cell": "B2"}),
    ]


def test_names_are_cleaned_and_deduplicated() -> None:
    doc = _body("성 명:", "", "성명 ：", "", "(*):", "")
    assert [c.name for c in detect_fields(doc)] == ["성명", "성명_2"]
    assert field_name("※ (주)소속!") == "주소속" and field_name("::") == "field"


def test_candidate_converts_to_template_field() -> None:
    field = detect_fields(_body("사업 기간:", ""))[0].to_field()
    assert (field.name, field.type, field.required) == ("사업기간", "date_range", True)


def test_guess_type_words() -> None:
    assert [guess_type(w) for w in ("사업기간", "작성일자", "총액", "신청 사유", "성명")] == [
        "date_range", "date", "number", "long_text", "text",
    ]


def test_suggest_template_id() -> None:
    assert suggest_template_id("sub/출장 신청서(2026).docx") == "출장_신청서_2026-v1"
    assert suggest_template_id(unicodedata.normalize("NFD", "출장.hwpx")) == "출장-v1"
    assert suggest_template_id("ᄎ...hwpx") == "form-v1"


def test_pdf_checkbox_becomes_choice_and_box_cell_is_not_label(tmp_path: Path) -> None:
    pdf = Document(path="a.pdf", format="pdf", fields=(
        FormField(id="f:agree", name="agree", value="", kind="checkbox", options=("/Yes", "/Off")),
        FormField(id="f:sig", name="sig", value="", kind="checkbox"),
    ))
    assert [(c.name, c.type, c.options) for c in detect_fields(pdf)] == [("agree", "choice", ("/Yes", "/Off"))]
    doc = _table_docx(tmp_path, [["□ 예 □ 아니오", ""]])
    assert [c.rule for c in detect_fields(doc)] == ["checkbox"]
