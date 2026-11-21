"""[test] PDF 어댑터: 쪽 글 줄과 폼 필드 읽기, 폼 필드 채우기, 본문 고치기 거부, 렌더 사본."""

import pytest
from pathlib import Path

from docparse import (
    EditPlan, Replacement, TemplateSchema, check_locators, detect_fields, verify_fill, fill, apply, inspect, render,
    to_html,
)
from docparse.render.render_service import LibreOfficeRenderer


def _schema(fields: list[dict[str, object]]) -> TemplateSchema:
    return TemplateSchema.model_validate({
        "template_id": "휴가-v1", "format": "pdf", "kind": "blank_form", "source_hash": "x", "fields": fields,
    })


def test_inspect_lines_and_fields(pdf_form_path: Path) -> None:
    doc = inspect(pdf_form_path)
    assert doc == inspect(pdf_form_path)
    assert doc.meta == {"pages": "1"}
    assert [(p.id, p.text) for p in doc.paragraphs] == [("pg1p0", "Leave Request"), ("pg1p1", "Name:")]
    assert [(f.id, f.name, f.kind, f.page, f.value) for f in doc.fields] == [
        ("f:date", "date", "text", 1, ""), ("f:name", "name", "text", 1, ""),
    ]


def test_fill_form_fields_and_verify(pdf_form_path: Path, tmp_path: Path) -> None:
    schema = _schema([
        {"name": "성명", "locator": {"kind": "form_field", "name": "name"}},
        {"name": "신청일자", "type": "date", "locator": {"kind": "form_field", "name": "date"}},
    ])
    assert check_locators(schema, inspect(pdf_form_path)) == []
    values = {"성명": "홍길동", "신청일자": "2026-12-01"}
    after = fill(pdf_form_path, schema, values, tmp_path / "filled.pdf")
    assert {f.name: f.value for f in after.fields} == {"name": "홍길동", "date": "2026-12-01"}
    assert verify_fill(after, schema, values).ok
    assert {f.value for f in inspect(pdf_form_path).fields} == {""}


def test_fill_unknown_field_and_body_edit_are_refused(pdf_form_path: Path, tmp_path: Path) -> None:
    schema = _schema([{"name": "x", "locator": {"kind": "form_field", "name": "nope"}}])
    assert check_locators(schema, inspect(pdf_form_path)) == ["x: 폼 필드가 없다 nope"]
    with pytest.raises(KeyError):
        fill(pdf_form_path, schema, {"x": "a"}, tmp_path / "o.pdf")
    with pytest.raises(ValueError):
        apply(pdf_form_path, EditPlan(replacements=(Replacement(target="pg1p0", text="x"),)), tmp_path / "o.pdf")


def test_detect_fields_gives_form_fields(pdf_form_path: Path) -> None:
    found = detect_fields(inspect(pdf_form_path))
    assert [(c.name, c.rule, c.confidence, c.locator.model_dump()) for c in found] == [
        ("date", "form_field", "high", {"kind": "form_field", "name": "date"}),
        ("name", "form_field", "high", {"kind": "form_field", "name": "name"}),
    ]


def test_render_pdf_copies_into_render_dir_without_soffice(pdf_form_path: Path, tmp_path: Path) -> None:
    renderer = LibreOfficeRenderer(soffice="/nonexistent/soffice", pdftoppm=None)
    out = tmp_path / "r"
    files = render(pdf_form_path, "pdf", out, renderer=renderer)
    assert files == [out / "휴가신청.pdf"] and files[0].read_bytes() == pdf_form_path.read_bytes()
    assert render(pdf_form_path, "pdf", out, renderer=renderer) == files


def test_to_html_lists_lines_and_fields(pdf_form_path: Path) -> None:
    page = to_html(pdf_form_path)
    assert "1쪽" in page and "Name:" in page and "<td>name</td>" in page


def test_broken_pdf_is_value_error(tmp_path: Path) -> None:
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"not a pdf")
    with pytest.raises(ValueError):
        inspect(bad)
