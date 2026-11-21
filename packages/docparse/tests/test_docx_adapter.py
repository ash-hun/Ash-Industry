import pytest
from pathlib import Path
from docx import Document as load_docx

from docparse import EditPlan, Replacement, apply, inspect, to_html
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
