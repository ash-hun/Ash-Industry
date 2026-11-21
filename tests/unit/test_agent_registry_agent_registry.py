"""agent_registry: 정의 파일이 에이전트가 되고 비운 항목은 main 을 이어받으며 도구 경계가 지켜지는지 검증한다."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock

from ash_industry.app.agent_registry import AgentRegistry, agent_model, load_agent_specs, profile_from_spec
from ash_industry.app.agent_profile import ANSWER_RULE, MAIN_AGENT_ID, TEAM_RULE, AgentProfile
from ash_industry.core.policy.approval_rules import ApprovalRule, ApprovalRules
from ash_industry.core.policy.mcp_policy_store import McpPolicyStore
from ash_industry.core.tools.tools_registry import ToolRegistry
from ash_industry.model_layer.model_types import ModelConfig
from tests.fixtures.agent_registry_helpers import app_tools
from ash_industry.core.policy.mcp_audit import McpAudit
from ash_industry.core.proactive import FeedbackLearner
from ash_industry.core.policy.mcp_gate import McpGate
from ash_industry.app.app_context import AppContext
from ash_industry.ash_config import AshSettings

TEAM_DIR = Path(__file__).parents[2] / "examples" / "team"
MAIN = ModelConfig(provider="ollama", model="gemma", api_key=None, base_url="http://x")
SCRIBE = """
name: S.C.R.I.B.E.
description: 정보 수집
palette:
  primary: "#97BC62"
system_prompt: 당신은 스크라이브입니다.
model: gemma-small
tools: [web_search, read_file]
proactive: false
"""
BOUNDED = """
name: S.C.R.I.B.E.
tools: [lh_notice, housing_profile, read_file, schedule]
boundaries:
  ask: [housing_profile]
  never: [read_file]
"""


def _main() -> AgentProfile:
    return AgentProfile.main(AshSettings(), MAIN, MagicMock())


def _bounded_registry(tmp_path, spec: str = BOUNDED) -> AgentRegistry:
    (tmp_path / "scribe.yaml").write_text(spec)
    tools = app_tools("lh_notice", "housing_profile", "read_file", "schedule", "bash")
    ctx = AppContext(session_repo=MagicMock(), tool_registry=tools, settings=AshSettings())
    ctx.agent_tools = ToolRegistry()
    return AgentRegistry.load(ctx, MagicMock(), _main(), str(tmp_path))


def test_spec_file_becomes_profile_on_top_of_main(tmp_path):
    (tmp_path / "scribe.yaml").write_text(SCRIBE)
    specs = load_agent_specs(str(tmp_path))
    main = _main()

    scribe = profile_from_spec("scribe", specs["scribe"], main)

    assert scribe.agent_id == "scribe" and scribe.name == "S.C.R.I.B.E."
    assert scribe.brand.palette.primary == "#97BC62"
    # 정하지 않은 색은 기본 팔레트
    assert scribe.brand.palette.background == main.brand.palette.background
    # 모델은 이름만 바뀌고 프로바이더와 주소는 main 것
    assert (scribe.model.provider, scribe.model.model, scribe.model.base_url) == ("ollama", "gemma-small", "http://x")
    assert scribe.tools == ("web_search", "read_file")
    assert scribe.system_prompt == f"당신은 스크라이브입니다.\n\n{ANSWER_RULE}"
    assert scribe.proactive.enabled is False
    assert scribe.thought is main.thought
    # 피드백 학습은 에이전트마다 따로
    assert scribe.feedback_learner is not main.feedback_learner


def test_unset_fields_inherit_main(tmp_path):
    (tmp_path / "scout.yaml").write_text("name: SCOUT\n")
    main = _main()
    scout = profile_from_spec("scout", load_agent_specs(str(tmp_path))["scout"], main)
    assert scout.model is main.model
    assert scout.proactive is main.proactive
    assert scout.tools == () and scout.system_prompt == ANSWER_RULE


@pytest.mark.parametrize("filename", ["main.yaml", "Bad Name.yaml", "9lives.yaml"])
def test_reserved_or_invalid_ids_are_skipped(tmp_path, filename):
    (tmp_path / filename).write_text("name: X\n")
    assert load_agent_specs(str(tmp_path)) == {}


def test_broken_file_skips_only_itself(tmp_path):
    (tmp_path / "scribe.yaml").write_text(SCRIBE)
    (tmp_path / "typo.yaml").write_text("name: T\nunknown_field: 1\n")
    (tmp_path / "noname.yaml").write_text("description: 이름 없음\n")
    assert list(load_agent_specs(str(tmp_path))) == ["scribe"]


def test_missing_dir_means_main_only(tmp_path):
    ctx = AppContext(session_repo=MagicMock(), tool_registry=MagicMock(), settings=AshSettings())
    registry = AgentRegistry.load(ctx, MagicMock(), _main(), str(tmp_path / "none"))
    assert registry.ids() == [MAIN_AGENT_ID]
    assert registry.main.is_main


def test_registry_keeps_main_first_and_builds_per_agent(tmp_path):
    (tmp_path / "scribe.yaml").write_text(SCRIBE)
    ctx = AppContext(session_repo=MagicMock(), tool_registry=MagicMock(), settings=AshSettings())
    registry = AgentRegistry.load(ctx, MagicMock(), _main(), str(tmp_path))

    assert registry.ids() == ["main", "scribe"]
    assert "scribe" in registry and "ghost" not in registry
    assert registry.builder("scribe").profile is registry.get("scribe")
    assert registry.get("ghost") is None
    with pytest.raises(KeyError):
        registry.builder("ghost")


def test_every_profile_reads_the_delegation_rule_with_the_others(tmp_path):
    (tmp_path / "scribe.yaml").write_text(SCRIBE)
    ctx = AppContext(session_repo=MagicMock(), tool_registry=MagicMock(), settings=AshSettings())
    registry = AgentRegistry.load(ctx, MagicMock(), _main(), str(tmp_path))

    main, scribe = registry.get("main"), registry.get("scribe")
    assert main is not None and scribe is not None
    assert main.system_prompt.endswith(f"{TEAM_RULE}\n팀:\n- scribe: S.C.R.I.B.E.: 정보 수집")
    assert scribe.system_prompt.startswith("당신은 스크라이브입니다.") and scribe.system_prompt.endswith("(팀 총괄)")
    assert registry.task_agent("scribe").system_prompt == scribe.system_prompt


def test_main_alone_gets_no_team_rule(tmp_path):
    ctx = AppContext(session_repo=MagicMock(), tool_registry=MagicMock(), settings=AshSettings())
    registry = AgentRegistry.load(ctx, MagicMock(), _main(), str(tmp_path / "none"))

    assert TEAM_RULE not in (registry.main.system_prompt or "")


def test_mcp_policy_hides_other_agents_servers_from_tool_lists(tmp_path):
    (tmp_path / "clerk.yaml").write_text("name: Clerk\ntools: [apply_edit]\n")
    (tmp_path / "policy.yaml").write_text("agents:\n  main: {servers: [google]}\n  clerk: {servers: [docs]}\n")
    gate = McpGate(McpPolicyStore(str(tmp_path / "policy.yaml")), McpAudit(None))
    gate.register("apply_edit", "docs", {"readOnlyHint": False})
    gate.register("get_events", "google", {"readOnlyHint": True})
    tools = app_tools("apply_edit", "get_events", "bash")
    ctx = AppContext(session_repo=MagicMock(), tool_registry=tools, settings=AshSettings(), mcp_gate=gate)
    ctx.agent_tools = ToolRegistry()
    registry = AgentRegistry.load(ctx, MagicMock(), _main(), str(tmp_path))

    main_names = {t.name for t in registry.builder("main").tool_registry().list_all()}
    clerk_names = {t.name for t in registry.builder("clerk").tool_registry().list_all()}

    assert main_names == {"get_events", "bash"} and clerk_names == {"apply_edit"}


def test_registry_rejects_non_main_first():
    ctx = AppContext(session_repo=MagicMock(), tool_registry=MagicMock(), settings=AshSettings())
    scribe = AgentProfile(
        agent_id="scribe", brand=MagicMock(), model=MAIN, thought=MagicMock(), proactive=MagicMock(),
        feedback_learner=MagicMock(),
    )
    with pytest.raises(ValueError):
        AgentRegistry(ctx, MagicMock(), [scribe])


def test_example_team_profile_loads_with_its_own_persona():
    """저장소의 examples/team 예시가 실제로 읽힌다."""
    main = AgentProfile.main(AshSettings(), ModelConfig(provider="faux", model="m"), FeedbackLearner())
    specs = load_agent_specs(str(TEAM_DIR))

    scribe = profile_from_spec("scribe", specs["scribe"], main)

    assert scribe.name == "S.C.R.I.B.E." and scribe.tools == ("read_file", "write_file", "list_dir")
    assert scribe.system_prompt is not None and scribe.system_prompt.startswith("너는 차분하고")
    assert scribe.brand.persona != main.brand.persona


def test_approval_rules_are_per_agent_and_cached(tmp_path):
    settings = AshSettings()
    settings.security.agent_approvals_dir = str(tmp_path / "approvals")
    common = ApprovalRules(str(tmp_path / "approvals.yaml"))
    services = MagicMock()
    services.approval_rules = common
    ctx = AppContext(session_repo=MagicMock(), tool_registry=MagicMock(), settings=settings)
    (tmp_path / "team").mkdir()
    (tmp_path / "team" / "scribe.yaml").write_text(SCRIBE)
    registry = AgentRegistry.load(ctx, services, _main(), str(tmp_path / "team"))

    scribe = registry.approval_rules("scribe")
    assert registry.approval_rules("scribe") is scribe
    scribe.add(ApprovalRule("bash", "ls"))
    assert (tmp_path / "approvals" / "scribe.yaml").exists()
    assert not registry.approval_rules("main").allows("bash", {"command": "ls"})


def test_spec_boundaries_reach_the_profile(tmp_path):
    (tmp_path / "scribe.yaml").write_text(BOUNDED)

    scribe = profile_from_spec("scribe", load_agent_specs(str(tmp_path))["scribe"], _main())

    assert (scribe.ask_tools, scribe.never_tools) == (("housing_profile",), ("read_file",))


@pytest.mark.parametrize(
    ("spec", "hidden", "visible"),
    [
        (BOUNDED, "read_file", {"lh_notice", "housing_profile", "schedule"}),
        ("name: SCOUT\nboundaries:\n  never: [bash]\n", "bash", {"lh_notice"}),
    ],
    ids=["listed_tools", "whole_app_registry"],
)
def test_never_tools_are_not_visible(tmp_path, spec, hidden, visible):
    names = {t.name for t in _bounded_registry(tmp_path, spec).builder("scribe").tool_registry().list_all()}

    assert hidden not in names and visible <= names


def test_task_agent_carries_ask_tools(tmp_path):
    agent = _bounded_registry(tmp_path).task_agent("scribe")

    assert agent is not None and agent.ask_tools == ("housing_profile",)


def test_agent_model_other_provider_drops_main_key_and_address():
    main = ModelConfig(provider="anthropic", model="claude", api_key="sk-ant", base_url="http://a", max_tokens=99)
    model = agent_model(main, "openai", "gpt-4o")
    assert (model.provider, model.model, model.api_key, model.base_url, model.max_tokens) == (
        "openai", "gpt-4o", None, None, 99
    )


def test_agent_model_same_or_no_provider_only_renames():
    assert agent_model(MAIN, "ollama", "gemma-small") == MAIN.model_copy(update={"model": "gemma-small"})
    assert agent_model(MAIN, None, None) is MAIN


def test_agent_model_max_tokens_overrides_main(tmp_path):
    assert agent_model(MAIN, None, None, 16000).max_tokens == 16000
    assert agent_model(MAIN, "openai", "gpt-4o", 8000).max_tokens == 8000
    (tmp_path / "studio.yaml").write_text("name: Studio\nmax_tokens: 16000\n")
    profile = profile_from_spec("studio", load_agent_specs(str(tmp_path))["studio"], _main())
    assert profile.model.max_tokens == 16000 and profile.model.model == MAIN.model

