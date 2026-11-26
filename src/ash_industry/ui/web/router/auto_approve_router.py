"""[ui] 에이전트별 auto mode(승인 자동 허용)를 보고 켜고 끄는 REST."""

from fastapi import APIRouter
from fastapi import Path as PathParam
from fastapi.responses import JSONResponse
from pydantic import BaseModel, StrictBool, ConfigDict

from ash_industry.ui.web.web_state import WebState

AUTO_EXAMPLE = {"agents": [
    {"id": "main", "name": "A.S.H.", "enabled": False}, {"id": "evi", "name": "E.V.I.", "enabled": True},
]}


class AutoApproveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: StrictBool


def build_auto_approve_router(state: WebState) -> APIRouter:
    router = APIRouter(tags=["auto-approve"])

    def _rows() -> list[dict[str, object]]:
        store = state.ctx.auto_approve
        return [
            {"id": p.agent_id, "name": p.name, "enabled": store.enabled(p.agent_id) if store is not None else False}
            for p in state.assembly.agents.profiles()
        ]

    @router.get(
        "/api/auto-approve",
        summary="에이전트별 auto mode",
        description=(
            "최상위 에이전트마다 auto mode 가 켜졌는지. 켜진 에이전트는 승인 모달이 뜰 호출(쓰기 도구, MCP ask)을"
            " 묻지 않고 실행한다. 위험 명령, MCP deny, never 는 켜도 막힌다."
        ),
        responses={200: {"content": {"application/json": {"example": AUTO_EXAMPLE}}}},
    )
    async def get_auto() -> JSONResponse:
        return JSONResponse({"agents": _rows()})

    @router.put(
        "/api/auto-approve/{agent}",
        summary="auto mode 켜고 끄기",
        description=(
            "그 에이전트의 auto mode 를 바꾸고 바로 적용한다(열린 세션도 다음 호출부터). 같은 값을 다시 보내도 같다."
        ),
        responses={
            200: {"content": {"application/json": {"example": AUTO_EXAMPLE}}},
            404: {"description": "모르는 에이전트"}, 422: {"description": "enabled 가 bool 이 아니다"},
        },
    )
    async def put_auto(body: AutoApproveRequest, agent: str = PathParam(description="에이전트 id")) -> JSONResponse:
        store = state.ctx.auto_approve
        if store is None or agent not in state.assembly.agents:
            return JSONResponse({"error": f"unknown agent: {agent}"}, status_code=404)
        store.set(agent, body.enabled)
        return JSONResponse({"agents": _rows()})

    return router
