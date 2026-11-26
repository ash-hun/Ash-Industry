"""[core] 지정한 MCP 서버의 툴을 한 번 불러 그 원문을 외부 이벤트로 바꾸는 소스."""

import asyncio
from typing import TYPE_CHECKING, Any
from collections.abc import Awaitable, Callable

from ash_industry.core.external.external_loader import ExternalSourceSpec
from ash_industry.core.external.external_protocol import ExternalSource
from ash_industry.core.external.external_types import ExternalEvent
from ash_industry.core.external.dedup import derive_events
from ash_industry.common.logger import get_logger

if TYPE_CHECKING:
    from ash_industry.ash_config import MCPServerConfig

# (server, tool_name, params) -> 원문 텍스트. 기본은 mcp_loader.call_mcp_tool.
CallMcpTool = Callable[["MCPServerConfig", str, dict[str, Any]], Awaitable[str]]

logger = get_logger(__name__)

# 인증이 풀리면 서버가 오류 대신 로그인 안내를 정상 결과로 돌려준다(workspace-mcp 2.5.0 의 google_auth.py).
# 안내 속 URL 의 state 가 매번 바뀌어 중복 제거를 지나므로 새 이벤트로 쌓이지 않게 실패로 본다
AUTH_REQUIRED_MARKERS = ("ACTION REQUIRED:",)


def needs_auth(raw: str) -> bool:
    return any(marker in raw[:500] for marker in AUTH_REQUIRED_MARKERS)


class McpToolSource(ExternalSource):
    """MCP 툴을 1회 호출해 원문을 이벤트로 변환하는 소스.

    ToolRegistry를 경유하지 않고 서버를 직접 지정 호출한다. 서로 다른 서버가
    같은 툴 이름을 쓰면 register_force로 덮여 충돌하기 때문(설계 §5).
    poll()은 예외를 던지지 않는다: 서버 무응답·오류는 빈 목록 + 로그로 끝난다.
    """

    def __init__(
        self,
        spec: ExternalSourceSpec,
        server: "MCPServerConfig",
        *,
        call: CallMcpTool | None = None,
        detail_max_chars: int = 500,
    ) -> None:
        super().__init__(spec.name, spec.interval_sec)
        self._spec = spec
        self._server = server
        self._call = call
        self._detail_max_chars = detail_max_chars
        self._auth_failing = False

    async def poll(self) -> list[ExternalEvent]:
        call = self._call
        if call is None:
            from ash_industry.core.tools.mcp_loader import call_mcp_tool

            call = call_mcp_tool

        try:
            raw = await asyncio.wait_for(
                call(self._server, self._spec.tool, dict(self._spec.args)),
                timeout=self._server.timeout,
            )
        except TimeoutError:
            logger.info(
                f"[McpToolSource] '{self.name}': '{self._spec.tool}' timed out after "
                f"{self._server.timeout}s (server '{self._server.name}') — skipping"
            )
            return []
        except Exception as exc:
            logger.info(f"[McpToolSource] '{self.name}': poll failed: {exc}")
            return []

        if needs_auth(raw):
            # 10분마다 같은 경고를 쌓지 않게 상태가 바뀔 때만 남긴다
            if not self._auth_failing:
                logger.warning(
                    f"[McpToolSource] '{self.name}': server '{self._server.name}' needs sign-in, "
                    f"skipping until it recovers"
                )
            self._auth_failing = True
            return []
        if self._auth_failing:
            logger.info(f"[McpToolSource] '{self.name}': server '{self._server.name}' sign-in recovered")
            self._auth_failing = False
        return derive_events(self.name, raw, detail_max_chars=self._detail_max_chars)


def build_mcp_sources(
    specs: list[ExternalSourceSpec],
    servers: "list[MCPServerConfig]",
    *,
    detail_max_chars: int = 500,
    call: CallMcpTool | None = None,
) -> list[McpToolSource]:
    """소스 선언 + MCP 서버 설정 → McpToolSource 목록.

    비활성 소스는 건너뛰고, 미지의 서버 이름은 경고 후 그 소스만 skip한다
    (MCPToolLoader의 서버별 격리 규약과 동일).
    """
    by_name = {s.name: s for s in servers}
    sources: list[McpToolSource] = []
    for spec in specs:
        if not spec.enabled:
            continue
        server = by_name.get(spec.server)
        if server is None:
            logger.info(
                f"[ExternalSourceLoader] '{spec.name}': unknown MCP server "
                f"'{spec.server}' — skipping"
            )
            continue
        sources.append(
            McpToolSource(spec, server, call=call, detail_max_chars=detail_max_chars)
        )
    return sources
