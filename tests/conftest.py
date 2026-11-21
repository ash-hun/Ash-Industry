"""공통 테스트 fixture. 모든 테스트는 실 API 없이 FauxProvider 로 돈다."""
import os
import sys
import pytest
import socket
from pathlib import Path

# src/ 를 import 경로에 추가 (Docker 외 로컬 실행 대비)
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# 환경변수 강제 설정 (테스트 전 config 오염 방지)
os.environ.setdefault("ASH_LLM__PROVIDER", "faux")
os.environ.setdefault("ASH_LLM__MODEL", "faux-model")
os.environ.setdefault("ASH_MEMORY__BACKEND", "in_memory")
os.environ.setdefault("ASH_SECURITY__REQUIRE_AUTH", "false")
# 개발자의 ~/.ash/team 이 테스트 앱에 에이전트를 더하지 않게. 팀 테스트는 monkeypatch 로 디렉터리를 준다
os.environ.setdefault("ASH_TEAM__DIR", str(Path(__file__).parent / "fixtures" / "no-team"))
# 개발자의 ~/.ash/settings.yaml 이 테스트 설정을 덮지 않게. 없는 파일을 가리킨다
os.environ.setdefault("ASH_SETTINGS_FILE", str(Path(__file__).parent / "fixtures" / "no-settings.yaml"))

# 개발자의 로컬 .env 가 테스트 기본값을 덮지 않게. 테스트는 환경변수와 monkeypatch 로만 설정을 바꾼다
from ash_industry.ash_config import AshSettings  # noqa: E402

AshSettings.model_config["env_file"] = None


# ── 외부 네트워크 차단 ─────────────────────────────────────────────────────────

LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}
_real_connect = socket.socket.connect
_real_connect_ex = socket.socket.connect_ex


def _guard(address: object) -> None:
    # 유닉스 소켓(asyncio 내부 socketpair)과 로컬 테스트 DB 는 허용한다. 그 밖은 외부 API 라 mock 이어야 한다
    if isinstance(address, tuple) and address and str(address[0]) not in LOOPBACK_HOSTS:
        raise RuntimeError(f"테스트가 외부 네트워크로 나가려 했다: {address!r}")


def _guarded_connect(self: socket.socket, address: object) -> None:
    _guard(address)
    _real_connect(self, address)


def _guarded_connect_ex(self: socket.socket, address: object) -> int:
    _guard(address)
    return _real_connect_ex(self, address)


@pytest.fixture(autouse=True)
def isolated_home(monkeypatch, tmp_path_factory):
    # 설정 기본 경로(~/.ash/focus 등)를 그대로 쓰는 조립이 실제 홈에 폴더를 만들었다(2026-11-21 실측)
    monkeypatch.setenv("HOME", str(tmp_path_factory.mktemp("home")))


@pytest.fixture(autouse=True)
def block_external_network(monkeypatch):
    monkeypatch.setattr(socket.socket, "connect", _guarded_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", _guarded_connect_ex)


# ── FauxProvider를 ProviderRegistry에 등록 ─────────────────────────────────────

@pytest.fixture(autouse=True)
def register_faux_provider():
    """모든 테스트에 자동 적용 — FauxProvider를 레지스트리에 등록."""
    from ash_industry.model_layer.model_registry import get_default_registry
    from tests.fixtures.faux_provider import FauxProvider

    registry = get_default_registry()
    if "faux" not in registry.list_names():
        registry.register(FauxProvider())
    yield
    # teardown: config 싱글톤 초기화
    from ash_industry.ash_config import reset_settings
    reset_settings()


# ── ModelConfig fixture ────────────────────────────────────────────────────────

@pytest.fixture
def faux_model():
    from ash_industry.model_layer.model_types import ModelConfig
    return ModelConfig(provider="faux", model="faux-model")


@pytest.fixture
def faux_model_with_response():
    """특정 응답을 반환하는 faux model — registry를 교체."""
    def _factory(response: str = "Hello!", tool_calls: list | None = None):
        from ash_industry.model_layer.model_registry import get_default_registry
        from ash_industry.model_layer.model_types import ModelConfig
        from tests.fixtures.faux_provider import FauxProvider

        registry = get_default_registry()
        registry._providers["faux"] = FauxProvider(response=response, tool_calls=tool_calls)
        return ModelConfig(provider="faux", model="faux-model")
    return _factory


# ── SecurityPipeline fixture ───────────────────────────────────────────────────

@pytest.fixture
def permissive_pipeline():
    """인증/권한 검사 없이 모두 통과하는 파이프라인."""
    from ash_industry.core.policy.authenticator import NoAuthAuthenticator
    from ash_industry.core.policy.validator import DefaultInputValidator
    from ash_industry.core.policy.pipeline import SecurityPipeline
    from ash_industry.core.policy.sandbox import PermissiveSandbox
    from ash_industry.core.policy.policy import AllowAllPolicy

    return SecurityPipeline(
        validator=DefaultInputValidator(),
        authenticator=NoAuthAuthenticator(),
        policy=AllowAllPolicy(),
        sandbox=PermissiveSandbox(),
    )


# ── Session + repo fixture ─────────────────────────────────────────────────────

@pytest.fixture
def tmp_session_dir(tmp_path):
    return str(tmp_path / "sessions")


@pytest.fixture
def jsonl_repo(tmp_session_dir):
    from ash_industry.agent_layer.session.jsonl import JsonlSessionRepo
    return JsonlSessionRepo(sessions_root=tmp_session_dir)


@pytest.fixture
def session_memory():
    from ash_industry.memory.stores.in_memory import InMemoryItemStore
    from ash_industry.memory.memory_service import MemoryService
    return MemoryService(InMemoryItemStore())


@pytest.fixture
def tool_registry():
    from ash_industry.core.tools.tools_registry import ToolRegistry
    return ToolRegistry()


@pytest.fixture
def skill_registry():
    from ash_industry.core.skills.skills_registry import SkillRegistry
    return SkillRegistry()


@pytest.fixture
def plugin_runner():
    from ash_industry.core.plugins.runner import PluginRunner
    return PluginRunner()


@pytest.fixture
async def agent_session(
    faux_model,
    permissive_pipeline,
    plugin_runner,
    session_memory,
    tool_registry,
    skill_registry,
    jsonl_repo,
    tmp_session_dir,
):
    """전체 레이어가 연결된 AgentSession (faux provider 사용)."""
    from ash_industry.core.session import AgentSession

    await jsonl_repo.create(session_id="test-session")

    return AgentSession(
        model=faux_model,
        session_id="test-session",
        security_pipeline=permissive_pipeline,
        plugin_runner=plugin_runner,
        memory=session_memory,
        tool_registry=tool_registry,
        skill_registry=skill_registry,
        session_repo=jsonl_repo,
    )
