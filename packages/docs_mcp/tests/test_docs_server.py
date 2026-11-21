import pytest
from pathlib import Path

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


def test_build_server_registers_five_tools(root: Path) -> None:
    server = build_server(DocsService(DocsPaths(root)))
    tools = {t.name: t for t in server._tool_manager.list_tools()}
    assert set(tools) == {"list_documents", "inspect_document", "plan_edit", "apply_edit", "render_document"}
    assert tools["apply_edit"].annotations is not None and tools["apply_edit"].annotations.read_only_hint is False
    assert tools["inspect_document"].annotations is not None and tools["inspect_document"].annotations.read_only_hint


@pytest.mark.anyio
async def test_tools_listed_with_camel_case_annotations(root: Path) -> None:
    server = build_server(DocsService(DocsPaths(root)))
    listed = await server.list_tools()
    by_name = {t.name: t for t in listed}
    dumped = by_name["apply_edit"].annotations.model_dump(by_alias=True, exclude_none=True)
    assert dumped == {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True}
