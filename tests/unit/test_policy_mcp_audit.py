"""mcp_policy 기능의 호출 기록: 줄 추가, 최근 조회, 시간당 호출 수, 재시작 뒤 복원과 파일 압축."""

from pathlib import Path

from ash_industry.core.policy.mcp_audit import McpAudit


def test_record_then_recent_and_hourly_count(tmp_path: Path):
    audit = McpAudit(str(tmp_path / "audit.jsonl"), clock=lambda: 10_000.0)
    audit.record({"type": "call", "server": "google", "tool": "get_events", "decision": "allow"})
    audit.record({"type": "call", "server": "google", "tool": "get_events", "decision": "deny"})
    audit.record({"ts": 1, "type": "call", "server": "google", "tool": "get_events", "decision": "allow"})

    assert [e["decision"] for e in audit.recent(2)] == ["allow", "deny"]
    assert audit.calls_last_hour("google", "get_events", 10_000_000) == 1

    again = McpAudit(str(tmp_path / "audit.jsonl"))
    assert len(again.recent()) == 3


def test_file_is_compacted_to_recent_lines(tmp_path: Path):
    path = tmp_path / "audit.jsonl"
    audit = McpAudit(str(path), keep=2)
    for i in range(5):
        audit.record({"type": "result", "tool": f"t{i}", "ok": True})

    # 상한 두 배(4줄)에서 최근 2줄로 다시 쓰고, 그 뒤 한 줄이 더 붙는다
    assert len(path.read_text().splitlines()) == 3
    assert [e["tool"] for e in audit.recent()] == ["t4", "t3"]


def test_memory_only_audit_without_path():
    audit = McpAudit(None)
    audit.record({"type": "result", "tool": "x", "ok": False})
    assert audit.recent() == [audit.recent()[0]] and audit.recent()[0]["tool"] == "x"
