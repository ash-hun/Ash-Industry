import pytest
from typing import Any
from pathlib import Path
from pypdf import PdfWriter
from hwpx import HwpxDocument
from openpyxl import Workbook
from pptx import Presentation
from docx import Document as new_docx
from pypdf.generic import NameObject, ArrayObject, FloatObject, TextStringObject, DictionaryObject

from docs_mcp.docs_server import DocsService, build_server
from docs_mcp.docs_paths import DocsPaths
from docparse import SlideSpec


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
    assert applied["preview"]["files"] == [".render/a.edited-20261116-090000/a.edited-20261116-090000-1.png"]
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


def test_write_succeeds_when_preview_render_fails(root: Path) -> None:
    from docparse.render.render_service import LibreOfficeRenderer

    svc = DocsService(DocsPaths(root), renderer=LibreOfficeRenderer(soffice="/nonexistent", pdftoppm=None))
    made = svc.create_document("새.docx", title="제목")
    assert made["paragraphs"] == 1 and "error" in made["preview"] and (root / "새.docx").exists()


def test_build_server_registers_twelve_tools(root: Path) -> None:
    server = build_server(DocsService(DocsPaths(root)))
    tools = {t.name: t for t in server._tool_manager.list_tools()}
    assert set(tools) == {
        "list_documents", "inspect_document", "plan_edit", "apply_edit", "render_document",
        "list_templates", "get_template_schema", "register_template", "fill_template", "detect_fields",
        "create_document", "make_placeholder_copy",
    }
    for name in ("apply_edit", "register_template", "fill_template", "create_document", "make_placeholder_copy"):
        annotations = tools[name].annotations
        assert annotations is not None and annotations.read_only_hint is False
    for name in ("list_templates", "get_template_schema", "detect_fields"):
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
    assert filled["preview"]["format"] == "png" and filled["preview"]["path"] == filled["path"]
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


def test_detect_register_fill_blank_docx(service: DocsService, root: Path) -> None:
    doc = new_docx()
    doc.add_paragraph("성명:")
    doc.add_paragraph("")
    doc.add_paragraph("연락처: ____")
    table = doc.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "출장 기간"
    table.cell(1, 0).text = "금액"
    doc.save(str(root / "출장 양식.docx"))
    detected = service.detect_fields("출장 양식.docx")
    assert detected["template_id"] == "출장_양식-v1" and detected["format"] == "docx"
    assert [(c["name"], c["type"], c["rule"]) for c in detected["candidates"]] == [
        ("성명", "text", "anchor_text"), ("연락처", "text", "anchor_text"),
        ("출장기간", "date_range", "table_right"), ("금액", "number", "table_right"),
    ]
    assert service.detect_fields("출장 양식.docx") == detected
    fields = [{k: c[k] for k in ("name", "type", "required", "locator")} for c in detected["candidates"]]
    registered = service.register_template("출장 양식.docx", detected["template_id"], "blank_form", fields)
    assert registered["registered"] is True
    values = {"성명": "홍길동", "연락처": "010-0000-0000", "출장기간": "2026-12-03 ~ 2026-12-05", "금액": "1,500"}
    filled = service.fill_template(detected["template_id"], values)
    assert filled["verify"] == {"ok": True, "issues": []}
    out = service.inspect_document(filled["path"])
    assert [p["text"] for p in out["paragraphs"]] == ["성명:", "홍길동", "연락처: 010-0000-0000"]
    assert [c["text"] for c in out["tables"][0]["cells"]] == ["출장 기간", "2026-12-03 ~ 2026-12-05", "금액", "1500"]


def test_detect_fields_xlsx_hwpx_and_errors(service: DocsService, root: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "신청"
    ws["A1"] = "성명"
    ws["A2"] = "수량"
    ws["B2"] = 3
    wb.save(str(root / "신청.xlsx"))
    sheet = service.detect_fields("신청.xlsx")
    assert sheet["format"] == "xlsx" and [(c["name"], c["locator"]) for c in sheet["candidates"]] == [
        ("성명", {"kind": "sheet_cell", "sheet": "신청", "cell": "B1"}),
    ]
    doc = HwpxDocument.new()
    doc.paragraphs[0].text = "성명:"
    doc.add_paragraph("")
    doc.save_to_path(root / "양식.hwpx")
    hwpx = service.detect_fields("양식.hwpx")
    assert hwpx["template_id"] == "양식-v1" and [c["locator"] for c in hwpx["candidates"]] == [
        {"kind": "anchor_text", "after": "성명:"},
    ]
    assert service.detect_fields("sub/a.docx")["candidates"] == []
    for bad in ("../a.docx", ".render/b.docx", "memo.txt", "none.docx"):
        assert "error" in service.detect_fields(bad)


def _pdf_form(path: Path) -> None:
    writer = PdfWriter()
    page = writer.add_blank_page(width=595, height=842)
    field = DictionaryObject({
        NameObject("/Type"): NameObject("/Annot"), NameObject("/Subtype"): NameObject("/Widget"),
        NameObject("/FT"): NameObject("/Tx"), NameObject("/T"): TextStringObject("성명"),
        NameObject("/Rect"): ArrayObject([FloatObject(v) for v in (100, 700, 300, 720)]),
    })
    ref = writer._add_object(field)
    page[NameObject("/Annots")] = ArrayObject([ref])
    writer._root_object[NameObject("/AcroForm")] = DictionaryObject({NameObject("/Fields"): ArrayObject([ref])})
    with open(path, "wb") as f:
        writer.write(f)


def test_pptx_and_pdf_are_listed_inspected_and_filled(service: DocsService, root: Path) -> None:
    prs = Presentation()
    prs.slides.add_slide(prs.slide_layouts[0]).shapes.title.text = "{{제목}}"
    prs.save(str(root / "발표.pptx"))
    _pdf_form(root / "신청.pdf")
    listed = [d["path"] for d in service.list_documents()["documents"]]
    assert listed == ["sub/a.docx", "발표.pptx", "신청.pdf"]
    title = service.inspect_document("발표.pptx")["paragraphs"]
    assert title == [{"id": "s0sh2p0", "text": "{{제목}}", "style": "Title 1"}]
    pdf = service.inspect_document("신청.pdf")
    assert pdf["fields"] == [{"id": "f:성명", "name": "성명", "kind": "text", "value": "", "page": 1}]
    detected = service.detect_fields("신청.pdf")
    fields = [{k: c[k] for k in ("name", "type", "required", "locator")} for c in detected["candidates"]]
    assert service.register_template("신청.pdf", detected["template_id"], "blank_form", fields)["registered"]
    filled = service.fill_template(detected["template_id"], {"성명": "홍길동"})
    assert filled["verify"] == {"ok": True, "issues": []} and filled["path"].endswith(".pdf")
    assert filled["preview"]["format"] == "pdf" and filled["preview"]["files"][0].endswith(".pdf")
    assert service.inspect_document(filled["path"])["fields"][0]["value"] == "홍길동"
    assert service.plan_edit("신청.pdf", [{"target": "f:성명", "text": "x"}])["issues"] == ["없는 대상: f:성명"]


def test_create_document_writes_new_file_once(service: DocsService, root: Path) -> None:
    slides = [SlideSpec(title="사업 계획", subtitle="2026"), SlideSpec(title="목표", bullets=["매출"])]
    made = service.create_document("발표/계획.pptx", slides=slides)
    assert made == {
        "path": "발표/계획.pptx", "format": "pptx", "paragraphs": 4, "tables": 0, "slides": 2,
        "preview": {"path": "발표/계획.pptx", "format": "png", "files": [".render/계획/계획-1.png"]},
    }
    assert service.create_document("발표/계획.pptx", slides=slides) == made
    assert "덮어쓰지 않는다" in service.create_document("발표/계획.pptx", slides=slides[:1])["error"]
    assert "발표/계획.pptx" in [d["path"] for d in service.list_documents()["documents"]]
    assert service.inspect_document("발표/계획.pptx")["paragraphs"][0]["text"] == "사업 계획"
    assert "덮어쓰지 않는다" in service.create_document("sub/a.docx", title="x")["error"]
    assert service.inspect_document("sub/a.docx")["paragraphs"][0]["text"] == "제목"


def test_create_document_refuses_bad_path_and_mismatched_content(service: DocsService, root: Path) -> None:
    for bad in ("../a.docx", ".render/a.docx", "/tmp/a.docx"):
        assert "error" in service.create_document(bad, title="x")
    assert "새로 만들 수 있는 형식" in service.create_document("a.hwpx", title="x")["error"]
    assert "slides 가 없다" in service.create_document("a.pptx", title="x")["error"]
    assert not (root / "a.pptx").exists()


def _big_doc() -> Any:
    from docparse.document_model import Cell, Document, Table, Paragraph

    def table(i: int, name: str, n: int) -> Table:
        cells = tuple(Cell(id=f"t{i}r{r}c0", row=r, col=0, text=f"v{r}") for r in range(n))
        return Table(id=f"t{i}", index=i, rows=n, cols=1, cells=cells, name=name)

    return Document(
        path="a.xlsx", format="xlsx", paragraphs=(Paragraph(id="p0", text="제목"),),
        tables=(table(0, "요약", 10), table(1, "원장", 2500), table(2, "부록", 5)),
    )


def test_document_dict_keeps_fitting_tables_and_lists_the_rest() -> None:
    from docs_mcp.docs_server import document_dict

    out = document_dict(_big_doc(), include_empty=False)
    assert [t["id"] for t in out["tables"]] == ["t0", "t2"] and out["paragraphs"][0]["text"] == "제목"
    assert out["tables_omitted"] == [{"id": "t1", "name": "원장", "rows": 2500, "cols": 1, "cells_total": 2500}]
    assert "table" in out["truncated"]
    small = document_dict(_big_doc().model_copy(update={"tables": _big_doc().tables[:1]}), include_empty=False)
    assert "truncated" not in small and "tables_omitted" not in small


def test_document_dict_pages_one_table_by_name_or_id() -> None:
    from docs_mcp.docs_server import document_dict

    first = document_dict(_big_doc(), include_empty=False, table="원장")
    assert first["paragraphs"] == [] and len(first["tables"][0]["cells"]) == 2000 and first["next_offset"] == 2000
    rest = document_dict(_big_doc(), include_empty=False, table="t1", offset=2000)
    assert [c["id"] for c in rest["tables"][0]["cells"]][:1] == ["t1r2000c0"] and "next_offset" not in rest
    assert len(document_dict(_big_doc(), False, table="t1", offset=-5, limit=0)["tables"][0]["cells"]) == 1
    assert "없는 표" in document_dict(_big_doc(), include_empty=False, table="없음")["error"]


def test_document_dict_marks_readonly_and_spans() -> None:
    from docparse import Cell, Table, Document, Paragraph
    from docs_mcp.docs_server import document_dict

    doc = Document(
        path="a.pptx", format="pptx", paragraphs=(Paragraph(id="s0np0", text="노트", editable=False),),
        tables=(Table(id="t0", index=0, rows=2, cols=2, anchor=1, cells=(
            Cell(id="t0r0c0", row=0, col=0, text="성명", merged=True, col_span=2),
            Cell(id="t0r1c0", row=1, col=0, text="홍길동"),
        )),),
    )
    out = document_dict(doc, include_empty=False)
    assert out["paragraphs"] == [{"id": "s0np0", "text": "노트", "readonly": True}]
    assert [c.get("col_span") for c in out["tables"][0]["cells"]] == [2, None]
    assert out["tables"][0]["anchor"] == 1
    assert "anchor" not in document_dict(_big_doc(), include_empty=False)["tables"][0]


def test_placeholder_copy_then_register_and_fill(service: DocsService, root: Path) -> None:
    doc = new_docx()
    doc.add_paragraph("성명(        ) 서명")
    doc.add_paragraph("□ 예 □ 아니오")
    table = doc.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "금액"
    doc.save(str(root / "빈 양식.docx"))
    candidates = service.detect_fields("빈 양식.docx")["candidates"]
    fields = [{k: c[k] for k in ("name", "type", "locator")} for c in candidates if c["rule"] != "checkbox"]
    made = service.make_placeholder_copy("빈 양식.docx", fields)
    assert (made["path"], made["placeholders"], made["created"]) == ("빈 양식.template.docx", ["금액", "성명"], True)
    assert service.make_placeholder_copy("빈 양식.docx", fields)["created"] is False
    texts = [p["text"] for p in service.inspect_document(made["path"])["paragraphs"]]
    assert texts[0] == "성명({{성명}}) 서명"
    assert service.inspect_document("빈 양식.docx")["paragraphs"][0]["text"] == "성명(        ) 서명"
    registered = service.register_template(made["path"], "빈양식-v1")
    assert registered["registered"] is True and registered["kind"] == "placeholder"
    filled = service.fill_template("빈양식-v1", {"성명": "홍길동", "금액": "1000"})
    assert filled["verify"] == {"ok": True, "issues": []}


def test_placeholder_copy_refuses_checkbox_missing_and_conflict(service: DocsService, root: Path) -> None:
    doc = new_docx()
    doc.add_paragraph("□ 예 □ 아니오")
    doc.save(str(root / "칸.docx"))
    box = {"name": "여부", "type": "choice", "locator": {"kind": "checkbox", "paragraph": "p0", "options": ["예"]}}
    assert "둘 수 없는 자리" in service.make_placeholder_copy("칸.docx", [box])["error"]
    missing = {"name": "성명", "locator": {"kind": "inline_slot", "paragraph": "p0", "label": "성명"}}
    assert service.make_placeholder_copy("칸.docx", [missing])["issues"] == ["성명: p0 에 '성명' 뒤 빈 괄호가 없다"]
    assert "fields" in service.make_placeholder_copy("칸.docx", [])["error"]
    (root / "칸.template.docx").write_bytes((root / "칸.docx").read_bytes())
    anchor = {"name": "x", "locator": {"kind": "anchor_text", "after": "□ 예"}}
    assert "이미 다른 사본" in service.make_placeholder_copy("칸.docx", [anchor])["error"]
