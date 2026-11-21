"""[api] docparse 공개 API. 에이전트와 MCP 서버는 이 모듈의 이름만 쓴다."""

from docparse.template.template_schema import (
    TemplateField, TemplateSchema, TemplateValueError, render_value, check_locators, validate_values,
    scan_placeholders, schema_from_placeholders,
)
from docparse.parser_registry import SUPPORTED_SUFFIXES, apply, fill, inspect, render, to_html, output_suffix
from docparse.template.field_detect import FieldCandidate, detect_fields, suggest_template_id
from docparse.document_model import Cell, Document, FormField, Paragraph, Run, Table
from docparse.verify.verify_service import VerifyResult, verify_edit, verify_fill
from docparse.edit_plan import Change, EditPlan, Replacement, preview
from docparse.render.render_service import RenderUnavailable

__all__ = [
    "SUPPORTED_SUFFIXES",
    "Cell",
    "Change",
    "Document",
    "FieldCandidate",
    "FormField",
    "EditPlan",
    "Paragraph",
    "RenderUnavailable",
    "Replacement",
    "Run",
    "Table",
    "TemplateField",
    "TemplateSchema",
    "TemplateValueError",
    "VerifyResult",
    "apply",
    "check_locators",
    "detect_fields",
    "fill",
    "inspect",
    "output_suffix",
    "preview",
    "render",
    "render_value",
    "scan_placeholders",
    "schema_from_placeholders",
    "suggest_template_id",
    "to_html",
    "validate_values",
    "verify_edit",
    "verify_fill",
]
