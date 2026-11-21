"""settings 의 AshSettings.shortcuts: HUD 단축키 기본값, 형식, 서로 겹치지 않기."""

import pytest
from pydantic import ValidationError

from ash_industry.ash_config import AshSettings, ShortcutsConfig, canonical_shortcut


def test_shortcuts_defaults_and_env_override(monkeypatch):
    monkeypatch.setenv("ASH_SHORTCUTS__VOICE_STOP", "Ctrl+Q")

    shortcuts = AshSettings().shortcuts

    assert shortcuts.voice_start == "Ctrl+Shift+Enter"
    assert (shortcuts.voice_stop, shortcuts.agent_prev) == ("Ctrl+Q", "Ctrl+Shift+ArrowLeft")


def test_canonical_shortcut_orders_modifiers_and_ignores_letter_case():
    assert canonical_shortcut("Shift+Ctrl+a") == "Ctrl+Shift+A"
    assert canonical_shortcut("Escape") == "Escape"
    assert canonical_shortcut("Meta+Alt+F1") == "Alt+Meta+F1"


def test_shortcuts_config_rejects_bad_combo_and_duplicates():
    with pytest.raises(ValidationError):
        ShortcutsConfig(voice_start="Cmd+Enter")
    with pytest.raises(ValidationError, match="voice_start 와 agent_next"):
        ShortcutsConfig(voice_start="Shift+Ctrl+x", agent_next="Ctrl+Shift+X")
