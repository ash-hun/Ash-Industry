import pytest
from pathlib import Path
from hwpx import HwpxDocument
from docx import Document as new_docx

from docs_mcp.docs_server import DocsService, build_server
from docs_mcp.docs_paths import DocsPaths


def test_list_and_inspect(service: DocsService) -> None:
    listed = service.list_documents()
    assert [d["path"] for d in listed["documents"]] == ["sub/a.docx"]
    doc = service.inspect_document("sub/a.docx")
    assert doc["paragraphs"] == [{"id": "p0", "text": "제목"}, {"id": "p1", "text": "본문 {{이름}}"}]
    assert "error" in service.inspect_document("memo.txt")
    assert "error" in service.inspect_document("../a.docx")
    assert "error" in service.inspect_document("sub/none.docx")


def test_plan_then_apply_is_idempotent_and_keeps_source(service: DocsService, root: Path) -> None:
    plan = service.plan_edit("sub/a.docx", [{"target": "p1", "text": "본문 홍길동"}])
    assert plan["ok"] and plan["changes"] == [{"target": "p1", "before": "본문 {{이름}}", "after": "본문 홍길동"}]
    assert service.plan_edit("sub/a.docx", [{"target": "p1", "text": "본문 홍길동"}])["plan_id"] == plan["plan_id"]
    applied = service.apply_edit(plan["plan_id"])
    assert applied["output"] == "sub/a.edited-20261116-090000.docx" and applied["verify"]["ok"]
    assert service.apply_edit(plan["plan_id"]) == applied
    assert (root / applied["output"]).exists()
    assert service.inspect_document("sub/a.docx")["paragraphs"][1]["text"] == "본문 {{이름}}"
    listed = [d["path"] for d in service.list_documents()["documents"]]
    assert listed == ["sub/a.docx", "sub/a.edited-20261116-090000.docx"]


def test_apply_refuses_bad_plan_unknown_id_and_changed_source(service: DocsService, root: Path) -> None:
    assert "error" in service.apply_edit("nope")
    bad = service.plan_edit("sub/a.docx", [{"target": "p7", "text": "x"}])
    assert not bad["ok"] and service.apply_edit(bad["plan_id"])["issues"] == ["없는 대상: p7"]
    plan = service.plan_edit("sub/a.docx", [{"target": "p0", "text": "새 제목"}])
    source = root / "sub" / "a.docx"
    source.write_bytes(source.read_bytes() + b" ")
    assert "원본이 바뀌었다" in service.apply_edit(plan["plan_id"])["error"]


def test_render_html_and_missing_renderer(service: DocsService) -> None:
    html = service.render_document("sub/a.docx", "html")
    assert "제목" in html["html"]
    from docparse.render.render_service import LibreOfficeRenderer

    svc = DocsService(service._paths, renderer=LibreOfficeRenderer(soffice="/nonexistent", pdftoppm=None))
    assert "error" in svc.render_document("sub/a.docx", "pdf")


def test_build_server_registers_nine_tools(root: Path) -> None:
    server = build_server(DocsService(DocsPaths(root)))
    tools = {t.name: t for t in server._tool_manager.list_tools()}
    assert set(tools) == {
        "list_documents", "inspect_document", "plan_edit", "apply_edit", "render_document",
        "list_templates", "get_template_schema", "register_template", "fill_template",
    }
    for name in ("apply_edit", "register_template", "fill_template"):
        annotations = tools[name].annotations
        assert annotations is not None and annotations.read_only_hint is False
    for name in ("list_templates", "get_template_schema"):
        annotations = tools[name].annotations
        assert annotations is not None and annotations.read_only_hint
    assert tools["inspect_document"].annotations is not None and tools["inspect_document"].annotations.read_only_hint


@pytest.mark.anyio
async def test_tools_listed_with_camel_case_annotations(root: Path) -> None:
    server = build_server(DocsService(DocsPaths(root)))
    listed = await server.list_tools()
    by_name = {t.name: t for t in listed}
    dumped = by_name["apply_edit"].annotations.model_dump(by_alias=True, exclude_none=True)
    assert dumped == {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True}


def test_register_get_fill_flow_is_idempotent(service: DocsService, root: Path) -> None:
    hints = [{"name": "이름", "max_chars": 10}]
    registered = service.register_template("sub/a.docx", "인사-v1", fields=hints)
    assert registered["registered"] is True and registered["source"] == "sub/a.docx"
    assert service.register_template("sub/a.docx", "인사-v1")["registered"] is False
    assert service.list_templates()["templates"] == [
        {"template_id": "인사-v1", "format": "docx", "kind": "placeholder", "source": "sub/a.docx", "fields": 1},
    ]
    assert service.get_template_schema("인사-v1")["fields"] == [
        {"name": "이름", "type": "text", "required": True, "max_chars": 10, "max_lines": None},
    ]
    filled = service.fill_template("인사-v1", {"이름": "홍길동"})
    assert filled["path"] == "sub/a.filled-20261116-090000.docx" and filled["verify"] == {"ok": True, "issues": []}
    assert service.fill_template("인사-v1", {"이름": "홍길동"}) == filled
    assert len(list((root / ".templates" / "인사-v1" / "fills").iterdir())) == 1
    assert service.inspect_document(filled["path"])["paragraphs"][1]["text"] == "본문 홍길동"
    assert service.inspect_document("sub/a.docx")["paragraphs"][1]["text"] == "본문 {{이름}}"


def test_register_blank_form_checks_locators(service: DocsService, root: Path) -> None:
    doc = new_docx()
    doc.add_paragraph("성명:")
    doc.add_paragraph("")
    doc.add_table(rows=1, cols=2).cell(0, 0).text = "기간"
    doc.save(str(root / "빈양식.docx"))
    fields = [
        {"name": "성명", "locator": {"kind": "anchor_text", "after": "성명:"}},
        {"name": "기간", "type": "date_range", "locator": {"kind": "table_cell", "table": 0, "row": 0, "col": 1}},
    ]
    missing = service.register_template("빈양식.docx", "빈양식-v1", "blank_form", fields + [
        {"name": "주소", "locator": {"kind": "anchor_text", "after": "주소:"}},
    ])
    assert missing["issues"] == ["주소: 기준 글이 없다 '주소:'"]
    assert service.register_template("빈양식.docx", "빈양식-v1", "blank_form", fields)["registered"] is True
    filled = service.fill_template("빈양식-v1", {"성명": "홍길동", "기간": "2026-12-03 ~ 2026-12-05"})
    assert filled["verify"]["ok"] and filled["path"] == "빈양식.filled-20261116-090000.docx"
    texts = service.inspect_document(filled["path"])
    assert texts["paragraphs"][1]["text"] == "홍길동"


def test_template_errors(service: DocsService) -> None:
    assert "자리표시자" in service.register_template("sub/a.docx", "x-v1", "placeholder", [{"name": "없음"}])["error"]
    assert "error" in service.register_template("sub/a.docx", "../x")
    assert "error" in service.register_template(".render/b.docx", "x-v1")
    assert "fields" in service.register_template("sub/a.docx", "x-v1", "blank_form")["error"]
    assert "error" in service.get_template_schema("../etc") and "error" in service.fill_template("none", {})
    service.register_template("sub/a.docx", "인사-v1")
    bad = service.fill_template("인사-v1", {"성명": "x"})
    assert bad["issues"] == ["모르는 필드: 성명", "빠진 필수 필드: 이름"]


def test_hwpx_listed_registered_filled_and_hwp_written_as_hwpx(service: DocsService, root: Path) -> None:
    doc = HwpxDocument.new()
    doc.paragraphs[0].text = "본문 {{이름}}"
    doc.add_paragraph("성명:")
    doc.add_paragraph("")
    doc.save_to_path(root / "양식.hwpx")
    doc.save_to_path(root / "옛양식.hwp")
    listed = [d["path"] for d in service.list_documents()["documents"]]
    assert listed == ["sub/a.docx", "양식.hwpx", "옛양식.hwp"]
    fields = [
        {"name": "이름", "locator": {"kind": "placeholder", "token": "{{이름}}"}},
        {"name": "성명", "locator": {"kind": "anchor_text", "after": "성명:"}},
    ]
    registered = service.register_template("양식.hwpx", "양식-v1", "blank_form", fields)
    assert registered["registered"] is True and registered["format"] == "hwpx"
    filled = service.fill_template("양식-v1", {"이름": "홍길동", "성명": "김철수"})
    assert filled["path"] == "양식.filled-20261116-090000.hwpx" and filled["verify"] == {"ok": True, "issues": []}
    assert service.fill_template("양식-v1", {"이름": "홍길동", "성명": "김철수"}) == filled
    texts = [p["text"] for p in service.inspect_document(filled["path"])["paragraphs"]]
    assert texts == ["본문 홍길동", "성명:", "김철수"]
    plan = service.plan_edit("옛양식.hwp", [{"target": "p0", "text": "본문 이영희"}])
    applied = service.apply_edit(plan["plan_id"])
    assert applied["output"] == "옛양식.edited-20261116-090001.hwpx" and applied["verify"]["ok"]
