"""[core] MCP 도구 색인(서버, 종류)과 정책, 기록을 묶어 샌드박스와 화면이 쓰는 판정 문."""

import time
from typing import Any
from dataclasses import dataclass
from collections.abc import Callable, Mapping

from ash_industry.core.policy.mcp_policy import Kind, McpPolicy, Mode, Verdict, decide, describe_call, kind_of
from ash_industry.core.policy.mcp_policy_store import McpPolicyStore
from ash_industry.core.policy.mcp_audit import McpAudit
from ash_industry.common.logger import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class McpToolInfo:
    server: str
    kind: Kind
    description: str = ""


class McpGate:
    """로더가 도구를 등록하고, 샌드박스가 호출마다 묻고, 라우터가 정책을 읽고 바꾼다."""

    def __init__(self, store: McpPolicyStore, audit: McpAudit, clock: Callable[[], float] | None = None) -> None:
        self._store = store
        self._audit = audit
        self._clock = clock or time.time
        self._index: dict[str, McpToolInfo] = {}
        self._policy = store.load()

    @property
    def policy(self) -> McpPolicy:
        return self._policy

    @property
    def audit(self) -> McpAudit:
        return self._audit

    @property
    def path(self) -> str:
        return str(self._store.path)

    def register(
        self, tool: str, server: str, annotations: Mapping[str, Any] | None = None, description: str = ""
    ) -> None:
        self._index[tool] = McpToolInfo(server=server, kind=kind_of(tool, annotations), description=description)

    def info(self, tool: str) -> McpToolInfo | None:
        return self._index.get(tool)

    def tools(self) -> list[tuple[str, McpToolInfo]]:
        return sorted(self._index.items(), key=lambda kv: (kv[1].server, kv[0]))

    def effective_mode(self, tool: str, agent: str = "main") -> Mode | None:
        """인자 없이 본 판정(화면의 🔒 표시용). MCP 도구가 아니면 None."""
        info = self._index.get(tool)
        if info is None:
            return None
        return decide(self._policy, agent, info.server, tool, {}, info.kind).mode

    def ask_tools(self, agent: str = "main") -> list[str]:
        return sorted(t for t in self._index if self.effective_mode(t, agent) == "ask")

    def hidden_tools(self, agent: str = "main") -> list[str]:
        """이 에이전트가 어떤 인자로도 못 쓰는 도구(서버 제한, 도구 deny). 목록에서 빼야 부르려다 막히지 않는다."""
        return sorted(t for t in self._index if self.effective_mode(t, agent) == "deny")

    def evaluate(self, agent: str, tool: str, params: Mapping[str, Any]) -> Verdict | None:
        """호출 하나를 판정하고 기록한다. MCP 도구가 아니면 None."""
        info = self._index.get(tool)
        if info is None:
            return None
        now_ms = int(self._clock() * 1000)
        verdict = decide(
            self._policy, agent, info.server, tool, params, info.kind,
            calls_last_hour=self._audit.calls_last_hour(info.server, tool, now_ms),
        )
        self._audit.record({
            "ts": now_ms, "type": "call", "agent": agent, "server": info.server, "tool": tool,
            "decision": verdict.mode, "reason": verdict.reason, "call": describe_call(info.server, tool, params),
        })
        if verdict.mode == "deny":
            logger.info(f"[MCP] denied {describe_call(info.server, tool, params)}: {verdict.reason}")
        return verdict

    def describe(self, tool: str, params: Mapping[str, Any]) -> str:
        info = self._index.get(tool)
        return describe_call(info.server if info else "mcp", tool, params)

    def record_result(self, tool: str, ok: bool, error: str = "") -> None:
        info = self._index.get(tool)
        self._audit.record({
            "type": "result", "server": info.server if info else "", "tool": tool, "ok": ok, "error": error[:200],
        })

    def update(self, policy: McpPolicy) -> None:
        """저장하고 바로 쓴다. 같은 정책을 두 번 넣어도 같다."""
        self._store.save(policy)
        self._policy = policy

    def reload(self) -> None:
        self._policy = self._store.load()
