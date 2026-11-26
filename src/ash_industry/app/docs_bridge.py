"""[service] HUD 문서 창이 에이전트 없이 docs MCP 도구를 부를 때 정책 판정, 호출, 결과 기록을 묶는다."""

import json
import asyncio
from typing import Any
from collections.abc import Callable, Awaitable

from ash_industry.core.tools.tool_artifacts import document_artifacts
from ash_industry.core.tools.mcp_loader import call_mcp_tool
from ash_industry.core.policy.mcp_gate import McpGate
from ash_industry.ash_config import MCPServerConfig
from ash_industry.common.logger import get_logger

logger = get_logger(__name__)

DOCS_SERVER = "docs"
# 호출 기록과 정책의 에이전트 이름. 사람이 화면의 버튼을 눌러 부른 호출이다
HUD_AGENT = "hud"
Caller = Callable[[MCPServerConfig, str, dict[str, Any]], Awaitable[str]]


class DocsUnavailable(RuntimeError):
    """docs MCP 서버가 설정에 없거나 응답하지 않는다."""


class DocsDenied(PermissionError):
    """MCP 정책이 막았다."""


class DocsBridge:
    """버튼이 곧 사람의 승인이라 정책의 ask 는 허용으로 본다. deny 만 막는다."""

    def __init__(self, server: MCPServerConfig | None, gate: McpGate | None, caller: Caller | None = None) -> None:
        self._server = server
        self._gate = gate
        self._caller = caller

    @property
    def available(self) -> bool:
        return self._server is not None

    async def call(self, tool: str, params: dict[str, Any]) -> dict[str, Any]:
        """도구 결과 JSON. 결과에 미리보기 렌더가 있으면 `document` 에 화면이 띄울 첨부를 싣는다."""
        if self._server is None:
            raise DocsUnavailable("docs MCP 서버가 설정에 없다")
        verdict = self._gate.evaluate(HUD_AGENT, tool, params) if self._gate is not None else None
        if verdict is not None and verdict.mode == "deny":
            raise DocsDenied(verdict.reason)
        try:
            caller = self._caller or call_mcp_tool
            text = await asyncio.wait_for(caller(self._server, tool, params), timeout=self._server.timeout)
        except TimeoutError as exc:
            self._record(tool, ok=False, error="timeout")
            raise DocsUnavailable(f"docs MCP 서버가 {self._server.timeout:g}초 안에 답하지 않았다") from exc
        except Exception as exc:
            self._record(tool, ok=False, error=str(exc))
            logger.info(f"[DocsBridge] {tool} failed: {exc}")
            raise DocsUnavailable(f"docs MCP 호출 실패: {exc}") from exc
        self._record(tool, ok=True)
        return parse_result(text)

    def _record(self, tool: str, ok: bool, error: str = "") -> None:
        if self._gate is not None:
            self._gate.record_result(tool, ok=ok, error=error)


def parse_result(text: str) -> dict[str, Any]:
    """도구 결과 글을 dict 로. JSON 객체가 아니면 그 글을 error 로 싣는다. 순수 함수."""
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        return {"error": text}
    if not isinstance(data, dict):
        return {"error": text}
    docs = document_artifacts(text)
    if docs:
        data["document"] = docs[0].model_dump()
    return data


def find_docs_server(servers: list[MCPServerConfig]) -> MCPServerConfig | None:
    return next((s for s in servers if s.name == DOCS_SERVER), None)
