"""[ui] HUD 문서 창이 docs MCP 도구를 직접 불러 구조를 읽고, 고친 곳을 미리 보고 적용하고, 양식을 등록하는 REST."""

from typing import Any
from fastapi import Query, APIRouter
from fastapi.responses import JSONResponse
from pydantic import Field, BaseModel, ConfigDict

from ash_industry.app.docs_bridge import DocsBridge, DocsDenied, DocsUnavailable, find_docs_server
from ash_industry.ui.web.web_state import WebState

PATH_MAX = 500
TEXT_MAX = 5000
EDITS_MAX = 200
FIELDS_MAX = 200
# docs 서버의 id 와 같은 꼴: 본문 문단, 표 칸, 칸 안 문단, PPTX 도형 문단
TARGET = r"^(p\d+|t\d+r\d+c\d+(p\d+)?|s\d+sh\d+p\d+)$"
STRUCTURE_EXAMPLE = {
    "path": "uploads/3f2a9c1d0b7e-출장신청서.docx", "format": "docx",
    "paragraphs": [{"id": "p0", "text": "출장 신청서", "style": "Title"}],
    "tables": [{"id": "t0", "rows": 2, "cols": 2, "cells": [
        {"id": "t0r0c0", "row": 0, "col": 0, "text": "성명"}, {"id": "t0r0c1", "row": 0, "col": 1, "text": ""},
    ]}],
}
PLAN_EXAMPLE = {
    "plan_id": "9c1d0b7e3f2a", "path": "uploads/3f2a9c1d0b7e-출장신청서.docx", "ok": True, "issues": [],
    "changes": [{"target": "t0r0c1", "before": "", "after": "홍길동"}],
}


class Edit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target: str = Field(pattern=TARGET)
    text: str = Field(max_length=TEXT_MAX)


class PlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1, max_length=PATH_MAX)
    replacements: list[Edit] = Field(min_length=1, max_length=EDITS_MAX)


class ApplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_id: str = Field(pattern=r"^[0-9a-f]{12}$")


class TemplateRequest(BaseModel):
    """fields 의 모양(name, type, locator 등)은 docs 서버가 검사한다."""

    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1, max_length=PATH_MAX)
    template_id: str = Field(pattern=r"^[0-9A-Za-z가-힣_-]{1,64}$")
    fields: list[dict[str, Any]] = Field(min_length=1, max_length=FIELDS_MAX)


def build_doc_edit_router(state: WebState) -> APIRouter:
    router = APIRouter(tags=["docs"])
    bridge = DocsBridge(find_docs_server(state.settings.mcp_servers), state.ctx.mcp_gate)

    async def _call(tool: str, params: dict[str, Any]) -> JSONResponse:
        try:
            data = await bridge.call(tool, params)
        except DocsDenied as exc:
            return JSONResponse({"error": f"MCP 정책이 막았다: {exc}"}, status_code=403)
        except DocsUnavailable as exc:
            return JSONResponse({"error": str(exc)}, status_code=503)
        # 도구가 돌려준 문제(없는 파일, 형식 오류, 계획 문제)는 사용자가 고칠 입력 문제다
        return JSONResponse(data, status_code=422 if "error" in data else 200)

    @router.get(
        "/api/docs/structure",
        summary="문서 구조(편집 보기)",
        description=(
            "docs MCP 의 inspect_document(include_empty=true) 결과. 빈 칸까지 id 가 붙은 문단과 표 칸을 준다."
            " 큰 문서는 tables_omitted 의 표를 table 과 offset 으로 나눠 받는다."
        ),
        responses={200: {"content": {"application/json": {"example": STRUCTURE_EXAMPLE}}}},
    )
    async def structure(
        path: str = Query(min_length=1, max_length=PATH_MAX, description="문서 폴더 기준 상대 경로"),
        table: str = Query(default="", max_length=64, description="표 id(t3)나 시트 이름"),
        offset: int = Query(default=0, ge=0),
    ) -> JSONResponse:
        params: dict[str, Any] = {"path": path, "include_empty": True}
        if table:
            params |= {"table": table, "offset": offset}
        return await _call("inspect_document", params)

    @router.post(
        "/api/docs/plan",
        summary="고칠 곳 미리보기",
        description="docs MCP 의 plan_edit. 아무것도 저장하지 않고 바뀔 곳(before, after)과 문제, plan_id 를 준다.",
        responses={200: {"content": {"application/json": {"example": PLAN_EXAMPLE}}}},
    )
    async def plan(body: PlanRequest) -> JSONResponse:
        return await _call("plan_edit", {
            "path": body.path, "replacements": [r.model_dump() for r in body.replacements],
        })

    @router.post(
        "/api/docs/apply",
        summary="미리 본 계획 적용",
        description=(
            "docs MCP 의 apply_edit. 원본 옆에 새 파일로 저장하고 검증 결과를 준다. 이 버튼 누름이 사람의 승인이다."
            " 미리보기 렌더가 있으면 document 에 문서 창이 띄울 첨부를 싣는다."
        ),
    )
    async def apply(body: ApplyRequest) -> JSONResponse:
        return await _call("apply_edit", {"plan_id": body.plan_id})

    @router.get(
        "/api/docs/fields",
        summary="빈 양식 필드 후보",
        description="docs MCP 의 detect_fields. 저장하지 않는다.",
    )
    async def fields(
        path: str = Query(min_length=1, max_length=PATH_MAX, description="문서 폴더 기준 상대 경로"),
    ) -> JSONResponse:
        return await _call("detect_fields", {"path": path})

    @router.post(
        "/api/docs/templates",
        summary="빈 양식 등록",
        description="docs MCP 의 register_template(kind=blank_form). 사용자가 표에서 고른 필드로 등록한다.",
    )
    async def register(body: TemplateRequest) -> JSONResponse:
        return await _call("register_template", {
            "path": body.path, "template_id": body.template_id, "kind": "blank_form", "fields": body.fields,
        })

    return router
