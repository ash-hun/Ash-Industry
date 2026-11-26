"""doc_edit 기능: HUD 문서 창이 REST 로 docs MCP 의 구조 읽기, 미리보기, 적용, 필드 후보, 양식 등록을 부른다."""

import json
import pytest
from typing import Any

pytest.importorskip("fastapi")

from tests.fixtures.web_hud_helpers import web_assembly, web_client  # noqa: E402
from ash_industry.ash_config import MCPServerConfig  # noqa: E402

DOCS = MCPServerConfig(name="docs", transport="streamable-http", url="http://docs:8001/mcp")
RESULTS: dict[str, Any] = {
    "inspect_document": {
        "path": "a.docx", "format": "docx", "paragraphs": [{"id": "p0", "text": "제목"}], "tables": [],
    },
    "plan_edit": {"plan_id": "9c1d0b7e3f2a", "path": "a.docx", "ok": True, "issues": [],
                  "changes": [{"target": "p0", "before": "제목", "after": "새 제목"}]},
    "apply_edit": {"plan_id": "9c1d0b7e3f2a", "output": "a.edited-1.docx", "verify": {"ok": True},
                   "preview": {"path": "a.edited-1.docx", "format": "png", "files": [".render/a.edited-1/a-1.png"]}},
    "detect_fields": {"template_id": "a-v1", "format": "docx", "candidates": []},
    "register_template": {"error": "채울 자리를 찾지 못했다", "issues": ["x: 표 칸이 없다 t0r0c1"]},
}


@pytest.fixture
def calls(monkeypatch):
    seen: list[tuple[str, dict[str, Any]]] = []

    async def fake_call(server: MCPServerConfig, tool: str, params: dict[str, Any]) -> str:
        seen.append((tool, params))
        return json.dumps(RESULTS[tool], ensure_ascii=False)

    monkeypatch.setattr("ash_industry.app.docs_bridge.call_mcp_tool", fake_call)
    monkeypatch.setattr("ash_industry.ui.web.router.doc_edit_router.find_docs_server", lambda servers: DOCS)
    return seen


def test_structure_plan_apply_fields_and_register(monkeypatch, tmp_path, calls):
    with web_client(web_assembly(monkeypatch, tmp_path)) as client:
        structure = client.get("/api/docs/structure", params={"path": "a.docx"})
        part = client.get("/api/docs/structure", params={"path": "a.docx", "table": "t3", "offset": 2000})
        edits = [{"target": "p0", "text": "새 제목"}]
        plan = client.post("/api/docs/plan", json={"path": "a.docx", "replacements": edits})
        applied = client.post("/api/docs/apply", json={"plan_id": "9c1d0b7e3f2a"})
        fields = client.get("/api/docs/fields", params={"path": "a.docx"})
        fields_body = [{"name": "x", "locator": {"kind": "table_cell", "table": 0, "row": 0, "col": 1}}]
        body = {"path": "a.docx", "template_id": "a-v1", "fields": fields_body}
        register = client.post("/api/docs/templates", json=body)

    assert structure.status_code == 200 and structure.json()["paragraphs"][0]["id"] == "p0"
    assert plan.json()["changes"][0]["after"] == "새 제목"
    assert applied.json()["document"]["source"] == "a.edited-1.docx"
    assert fields.json()["template_id"] == "a-v1"
    assert register.status_code == 422 and register.json()["issues"] == ["x: 표 칸이 없다 t0r0c1"]
    assert calls[0] == ("inspect_document", {"path": "a.docx", "include_empty": True})
    assert calls[1] == ("inspect_document", {"path": "a.docx", "include_empty": True, "table": "t3", "offset": 2000})
    assert calls[-1][1]["kind"] == "blank_form" and part.status_code == 200


def test_bad_input_is_rejected_before_calling(monkeypatch, tmp_path, calls):
    with web_client(web_assembly(monkeypatch, tmp_path)) as client:
        bad_edit = [{"target": "x;rm", "text": "a"}]
        bad_target = client.post("/api/docs/plan", json={"path": "a.docx", "replacements": bad_edit})
        empty = client.post("/api/docs/plan", json={"path": "a.docx", "replacements": []})
        bad_plan = client.post("/api/docs/apply", json={"plan_id": "../../etc"})
        bad_id = client.post("/api/docs/templates", json={"path": "a.docx", "template_id": "a/b", "fields": [{}]})
        no_path = client.get("/api/docs/structure")

    assert [r.status_code for r in (bad_target, empty, bad_plan, bad_id, no_path)] == [422] * 5
    assert calls == []


def test_without_docs_server_is_503(monkeypatch, tmp_path):
    with web_client(web_assembly(monkeypatch, tmp_path)) as client:
        res = client.get("/api/docs/structure", params={"path": "a.docx"})
    assert res.status_code == 503 and "설정에 없다" in res.json()["error"]
