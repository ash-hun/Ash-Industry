"""approval 기능: 승인 규칙을 프롬프트에 붙이고, 거부 뒤에도 도구를 쓴다고 알리며, 위험 명령은 묻지 않고 막는다.

다른 에이전트로 옮겨 간 동안 온 승인 요청은 기다렸다가 돌아온 화면이 답하고, 진행 중인 턴도 다시 그려진다.
"""

from typing import Any

from tests.fixtures.web_hud_helpers import scripted_env, use_provider, web_assembly, web_client
from tests.fixtures.agent_loop_helpers import ScriptedProvider, register, text_turn, tool_turn
from ash_industry.core.policy.authenticator import NoAuthAuthenticator
from ash_industry.core.policy.validator import DefaultInputValidator
from ash_industry.model_layer.model_types import ToolResultMessage
from ash_industry.core.policy.pipeline import SecurityPipeline
from ash_industry.core.policy.sandbox import DefaultSandbox
from ash_industry.core.policy.policy import AllowAllPolicy
from ash_industry.core.session import AgentSession

APPROVAL_RULE_HEAD = "[도구 승인] bash 는 실행 전에 시스템이 사용자에게 승인을 묻는다"


def _session(provider: ScriptedProvider, pipeline: SecurityPipeline, fx: dict[str, Any]) -> AgentSession:
    return AgentSession(
        model=register(provider),
        session_id="approval-rule",
        security_pipeline=pipeline,
        plugin_runner=fx["plugin_runner"],
        memory=fx["session_memory"],
        tool_registry=fx["tool_registry"],
        skill_registry=fx["skill_registry"],
        session_repo=fx["repo"],
    )


async def test_rule_lists_approval_tools_and_denial_keeps_tool_usable(
    plugin_runner, session_memory, tool_registry, skill_registry, jsonl_repo
) -> None:
    async def deny(command: str, reason: str, always_pattern: str = "") -> bool:
        return False

    sandbox = DefaultSandbox(require_approval_for=["bash"])
    sandbox.set_approval_callback(deny)
    pipeline = SecurityPipeline(
        validator=DefaultInputValidator(), authenticator=NoAuthAuthenticator(), policy=AllowAllPolicy(), sandbox=sandbox
    )
    provider = ScriptedProvider([tool_turn(("call-1", "bash", {"command": "chmod 000 a.md"})), text_turn("네")])
    fx = {"plugin_runner": plugin_runner, "session_memory": session_memory, "tool_registry": tool_registry,
          "skill_registry": skill_registry, "repo": jsonl_repo}
    await jsonl_repo.create(session_id="approval-rule")

    await _session(provider, pipeline, fx).prompt("권한을 바꿔 줘")

    assert APPROVAL_RULE_HEAD in (provider.calls[-1].full_system_prompt() or "")
    result = next(m for m in await jsonl_repo.get_messages("approval-rule") if isinstance(m, ToolResultMessage))
    assert result.is_error
    assert "도구는 계속 쓸 수 있다" in result.content[0].text


async def test_no_rule_without_approval_tools(
    permissive_pipeline, plugin_runner, session_memory, tool_registry, skill_registry, jsonl_repo
) -> None:
    provider = ScriptedProvider([text_turn("네")])
    fx = {"plugin_runner": plugin_runner, "session_memory": session_memory, "tool_registry": tool_registry,
          "skill_registry": skill_registry, "repo": jsonl_repo}
    await jsonl_repo.create(session_id="approval-rule")

    await _session(provider, permissive_pipeline, fx).prompt("안녕")

    assert "[도구 승인]" not in (provider.calls[-1].full_system_prompt() or "")


async def test_dangerous_command_is_blocked_without_asking_even_when_approved(
    plugin_runner, session_memory, tool_registry, skill_registry, jsonl_repo
) -> None:
    asked: list[str] = []

    async def approve(command: str, reason: str, always_pattern: str = "") -> bool:
        asked.append(command)
        return True

    sandbox = DefaultSandbox(require_approval_for=["bash"])
    sandbox.set_approval_callback(approve)
    pipeline = SecurityPipeline(
        validator=DefaultInputValidator(), authenticator=NoAuthAuthenticator(), policy=AllowAllPolicy(), sandbox=sandbox
    )
    provider = ScriptedProvider([tool_turn(("call-1", "bash", {"command": "sudo rm -rf /"})), text_turn("못 했어요")])
    fx = {"plugin_runner": plugin_runner, "session_memory": session_memory, "tool_registry": tool_registry,
          "skill_registry": skill_registry, "repo": jsonl_repo}
    await jsonl_repo.create(session_id="approval-rule")

    await _session(provider, pipeline, fx).prompt("디스크를 비워 줘")

    result = next(m for m in await jsonl_repo.get_messages("approval-rule") if isinstance(m, ToolResultMessage))
    assert asked == []
    assert result.is_error and "dangerous_commands" in result.content[0].text


def _receive_until(ws: Any, kind: str) -> list[dict[str, Any]]:
    seen = []
    while True:
        msg = ws.receive_json()
        seen.append(msg)
        if msg["type"] == kind:
            return seen


def test_switching_away_keeps_turn_and_approval_for_return(monkeypatch, tmp_path) -> None:
    provider = ScriptedProvider([tool_turn(("call-1", "bash", {"command": "echo hi"})), text_turn("끝났습니다")])
    for _ in use_provider(provider):
        assembly = web_assembly(monkeypatch, tmp_path, **scripted_env(provider.provider_name, tmp_path))
        with web_client(assembly) as client:
            with client.websocket_connect("/ws?session_id=alpha") as ws:
                ws.receive_json()
                ws.send_json({"type": "user_message", "text": "echo 해 줘"})
                _receive_until(ws, "approval_request")

            with client.websocket_connect("/ws?session_id=beta") as other:
                hello = other.receive_json()
            assert hello["approval_waiting"] == [{"session_id": "alpha", "agent": "main", "count": 1}]
            assert hello["in_flight"] == []

            with client.websocket_connect("/ws?session_id=alpha") as ws:
                # 기다리던 요청은 붙는 순간(connected 보다 먼저) 다시 온다
                request = _receive_until(ws, "approval_request")[-1]
                back = _receive_until(ws, "connected")[-1]
                ws.send_json({"type": "approval_response", "id": request["id"], "approved": True})
                seen = _receive_until(ws, "agent_end")

    replayed = [e["type"] for e in back["in_flight"]]
    assert replayed[0] == "agent_start" and "agent_end" not in replayed
    assert seen[-1]["final_message"] is not None
    assert "끝났습니다" in "".join(m.get("text_delta", "") for m in seen if m["type"] == "message_update")
