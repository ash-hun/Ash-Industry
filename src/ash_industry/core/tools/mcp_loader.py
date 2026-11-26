"""[core] MCP 서버의 툴을 열거해 AshTool 로 감싸 ToolRegistry 에 등록하고 호출을 중계한다."""

import json
import asyncio
import contextlib
from typing import TYPE_CHECKING, Any
from collections.abc import Callable, AsyncIterator

from ash_industry.core.tools.tool_artifacts import docs_artifacts, artifacts_from_result, collect_peer_artifacts
from ash_industry.core.tools.tools_registry import AshTool
from ash_industry.common.logger import get_logger

if TYPE_CHECKING:
    from ash_industry.model_layer.model_types import Artifact, ToolResultMessage
    from ash_industry.core.tools.tools_registry import ToolRegistry
    from ash_industry.core.policy.mcp_gate import McpGate
    from ash_industry.ash_config import MCPServerConfig

logger = get_logger(__name__)


# 결과물 파일을 화면이 받아 볼 수 있는 서버와 그 결과에서 첨부를 고르는 규칙. 미디어 워커의 파일은
# /api/creative/files/, docs 서버의 렌더 파일은 /api/docs/files/ 로 내준다. 다른 서버의 글은 첨부하지 않는다
ARTIFACT_RULES: "dict[str, Callable[[str], list[Artifact]]]" = {
    "media": artifacts_from_result,
    "docs": docs_artifacts,
}


class MCPToolWrapper(AshTool):
    """MCP 서버 단일 툴을 AshTool 로 래핑."""

    def __init__(
        self,
        server_config: "MCPServerConfig",
        tool_name: str,
        description: str,
        input_schema: dict[str, Any],
        gate: "McpGate | None" = None,
    ) -> None:
        self.name = tool_name
        self.description = description
        self.parameters = input_schema or {"type": "object", "properties": {}}
        self.execution_mode = "parallel"
        self._server = server_config
        self._gate = gate  # 결과(성공, 실패)를 호출 기록에 남긴다. 판정은 샌드박스가 같은 문에 묻는다

    async def execute(self, tool_call_id: str, params: dict[str, Any], signal: Any = None) -> "ToolResultMessage":
        from ash_industry.model_layer.model_types import TextContent, ToolResultMessage

        try:
            result_text = await asyncio.wait_for(
                call_mcp_tool(self._server, self.name, params),
                timeout=self._server.timeout,
            )
            if self._gate is not None:
                self._gate.record_result(self.name, ok=True)
            rule = ARTIFACT_RULES.get(self._server.name)
            artifacts = rule(result_text) if rule is not None else []
            collect_peer_artifacts(artifacts)
            return ToolResultMessage(
                tool_call_id=tool_call_id,
                tool_name=self.name,
                content=[TextContent(text=result_text)],
                artifacts=artifacts,
            )
        except TimeoutError:
            if self._gate is not None:
                self._gate.record_result(self.name, ok=False, error="timeout")
            return ToolResultMessage(
                tool_call_id=tool_call_id,
                tool_name=self.name,
                content=[TextContent(
                    text=f"MCP tool '{self.name}' timed out after {self._server.timeout}s "
                         f"(server '{self._server.name}')"
                )],
                is_error=True,
            )
        except Exception as exc:
            if self._gate is not None:
                self._gate.record_result(self.name, ok=False, error=str(exc))
            return ToolResultMessage(
                tool_call_id=tool_call_id,
                tool_name=self.name,
                content=[TextContent(text=str(exc))],
                is_error=True,
            )


class MCPToolLoader:
    """MCP 서버에 연결해 툴을 열거하고 ToolRegistry에 등록한다."""

    def __init__(self, registry: "ToolRegistry", gate: "McpGate | None" = None) -> None:
        self._registry = registry
        self._gate = gate

    async def load_servers(self, servers: "list[MCPServerConfig]") -> list[str]:
        """각 서버에 연결해 툴 목록을 등록. mcp 패키지 없으면 skip. Returns registered tool names."""
        try:
            import mcp  # noqa: F401
        except ImportError:
            logger.info("[MCPToolLoader] mcp package not installed — skipping. Run: uv add mcp")
            return []

        loaded: list[str] = []
        for server in servers:
            # 서버별 격리. 한 서버의 실패/타임아웃이 다른 서버 로딩을 막지 않는다.
            try:
                tools = await asyncio.wait_for(
                    _list_mcp_tools(server), timeout=server.timeout
                )
            except TimeoutError:
                logger.info(
                    f"[MCPToolLoader] '{server.name}' timed out after {server.timeout}s "
                    f"— skipping"
                )
                continue
            except Exception as exc:
                logger.info(f"[MCPToolLoader] Failed to load from '{server.name}': {exc}")
                continue

            count = 0
            for tool in tools:
                name = tool.get("name")
                if not name:
                    logger.info(f"[MCPToolLoader] '{server.name}': skipping tool with no name")
                    continue
                wrapper = MCPToolWrapper(
                    server_config=server,
                    tool_name=name,
                    description=tool.get("description", ""),
                    input_schema=tool.get("inputSchema", {}),
                    gate=self._gate,
                )
                if self._gate is not None:
                    self._gate.register(name, server.name, tool.get("annotations"), tool.get("description", ""))
                self._registry.register_force(wrapper)
                loaded.append(name)
                count += 1
            logger.info(f"[MCPToolLoader] Loaded {count} tool(s) from '{server.name}'")

        return loaded


@contextlib.asynccontextmanager
async def _open_session(server: "MCPServerConfig") -> AsyncIterator[Any]:
    """transport 에 맞는 연결을 열고 초기화한 ClientSession 을 낸다. 열거와 호출이 같은 길을 쓴다."""
    from mcp import ClientSession
    if server.transport == "stdio":
        if not server.command:
            raise ValueError(f"MCP server '{server.name}': transport=stdio requires command")
        from mcp.client.stdio import StdioServerParameters, stdio_client
        server_params = StdioServerParameters(
            command=server.command[0], args=server.command[1:], env=server.env or None
        )
        async with stdio_client(server_params) as (read, write), ClientSession(read, write) as session:
            await session.initialize()
            yield session
        return

    if not server.url:
        raise ValueError(f"MCP server '{server.name}': transport={server.transport} requires url")
    headers = _build_http_headers(server)
    if server.transport == "http":
        from mcp.client.sse import sse_client
        async with sse_client(server.url, headers=headers) as (read, write), ClientSession(read, write) as session:
            await session.initialize()
            yield session
        return

    if server.transport == "streamable-http":
        # create_mcp_http_client 는 mcp 가 __all__ 에 올리지 않았다. 헤더(Bearer)를 실으려면 이 클라이언트가 필요하다
        from mcp.client.streamable_http import streamable_http_client
        from mcp.client.streamable_http import create_mcp_http_client  # type: ignore[attr-defined]
        async with (
            create_mcp_http_client(headers=headers) as http,
            streamable_http_client(server.url, http_client=http) as streams,
            ClientSession(streams[0], streams[1]) as session,
        ):
            await session.initialize()
            yield session
        return

    raise ValueError(f"Unsupported MCP transport '{server.transport}' for '{server.name}'")


async def _list_mcp_tools(server: "MCPServerConfig") -> list[dict[str, Any]]:
    async with _open_session(server) as session:
        result = await session.list_tools()
        return _tools_to_dicts(result.tools)


async def call_mcp_tool(server: "MCPServerConfig", tool_name: str, params: dict[str, Any]) -> str:
    async with _open_session(server) as session:
        result = await session.call_tool(tool_name, params)
        return _extract_result_text(result)


def _build_http_headers(server: "MCPServerConfig") -> dict[str, str] | None:
    """http transport용 헤더 구성. auth_token이 있으면 Authorization: Bearer로 추가.

    명시적으로 지정한 headers가 auth_token 파생 헤더보다 우선한다.
    헤더가 없으면 None을 반환해 mcp 기본 동작을 따른다.
    """
    headers: dict[str, str] = {}
    if server.auth_token is not None:
        headers["Authorization"] = f"Bearer {server.auth_token.get_secret_value()}"
    headers.update(server.headers)
    return headers or None


def _tools_to_dicts(tools: Any) -> list[dict[str, Any]]:
    return [
        {
            "name": t.name,
            "description": t.description or "",
            "inputSchema": getattr(t, "input_schema", None) or getattr(t, "inputSchema", None) or {},
            "annotations": _annotations_dict(getattr(t, "annotations", None)),
        }
        for t in tools
    ]


def _annotations_dict(annotations: Any) -> dict[str, Any] | None:
    """도구 주석(readOnlyHint 등)을 평범한 dict 로. 없으면 None."""
    if annotations is None:
        return None
    if isinstance(annotations, dict):
        return annotations
    # mcp 2.x 모델은 snake_case 필드(read_only_hint)라 와이어 이름(readOnlyHint)으로 맞춘다
    dump = getattr(annotations, "model_dump", None)
    return dump(by_alias=True, exclude_none=True) if callable(dump) else None


def _extract_result_text(result: Any) -> str:
    parts: list[str] = []
    for block in result.content:
        if hasattr(block, "text"):
            parts.append(block.text)
        else:
            try:
                parts.append(json.dumps(block.model_dump()))
            except Exception:
                parts.append(str(block))
    return "\n".join(parts) or "(empty)"
