"""[ui] 저장한 설정을 지금 프로세스의 객체에 바로 쓴다. 바로 못 쓰는 키는 재시작 대기로 남긴다."""

import asyncio
from typing import TYPE_CHECKING, Any
from dataclasses import dataclass, field

from ash_industry.app.settings_overlay import SettingsPatch
from ash_industry.common.logger import get_logger

if TYPE_CHECKING:
    from ash_industry.ui.web.web_lifecycle import WebLifecycle
    from ash_industry.ui.web.web_state import WebState
    from ash_industry.ash_config import AshSettings

logger = get_logger(__name__)

# 기동 때 구조(저장소, 사고 엔진, 분류기, 슬래시 명령)를 정하는 키. 값만 바꿔서는 반영되지 않는다
RESTART_KEYS = frozenset({"thought.enabled"})
# 만들 때 값을 복사하는 객체를 다시 만들어야 하는 키
VOICE_REBUILD_KEYS = frozenset({"stt_provider", "stt_fallback", "tts_provider", "whisper_model_size"})
DAEMON_KEYS = frozenset({"daemon_enabled", "daemon_trigger", "daemon_interval_sec", "daemon_idle_sec"})


@dataclass
class AppliedChanges:
    """한 번의 저장이 프로세스에 남긴 것. 키는 `섹션.이름` 꼴."""

    applied: list[str] = field(default_factory=list)
    restart_required: list[str] = field(default_factory=list)


def changed_values(settings: "AshSettings", patch: SettingsPatch) -> dict[str, dict[str, Any]]:
    """patch 중 지금 적용값과 다른 것만. 순수 함수라 같은 patch 를 두 번 넣으면 두 번째는 빈 dict 다."""
    changed: dict[str, dict[str, Any]] = {}
    for section, values in patch.model_dump(exclude_none=True).items():
        current = getattr(settings, section)
        diff = {name: value for name, value in values.items() if getattr(current, name) != value}
        if diff:
            changed[section] = diff
    return changed


class SettingsApplier:
    """설정 객체는 공유라 값을 쓰면 읽는 쪽이 바로 본다. 값을 복사해 둔 객체(음성, daemon, focus)는 다시 만든다."""

    def __init__(self, state: "WebState", lifecycle: "WebLifecycle") -> None:
        self._state = state
        self._lifecycle = lifecycle

    async def apply(self, patch: SettingsPatch) -> AppliedChanges:
        """저장된 patch 를 프로세스에 쓴다. 바뀐 값이 없으면 아무것도 건드리지 않는다."""
        settings = self._state.settings
        changed = changed_values(settings, patch)
        result = AppliedChanges()
        for section, values in changed.items():
            for name, value in values.items():
                key = f"{section}.{name}"
                if key in RESTART_KEYS:
                    result.restart_required.append(key)
                    continue
                setattr(getattr(settings, section), name, value)
                result.applied.append(key)

        voice = changed.get("voice", {})
        if VOICE_REBUILD_KEYS & voice.keys():
            # whisper 는 만들 때 모델을 적재한다. 이벤트 루프를 막지 않게 스레드에서
            await asyncio.to_thread(self._state.rebuild_voice)
        proactive = changed.get("proactive", {})
        if proactive:
            self._sync_agent_profiles(proactive)
        if "confidence_threshold" in proactive:
            for profile in self._state.assembly.agents.profiles():
                profile.feedback_learner.reset(profile.proactive.effective_threshold())
        if "enabled" in proactive:
            self._rebind_sessions()
        if DAEMON_KEYS & proactive.keys():
            await self._lifecycle.restart_daemon()
        if "enabled" in changed.get("focus", {}):
            self._state.rebuild_focus()
        if result.applied or result.restart_required:
            logger.info(
                "[Settings] 저장값 반영", applied=result.applied, restart_required=result.restart_required
            )
        return result

    def _sync_agent_profiles(self, values: dict[str, Any]) -> None:
        """정의 파일이 proactive 를 고정한 에이전트는 설정 사본을 든다. 그 사본에도 쓴다(고정한 enabled 는 빼고)."""
        shared = self._state.settings.proactive
        for profile in self._state.assembly.agents.profiles():
            if profile.proactive is shared:
                continue
            for name, value in values.items():
                if name != "enabled":
                    setattr(profile.proactive, name, value)

    def _rebind_sessions(self) -> None:
        """열린 세션의 proactive 코어를 지금 설정대로 다시 묶는다. 새 세션은 조립 때 설정을 읽는다."""
        registry, agents = self._state.registry, self._state.assembly.agents
        for session in registry.active_sessions():
            profile = agents.get(registry.agent_of(session.session_id))
            if profile is not None:
                session.set_proactivity(profile.proactivity_factory())
