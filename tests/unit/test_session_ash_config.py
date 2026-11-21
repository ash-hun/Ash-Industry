"""session 이 쓰는 AshSettings: 기본값, 환경변수, 싱글톤, 비밀값, 브랜드, 접근 키, 음성, MCP, 스케줄러."""

import pytest
from pydantic import SecretStr

from ash_industry.ash_config import (
    AshSettings,
    get_settings,
    reset_settings,
    MCPServerConfig,
    SchedulerConfig,
    VoiceConfig,
)


def test_default_settings(monkeypatch):
    monkeypatch.delenv("ASH_LLM__PROVIDER", raising=False)
    monkeypatch.delenv("ASH_LLM__MODEL", raising=False)
    monkeypatch.delenv("ASH_SECURITY__REQUIRE_AUTH", raising=False)
    monkeypatch.delenv("ASH_MEMORY__BACKEND", raising=False)
    monkeypatch.delenv("ASH_DEBUG", raising=False)
    settings = AshSettings()
    assert settings.llm.provider == "anthropic"
    assert settings.llm.model == "claude-sonnet-4-5"
    assert settings.security.require_auth is True
    assert settings.memory.backend == "postgres"
    assert settings.debug is False


def test_env_override(monkeypatch):
    monkeypatch.setenv("ASH_LLM__PROVIDER", "openai")
    monkeypatch.setenv("ASH_LLM__MODEL", "gpt-4o")
    monkeypatch.setenv("ASH_DEBUG", "true")

    settings = AshSettings()
    assert settings.llm.provider == "openai"
    assert settings.llm.model == "gpt-4o"
    assert settings.debug is True


def test_get_settings_is_a_singleton_until_reset(monkeypatch):
    monkeypatch.setenv("ASH_LLM__PROVIDER", "anthropic")
    reset_settings()

    s1 = get_settings()

    assert get_settings() is s1
    reset_settings()
    assert get_settings() is not s1


def test_api_key_is_secret(monkeypatch):
    monkeypatch.setenv("ASH_LLM__PROVIDER", "anthropic")
    monkeypatch.setenv("ASH_LLM__API_KEY", "sk-secret-key-123")
    settings = AshSettings()
    assert settings.llm.api_key is not None
    assert settings.llm.api_key.get_secret_value() == "sk-secret-key-123"
    assert "sk-secret" not in str(settings.llm.api_key)


def test_security_config_defaults(monkeypatch):
    monkeypatch.setenv("ASH_LLM__PROVIDER", "anthropic")
    settings = AshSettings()
    assert "user" in settings.security.allowed_roles
    assert settings.security.input_max_length == 10_000
    assert len(settings.security.dangerous_commands) > 0


def test_brand_defaults():
    settings = AshSettings()
    assert settings.brand.name == "A.S.H."
    assert settings.brand.quote == "System Online"
    assert settings.brand.palette.primary == "#e6e8ea"
    assert len(settings.brand.palette.nebula) == 3


def test_brand_env_override(monkeypatch):
    monkeypatch.setenv("ASH_BRAND__NAME", "F.R.I.D.A.Y.")
    monkeypatch.setenv("ASH_BRAND__PALETTE__PRIMARY", "#ff7a45")
    monkeypatch.setenv("ASH_BRAND__PALETTE__NEBULA", '["#ff4b2b", "#ffb347"]')
    settings = AshSettings()
    assert settings.brand.name == "F.R.I.D.A.Y."
    assert settings.brand.palette.primary == "#ff7a45"
    assert settings.brand.palette.nebula == ["#ff4b2b", "#ffb347"]


def test_dangerous_commands_reject_broken_regex(monkeypatch):
    from pydantic import ValidationError

    monkeypatch.setenv("ASH_SECURITY__DANGEROUS_COMMANDS", '["rm -rf (", "sudo"]')
    with pytest.raises(ValidationError, match="dangerous_commands"):
        AshSettings()


def test_brand_rejects_non_hex_color(monkeypatch):
    from pydantic import ValidationError

    monkeypatch.setenv("ASH_BRAND__PALETTE__PRIMARY", "cyan")
    with pytest.raises(ValidationError):
        AshSettings()


def test_api_keys_parse_from_env_json(monkeypatch):
    monkeypatch.setenv(
        "ASH_SECURITY__API_KEYS",
        '{"k-123": {"name": "jh", "roles": ["admin"]}, "k-456": {"name": "guest"}}',
    )
    s = AshSettings()
    assert s.security.api_keys["k-123"].name == "jh"
    assert s.security.api_keys["k-123"].roles == ["admin"]
    assert s.security.api_keys["k-456"].roles == ["user"]  # roles 생략 시 기본값


def test_api_keys_default_empty_means_web_auth_off(monkeypatch):
    monkeypatch.delenv("ASH_SECURITY__API_KEYS", raising=False)
    assert AshSettings().security.api_keys == {}


def test_nested_config_ignores_bare_env(monkeypatch):
    # 중첩 설정이 BaseSettings 이면 자체 생성 시 PATH 같은 bare 환경변수를 필드로 읽는다.
    monkeypatch.setenv("PATH", "/bogus/bin")
    monkeypatch.setenv("MODEL", "bogus-model")
    monkeypatch.delenv("ASH_OPENLOOP__PATH", raising=False)
    monkeypatch.delenv("ASH_USER_MODEL__PATH", raising=False)
    monkeypatch.delenv("ASH_LLM__MODEL", raising=False)
    settings = AshSettings()
    assert settings.openloop.path == "~/.ash/openloops.jsonl"
    assert settings.user_model.path != "/bogus/bin"
    assert settings.llm.model != "bogus-model"


def test_voice_options_reach_the_providers(monkeypatch):
    """ASH_VOICE__WHISPER_MODEL_SIZE, SUPERTONIC_MODEL 이 공급자 생성 옵션으로 간다(전에는 읽기만 하고 버렸다)."""
    from ash_industry.ash_config import VoiceConfig

    v = VoiceConfig(stt_provider="whisper", whisper_model_size="small", tts_provider="browser")
    assert v.stt_options() == {"model_size": "small", "hotwords": ""}
    assert v.tts_options() == {}
    assert v.tts_options("supertonic") == {"model_name": "supertonic-3"}
    assert VoiceConfig().stt_options() == {}


def test_server_config_defaults_to_stdio_without_auth():
    cfg = MCPServerConfig(name="my-server")

    assert cfg.transport == "stdio"
    assert (cfg.command, cfg.url, cfg.env, cfg.headers, cfg.auth_token) == ([], None, {}, {}, None)
    assert cfg.timeout == 30.0


def test_server_config_http_keeps_url():
    cfg = MCPServerConfig(name="http-server", transport="http", url="http://localhost:8080/sse")

    assert (cfg.transport, cfg.url) == ("http", "http://localhost:8080/sse")


def test_server_config_auth_token_is_secret():
    cfg = MCPServerConfig(name="s", auth_token="my-secret")

    assert isinstance(cfg.auth_token, SecretStr)
    assert "my-secret" not in str(cfg)
    assert cfg.auth_token.get_secret_value() == "my-secret"


def test_scheduler_config_defaults_to_enabled_and_schedules_dir(monkeypatch):
    monkeypatch.delenv("ASH_SCHEDULER__ENABLED", raising=False)
    monkeypatch.delenv("ASH_SCHEDULER__SCHEDULES_DIR", raising=False)

    cfg = SchedulerConfig()
    settings = AshSettings()

    assert cfg.enabled is True
    assert "schedules" in cfg.schedules_dir
    assert settings.scheduler.enabled is True


@pytest.mark.parametrize(
    ("config", "expected"),
    [
        (
            VoiceConfig(english_tts_provider="piper", piper_model="/m.onnx"),
            {"model_path": "/m.onnx", "noise_scale": 0.4},
        ),
        (
            VoiceConfig(english_tts_provider="qwen", piper_model="/m/voice.onnx"),
            {"url": "http://host.docker.internal:8770", "piper_model": "/m/voice.onnx", "noise_scale": 0.4},
        ),
        (VoiceConfig(), {}),
    ],
)
def test_english_tts_options_match_the_provider(config, expected):
    assert config.english_tts_options() == expected


def test_profile_settings_sit_between_screen_overlay_and_env(monkeypatch, tmp_path):
    overlay, profile = tmp_path / "settings.yaml", tmp_path / "profile.yaml"
    overlay.write_text("brand:\n  quote: from-screen\n", encoding="utf-8")
    profile.write_text("brand:\n  name: P.R.O.F.\n  quote: from-profile\n", encoding="utf-8")
    monkeypatch.setenv("ASH_SETTINGS_FILE", str(overlay))
    monkeypatch.setenv("ASH_PROFILE_SETTINGS_FILE", str(profile))
    monkeypatch.setenv("ASH_BRAND__NAME", "from-env")

    settings = AshSettings()

    assert (settings.brand.name, settings.brand.quote) == ("P.R.O.F.", "from-screen")


def test_missing_profile_settings_file_falls_back_to_defaults(monkeypatch, tmp_path):
    monkeypatch.setenv("ASH_SETTINGS_FILE", str(tmp_path / "none.yaml"))
    monkeypatch.setenv("ASH_PROFILE_SETTINGS_FILE", str(tmp_path / "missing.yaml"))

    assert AshSettings().brand.name == "A.S.H."
