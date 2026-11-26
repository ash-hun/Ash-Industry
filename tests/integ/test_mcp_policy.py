"""mcp_policy 기능: 정책 API 가 도구 목록과 판정을 보이고, 저장한 정책이 바로 적용되며, 기록이 조회된다."""

import pytest

pytest.importorskip("fastapi")

from tests.fixtures.web_hud_helpers import web_assembly, web_client  # noqa: E402


@pytest.fixture
def client(monkeypatch, tmp_path):
    env = {
        "MCP_SERVERS": '[{"name":"google","transport":"streamable-http","url":"http://127.0.0.1:1/mcp","timeout":0.2}]',
        "SECURITY__MCP_POLICY_PATH": str(tmp_path / "mcp_policy.yaml"),
        "SECURITY__MCP_AUDIT_PATH": str(tmp_path / "mcp_audit.jsonl"),
    }
    assembly = web_assembly(monkeypatch, tmp_path, **env)
    gate = assembly.ctx.mcp_gate
    assert gate is not None
    gate.register("search_gmail_messages", "google", None, "메일 검색")
    gate.register("send_gmail_message", "google", None, "메일 보내기")
    with web_client(assembly) as c:
        yield c, gate


def test_policy_roundtrip_changes_effective_mode_and_records_denial(client):
    c, gate = client
    body = c.get("/api/mcp/policy").json()
    assert body["enabled"] and [t["name"] for t in body["tools"]] == ["search_gmail_messages", "send_gmail_message"]
    effective = {t["name"]: t["effective"] for t in body["tools"]}
    assert effective == {"search_gmail_messages": "allow", "send_gmail_message": "ask"}

    doc = {"defaults": {"read": "ask"}, "servers": {"google": {"tools": {"send_gmail_message": {"mode": "deny"}}}}}
    saved = c.put("/api/mcp/policy", json=doc).json()
    effective = {t["name"]: t["effective"] for t in saved["tools"]}
    assert effective == {"search_gmail_messages": "ask", "send_gmail_message": "deny"}
    assert c.put("/api/mcp/policy", json=doc).json()["policy"] == saved["policy"]
    assert gate.evaluate("main", "send_gmail_message", {}).mode == "deny"

    audit = c.get("/api/mcp/audit?limit=5").json()["entries"]
    assert audit[0]["tool"] == "send_gmail_message" and audit[0]["decision"] == "deny"


def test_policy_rejects_unknown_mode_and_fields(client):
    c, _ = client
    assert c.put("/api/mcp/policy", json={"defaults": {"read": "maybe"}}).status_code == 422
    bad_limit = {"servers": {"google": {"tools": {"x": {"calls_per_hour": -1}}}}}
    assert c.put("/api/mcp/policy", json=bad_limit).status_code == 422
    assert c.put("/api/mcp/policy", json={"bogus": 1}).status_code == 422


def test_policy_effective_follows_agent_query(client):
    c, _ = client
    doc = {"agents": {"evi": {"servers": ["docs"]}}}
    saved = c.put("/api/mcp/policy?agent=evi", json=doc).json()
    assert saved["agent"] == "evi" and {t["effective"] for t in saved["tools"]} == {"deny"}
    main = c.get("/api/mcp/policy").json()
    assert main["agent"] == "main" and {t["effective"] for t in main["tools"]} == {"allow", "ask"}
    assert {t["effective"] for t in c.get("/api/mcp/policy?agent=evi").json()["tools"]} == {"deny"}
    assert c.get("/api/mcp/policy?agent=../x").status_code == 422
