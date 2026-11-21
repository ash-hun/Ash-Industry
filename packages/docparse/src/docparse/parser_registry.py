"""[service] 확장자로 어댑터를 고르는 입구. 에이전트 쪽은 이 함수들만 부른다."""

from pathlib import Path
from typing import Any, Literal
from collections.abc import Mapping

from docparse.template.template_schema import TemplateSchema, TemplateValueError, validate_values, build_assignments
from docparse.render.render_service import LibreOfficeRenderer
from docparse.adapters.docx_adapter import DocxAdapter
from docparse.adapters.xlsx_adapter import XlsxAdapter
from docparse.parser_protocol import FormatAdapter
from docparse.document_model import Document
from docparse.edit_plan import EditPlan

RenderFormat = Literal["html", "pdf", "png"]

_ADAPTERS: tuple[FormatAdapter, ...] = (DocxAdapter(), XlsxAdapter())
SUPPORTED_SUFFIXES: tuple[str, ...] = tuple(s for a in _ADAPTERS for s in a.suffixes)


class UnsupportedFormat(ValueError):
    pass


def adapter_for(path: Path) -> FormatAdapter:
    suffix = path.suffix.lower()
    for adapter in _ADAPTERS:
        if suffix in adapter.suffixes:
            return adapter
    raise UnsupportedFormat(f"지원하지 않는 형식: {suffix or '(확장자 없음)'}")


def inspect(path: Path) -> Document:
    return adapter_for(path).inspect(path)


def apply(path: Path, plan: EditPlan, out_path: Path) -> Document:
    """원본은 두고 out_path 에 저장한다. 같은 계획을 같은 원본에 다시 적용하면 같은 결과다."""
    return adapter_for(path).replace(path, plan, out_path)


def fill(path: Path, schema: TemplateSchema, values: Mapping[str, Any], out_path: Path) -> Document:
    """값을 검사하고 로케이터마다 넣어 out_path 에 저장한다. 원본은 두고, 같은 값이면 같은 결과."""
    if path.suffix.lower() != f".{schema.format}":
        raise UnsupportedFormat(f"템플릿은 {schema.format} 인데 파일은 {path.suffix or '(확장자 없음)'}")
    issues = validate_values(schema, values)
    if issues:
        raise TemplateValueError(issues)
    return adapter_for(path).fill(path, build_assignments(schema, values), out_path)


def to_html(path: Path) -> str:
    return adapter_for(path).to_html(path)


def render(
    path: Path, fmt: RenderFormat, out_dir: Path, renderer: LibreOfficeRenderer | None = None
) -> list[Path]:
    """html 은 어댑터가, pdf 와 png 는 LibreOffice 가 만든다. 만든 파일 경로 목록."""
    out_dir.mkdir(parents=True, exist_ok=True)
    if fmt == "html":
        target = out_dir / f"{path.stem}.html"
        target.write_text(to_html(path), encoding="utf-8")
        return [target]
    office = renderer or LibreOfficeRenderer()
    pdf = office.to_pdf(path, out_dir)
    if fmt == "pdf":
        return [pdf]
    return office.to_png(pdf, out_dir)
