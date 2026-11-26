"""[core] 보안 파이프라인 Step 4 의 샌드박스 구현체(위험 명령 차단과 승인 흐름, 전부 허용)를 제공한다."""

import re
from typing import Any
from collections.abc import Awaitable, Callable

from ash_industry.core.policy.pipeline import ApprovalResult, Decision, PolicyResult, SandboxBlocked, SandboxProtocol
from ash_industry.core.policy.approval_rules import ApprovalRule, ApprovalRules, describe, suggest_pattern
from ash_industry.ash_config import DEFAULT_DANGEROUS_COMMANDS
from ash_industry.core.policy.mcp_gate import McpGate
from ash_industry.common.logger import get_logger

logger = get_logger(__name__)

# 승인 콜백의 답. True/False 는 이번 한 번, "always" 는 제안된 패턴을 규칙으로 남긴다.
ApprovalChoice = bool | str
ApprovalCallback = Callable[[str, str, str], Awaitable[ApprovalChoice]]
ALWAYS = "always"
# 승인 창이 시간 안에 답을 받지 못했다. 거부와 같지만 사용자에게 다르게 알린다
TIMEOUT = "timeout"
DEFAULT_APPROVAL_TOOLS = ("bash", "write_file")
# 위험 패턴을 보는 인자. 셸 도구(bash)가 받는 명령이다. 파일 내용(write_file 의 content)은 보지 않는다
COMMAND_PARAM = "command"


class DefaultSandbox(SandboxProtocol):
    """Step 4: 실행 샌드박스.

    - 위험 명령어 패턴 차단
    - require_approval 툴 목록에 대해 Human-in-the-loop 승인 플로우
    - 승인 기억(approval_rules): 사용자가 "항상 허용"한 패턴은 다시 묻지 않는다
    """

    def __init__(
        self,
        dangerous_patterns: list[str] | None = None,
        require_approval_for: list[str] | None = None,
        approval_callback: ApprovalCallback | None = None,
        approval_rules: ApprovalRules | None = None,
        mcp_gate: McpGate | None = None,
        agent_id: str = "main",
        auto_approve: Callable[[], bool] | None = None,
    ) -> None:
        # None 이면 기본 목록, 빈 목록이면 차단을 끈다. 설정에서 []를 주면 그 뜻 그대로 따른다
        patterns = DEFAULT_DANGEROUS_COMMANDS if dangerous_patterns is None else dangerous_patterns
        self._patterns = [re.compile(p, re.IGNORECASE) for p in patterns]
        self._require_approval = set(
            DEFAULT_APPROVAL_TOOLS if require_approval_for is None else require_approval_for
        )
        self._approval_callback = approval_callback
        self._rules = approval_rules
        # MCP 도구는 정책 문이 먼저 본다(인자 고정, deny, 에이전트 제한, 시간당 상한). ask 면 아래 승인 흐름을 탄다
        self._mcp_gate = mcp_gate
        self._agent_id = agent_id
        # auto mode. 켜져 있으면 물을 호출을 묻지 않고 허용한다. 위험 명령과 정책 deny 는 그 앞에서 막힌다.
        # 매번 불러 읽으므로 HUD 에서 바꾸면 세션을 다시 만들지 않아도 바로 따른다
        self._auto_approve = auto_approve
        self.policy_reason = ""  # 마지막 "policy" 판정의 이유. 세션이 도구 결과에 싣는다

    async def approve(
        self,
        policy_result: PolicyResult,
        command: str,
    ) -> ApprovalResult:
        pattern = self.dangerous_pattern(command)
        if pattern is not None:
            raise SandboxBlocked(reason=f"Blocked by sandbox: dangerous pattern '{pattern}'", command=command)
        return ApprovalResult(approved=True)

    def dangerous_pattern(self, command: str) -> str | None:
        """command 에 걸리는 첫 위험 패턴. 없으면 None."""
        return next((p.pattern for p in self._patterns if p.search(command)), None)

    async def request_approval(self, command: str, reason: str, always_pattern: str = "") -> ApprovalChoice:
        """Human-in-the-loop 승인 요청. approval_callback이 없으면 자동 거부."""
        if self._approval_callback:
            return await self._approval_callback(command, reason, always_pattern)
        return False

    async def authorize(self, tool_name: str, params: dict[str, Any]) -> bool:
        return await self.decide(tool_name, params) == "allow"

    async def decide(self, tool_name: str, params: dict[str, Any]) -> Decision:
        """이 호출을 실행해도 되는가. 위험 명령 → 승인 불필요 → 기억된 규칙 → 사용자에게 질문 순으로 결정한다.

        규칙은 사용자가 승인 화면에서 "항상 허용"을 골랐을 때만 생긴다. 코드가 먼저 넓히지 않는다.
        """
        command = params.get(COMMAND_PARAM)
        if isinstance(command, str) and self.dangerous_pattern(command) is not None:
            # 승인과 "항상 허용" 규칙보다 먼저 본다. 사람이 bash 를 늘 허용해도 rm -rf / 는 나가지 않는다
            return "blocked"
        verdict = self._mcp_gate.evaluate(self._agent_id, tool_name, params) if self._mcp_gate else None
        if verdict is not None and verdict.mode == "deny":
            self.policy_reason = verdict.reason
            return "policy"
        if verdict is None and not self.is_approval_required(tool_name):
            return "allow"
        if verdict is not None and verdict.mode == "allow":
            return "allow"
        if self._rules is not None and self._rules.allows(tool_name, params):
            return "allow"
        if self.auto_mode():
            logger.info(f"[Sandbox] auto mode allowed '{tool_name}' for agent '{self._agent_id}'")
            return "allow"
        pattern = suggest_pattern(tool_name, params) if self._rules is not None else ""
        shown = describe(tool_name, params)
        if verdict is not None and self._mcp_gate is not None:
            shown = self._mcp_gate.describe(tool_name, params)
        reason = f"MCP 도구 · {verdict.reason}" if verdict is not None else f"Tool '{tool_name}' requires approval"
        choice = await self.request_approval(command=shown, reason=reason, always_pattern=pattern)
        if choice == ALWAYS:
            if self._rules is not None and pattern:
                self._rules.add(ApprovalRule(tool=tool_name, pattern=pattern))
            return "allow"
        if choice == TIMEOUT:
            return "timeout"
        return "allow" if choice is True else "deny"

    def set_approval_callback(self, callback: ApprovalCallback) -> None:
        self._approval_callback = callback

    def set_approval_rules(self, rules: ApprovalRules | None) -> None:
        """세션의 에이전트가 정해진 뒤 그 에이전트의 승인 규칙으로 바꾼다(TUI 가 기동 때 부른다)."""
        self._rules = rules

    def is_approval_required(self, tool_name: str) -> bool:
        if self._mcp_gate is not None and self._mcp_gate.info(tool_name) is not None:
            return self._mcp_gate.effective_mode(tool_name, self._agent_id) == "ask"
        return tool_name in self._require_approval

    def auto_mode(self) -> bool:
        return self._auto_approve is not None and self._auto_approve()

    def approval_tools(self) -> list[str]:
        """승인을 묻는 도구. auto mode 면 묻지 않으므로 빈 목록이다(프롬프트에 승인 규칙을 붙이지 않는다)."""
        if self.auto_mode():
            return []
        asks = self._mcp_gate.ask_tools(self._agent_id) if self._mcp_gate is not None else []
        return sorted(self._require_approval | set(asks))


class PermissiveSandbox(SandboxProtocol):
    """모든 명령 허용. 개발/테스트 전용. 네 메서드 모두 기반의 Permissive 동작을 쓴다."""
