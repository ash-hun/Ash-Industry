"""[ui] MCP 도구 정책(서버, 도구별 모드, 인자 고정, 상한, 에이전트 제한)을 읽고 바꾸고 호출 기록을 내주는 REST."""

from typing import Any, Literal
from fastapi import Query, APIRouter
from fastapi.responses import JSONResponse
from pydantic import Field, BaseModel, ConfigDict

from ash_industry.core.policy.mcp_policy import MAX_CALLS_PER_HOUR, parse_policy, policy_to_dict
from ash_industry.ui.web.web_state import WebState

Mode = Literal["allow", "ask", "deny"]
# 팀 프로필 파일 이름이 에이전트 id 다. 모르는 id 는 에이전트 제한이 없는 것으로 판정된다
AGENT_ID_PATTERN = r"^[a-z0-9][a-z0-9_-]{0,39}$"


class ToolPolicyPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Mode | None = None
    lock: dict[str, list[str]] = Field(default_factory=dict)
    calls_per_hour: int | None = Field(default=None, ge=0, le=MAX_CALLS_PER_HOUR)


class ServerPolicyPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tools: dict[str, ToolPolicyPatch] = Field(default_factory=dict)
    lock: dict[str, list[str]] = Field(default_factory=dict)  # 서버의 모든 도구에 거는 인자 고정(계정 등)


class AgentPolicyPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    servers: list[str] | None = None
    deny: list[str] = Field(default_factory=list)


class McpPolicyPatch(BaseModel):
    """정책 문서 전체. 부분 갱신이 아니라 통째로 바꾼다(화면이 전체를 들고 있어 두 번 보내도 같다)."""

    model_config = ConfigDict(extra="forbid")

    defaults: dict[Literal["read", "write", "unknown"], Mode] = Field(default_factory=dict)
    servers: dict[str, ServerPolicyPatch] = Field(default_factory=dict)
    agents: dict[str, AgentPolicyPatch] = Field(default_factory=dict)


POLICY_EXAMPLE = {
    "path": "/root/.ash/mcp_policy.yaml",
    "agent": "main",
    "policy": {
        "defaults": {"read": "allow", "write": "ask", "unknown": "ask"},
        "servers": {"google": {"tools": {
            "send_gmail_message": {"mode": "ask", "lock": {"to": ["me@example.com"]}},
        }}},
        "agents": {"scribe": {"servers": ["google"], "deny": ["send_gmail_message"]}},
    },
    "tools": [{
        "server": "google", "name": "send_gmail_message", "kind": "write", "effective": "ask",
        "description": "메일 보내기",
    }],
}
AUDIT_EXAMPLE = {"entries": [
    {"ts": 1794741852895, "type": "call", "agent": "main", "server": "google", "tool": "send_gmail_message",
     "decision": "ask", "reason": "write 도구 · 도구 정책 ask",
     "call": "google.send_gmail_message(to=me@example.com)"},
    {"ts": 1794741853895, "type": "result", "server": "google", "tool": "send_gmail_message", "ok": True, "error": ""},
]}


def build_mcp_router(state: WebState) -> APIRouter:
    router = APIRouter(tags=["mcp"])

    def _body(agent: str) -> dict[str, Any]:
        gate = state.ctx.mcp_gate
        if gate is None:
            return {
                "path": "", "agent": agent, "policy": policy_to_dict(parse_policy(None)), "tools": [],
                "enabled": False,
            }
        return {
            "path": gate.path,
            "agent": agent,
            "policy": policy_to_dict(gate.policy),
            "tools": [
                {"server": info.server, "name": name, "kind": info.kind,
                 "effective": gate.effective_mode(name, agent), "description": info.description}
                for name, info in gate.tools()
            ],
            "enabled": True,
        }

    @router.get(
        "/api/mcp/policy",
        summary="MCP 도구 정책과 도구 목록",
        description=(
            "policy 는 저장된 정책 문서(defaults, servers.<서버>.tools.<도구>, agents), tools 는 붙은 MCP 도구마다"
            " 서버, 종류(read, write, unknown), agent 쿼리(기본 main)의 에이전트가 부를 때 판정(effective: allow, ask,"
            " deny). mcp_servers 가 없으면 enabled false."
        ),
        responses={200: {"content": {"application/json": {"example": POLICY_EXAMPLE}}}},
    )
    async def get_policy(agent: str = Query(default="main", pattern=AGENT_ID_PATTERN)) -> JSONResponse:
        return JSONResponse(_body(agent))

    @router.put(
        "/api/mcp/policy",
        summary="MCP 도구 정책 바꾸기",
        description=(
            "정책 문서 전체를 받아 검증한 뒤 파일에 쓰고 바로 적용한다. 같은 본문을 두 번 보내도 같다."
            " 응답의 effective 는 agent 쿼리(기본 main) 기준."
        ),
        responses={
            200: {"content": {"application/json": {"example": POLICY_EXAMPLE}}},
            404: {"description": "mcp_servers 가 없어 정책 문이 없다"},
            422: {"description": "모르는 mode, 범위 밖 calls_per_hour, 모르는 필드, 형식이 틀린 agent"},
        },
    )
    async def put_policy(
        patch: McpPolicyPatch, agent: str = Query(default="main", pattern=AGENT_ID_PATTERN),
    ) -> JSONResponse:
        gate = state.ctx.mcp_gate
        if gate is None:
            return JSONResponse({"error": "mcp_servers 가 없다"}, status_code=404)
        gate.update(parse_policy(patch.model_dump(exclude_none=True)))
        return JSONResponse(_body(agent))

    @router.get(
        "/api/mcp/audit",
        summary="MCP 호출 기록",
        description="최근 호출의 판정(call)과 결과(result) 줄, 최신이 앞. 인자는 요약(비밀값 가림)만 남는다.",
        responses={200: {"content": {"application/json": {"example": AUDIT_EXAMPLE}}}},
    )
    async def get_audit(limit: int = Query(default=50, ge=1, le=500)) -> JSONResponse:
        gate = state.ctx.mcp_gate
        return JSONResponse({"entries": gate.audit.recent(limit) if gate is not None else []})

    return router
