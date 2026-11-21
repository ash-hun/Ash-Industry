"""mcp_policy 기능의 문: 도구 색인, 판정과 기록, 🔒 표시용 모드, 정책 갱신 저장."""

from pathlib import Path

from ash_industry.core.policy.mcp_policy import McpPolicy, ServerPolicy, ToolPolicy, parse_policy
from ash_industry.core.policy.mcp_policy_store import McpPolicyStore
from ash_industry.core.policy.mcp_audit import McpAudit
from ash_industry.core.policy.mcp_gate import McpGate


def _gate(tmp_path: Path) -> McpGate:
    gate = McpGate(McpPolicyStore(str(tmp_path / "policy.yaml")), McpAudit(None), clock=lambda: 1000.0)
    gate.register("search_gmail_messages", "google", None, "메일 검색")
    gate.register("send_gmail_message", "google", None, "메일 보내기")
    return gate


def test_evaluate_records_and_returns_none_for_non_mcp_tools(tmp_path: Path):
    gate = _gate(tmp_path)

    assert gate.evaluate("main", "bash", {"command": "ls"}) is None
    allow = gate.evaluate("main", "search_gmail_messages", {"query": "is:unread"})
    ask = gate.evaluate("main", "send_gmail_message", {"to": "a@b.c"})

    assert (allow.mode, ask.mode) == ("allow", "ask")
    assert [e["decision"] for e in gate.audit.recent()] == ["ask", "allow"]
    assert gate.audit.recent()[1]["call"] == "google.search_gmail_messages(query=is:unread)"
    assert gate.effective_mode("send_gmail_message") == "ask" and gate.effective_mode("bash") is None
    assert gate.ask_tools() == ["send_gmail_message"]


def test_hidden_tools_are_those_the_agent_can_never_call(tmp_path: Path):
    gate = _gate(tmp_path)
    gate.update(parse_policy({
        "agents": {"scribe": {"servers": []}},
        "servers": {"google": {"tools": {"send_gmail_message": {"mode": "deny"}}}},
    }))

    assert gate.hidden_tools("main") == ["send_gmail_message"]
    assert gate.hidden_tools("scribe") == ["search_gmail_messages", "send_gmail_message"]


def test_update_saves_and_applies_and_survives_reload(tmp_path: Path):
    gate = _gate(tmp_path)
    policy = McpPolicy(servers={"google": ServerPolicy(tools={"send_gmail_message": ToolPolicy(mode="deny")})})

    gate.update(policy)
    gate.update(policy)

    assert gate.evaluate("main", "send_gmail_message", {}).mode == "deny"
    assert McpPolicyStore(str(tmp_path / "policy.yaml")).load() == policy
    assert parse_builds_same(tmp_path)


def parse_builds_same(tmp_path: Path) -> bool:
    import yaml
    with open(tmp_path / "policy.yaml", encoding="utf-8") as f:
        return parse_policy(yaml.safe_load(f)).servers["google"].tools["send_gmail_message"].mode == "deny"


def test_record_result_keeps_server_and_short_error(tmp_path: Path):
    gate = _gate(tmp_path)
    gate.record_result("send_gmail_message", ok=False, error="x" * 300)
    entry = gate.audit.recent()[0]
    assert (entry["type"], entry["server"], entry["ok"], len(entry["error"])) == ("result", "google", False, 200)
