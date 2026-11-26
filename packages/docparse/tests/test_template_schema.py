import pytest
from pathlib import Path
from pydantic import ValidationError

from docparse import (
    Document, Paragraph, inspect, render_value, check_locators, validate_values, scan_placeholders,
    schema_from_placeholders,
)
from docparse.template.template_schema import TemplateField, TemplateSchema, build_assignments


def _schema(**overrides: object) -> TemplateSchema:
    fields = [
        {"name": "이름", "locator": {"kind": "placeholder", "token": "{{이름}}"}, "max_chars": 5},
        {"name": "기간", "type": "date_range", "locator": {"kind": "table_cell", "table": 0, "row": 0, "col": 1}},
        {"name": "날짜", "type": "date", "required": False, "locator": {"kind": "anchor_text", "after": "소속:"}},
        {"name": "금액", "type": "number", "locator": {"kind": "table_cell", "table": 0, "row": 1, "col": 1}},
        {"name": "메모", "type": "long_text", "required": False, "max_lines": 2,
         "locator": {"kind": "placeholder", "token": "{{메모}}"}},
    ]
    body = {"template_id": "출장-v1", "format": "docx", "kind": "blank_form", "source_hash": "h", "fields": fields}
    return TemplateSchema.model_validate({**body, **overrides})


def test_scan_placeholders_in_first_appearance_order(form_docx_path: Path) -> None:
    assert scan_placeholders(inspect(form_docx_path)) == ["이름", "기간"]
    doc = Document(path="a", format="docx", paragraphs=(
        Paragraph(id="p0", text="{{b_2}} {{가}} {{b_2}}"), Paragraph(id="p1", text="{{ 공백 }} {{}} {x}"),
    ))
    assert scan_placeholders(doc) == ["b_2", "가"]


def test_scan_placeholders_empty_document() -> None:
    assert scan_placeholders(Document(path="a", format="docx")) == []


def test_schema_from_placeholders_applies_hints(form_docx_path: Path) -> None:
    schema = schema_from_placeholders(
        "양식-v1", inspect(form_docx_path), "abc", hints=[{"name": "기간", "type": "date_range"}], origin="양식.docx",
    )
    assert [(f.name, f.type) for f in schema.fields] == [("이름", "text"), ("기간", "date_range")]
    assert schema.fields[0].locator.model_dump() == {"kind": "placeholder", "token": "{{이름}}"}
    assert schema.format == "docx" and schema.origin == "양식.docx"


def test_schema_from_placeholders_rejects_unknown_hint(form_docx_path: Path) -> None:
    with pytest.raises(ValueError, match="없는 자리표시자"):
        schema_from_placeholders("양식-v1", inspect(form_docx_path), "abc", hints=[{"name": "주소"}])


@pytest.mark.parametrize("override", [
    {"template_id": "../x"}, {"template_id": ".templates"}, {"template_id": "a" * 65}, {"format": "txt"},
    {"fields": []},
])
def test_schema_rejects_bad_ids_and_formats(override: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        _schema(**override)


def test_sheet_cell_address_is_normalized_and_validated() -> None:
    field = TemplateField.model_validate({"name": "a", "locator": {"kind": "sheet_cell", "sheet": "S", "cell": "b2"}})
    assert field.locator.model_dump()["cell"] == "B2"
    with pytest.raises(ValidationError):
        TemplateField.model_validate({"name": "a", "locator": {"kind": "sheet_cell", "sheet": "S", "cell": "A0"}})


def test_validate_values_accepts_good_values() -> None:
    values = {"이름": "홍길동", "기간": "2026-12-03~2026-12-05", "금액": "150,000", "메모": "한 줄\n두 줄"}
    assert validate_values(_schema(), values) == []


def test_validate_values_reports_each_problem() -> None:
    values = {"이름": "홍길동입니다요", "기간": "2026-12-05 ~ 2026-12-03", "날짜": "2026-02-30",
              "금액": "많이", "메모": "1\n2\n3", "주소": "x"}
    assert validate_values(_schema(), values) == [
        "모르는 필드: 주소", "이름: 5자를 넘는다(7자)", "기간: 기간의 시작이 끝보다 늦다", "날짜: 날짜는 YYYY-MM-DD",
        "금액: 숫자가 아니다", "메모: 2줄을 넘는다",
    ]
    assert validate_values(_schema(), {"이름": " ", "금액": True}) == [
        "빠진 필수 필드: 이름", "빠진 필수 필드: 기간", "금액: 숫자가 아니다",
    ]


def test_render_value_normalizes() -> None:
    schema = _schema()
    assert render_value(schema.fields[1], " 2026-12-03~ 2026-12-05 ") == "2026-12-03 ~ 2026-12-05"
    assert render_value(schema.fields[3], "1,500") == "1500" and render_value(schema.fields[3], 2.5) == "2.5"


def test_render_value_blank_and_invalid() -> None:
    assert render_value(_schema().fields[0], None) == ""
    with pytest.raises(ValueError):
        render_value(_schema().fields[3], "x")


def test_build_assignments_types_numbers_and_skips_blank_optional() -> None:
    schema = _schema()
    out = build_assignments(schema, {"이름": "a", "기간": "2026-01-01 ~ 2026-01-02", "금액": "7"})
    assert out[schema.fields[3].locator] == 7
    assert out[schema.fields[4].locator] == ""
    assert schema.fields[2].locator not in out


def test_check_locators_ok_and_reports_missing(form_docx_path: Path) -> None:
    doc = inspect(form_docx_path)
    assert check_locators(_schema(), doc) == ["메모: 문서에 {{메모}} 이 없다"]
    bad = _schema(fields=[
        {"name": "a", "locator": {"kind": "table_cell", "table": 0, "row": 5, "col": 0}},
        {"name": "b", "locator": {"kind": "anchor_text", "after": "주소:"}},
        {"name": "c", "locator": {"kind": "sheet_cell", "sheet": "S", "cell": "A1"}},
    ])
    assert check_locators(bad, doc) == [
        "a: 표 칸이 없다 t0r5c0", "b: 기준 글이 없다 '주소:'", "c: sheet_cell 은 XLSX 만",
    ]


def test_choice_field_takes_checkbox_options_and_checks_value() -> None:
    box = {"kind": "checkbox", "paragraph": "p1", "options": ["예", "아니오"]}
    field = TemplateField.model_validate({"name": "여부", "type": "choice", "locator": box})
    assert field.options == ("예", "아니오")
    schema = _schema(fields=[{"name": "여부", "type": "choice", "locator": box}])
    assert validate_values(schema, {"여부": "예"}) == []
    assert validate_values(schema, {"여부": "모름"}) == ["여부: 선택지 중 하나(예, 아니오)"]


@pytest.mark.parametrize("field", [
    {"name": "a", "type": "text", "locator": {"kind": "checkbox", "paragraph": "p0", "options": ["예"]}},
    {"name": "a", "type": "choice", "locator": {"kind": "anchor_text", "after": "성명:"}},
    {"name": "a", "type": "choice", "options": ["모름"],
     "locator": {"kind": "checkbox", "paragraph": "p0", "options": ["예"]}},
    {"name": "a", "locator": {"kind": "inline_slot", "paragraph": "x1", "label": "성명"}},
])
def test_choice_and_inline_locators_reject_bad_shapes(field: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        TemplateField.model_validate(field)
