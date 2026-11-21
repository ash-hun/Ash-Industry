"""mcp_policy 기능의 순수 판정: 도구 종류, 판정 순서(고정, deny, 에이전트, 상한, 기본값), 설명, 정책 왕복."""

import pytest

from ash_industry.core.policy.mcp_policy import (
    AgentPolicy,
    McpPolicy,
    ServerPolicy,
    ToolPolicy,
    decide,
    describe_call,
    kind_of,
    parse_policy,
    policy_to_dict,
)

POLICY = McpPolicy(
    servers={"google": ServerPolicy(
        tools={
            "send_gmail_message": ToolPolicy(mode="ask", lock={"to": ("me@example.com",)}, calls_per_hour=5),
            "delete_gmail_message": ToolPolicy(mode="deny"),
            "search_gmail_messages": ToolPolicy(calls_per_hour=2),
        },
        lock={"user_google_email": ("me@gmail.com",)},
    )},
    agents={
        "scribe": AgentPolicy(servers=("google",), deny=frozenset({"send_gmail_message"})),
        "ion": AgentPolicy(servers=()),
    },
)


@pytest.mark.parametrize(
    ("tool", "annotations", "kind"),
    [
        ("search_gmail_messages", None, "read"),
        ("send_gmail_message", None, "write"),
        ("start_google_auth", None, "unknown"),
        ("anything", {"readOnlyHint": True}, "read"),
        ("anything", {"destructiveHint": True}, "write"),
        ("anything", {"read_only_hint": True}, "read"),
        ("anything", {"read_only_hint": False, "destructive_hint": False}, "write"),
    ],
)
def test_kind_of_uses_annotations_then_name_prefix(tool, annotations, kind):
    assert kind_of(tool, annotations) == kind


def test_decide_defaults_by_kind_when_tool_has_no_policy():
    assert decide(McpPolicy(), "main", "google", "get_events", {}, "read").mode == "allow"
    assert decide(McpPolicy(), "main", "google", "manage_event", {}, "write").mode == "ask"
    assert decide(McpPolicy(), "main", "google", "start_google_auth", {}, "unknown").mode == "ask"


@pytest.mark.parametrize(
    ("agent", "tool", "params", "calls", "mode", "reason_part"),
    [
        ("main", "send_gmail_message", {"to": "me@example.com"}, 0, "ask", "도구 정책 ask"),
        ("main", "send_gmail_message", {"to": "x@evil.com"}, 0, "deny", "고정 값"),
        ("main", "send_gmail_message", {"to": ["me@example.com", "x@evil.com"]}, 0, "deny", "고정 값"),
        ("main", "delete_gmail_message", {}, 0, "deny", "막혀"),
        ("scribe", "send_gmail_message", {"to": "me@example.com"}, 0, "deny", "scribe"),
        ("ion", "search_gmail_messages", {}, 0, "deny", "서버"),
        ("main", "search_gmail_messages", {}, 2, "deny", "상한"),
        ("main", "search_gmail_messages", {}, 1, "allow", "종류 기본값"),
    ],
)
def test_decide_checks_lock_deny_agent_limit_in_order(agent, tool, params, calls, mode, reason_part):
    verdict = decide(POLICY, agent, "google", tool, params, "read" if tool.startswith("search") else "write", calls)
    assert verdict.mode == mode and reason_part in verdict.reason


def test_server_lock_applies_to_every_tool_and_tool_lock_wins():
    ok = decide(POLICY, "main", "google", "search_gmail_messages", {"user_google_email": "me@gmail.com"}, "read")
    bad = decide(POLICY, "main", "google", "get_events", {"user_google_email": "other@gmail.com"}, "read")
    assert (ok.mode, bad.mode) == ("allow", "deny") and "고정 값" in bad.reason
    lock = {"user_google_email": ("me@gmail.com",), "to": ("me@example.com",)}
    merged = ToolPolicy(mode="ask", lock=lock, calls_per_hour=5)
    from ash_industry.core.policy.mcp_policy import tool_policy
    assert tool_policy(POLICY, "google", "send_gmail_message") == merged


def test_describe_call_masks_secrets_and_truncates():
    text = describe_call("google", "send_gmail_message", {"to": "a@b.c", "api_token": "xyz", "body": "가" * 100})
    assert text.startswith("google.send_gmail_message(to=a@b.c, api_token=***, body=")
    assert "가" * 60 not in text and text.endswith("…)")


def test_policy_roundtrips_through_dict_and_rejects_bad_mode():
    data = policy_to_dict(POLICY)
    assert parse_policy(data) == POLICY
    assert parse_policy(None) == McpPolicy()
    with pytest.raises(ValueError):
        parse_policy({"servers": {"google": {"tools": {"x": {"mode": "maybe"}}}}})
    with pytest.raises(ValueError):
        parse_policy({"defaults": {"read": "never"}})
