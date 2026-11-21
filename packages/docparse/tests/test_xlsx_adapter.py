import pytest
from pathlib import Path
from openpyxl import load_workbook

from docparse import EditPlan, Replacement, TemplateSchema, fill, apply, inspect, to_html
from docparse.adapters.xlsx_adapter import XlsxAdapter, _as_value


def test_inspect_lists_filled_cells_with_addresses(xlsx_path: Path) -> None:
    doc = inspect(xlsx_path)
    table = doc.tables[0]
    assert table.name == "경비" and table.id == "t0"
    cells = {c.id: c for c in table.cells}
    assert cells["t0r1c1"].text == "120000" and cells["t0r1c1"].address == "B2"
    assert cells["t0r2c1"].text == "=SUM(B2:B2)"
    assert cells["t0r4c0"].merged is True
    assert "t0r0c2" not in cells


def test_replace_keeps_numbers_numeric_and_source_untouched(xlsx_path: Path, tmp_path: Path) -> None:
    plan = EditPlan(replacements=(
        Replacement(target="t0r1c1", text="150000"), Replacement(target="t0r1c0", text="숙박비"),
    ))
    out = tmp_path / "out.xlsx"
    after = apply(xlsx_path, plan, out)
    assert after.texts()["t0r1c1"] == "150000" and after.texts()["t0r1c0"] == "숙박비"
    assert load_workbook(str(out))["경비"]["B2"].value == 150000
    assert inspect(xlsx_path).texts()["t0r1c1"] == "120000"


def test_replace_unknown_target_raises(xlsx_path: Path, tmp_path: Path) -> None:
    with pytest.raises(KeyError):
        plan = EditPlan(replacements=(Replacement(target="p0", text=""),))
        XlsxAdapter().replace(xlsx_path, plan, tmp_path / "o.xlsx")


def test_as_value_only_converts_numeric_origins() -> None:
    assert _as_value(1, "2") == 2 and _as_value(1.5, "2.5") == 2.5
    assert _as_value(1, "abc") == "abc" and _as_value("x", "2") == "2" and _as_value(True, "2") == "2"


def test_to_html_escapes_cell_text(tmp_path: Path) -> None:
    from openpyxl import Workbook

    wb = Workbook()
    wb.active["A1"] = "<b>x</b>"
    path = tmp_path / "x.xlsx"
    wb.save(str(path))
    html = to_html(path)
    assert "&lt;b&gt;x&lt;/b&gt;" in html and "<b>x</b>" not in html


def _sheet_schema() -> TemplateSchema:
    return TemplateSchema.model_validate({
        "template_id": "경비-v1", "format": "xlsx", "kind": "blank_form", "source_hash": "h", "fields": [
            {"name": "이름", "locator": {"kind": "placeholder", "token": "{{이름}}"}},
            {"name": "인원", "type": "number", "locator": {"kind": "placeholder", "token": "{{인원}}"}},
            {"name": "비고", "required": False, "locator": {"kind": "placeholder", "token": "{{비고}}"}},
            {"name": "금액", "type": "number", "locator": {"kind": "sheet_cell", "sheet": "신청", "cell": "B2"}},
            {"name": "메모", "required": False, "locator": {"kind": "sheet_cell", "sheet": "신청", "cell": "D1"}},
        ],
    })


def test_fill_writes_numbers_into_empty_cells_and_replaces_tokens(form_xlsx_path: Path, tmp_path: Path) -> None:
    out = tmp_path / "out.xlsx"
    values = {"이름": "홍길동", "인원": "3", "비고": "=1+1", "금액": "150,000", "메모": "=HYPERLINK(\"x\")"}
    fill(form_xlsx_path, _sheet_schema(), values, out)
    ws = load_workbook(str(out))["신청"]
    assert ws["B1"].value == "홍길동" and ws["A3"].value == 3 and ws["B2"].value == 150000
    assert ws["C1"].value == "비고: =1+1" and ws["D1"].value == "=HYPERLINK(\"x\")" and ws["D1"].data_type == "s"
    assert load_workbook(str(form_xlsx_path))["신청"]["B2"].value is None


def test_fill_unknown_sheet_raises(form_xlsx_path: Path, tmp_path: Path) -> None:
    schema = TemplateSchema.model_validate({
        "template_id": "경비-v1", "format": "xlsx", "kind": "blank_form", "source_hash": "h",
        "fields": [{"name": "a", "locator": {"kind": "sheet_cell", "sheet": "없음", "cell": "A1"}}],
    })
    with pytest.raises(KeyError):
        fill(form_xlsx_path, schema, {"a": "x"}, tmp_path / "o.xlsx")
