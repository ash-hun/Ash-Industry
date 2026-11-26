"""[test] PPTX 어댑터: 도형과 표 id, 서식 유지 치환, 양식 채우기(자리표시자, 도형, 표 칸), HTML 이스케이프."""

import pytest
from pathlib import Path
from pptx.util import Inches
from pptx import Presentation
from pptx.enum.chart import XL_CHART_TYPE
from pptx.chart.data import CategoryChartData

from docparse import EditPlan, Replacement, TemplateSchema, check_locators, verify_fill, fill, apply, inspect, to_html


def _schema(fields: list[dict[str, object]]) -> TemplateSchema:
    return TemplateSchema.model_validate({
        "template_id": "발표-v1", "format": "pptx", "kind": "blank_form", "source_hash": "x", "fields": fields,
    })


def test_inspect_gives_stable_shape_and_table_ids(pptx_path: Path) -> None:
    doc = inspect(pptx_path)
    assert doc == inspect(pptx_path)
    assert doc.format == "pptx" and doc.meta == {"slides": "2"}
    assert [(p.id, p.text) for p in doc.paragraphs] == [
        ("s0sh2p0", "사업 계획 발표"), ("s0sh3p0", "발표자: {{발표자}}"), ("s1sh2p0", "일정"), ("s1sh2p1", "둘째 줄"),
    ]
    assert [r.text for r in doc.paragraphs[1].runs] == ["발표자: ", "{{발", "표자}}"]
    (table,) = doc.tables
    assert (table.id, table.rows, table.cols, table.name) == ("t0", 2, 2, "슬라이드 2")
    assert {c.id: c.text for c in table.cells}["t0r1c1"] == "{{기간}}"


def test_notes_and_chart_text_are_read_only(tmp_path: Path) -> None:
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[5])
    data = CategoryChartData()
    data.categories = ["1분기", "2분기"]
    data.add_series("매출", (10.0, 12.5))
    frame = slide.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, 0, 0, Inches(4), Inches(3), data)
    frame.chart.has_title = True
    frame.chart.chart_title.text_frame.text = "분기 매출"
    slide.notes_slide.notes_text_frame.text = "천천히 말한다"
    path = tmp_path / "차트.pptx"
    prs.save(str(path))
    doc = inspect(path)
    readonly = [(p.id, p.text, p.style) for p in doc.paragraphs if not p.editable]
    chart = f"s0c{frame.shape_id}"
    assert readonly == [
        (f"{chart}p0", "분기 매출", "chart"), (f"{chart}p1", "항목: 1분기, 2분기", "chart"),
        (f"{chart}p2", "매출: 10, 12.5", "chart"), ("s0np0", "천천히 말한다", "notes"),
    ]
    with pytest.raises(KeyError):
        apply(path, EditPlan(replacements=(Replacement(target="s0np0", text="x"),)), tmp_path / "out.pptx")
    assert "천천히 말한다" in to_html(path)


def test_merged_table_cell_carries_span(tmp_path: Path) -> None:
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[5])
    table = slide.shapes.add_table(2, 3, 0, 0, Inches(4), Inches(1)).table
    table.cell(0, 0).merge(table.cell(1, 1))
    path = tmp_path / "병합.pptx"
    prs.save(str(path))
    cells = {c.id: c for c in inspect(path).tables[0].cells}
    assert (cells["t0r0c0"].row_span, cells["t0r0c0"].col_span) == (2, 2)
    assert (cells["t0r0c2"].row_span, cells["t0r0c2"].col_span) == (1, 1)


def test_replace_keeps_first_run_and_source(pptx_path: Path, tmp_path: Path) -> None:
    out = tmp_path / "out.pptx"
    plan = EditPlan(replacements=(
        Replacement(target="s0sh3p0", text="발표자: 김철수"), Replacement(target="t0r0c1", text="3억"),
    ))
    after = apply(pptx_path, plan, out)
    texts = after.texts()
    assert texts["s0sh3p0"] == "발표자: 김철수" and texts["t0r0c1"] == "3억"
    assert [r.text for r in after.paragraphs[1].runs] == ["발표자: 김철수"]
    assert inspect(pptx_path).texts()["s0sh3p0"] == "발표자: {{발표자}}"
    assert apply(pptx_path, plan, tmp_path / "again.pptx").texts() == texts


def test_replace_unknown_target_raises(pptx_path: Path, tmp_path: Path) -> None:
    with pytest.raises(KeyError):
        apply(pptx_path, EditPlan(replacements=(Replacement(target="s0sh99p0", text="x"),)), tmp_path / "o.pptx")


def test_fill_placeholder_shape_and_cell(pptx_path: Path, tmp_path: Path) -> None:
    schema = _schema([
        {"name": "발표자", "locator": {"kind": "placeholder", "token": "{{발표자}}"}},
        {"name": "일정", "locator": {"kind": "shape_text", "slide": 1, "shape": 2}},
        {"name": "예산", "type": "number", "locator": {"kind": "table_cell", "table": 0, "row": 0, "col": 1}},
    ])
    assert check_locators(schema, inspect(pptx_path)) == []
    values = {"발표자": "홍길동", "일정": "12월 첫 주", "예산": "300000000"}
    after = fill(pptx_path, schema, values, tmp_path / "filled.pptx")
    texts = after.texts()
    assert texts["s0sh3p0"] == "발표자: 홍길동" and texts["s1sh2p0"] == "12월 첫 주" and "s1sh2p1" not in texts
    assert texts["t0r0c1"] == "300000000"
    assert verify_fill(after, schema, values).ok
    assert len(Presentation(str(tmp_path / "filled.pptx")).slides) == 2


def test_check_locators_reports_wrong_format_and_missing_shape(pptx_path: Path, docx_path: Path) -> None:
    schema = _schema([
        {"name": "a", "locator": {"kind": "shape_text", "slide": 0, "shape": 99}},
        {"name": "b", "locator": {"kind": "anchor_text", "after": "일정"}},
        {"name": "c", "locator": {"kind": "form_field", "name": "x"}},
    ])
    assert check_locators(schema, inspect(pptx_path)) == [
        "a: 글 도형이 없다 s0sh99", "b: anchor_text 는 DOCX, HWPX 만", "c: form_field 는 PDF 만",
    ]
    assert check_locators(schema, inspect(docx_path))[0] == "a: shape_text 는 PPTX 만"


def test_to_html_escapes(pptx_path: Path, tmp_path: Path) -> None:
    out = tmp_path / "x.pptx"
    apply(pptx_path, EditPlan(replacements=(Replacement(target="s1sh2p0", text="<script>"),)), out)
    page = to_html(out)
    assert "<script>" not in page and "&lt;script&gt;" in page and "슬라이드 2" in page


def test_broken_file_is_value_error(tmp_path: Path) -> None:
    bad = tmp_path / "bad.pptx"
    bad.write_bytes(b"not a zip")
    with pytest.raises(ValueError):
        inspect(bad)
