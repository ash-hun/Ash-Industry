"""[service] PDF 어댑터. pypdf 로 쪽마다 글 줄과 AcroForm 필드를 읽고, 채우기는 폼 필드에만 한다."""

import html
from typing import Any
from pathlib import Path
from collections.abc import Mapping
from pypdf.errors import PdfReadError
from pypdf import PdfReader, PdfWriter

from docparse.document_model import Document, FormField, Paragraph, form_field_id, paragraph_id
from docparse.template.template_schema import AnyLocator, FillValue, FormFieldLocator
from docparse.edit_plan import EditPlan

FIELD_KINDS = {"/Tx": "text", "/Btn": "checkbox", "/Ch": "choice"}


def _open(path: Path) -> PdfReader:
    try:
        reader = PdfReader(str(path))
        _ = len(reader.pages)
    except (PdfReadError, OSError, ValueError) as exc:
        raise ValueError(f"PDF 를 열 수 없다: {exc}") from exc
    if reader.is_encrypted:
        raise ValueError("암호가 걸린 PDF 는 열지 않는다")
    return reader


def _full_name(annot: Any) -> str:
    """위젯에서 부모를 따라 올라가며 `/T` 를 점으로 잇는다. get_fields 의 키와 같은 이름이다."""
    parts: list[str] = []
    node = annot
    while node is not None:
        if "/T" in node:
            parts.append(str(node["/T"]))
        parent = node.get("/Parent")
        node = parent.get_object() if parent is not None else None
    return ".".join(reversed(parts))


def _field_pages(reader: PdfReader) -> dict[str, int]:
    """필드 이름마다 처음 나온 쪽(1부터)."""
    pages: dict[str, int] = {}
    for n, page in enumerate(reader.pages, start=1):
        for ref in page.get("/Annots") or []:
            annot = ref.get_object()
            if annot.get("/Subtype") == "/Widget":
                pages.setdefault(_full_name(annot), n)
    return pages


def _options(field: Any) -> tuple[str, ...]:
    """체크박스는 켜고 끄는 값 이름(pypdf 의 /_States_), 선택 필드는 선택지(쌍이면 내보내는 값)."""
    states = field.get("/_States_") or field.get("/Opt") or []
    return tuple(str(o[0] if isinstance(o, list) else o) for o in states)


def _fields(reader: PdfReader) -> tuple[FormField, ...]:
    # ponytail: 서명(/Sig)과 값 없는 상위 노드는 other 로 싣는다, 계층 폼에서 헷갈리면 잎만 남긴다
    raw = reader.get_fields() or {}
    pages = _field_pages(reader)
    out: list[FormField] = []
    for name in sorted(raw):
        field = raw[name]
        if "/FT" not in field:
            continue
        value = field.get("/V")
        out.append(FormField(
            id=form_field_id(name), name=name, value="" if value is None else str(value),
            kind=FIELD_KINDS.get(str(field["/FT"]), "other"), page=pages.get(name, 0), options=_options(field),
        ))
    return tuple(out)


def _lines(reader: PdfReader) -> tuple[Paragraph, ...]:
    """쪽마다 빈 줄을 뺀 글 줄. id 는 `pg<쪽>p<줄>`. 글자 위치를 모르므로 고치기 대상이 아니다."""
    out: list[Paragraph] = []
    for n, page in enumerate(reader.pages, start=1):
        lines = [line.strip() for line in (page.extract_text() or "").splitlines() if line.strip()]
        out.extend(
            Paragraph(id=paragraph_id(k, f"pg{n}"), text=line, editable=False) for k, line in enumerate(lines)
        )
    return tuple(out)


class PdfAdapter:
    suffixes: tuple[str, ...] = (".pdf",)

    def inspect(self, path: Path) -> Document:
        reader = _open(path)
        meta = {"pages": str(len(reader.pages))}
        return Document(path=str(path), format="pdf", paragraphs=_lines(reader), fields=_fields(reader), meta=meta)

    def replace(self, path: Path, plan: EditPlan, out_path: Path) -> Document:
        raise ValueError("PDF 본문은 고치지 않는다. 폼 필드는 양식 템플릿(form_field)으로 채운다")

    def fill(self, path: Path, assignments: Mapping[AnyLocator, FillValue], out_path: Path) -> Document:
        reader = _open(path)
        known = {f.name: f for f in _fields(reader)}
        values: dict[str, str] = {}
        for locator, value in assignments.items():
            if not isinstance(locator, FormFieldLocator):
                raise KeyError(f"PDF 에 쓸 수 없는 자리: {locator.kind}")
            if locator.name not in known:
                raise KeyError(f"폼 필드가 없다: {locator.name}")
            values[locator.name] = str(value)
        writer = PdfWriter(clone_from=reader)
        for page in writer.pages:
            # 외형은 보는 쪽이 다시 그리게 둔다. pypdf 가 그리는 외형은 한글 글꼴이 없어 깨진다
            writer.update_page_form_field_values(page, values, auto_regenerate=False)
        writer.set_need_appearances_writer(True)
        with open(out_path, "wb") as f:
            writer.write(f)
        return self.inspect(out_path)

    def to_html(self, path: Path) -> str:
        doc = self.inspect(path)
        parts: list[str] = []
        for n in range(1, int(doc.meta.get("pages", "0")) + 1):
            parts.append(f"<section><h2>{n}쪽</h2>")
            parts.extend(f"<p>{html.escape(p.text)}</p>" for p in doc.paragraphs if p.id.startswith(f"pg{n}p"))
            parts.append("</section>")
        if doc.fields:
            rows = "".join(
                f"<tr><td>{html.escape(f.name)}</td><td>{html.escape(f.value)}</td></tr>" for f in doc.fields
            )
            parts.append(f"<h2>폼 필드</h2><table>{rows}</table>")
        return "".join(parts)
