"""[api] docparse 공개 API. 에이전트와 MCP 서버는 이 모듈의 이름만 쓴다."""

from docparse.parser_registry import SUPPORTED_SUFFIXES, apply, inspect, render, to_html
from docparse.document_model import Cell, Document, Paragraph, Run, Table
from docparse.edit_plan import Change, EditPlan, Replacement, preview
from docparse.verify.verify_service import VerifyResult, verify_edit
from docparse.render.render_service import RenderUnavailable

__all__ = [
    "SUPPORTED_SUFFIXES",
    "Cell",
    "Change",
    "Document",
    "EditPlan",
    "Paragraph",
    "RenderUnavailable",
    "Replacement",
    "Run",
    "Table",
    "VerifyResult",
    "apply",
    "inspect",
    "preview",
    "render",
    "to_html",
    "verify_edit",
]
