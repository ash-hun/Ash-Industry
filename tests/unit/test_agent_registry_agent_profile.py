"""agent_registry: 시스템 프롬프트 조립, 사고 모델 상속, 분류기와 proactivity 팩토리 생성 조건을 검증한다."""

import pytest
from pydantic import SecretStr
from unittest.mock import MagicMock

from ash_industry.app.agent_profile import (
    ANSWER_RULE,
    MAIN_AGENT_ID,
    TEAM_RULE,
    AgentProfile,
    compose_system_prompt,
    team_rule,
)
from tests.fixtures.agent_loop_helpers import ScriptedProvider, register, text_turn
from ash_industry.model_layer.model_types import ModelConfig
from ash_industry.ash_config import AshSettings

MAIN = ModelConfig(provider="anthropic", model="claude", api_key="mainkey", base_url="https://main", temperature=0.3,
                   max_tokens=123)


def _profile(thought_enabled: bool = True, proactive_enabled: bool = True, **thought: object) -> AgentProfile:
    settings = AshSettings()
    settings.thought.enabled = thought_enabled
    settings.proactive.enabled = proactive_enabled
    for k, v in thought.items():
        setattr(settings.thought, k, v)
    learner = MagicMock()
    learner.threshold = lambda: 0.5
    return AgentProfile.main(settings, MAIN, learner)


@pytest.mark.parametrize(
    ("persona", "instructions", "expected"),
    [
        ("차분하게", "lh_notice 로", f"차분하게\n\nlh_notice 로\n\n{ANSWER_RULE}"),
        ("차분하게", None, f"차분하게\n\n{ANSWER_RULE}"),
        ("", "  ", ANSWER_RULE),
    ],
)
def test_persona_comes_before_work_instructions_and_answer_rule_is_always_last(persona, instructions, expected):
    assert compose_system_prompt(persona, instructions) == expected


def test_main_uses_main_agent_id_and_settings_parts():
    settings = AshSettings()
    profile = AgentProfile.main(settings, MAIN, MagicMock())
    assert profile.agent_id == MAIN_AGENT_ID == "main"
    assert profile.brand == settings.brand
    assert profile.model is MAIN


def test_thought_model_inherits_everything_when_unset():
    m = _profile(provider="", model="", api_key=None, base_url="").thought_model()
    assert (m.provider, m.model, m.api_key, m.base_url) == ("anthropic", "claude", "mainkey", "https://main")
    assert (m.temperature, m.max_tokens) == (0.3, 123)


def test_thought_model_overrides_only_given_fields():
    m = _profile(model="haiku", api_key=SecretStr("tkey")).thought_model()
    assert (m.provider, m.model, m.api_key, m.base_url) == ("anthropic", "haiku", "tkey", "https://main")


def test_thought_model_caps_output_tokens_from_long_answer_agents():
    from ash_industry.app.agent_profile import THOUGHT_MAX_TOKENS, thought_model_config

    settings = AshSettings()
    long = ModelConfig(provider="anthropic", model="sonnet", max_tokens=128000)
    short = ModelConfig(provider="anthropic", model="sonnet", max_tokens=1024)
    assert thought_model_config(settings.thought, long).max_tokens == THOUGHT_MAX_TOKENS
    assert thought_model_config(settings.thought, short).max_tokens == 1024


def test_reply_classifier_none_when_thought_disabled():
    assert _profile(thought_enabled=False).reply_classifier() is None


async def test_reply_classifier_asks_the_thought_model():
    seen: list[str] = []

    class Recording(ScriptedProvider):
        async def stream(self, model, context, options=None):
            seen.append(model.model)
            async for event in super().stream(model, context, options):
                yield event

    provider_name = register(Recording([text_turn('{"verdict": "accept"}')])).provider
    classifier = _profile(provider=provider_name, model="haiku").reply_classifier()
    assert classifier is not None

    await classifier.classify("feedback", "좋아")

    assert seen == ["haiku"]


def test_proactivity_factory_none_unless_proactive_and_thought():
    assert _profile(thought_enabled=False).proactivity_factory() is None
    assert _profile(proactive_enabled=False).proactivity_factory() is None
    assert _profile(thought_enabled=False, proactive_enabled=False).proactivity_factory() is None


def test_turn_detach_ignores_proactive_switch_and_is_off_at_zero():
    from ash_industry.core.turn import TurnDetach

    assert isinstance(_profile(proactive_enabled=False).turn_detach(), TurnDetach)
    assert isinstance(_profile(thought_enabled=False).turn_detach(), TurnDetach)
    off = _profile()
    off.proactive.detach_after_sec = 0
    assert off.turn_detach() is None


def test_proactivity_factory_binds_emit_and_learner_threshold():
    from ash_industry.core.proactive import DefaultProactivityCore

    factory = _profile().proactivity_factory()
    assert factory is not None

    async def emit(_msg: object) -> None:
        return None

    core = factory(emit)
    assert isinstance(core, DefaultProactivityCore)
    assert core._emit is emit
    assert core._policy._threshold_provider() == 0.5


def _teammate(agent_id: str, name: str, description: str) -> AgentProfile:
    main = _profile()
    from dataclasses import replace

    from ash_industry.ash_config import BrandConfig

    return replace(main, agent_id=agent_id, brand=BrandConfig(name=name), description=description, system_prompt="일")


def test_team_rule_lists_teammates_except_self_and_marks_main():
    main, clerk = _profile(), _teammate("clerk", "Clerk", "행정문서 담당")

    for_main = team_rule("main", [main, clerk])
    for_clerk = team_rule("clerk", [main, clerk])

    assert for_main.startswith(TEAM_RULE) and for_main.endswith("팀:\n- clerk: Clerk: 행정문서 담당")
    assert for_clerk.endswith(f"팀:\n- main: {main.name} (팀 총괄)") and "clerk:" not in for_clerk


def test_team_rule_is_empty_without_teammates_and_with_team_is_idempotent():
    main, clerk = _profile(), _teammate("clerk", "Clerk", "행정문서 담당")
    rule = team_rule("clerk", [main, clerk])

    assert team_rule("main", [main]) == "" and main.with_team("") is main
    once = clerk.with_team(rule)
    assert once.system_prompt == f"일\n\n{rule}" and once.with_team(rule) is once
