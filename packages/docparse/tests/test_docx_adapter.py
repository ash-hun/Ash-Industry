import pytest
from pathlib import Path
from docx import Document as load_docx

from docparse import EditPlan, Replacement, TemplateSchema, TemplateValueError, fill, apply, inspect, to_html
from docparse.adapters.docx_adapter import DocxAdapter


def test_inspect_gives_stable_ids_runs_and_cells(docx_path: Path) -> None:
    doc = inspect(docx_path)
    again = inspect(docx_path)
    assert doc == again
    assert doc.format == "docx"
    assert doc.paragraphs[1].text == "신청자: 홍길동"
    assert [r.text for r in doc.paragraphs[1].runs] == ["신청자: ", "홍길동"]
    assert doc.paragraphs[0].style == "Title"
    table = doc.tables[0]
    assert (table.rows, table.cols) == (2, 2)
    cells = {c.id: c for c in table.cells}
    assert cells["t0r0c1"].text == "{{출장기간}}"
    assert [p.id for p in cells["t0r1c1"].paragraphs] == ["t0r1c1p0", "t0r1c1p1"]
    assert doc.texts()["t0r1c1p1"] == "둘째 줄"


def test_replace_keeps_first_run_format_and_leaves_source(docx_path: Path, tmp_path: Path) -> None:
    plan = EditPlan(replacements=(
        Replacement(target="p1", text="신청자: 김철수"),
        Replacement(target="t0r0c1", text="2026-12-03 ~ 2026-12-05"),
        Replacement(target="t0r1c1p1", text="둘째 줄 수정"),
    ))
    out = tmp_path / "out.docx"
    after = apply(docx_path, plan, out)
    texts = after.texts()
    assert texts["p1"] == "신청자: 김철수" and texts["t0r0c1"] == "2026-12-03 ~ 2026-12-05"
    assert texts["t0r1c1"] == "첫 줄\n둘째 줄 수정"
    raw = load_docx(str(out))
    assert raw.paragraphs[1].runs[0].bold is True and len(raw.paragraphs[1].runs) == 1
    assert inspect(docx_path).texts()["p1"] == "신청자: 홍길동"
    assert apply(docx_path, plan, tmp_path / "out2.docx").texts() == texts


def test_replace_whole_cell_collapses_to_one_paragraph(docx_path: Path, tmp_path: Path) -> None:
    plan = EditPlan(replacements=(Replacement(target="t0r1c1", text="한 줄로"),))
    after = apply(docx_path, plan, tmp_path / "out.docx")
    cell = next(c for c in after.tables[0].cells if c.id == "t0r1c1")
    assert cell.text == "한 줄로" and len(cell.paragraphs) == 1


def test_replace_unknown_target_raises(docx_path: Path, tmp_path: Path) -> None:
    with pytest.raises(KeyError):
        plan = EditPlan(replacements=(Replacement(target="x9", text=""),))
        DocxAdapter().replace(docx_path, plan, tmp_path / "o.docx")


def test_to_html_escapes_markup(tmp_path: Path) -> None:
    from docx import Document as new_docx

    doc = new_docx()
    doc.add_paragraph("<script>alert(1)</script>")
    path = tmp_path / "x.docx"
    doc.save(str(path))
    html = to_html(path)
    assert "<script>" not in html and "&lt;script&gt;" in html


def _form_schema(fields: list[dict[str, object]]) -> TemplateSchema:
    return TemplateSchema.model_validate(
        {"template_id": "양식-v1", "format": "docx", "kind": "blank_form", "source_hash": "h", "fields": fields}
    )


FORM_FIELDS: list[dict[str, object]] = [
    {"name": "이름", "locator": {"kind": "placeholder", "token": "{{이름}}"}},
    {"name": "기간", "type": "date_range", "locator": {"kind": "placeholder", "token": "{{기간}}"}},
    {"name": "소속", "locator": {"kind": "anchor_text", "after": "소속:"}},
    {"name": "목적", "type": "long_text", "locator": {"kind": "anchor_text", "after": "출장 목적"}},
    {"name": "금액", "type": "number", "locator": {"kind": "table_cell", "table": 0, "row": 1, "col": 1}},
]
FORM_VALUES = {
    "이름": "홍길동", "기간": "2026-12-03 ~ 2026-12-05", "소속": "기획팀", "목적": "현장 점검\n회의", "금액": 150000,
}


def test_fill_merges_split_token_and_fills_anchor_and_cell(form_docx_path: Path, tmp_path: Path) -> None:
    out = tmp_path / "out.docx"
    after = fill(form_docx_path, _form_schema(FORM_FIELDS), FORM_VALUES, out)
    texts = after.texts()
    assert texts["p0"] == "신청자: 홍길동 님" and texts["p1"] == "소속: 기획팀"
    assert texts["p2"] == "출장 목적" and texts["p3"] == "현장 점검\n회의"
    assert texts["t0r0c1"] == "2026-12-03 ~ 2026-12-05" and texts["t0r1c1"] == "150000"
    runs = load_docx(str(out)).paragraphs[0].runs
    assert [r.text for r in runs] == ["신청자: ", "홍길동", " 님"]
    assert runs[0].bold is True and runs[1].italic is True and not runs[2].italic
    assert inspect(form_docx_path).texts()["p0"] == "신청자: {{이름}} 님"
    assert fill(form_docx_path, _form_schema(FORM_FIELDS), FORM_VALUES, tmp_path / "again.docx").texts() == texts


def test_fill_missing_anchor_or_bad_values_raise(form_docx_path: Path, tmp_path: Path) -> None:
    schema = _form_schema([{"name": "주소", "locator": {"kind": "anchor_text", "after": "주소:"}}])
    with pytest.raises(KeyError):
        fill(form_docx_path, schema, {"주소": "서울"}, tmp_path / "o.docx")
    with pytest.raises(TemplateValueError) as err:
        fill(form_docx_path, _form_schema(FORM_FIELDS), {**FORM_VALUES, "금액": "많이"}, tmp_path / "o.docx")
    assert err.value.issues == ("금액: 숫자가 아니다",)
    assert not (tmp_path / "o.docx").exists()
