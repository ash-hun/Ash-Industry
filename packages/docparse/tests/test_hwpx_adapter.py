"""[test] HWPX 어댑터: id, 서식 유지 치환, 양식 채우기, HWP 읽기, HTML 이스케이프."""

import pytest
from pathlib import Path
from hwpx import HwpxDocument

from docparse import EditPlan, Replacement, TemplateSchema, check_locators, fill, apply, inspect, to_html
from docparse.adapters.hwpx_adapter import HwpxAdapter


def _runs(path: Path, index: int) -> list[tuple[str, str | None, bool | None]]:
    with HwpxDocument.open(path) as doc:
        return [(r.text, r.char_pr_id_ref, r.bold) for r in doc.paragraphs[index].runs]


def _kinds(path: Path, index: int) -> set[str]:
    with HwpxDocument.open(path) as doc:
        return {k for r in doc.paragraphs[index].runs for k in r.content_kinds()}


def test_inspect_gives_stable_ids_runs_and_cells(hwpx_path: Path) -> None:
    doc = inspect(hwpx_path)
    assert doc == inspect(hwpx_path)
    assert doc.format == "hwpx" and doc.meta == {}
    assert doc.paragraphs[1].text == "신청자: {{이름}} 님"
    assert [(r.id, r.text) for r in doc.paragraphs[1].runs] == [
        ("p1.0", "신청자: "), ("p1.1", "{{이"), ("p1.2", "름}}"), ("p1.3", " 님"),
    ]
    first, merged = doc.tables
    assert (first.id, first.rows, first.cols) == ("t0", 2, 2)
    cells = {c.id: c for c in first.cells}
    assert cells["t0r0c1"].text == "{{기간}}" and [p.id for p in cells["t0r0c1"].paragraphs] == ["t0r0c1p0"]
    assert [c.id for c in merged.cells if c.merged] == ["t1r0c1"]
    assert "t1r0c2" not in {c.id for c in merged.cells}


def test_replace_keeps_first_run_format_and_leaves_source(hwpx_path: Path, tmp_path: Path) -> None:
    plan = EditPlan(replacements=(
        Replacement(target="p0", text="출장 신청서(수정)"),
        Replacement(target="p1", text="신청자: 김철수"),
        Replacement(target="t0r0c1", text="2026-12-03 ~ 2026-12-05"),
        Replacement(target="t0r1c1p0", text="150000"),
    ))
    bold_run = _runs(hwpx_path, 1)[0]
    out = tmp_path / "out.hwpx"
    after = apply(hwpx_path, plan, out)
    texts = after.texts()
    assert {r.target: texts[r.target] for r in plan.replacements} == {r.target: r.text for r in plan.replacements}
    assert _runs(out, 1) == [("신청자: 김철수", bold_run[1], True)]
    assert "section_properties" in _kinds(out, 0)
    assert inspect(hwpx_path).texts()["p1"] == "신청자: {{이름}} 님"
    assert apply(hwpx_path, plan, tmp_path / "out2.hwpx").texts() == texts


def test_round_trip_keeps_table_shape_and_char_properties(hwpx_path: Path, tmp_path: Path) -> None:
    before = inspect(hwpx_path)
    plan = EditPlan(replacements=(
        Replacement(target="t1r0c1", text="병합 칸"), Replacement(target="p2", text="성명: 가"),
    ))
    after = apply(hwpx_path, plan, tmp_path / "out.hwpx")
    assert after.texts()["t1r0c1"] == "병합 칸" and after.texts()["p2"] == "성명: 가"
    for old, new in zip(before.tables, after.tables, strict=True):
        assert (old.rows, old.cols, len(old.cells)) == (new.rows, new.cols, len(new.cells))
        assert [(c.id, c.merged) for c in old.cells] == [(c.id, c.merged) for c in new.cells]
    assert _runs(tmp_path / "out.hwpx", 1) == _runs(hwpx_path, 1)


def test_replace_unknown_target_raises(hwpx_path: Path, tmp_path: Path) -> None:
    for target in ("x9", "p99", "t5r0c0", "t0r9c0", "t0r0c0p3"):
        plan = EditPlan(replacements=(Replacement(target=target, text=""),))
        with pytest.raises(KeyError):
            HwpxAdapter().replace(hwpx_path, plan, tmp_path / "o.hwpx")
    assert not (tmp_path / "o.hwpx").exists()


def _schema(fields: list[dict[str, object]], fmt: str = "hwpx") -> TemplateSchema:
    return TemplateSchema.model_validate(
        {"template_id": "양식-v1", "format": fmt, "kind": "blank_form", "source_hash": "h", "fields": fields}
    )


FIELDS: list[dict[str, object]] = [
    {"name": "이름", "locator": {"kind": "placeholder", "token": "{{이름}}"}},
    {"name": "기간", "type": "date_range", "locator": {"kind": "placeholder", "token": "{{기간}}"}},
    {"name": "성명", "type": "long_text", "locator": {"kind": "anchor_text", "after": "성명:"}},
    {"name": "금액", "type": "number", "locator": {"kind": "table_cell", "table": 0, "row": 1, "col": 1}},
]
VALUES = {"이름": "홍길동", "기간": "2026-12-03 ~ 2026-12-05", "성명": "현장 점검\n회의", "금액": 150000}


def test_fill_merges_split_token_and_fills_anchor_and_cell(hwpx_path: Path, tmp_path: Path) -> None:
    schema = _schema(FIELDS)
    assert check_locators(schema, inspect(hwpx_path)) == []
    out = tmp_path / "out.hwpx"
    texts = fill(hwpx_path, schema, VALUES, out).texts()
    assert texts["p1"] == "신청자: 홍길동 님" and texts["p2"] == "성명:" and texts["p3"] == "현장 점검\n회의"
    assert texts["t0r0c1"] == "2026-12-03 ~ 2026-12-05" and texts["t0r1c1"] == "150000"
    source_runs = _runs(hwpx_path, 1)
    assert _runs(out, 1) == [source_runs[0], ("홍길동", source_runs[1][1], False), source_runs[3]]
    assert inspect(hwpx_path).texts()["p1"] == "신청자: {{이름}} 님"
    assert fill(hwpx_path, schema, VALUES, tmp_path / "again.hwpx").texts() == texts


def test_fill_missing_anchor_or_token_raises(hwpx_path: Path, tmp_path: Path) -> None:
    anchor = _schema([{"name": "주소", "locator": {"kind": "anchor_text", "after": "주소:"}}])
    with pytest.raises(KeyError):
        fill(hwpx_path, anchor, {"주소": "서울"}, tmp_path / "o.hwpx")
    token = _schema([{"name": "x", "locator": {"kind": "placeholder", "token": "{{x}}"}}])
    with pytest.raises(KeyError):
        fill(hwpx_path, token, {"x": "1"}, tmp_path / "o.hwpx")
    sheet = _schema([{"name": "a", "locator": {"kind": "sheet_cell", "sheet": "s", "cell": "A1"}}])
    assert check_locators(sheet, inspect(hwpx_path)) == ["a: sheet_cell 은 XLSX 만"]


def test_hwp_is_read_and_written_as_hwpx(hwp_path: Path, tmp_path: Path) -> None:
    doc = inspect(hwp_path)
    assert doc.format == "hwp" and doc.meta["source_format"] == "hwp"
    assert doc.texts()["p1"] == "신청자: {{이름}} 님"
    plan = EditPlan(replacements=(Replacement(target="p2", text="성명: 홍길동"),))
    after = apply(hwp_path, plan, tmp_path / "out.hwpx")
    assert after.format == "hwpx" and after.texts()["p2"] == "성명: 홍길동"
    with pytest.raises(ValueError):
        apply(hwp_path, plan, tmp_path / "out.hwp")
    filled = fill(hwp_path, _schema(FIELDS[:1], "hwp"), {"이름": "김"}, tmp_path / "f.hwpx")
    assert filled.texts()["p1"] == "신청자: 김 님"


def test_to_html_escapes_markup_and_keeps_merge(hwpx_path: Path, tmp_path: Path) -> None:
    with HwpxDocument.open(hwpx_path) as doc:
        doc.paragraphs[3].text = "<script>alert(1)</script>"
        doc.save_to_path(tmp_path / "x.hwpx")
    html = to_html(tmp_path / "x.hwpx")
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert '<td colspan="2"></td>' in html and "{{기간}}" in html


def test_broken_file_raises_value_error(tmp_path: Path) -> None:
    bad = tmp_path / "bad.hwpx"
    bad.write_bytes(b"not a zip")
    with pytest.raises(ValueError):
        inspect(bad)
