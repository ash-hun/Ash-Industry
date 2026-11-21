"""settings 의 applier: 값을 공유 설정 객체에 쓰고, 값을 복사한 객체는 다시 만들고, 못 쓰는 키는 재시작 대기로."""

import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from ash_industry.app.settings_overlay import FocusPatch, VoicePatch, ThoughtPatch, SettingsPatch, ProactivePatch
from ash_industry.ui.web.settings_applier import SettingsApplier, changed_values
from ash_industry.app.agent_profile import AgentProfile
from ash_industry.core.proactive import FeedbackLearner
from ash_industry.ash_config import AshSettings


def _profile(settings: AshSettings, agent_id: str = "main", shared: bool = True) -> AgentProfile:
    proactive = settings.proactive if shared else settings.proactive.model_copy(update={"enabled": False})
    return AgentProfile(
        agent_id=agent_id,
        brand=settings.brand,
        model=MagicMock(),
        thought=settings.thought,
        proactive=proactive,
        feedback_learner=FeedbackLearner(base_threshold=proactive.effective_threshold()),
    )


@pytest.fixture
def world():
    settings = AshSettings(thought={"enabled": True}, proactive={"enabled": True}, focus={"enabled": True})
    main, scribe = _profile(settings), _profile(settings, "scribe", shared=False)
    by_id = {"main": main, "scribe": scribe}
    agents = SimpleNamespace(profiles=lambda: [main, scribe], get=by_id.get)
    session = MagicMock(session_id="s1")
    registry = SimpleNamespace(active_sessions=lambda: [session], agent_of=lambda sid: "main")
    state = SimpleNamespace(
        settings=settings,
        assembly=SimpleNamespace(agents=agents),
        registry=registry,
        rebuild_voice=MagicMock(),
        rebuild_focus=MagicMock(),
    )
    lifecycle = SimpleNamespace(restart_daemon=AsyncMock())
    return SimpleNamespace(
        settings=settings, state=state, lifecycle=lifecycle, main=main, scribe=scribe, session=session
    )


def test_changed_values_keeps_only_differences_and_is_idempotent():
    settings = AshSettings()
    patch = SettingsPatch(voice=VoicePatch(wake_threshold=settings.voice.wake_threshold, stt_lang="en-US"))

    diff = changed_values(settings, patch)
    settings.voice.stt_lang = "en-US"

    assert diff == {"voice": {"stt_lang": "en-US"}}
    assert changed_values(settings, patch) == {}


async def test_apply_writes_shared_settings_and_rebuilds_copying_objects(world):
    applier = SettingsApplier(world.state, world.lifecycle)
    patch = SettingsPatch(
        voice=VoicePatch(stt_provider="whisper", wake_threshold=0.8),
        proactive=ProactivePatch(daemon_interval_sec=600, cooldown_sec=42, confidence_threshold=0.7),
        focus=FocusPatch(enabled=False),
    )

    result = await applier.apply(patch)
    again = await applier.apply(patch)

    v, pcfg = world.settings.voice, world.settings.proactive
    assert (v.stt_provider, v.wake_threshold, pcfg.daemon_interval_sec, pcfg.cooldown_sec) == ("whisper", 0.8, 600, 42)
    assert world.settings.focus.enabled is False
    assert result.restart_required == [] and len(result.applied) == 6
    assert world.state.rebuild_voice.call_count == 1 and world.state.rebuild_focus.call_count == 1
    assert world.lifecycle.restart_daemon.await_count == 1
    assert world.main.feedback_learner.threshold() == 0.7
    # 정의가 proactive 를 고정한 에이전트의 사본에도 값은 쓰되 enabled 는 그대로
    assert (world.scribe.proactive.cooldown_sec, world.scribe.proactive.enabled) == (42, False)
    assert again.applied == [] and world.state.rebuild_voice.call_count == 1


async def test_apply_marks_thought_enabled_as_restart_required_without_touching_it(world):
    applier = SettingsApplier(world.state, world.lifecycle)

    result = await applier.apply(SettingsPatch(thought=ThoughtPatch(enabled=False, router_threshold=0.5)))

    assert result.restart_required == ["thought.enabled"] and result.applied == ["thought.router_threshold"]
    assert world.settings.thought.enabled is True and world.settings.thought.router_threshold == 0.5


async def test_apply_rebinds_open_sessions_when_proactive_is_toggled(world):
    applier = SettingsApplier(world.state, world.lifecycle)

    await applier.apply(SettingsPatch(proactive=ProactivePatch(enabled=False)))

    world.session.set_proactivity.assert_called_once_with(None)
    assert world.lifecycle.restart_daemon.await_count == 0
