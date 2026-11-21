"""agent_registry 의 InfraBuilder: 모델, 도구, 성찰 트리거, 알림, 에이전트 신원과 도구, openloop 저장소 조립."""

import pytest
import asyncio
from pydantic import SecretStr

from ash_industry.core.proactive import ActivityClock, AnyTrigger, ExternalTrigger, IdleTrigger, IntervalTrigger
from ash_industry.agent_layer.openloop import InMemoryOpenLoopStore, JsonlOpenLoopStore
from ash_industry.app.infra_builder import InfraBuilder, build_app
from ash_industry.memory.stores.in_memory import InMemoryItemStore
from ash_industry.memory.memory_service import MemoryService
from tests.fixtures.extension_helpers import write_extension
from ash_industry.ash_config import AshSettings


FOREVER = 3600


def _settings(**proactive: object) -> AshSettings:
    settings = AshSettings()
    for k, v in proactive.items():
        setattr(settings.proactive, k, v)
    return settings


def test_build_model_config_copies_llm_settings():
    settings = AshSettings()

    m = InfraBuilder(settings).build_model_config()

    llm = settings.llm
    assert (m.provider, m.model, m.base_url, m.temperature, m.max_tokens) == (
        llm.provider, llm.model, llm.base_url, llm.temperature, llm.max_tokens,
    )


def test_build_tool_registry_has_builtin_tools_and_same_names_twice():
    builder = InfraBuilder(_settings())

    first = sorted(t.name for t in builder.build_tool_registry().list_all())

    assert {"bash", "read_file", "write_file", "edit_file", "glob", "grep", "list_dir"} <= set(first)
    assert first == sorted(t.name for t in builder.build_tool_registry().list_all())


def test_extension_tools_are_kept_out_of_the_app_registry(tmp_path):
    write_extension(tmp_path, "sample", ("agent_only_a", "agent_only_b"), memory_tool="needs_memory", command="sample")
    settings = _settings()
    settings.plugin.extensions_dir = str(tmp_path)
    builder = InfraBuilder(settings)

    ext = builder.build_agent_tools()
    agent_only = {t.name for t in ext.agent_tools.list_all()}

    assert agent_only == {"agent_only_a", "agent_only_b"}
    assert [c.name for c in ext.commands] == ["sample"]
    assert not agent_only & {t.name for t in builder.build_tool_registry().list_all()}
    with_memory = {t.name for t in builder.build_agent_tools(MemoryService(InMemoryItemStore())).agent_tools.list_all()}
    assert with_memory == agent_only | {"needs_memory"}


@pytest.mark.parametrize(
    ("mode", "kind"),
    [("interval", IntervalTrigger), ("idle", IdleTrigger), ("both", AnyTrigger)],
)
def test_build_reflection_trigger_modes(mode, kind):
    trigger = InfraBuilder(_settings(daemon_trigger=mode)).build_reflection_trigger(ActivityClock())

    assert isinstance(trigger, kind)


@pytest.mark.parametrize(("interval", "idle"), [(0, FOREVER), (FOREVER, 0)])
async def test_both_mode_wakes_on_interval_or_idle(interval, idle):
    settings = _settings(daemon_trigger="both", daemon_interval_sec=interval, daemon_idle_sec=idle)

    trigger = InfraBuilder(settings).build_reflection_trigger(ActivityClock())

    await asyncio.wait_for(trigger.wait(), timeout=1.0)


@pytest.mark.parametrize(("idle", "fire"), [(FOREVER, True), (0, False)])
async def test_external_trigger_is_combined_with_the_mode(idle, fire):
    external = ExternalTrigger()
    settings = _settings(daemon_trigger="idle", daemon_idle_sec=idle)
    trigger = InfraBuilder(settings).build_reflection_trigger(ActivityClock(), external)
    if fire:
        external.fire()

    await asyncio.wait_for(trigger.wait(), timeout=1.0)

    assert isinstance(trigger, AnyTrigger)


def test_build_notifier_none_without_channel():
    assert InfraBuilder(_settings()).build_notifier() is None


async def test_build_notifier_sends_to_slack_and_discord_once(monkeypatch, tmp_path):
    sent: list[str] = []

    async def fake_post(url, body):  # type: ignore[no-untyped-def]
        sent.append(url)
        return 204

    monkeypatch.setattr("ash_industry.core.notify.slack.post_json", fake_post)
    monkeypatch.setattr("ash_industry.core.notify.discord.post_json", fake_post)
    settings = _settings()
    settings.notify.slack_webhook_url = SecretStr("https://hooks.slack.com/x")
    settings.notify.discord_webhook_url = SecretStr("https://discord.com/api/webhooks/1/t")
    settings.notify.sent_path = str(tmp_path / "notify_sent.jsonl")
    notify = InfraBuilder(settings).build_notifier()
    assert notify is not None

    await notify({"type": "reminder", "id": "r1", "name": "n", "text": "t"})
    await notify({"type": "reminder", "id": "r1", "name": "n", "text": "t"})  # 같은 알림은 채널마다 한 번

    assert sent == ["https://hooks.slack.com/x", "https://discord.com/api/webhooks/1/t"]
    assert len((tmp_path / "notify_sent.jsonl").read_text().splitlines()) == 2


def test_agent_identities_use_brand_names_and_avatar_folder(tmp_path):
    (tmp_path / "scribe.yaml").write_text("name: S.C.R.I.B.E.\npalette:\n  primary: \"#97BC62\"\n", encoding="utf-8")
    settings = _settings()
    settings.team.dir = str(tmp_path)
    settings.notify.avatar_base_url = "https://cdn.example/avatars/"
    builder = InfraBuilder(settings)

    identities = builder.agent_identities()

    assert identities["scribe"] == ("S.C.R.I.B.E.", "https://cdn.example/avatars/scribe.png", "#97BC62")
    main_brand = settings.brand
    assert identities["main"] == (main_brand.name, "https://cdn.example/avatars/main.png", main_brand.palette.primary)
    settings.notify.avatar_base_url = ""
    assert builder.agent_identities()["scribe"][:2] == ("S.C.R.I.B.E.", "")


@pytest.fixture
def agents_dir(monkeypatch, tmp_path):
    agents = tmp_path / "agents"
    monkeypatch.setenv("ASH_AGENTS__AGENTS_DIR", str(agents))
    monkeypatch.setenv("ASH_PROACTIVE__DAEMON_ENABLED", "false")
    monkeypatch.setenv("ASH_SCHEDULER__ENABLED", "false")
    monkeypatch.setenv("ASH_MEMORY__BACKEND", "in_memory")
    monkeypatch.setenv("ASH_SESSION__PERSISTENCE_BACKEND", "jsonl")
    monkeypatch.setenv("ASH_SESSION__SESSIONS_DIR", str(tmp_path / "sessions"))
    return agents


def test_build_app_wires_agent_tools_orchestrate_tool_and_slash(agents_dir):
    agents_dir.mkdir()
    (agents_dir / "team.yaml").write_text(
        "- name: planner\n  description: 계획\n  level: 0\n"
        "- name: writer\n  description: 작성\n  capabilities: [보고서]\n  level: 1\n  tools: [read_file]\n"
    )

    ctx = build_app(AshSettings()).ctx

    names = {t.name for t in ctx.tool_registry.list_all()}
    assert {"agent_planner", "agent_writer", "orchestrate"} <= names
    assert "orchestrate" in ctx.dispatcher.commands
    orchestrate = ctx.tool_registry.get("orchestrate")
    assert "planner" in orchestrate.description and "writer" in orchestrate.description


def test_build_app_without_agents_has_no_orchestrate(agents_dir):
    ctx = build_app(AshSettings()).ctx

    assert ctx.tool_registry.get("orchestrate") is None
    assert "orchestrate" not in ctx.dispatcher.commands


def test_build_openloop_store_defaults_to_jsonl_and_honors_in_memory(tmp_path):
    settings = AshSettings()
    settings.openloop.path = str(tmp_path / "ol.jsonl")

    default_store = InfraBuilder(settings).build_openloop_store()
    settings.openloop.backend = "in_memory"
    memory_store = InfraBuilder(settings).build_openloop_store()

    assert AshSettings().openloop.backend == "jsonl"
    assert isinstance(default_store, JsonlOpenLoopStore)
    assert isinstance(memory_store, InMemoryOpenLoopStore)
