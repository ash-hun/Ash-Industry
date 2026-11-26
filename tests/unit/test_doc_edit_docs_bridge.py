"""doc_edit 기능의 다리: 정책 판정, docs MCP 호출과 기록, 결과 글을 dict 와 문서 첨부로."""

import json
import pytest
import asyncio
from typing import Any
from pathlib import Path

from ash_industry.app.docs_bridge import (
    HUD_AGENT, DocsBridge, DocsDenied, DocsUnavailable, parse_result, find_docs_server,
)
from ash_industry.core.policy.mcp_policy_store import McpPolicyStore
from ash_industry.core.policy.mcp_policy import parse_policy
from ash_industry.core.policy.mcp_audit import McpAudit
from ash_industry.core.policy.mcp_gate import McpGate
from ash_industry.ash_config import MCPServerConfig

SERVER = MCPServerConfig(name="docs", transport="streamable-http", url="http://docs:8001/mcp", timeout=0.2)
APPLIED = {
    "plan_id": "9c1d0b7e3f2a", "output": "a.edited-1.docx",
    "preview": {"path": "a.edited-1.docx", "format": "png", "files": [".render/a.edited-1/a-1.png"]},
}


def _gate(tmp_path: Path) -> McpGate:
    gate = McpGate(McpPolicyStore(str(tmp_path / "policy.yaml")), McpAudit(None), clock=lambda: 1000.0)
    gate.register("apply_edit", "docs", {"readOnlyHint": False})
    return gate


def test_call_records_hud_and_attaches_document(tmp_path: Path) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    async def caller(server: MCPServerConfig, tool: str, params: dict[str, Any]) -> str:
        calls.append((tool, params))
        return json.dumps(APPLIED)

    gate = _gate(tmp_path)
    out = asyncio.run(DocsBridge(SERVER, gate, caller).call("apply_edit", {"plan_id": "9c1d0b7e3f2a"}))
    assert calls == [("apply_edit", {"plan_id": "9c1d0b7e3f2a"})]
    assert out["document"]["source"] == "a.edited-1.docx" and out["document"]["pages"] == [".render/a.edited-1/a-1.png"]
    assert [(e.get("agent"), e["type"]) for e in gate.audit.recent()] == [(None, "result"), (HUD_AGENT, "call")]


def test_denied_by_policy_does_not_call(tmp_path: Path) -> None:
    async def caller(server: MCPServerConfig, tool: str, params: dict[str, Any]) -> str:
        raise AssertionError("부르면 안 된다")

    gate = _gate(tmp_path)
    gate.update(parse_policy({"servers": {"docs": {"tools": {"apply_edit": {"mode": "deny"}}}}}))
    with pytest.raises(DocsDenied):
        asyncio.run(DocsBridge(SERVER, gate, caller).call("apply_edit", {"plan_id": "x"}))


def test_missing_server_timeout_and_failure_are_unavailable(tmp_path: Path) -> None:
    async def slow(server: MCPServerConfig, tool: str, params: dict[str, Any]) -> str:
        await asyncio.sleep(1)
        return "{}"

    async def broken(server: MCPServerConfig, tool: str, params: dict[str, Any]) -> str:
        raise ConnectionError("연결 거부")

    with pytest.raises(DocsUnavailable):
        asyncio.run(DocsBridge(None, None).call("apply_edit", {}))
    with pytest.raises(DocsUnavailable, match="답하지 않았다"):
        asyncio.run(DocsBridge(SERVER, None, slow).call("apply_edit", {}))
    gate = _gate(tmp_path)
    with pytest.raises(DocsUnavailable, match="연결 거부"):
        asyncio.run(DocsBridge(SERVER, gate, broken).call("apply_edit", {}))
    assert gate.audit.recent()[0]["ok"] is False


def test_parse_result_and_find_server() -> None:
    assert parse_result('{"changes": []}') == {"changes": []}
    assert parse_result("MCP error: boom") == {"error": "MCP error: boom"}
    assert parse_result("[1, 2]") == {"error": "[1, 2]"}
    assert find_docs_server([MCPServerConfig(name="media"), SERVER]) is SERVER
    assert find_docs_server([]) is None
