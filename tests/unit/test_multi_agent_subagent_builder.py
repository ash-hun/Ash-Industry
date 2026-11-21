"""multi_agent: SubagentBuilder 가 정의의 도구 서브셋과 model_override 를 서브 세션에 넘기는지 검증한다."""

import pytest
from typing import Any
from unittest.mock import MagicMock

from ash_industry.core.multi_agent.factory import AgentDefinition, AgentMemoryPolicy
from ash_industry.core.procedures.procedures_store import STATUS_APPROVED, Procedure
from ash_industry.core.tools.builtin.read_file import ReadFileTool
from ash_industry.core.tools.tools_registry import ToolRegistry
from ash_industry.app.subagent_builder import SubagentBuilder
from ash_industry.model_layer.model_types import ModelConfig
from ash_industry.core.procedures.tool import ProcedureTool
from ash_industry.core.tools.builtin.bash import BashTool
from ash_industry.app.app_context import AppContext
from ash_industry.ash_config import AshSettings


@pytest.fixture
def captured(monkeypatch) -> dict[str, Any]:
    seen: dict[str, Any] = {}

    def fake_session(**kwargs: Any) -> dict[str, Any]:
        seen.update(kwargs)
        return kwargs

    monkeypatch.setattr("ash_industry.core.session.AgentSession", fake_session)
    return seen


def _builder(main_registry: ToolRegistry) -> tuple[SubagentBuilder, MagicMock]:
    settings = AshSettings()
    ctx = AppContext(session_repo=MagicMock(), tool_registry=main_registry, settings=settings)
    services = MagicMock()
    return SubagentBuilder(ctx, services, main_registry), services


def _main_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(BashTool())
    registry.register(ReadFileTool())
    return registry


def test_build_session_with_tools_keeps_only_known_names(captured):
    main = _main_registry()
    builder, _ = _builder(main)

    builder.build_session(AgentDefinition(name="w", description="d", tools=["read_file", "ghost"]), "agent_w")

    registry = captured["tool_registry"]
    assert registry is not main
    assert [t.name for t in registry.list_all()] == ["read_file"]
    assert captured["agent_name"] == "w" and captured["inherit_scope"] is True


def test_build_session_without_tools_sees_main_tools_but_not_other_agents_procedures(captured):
    main = _main_registry()
    main.register(ProcedureTool(Procedure(name="mine", description="d", body="b", status=STATUS_APPROVED, agent="p")))
    main.register(ProcedureTool(Procedure(name="other", description="d", body="b", status=STATUS_APPROVED)))
    builder, _ = _builder(main)

    builder.build_session(AgentDefinition(name="p", description="d"), "agent_p")

    names = sorted(t.name for t in captured["tool_registry"].list_all())
    assert names == ["bash", "procedure_mine", "read_file"]


def test_build_session_model_override_replaces_only_model_name(captured):
    builder, _ = _builder(_main_registry())

    builder.build_session(AgentDefinition(name="p", description="d", model_override="tiny"), "agent_p")

    model = captured["model"]
    llm = AshSettings().llm
    assert (model.provider, model.model, model.temperature, model.max_tokens) == (
        llm.provider, "tiny", llm.temperature, llm.max_tokens,
    )


def test_build_session_without_override_uses_app_model_config(captured):
    builder, services = _builder(_main_registry())

    builder.build_session(AgentDefinition(name="p", description="d"), "agent_p")

    assert captured["model"] is services.model_config


def test_node_tool_uses_definition_name_and_description():
    builder, _ = _builder(_main_registry())

    tool = builder.node_tool(AgentDefinition(name="planner", description="계획 세우기"), MagicMock())

    assert tool.name == "agent_planner"
    assert tool.description == "계획 세우기"


def test_build_session_keeps_long_term_memory_by_default(captured):
    builder, services = _builder(_main_registry())

    builder.build_session(AgentDefinition(name="w", description="d"), "agent_w")

    assert captured["memory"] is services.memory


def test_build_session_without_ltm_gets_no_memory(captured):
    builder, _ = _builder(_main_registry())

    definition = AgentDefinition(name="focus-analysis", description="d", memory=AgentMemoryPolicy(ltm=False))
    builder.build_session(definition, "focus_t_analysis")

    assert captured["memory"] is None


def test_build_session_with_parent_inherits_persona_model_memory_and_tool_pool(captured, tmp_path, monkeypatch):
    team = tmp_path / "team"
    team.mkdir()
    (team / "scribe.yaml").write_text(
        "name: S.C.R.I.B.E.\npersona: |\n  스크라이브처럼 말한다.\nprovider: openai\nmodel: gpt-4o\ntools: [bash]\n"
    )
    monkeypatch.setenv("ASH_TEAM__DIR", str(team))
    main_registry = _main_registry()
    pool = ToolRegistry()
    pool.register(ReadFileTool())
    settings = AshSettings()
    ctx = AppContext(session_repo=MagicMock(), tool_registry=main_registry, settings=settings, agent_tools=pool)
    services = MagicMock()
    services.model_config = ModelConfig(provider="anthropic", model="claude", api_key="k")
    builder = SubagentBuilder(ctx, services, main_registry)

    builder.build_session(
        AgentDefinition(
            name="housing", description="d", parent="scribe", tools=["read_file", "bash"], system_prompt="문서 규칙"
        ),
        "agent_housing__s1",
    )

    assert captured["system_prompt"].startswith("스크라이브처럼 말한다.") and "문서 규칙" in captured["system_prompt"]
    assert captured["memory_agent"] == "scribe" and captured["agent_name"] == "housing"
    assert sorted(t.name for t in captured["tool_registry"].list_all()) == ["bash", "read_file"]
    assert captured["model"].provider == "openai" and captured["model"].model == "gpt-4o"
