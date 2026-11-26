"""[config] AshSettings: settings.yaml, env, .env 에서 읽는 전체 설정 모델."""

import os
import re
from pathlib import Path
from typing import Annotated, Any, Literal
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict, PydanticBaseSettingsSource, YamlConfigSettingsSource


# 화면(Settings)에서 고친 값이 쌓이는 파일. 테스트와 다른 설치는 ASH_SETTINGS_FILE 로 바꾼다
SETTINGS_FILE_ENV = "ASH_SETTINGS_FILE"
DEFAULT_SETTINGS_FILE = "~/.ash/settings.yaml"
# 개인 프로필 저장소의 설정(main 의 이름, 말투, 음성). 화면에서 고친 값보다 약하고 env 보다 강하다
PROFILE_SETTINGS_FILE_ENV = "ASH_PROFILE_SETTINGS_FILE"

# 정규식이다. "curl | bash" 처럼 쓰면 | 가 "또는" 이 되어 curl 이 든 명령을 전부 막는다
DEFAULT_DANGEROUS_COMMANDS: tuple[str, ...] = (
    r"rm\s+-rf\s+/",
    r"sudo\s+",
    r"curl\s+.*\|\s*(ba)?sh",
    r"wget\s+.*\|\s*(ba)?sh",
    r">\s*/dev/(sda|hda|nvme)",
    r"mkfs\.",
    r"dd\s+if=.*of=/dev/",
    r":\(\)\s*\{\s*:\|:&\s*\};:",
)


class MCPServerConfig(BaseModel):
    """MCP 서버 연결 설정."""

    name: str
    # http 는 SSE(구형 /sse), streamable-http 는 MCP 2025-03 의 /mcp 한 엔드포인트. 새 서버는 대개 후자만 낸다
    transport: Literal["stdio", "http", "streamable-http"] = "stdio"
    command: list[str] = Field(default_factory=list)  # stdio transport용 명령
    url: str | None = None  # http(sse), streamable-http transport용 엔드포인트
    env: dict[str, Any] = Field(default_factory=dict)  # MCP 서버 환경 변수. 값 타입을 좁히면 기존 설정 검증이 깨진다
    timeout: float = 30.0  # 연결/툴 호출 타임아웃(초) — 응답 없는 서버가 startup을 막지 않도록
    headers: dict[str, str] = Field(default_factory=dict)  # http transport용 커스텀 헤더
    auth_token: SecretStr | None = None  # http transport용 Bearer 토큰 (Authorization 헤더로 변환)


class WebSearchConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    brave_api_key: SecretStr | None = None  # 미설정 시 DuckDuckGo fallback


class LLMProviderConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    provider: str = "anthropic"
    model: str = "claude-sonnet-4-5"
    api_key: SecretStr | None = None
    base_url: str | None = None
    temperature: float = 0.7
    max_tokens: int = 4096
    timeout: float = 120.0


class ApiUser(BaseModel):
    """Web HUD 접근 키 하나에 대응하는 사용자. 키 자체가 식별자이자 비밀값이다."""

    name: str
    roles: list[str] = Field(default_factory=lambda: ["user"])


class SecurityConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    require_auth: bool = True
    # Web HUD 접근 키 → 사용자. 비어 있으면 web 인증을 끈다(로컬 단독 사용). TUI 는 항상 NoAuth.
    # 예: ASH_SECURITY__API_KEYS='{"<random-key>": {"name": "jh", "roles": ["admin"]}}'
    api_keys: dict[str, ApiUser] = Field(default_factory=dict)
    allowed_roles: list[str] = Field(default_factory=lambda: ["user", "admin"])
    # 셸 도구의 command 인자를 대소문자 무시 정규식으로 본다. 걸리면 승인 규칙과 무관하게 막고, 빈 목록이면 끈다
    dangerous_commands: list[str] = Field(default_factory=lambda: list(DEFAULT_DANGEROUS_COMMANDS))
    require_approval_for: list[str] = Field(default_factory=lambda: ["bash", "write_file", "edit_file"])
    input_max_length: int = 10_000
    # 공용 승인 규칙. 모든 에이전트가 읽고, 사람이 직접 고친다
    approvals_path: str = "~/.ash/approvals.yaml"
    # 에이전트별 승인 규칙(<agent_id>.yaml). 승인 화면에서 "항상 허용"을 고르면 그 에이전트 파일에 쌓인다
    agent_approvals_dir: str = "~/.ash/approvals"
    # MCP 도구 정책(서버, 도구별 allow, ask, deny, 인자 고정, 시간당 상한)과 호출 기록
    mcp_policy_path: str = "~/.ash/mcp_policy.yaml"
    mcp_audit_path: str = "~/.ash/mcp_audit.jsonl"
    # 에이전트별 auto mode(승인을 묻지 않고 허용). HUD 토글이 쓴다
    auto_approve_path: str = "~/.ash/auto_approve.yaml"


    @field_validator("dangerous_commands")
    @classmethod
    def _compiles(cls, patterns: list[str]) -> list[str]:
        # 틀린 정규식은 첫 셸 호출이 아니라 기동 때 알린다
        for pattern in patterns:
            try:
                re.compile(pattern)
            except re.error as exc:
                raise ValueError(f"dangerous_commands 의 정규식이 틀렸다: {pattern!r} ({exc})") from exc
        return patterns

class MemoryConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    backend: Literal["in_memory", "postgres"] = "postgres"
    postgres_dsn: str | None = None  # None이면 session.postgres_dsn fallback
    stm_turns: int = 3  # 모델에 넣는 최근 턴 수. 그 밖은 턴마다 쓴 EDM 에서 회상한다
    stm_max_age_hours: float = 24.0  # 이보다 오래된 턴은 턴 수 안이어도 창에서 뺀다(마지막 턴은 둔다). 0 이면 안 본다
    fixed_facts: int = 3  # 매 턴 항상 넣는 상위 의미 사실 수(고정 블록)
    recall_limit: int = 3  # 질의로 회상해 넣는 항목 수(회상 블록)
    # 회상이 질문의 대상(사람, 장소, 물건)을 다 덮지 못하면 빠진 대상으로 다시 찾는다. 사고 모델로 대상을 뽑는다
    coverage_recall: bool = False
    # 세기, 순서, 기간을 묻는 질문이면 대상별 일화를 시간순으로 붙인다. coverage_recall 이 켜져 있어야 돈다
    timeline_recall: bool = False
    importance_threshold: float = 0.5  # 의미 추출 결과 중 이 값 미만은 버린다
    recency_half_life_hours: float = 168.0  # 검색 점수의 recency 반감기(일주일)
    importance_half_life_days: float = 90.0  # 되뇌기 없는 항목의 importance 반감기. 0 이면 감쇠 없음
    interference_threshold: float = 0.6  # 주제가 다른데 이보다 비슷한 의미 항목 쌍은 간섭 후보로 표시
    consolidate_on_idle: bool = True  # proactive.daemon_idle_sec 넘게 조용한 daemon 틱에 사실 추출과 절차 정제
    # 의미 유사도 검색. provider 를 비우면 키워드 검색만 한다. Postgres 는 pgvector 확장이 필요하다
    embedding_provider: str = ""  # "" | openai | ollama | vllm
    embedding_model: str = ""  # 비우면 provider 기본값 (openai: text-embedding-3-small, ollama: nomic-embed-text)
    embedding_dimensions: int = 0  # 비우면 provider 기본값. vllm 은 필수
    embedding_api_key: SecretStr | None = None  # 비우면 llm.api_key
    embedding_base_url: str | None = None  # 비우면 provider 기본값
    min_similarity: float = 0.3  # 이 코사인 미만은 의미 검색 후보에서 제외


class SessionConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    persistence_backend: Literal["jsonl", "postgres"] = "jsonl"
    sessions_dir: str = "~/.ash/sessions"
    postgres_dsn: str | None = None


class UIConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    theme: str = "dark"
    show_thinking: bool = True


HexColor = Annotated[str, Field(pattern=r"^#[0-9a-fA-F]{6}$")]


class BrandPalette(BaseModel):
    """에이전트 색감. 나머지 톤(밝은/어두운 변형, 반투명 선)은 UI가 여기서 유도한다. 기본값은 Ash 로고 색."""

    primary: HexColor = "#e6e8ea"  # 선·링·텍스트 강조의 주색
    accent: HexColor = "#f0642d"  # 경고·인디케이터 보조색
    background: HexColor = "#14161a"  # 화면 바탕
    nebula: list[HexColor] = Field(  # 리액터 코어 성운 입자 색 (안쪽 → 바깥)
        default_factory=lambda: ["#ffb38a", "#f0642d", "#d9481a"]
    )


# 기본 에이전트(main)의 말투. ASH_BRAND__PERSONA 나 settings.yaml 의 brand.persona 로 바꾼다. 비우면 모델 기본 말투
DEFAULT_PERSONA = (
    "너는 침착하고 정확한 업무 비서처럼 말한다.\n"
    "- 지시받은 것에 필요한 답만 짧게 한다. 결론과 숫자를 먼저 말하고, "
    "묻지 않은 배경 설명, 일반론, 대안, 부연은 붙이지 않는다.\n"
    "- 사람이 옆에서 말하듯 구어체로 말한다. 번호 목록, 불릿, 표, 제목 같은 문서 서식을 쓰지 않는다.\n"
    "- 위험하거나 무리한 요청에는 공손하지만 분명하게 우려를 말한다.\n"
    "- 모르는 것은 추측하지 않고 확인하겠다고 말한다."
)


class BrandConfig(BaseModel):
    """에이전트 정체성: 워드마크, 명언, 색감, 말투. main 은 설정에서, 팀 에이전트는 팀 정의 파일에서 채운다."""

    model_config = ConfigDict(extra="ignore")

    name: str = "A.S.H."
    quote: str = "System Online"
    palette: BrandPalette = Field(default_factory=BrandPalette)
    # 말투와 성격. 대화의 시스템 프롬프트 앞과 사고 모델(먼저 건네는 말, filler)에 같이 들어간다
    persona: str = DEFAULT_PERSONA


class PluginConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    plugins_dir: str = "~/.ash/plugins"
    skills_dir: str = "~/.ash/skills"
    tools_dir: str = "~/.ash/tools"
    # 에이전트 전용 도구와 슬래시 명령을 담은 패키지들(app/extension_loader.py)
    extensions_dir: str = "~/.ash/extensions"
    watch_files: bool = True


class SchedulerConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    enabled: bool = True
    schedules_dir: str = "~/.ash/schedules"
    # 열린 화면이 없을 때 쌓는 알림 보류 큐. postgres 면 재시작해도 이어진다
    notice_backend: Literal["in_memory", "postgres"] = "in_memory"
    postgres_dsn: str | None = None  # None이면 session/memory DSN fallback


class WorkflowConfig(BaseModel):
    """Workflow 화면의 위임 간선과 작업 실행 기록 저장. postgres 면 재시작해도 그래프와 runs 가 이어진다."""

    model_config = ConfigDict(extra="ignore")

    backend: Literal["in_memory", "postgres"] = "in_memory"
    postgres_dsn: str | None = None  # None이면 session/memory DSN fallback
    layout_path: str = "~/.ash/workflow_layout.json"  # 그래프에서 옮긴 노드 자리. 설치 하나에 하나


class AgentConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    enabled: bool = True
    agents_dir: str = "~/.ash/agents"
    # supervisor 패턴의 감독자 system_prompt. 비우면 기본 문구. 파일 경로면 그 내용을 읽는다
    supervisor_prompt: str = ""


class TeamConfig(BaseModel):
    """최상위 에이전트(main 과 같은 층) 정의 디렉터리. 파일 하나가 에이전트 하나이고 파일 이름이 id 다.

    서브 에이전트(agents_dir)와 다르다. 여기 에이전트는 자기 세션, 기억, 약속, 승인 규칙을 가진다.
    """

    model_config = ConfigDict(extra="ignore")

    dir: str = "~/.ash/team"


class ThoughtConfig(BaseModel):
    """Inner Thought Engine 설정 (Tier 0). 기본 on — ASH_THOUGHT__ENABLED=false로 끈다."""

    model_config = ConfigDict(extra="ignore")

    enabled: bool = True
    model: str = ""  # 비우면 메인 LLM 모델, 지정 시 별도 모델
    # 사고 모델을 메인과 완전 분리 (예: 메인=anthropic, 사고=ollama 로컬).
    # 비우면 메인 LLM의 provider/key/base_url을 그대로 상속.
    provider: str = ""
    api_key: SecretStr | None = None
    base_url: str = ""
    prompt_path: str = "~/.ash/inner_thought.md"
    reflection_prompt_path: str = "~/.ash/inner_thought_reflection.md"  # daemon 성찰용
    confidence_threshold: float = 0.6  # Tier 1 게이팅용 (Tier 0은 기록만)
    proactive_cooldown_sec: int = 300  # Tier 1 발화 쿨다운 (예약)
    skip_if_shorter_than: int = 0  # 이보다 짧은 입력은 사고 생략(지연/비용 완화)
    recall_limit: int = 5  # 사고 시 회상할 기억 개수
    # 요청 사고 시점. before: 사고 뒤 응답(해석이 이번 응답에 섞임). race: wait_sec 까지만 기다림.
    # after: 응답 뒤 사고. 사고와 메인이 같은 GPU 면 after 가 가장 빠르다. race, after 의 늦은 사고는 기록만 남긴다
    request_timing: Literal["before", "race", "after"] = "race"
    wait_sec: float = 3.0  # race 에서 기다리는 상한
    # router decision model(scripts/router_server.py). 지정하면 request_timing 대신 router 가 턴마다 정한다:
    # direct 면 사고 없이 답하고, think 면 사고를 응답과 함께 돌려 그 결과를 다음 턴에 넣는다
    router_model: str = ""
    router_base_url: str = "http://localhost:11435"
    router_threshold: float = 0.2  # 맥락 없는 판정과 두 턴 맥락 판정 중 큰 값이 이 이상이면 think
    router_timeout_sec: float = 1.0  # 넘기면 think 로 둔다
    history_turns: int = 8  # 사고 프롬프트에 넣는 최근 대화 턴 수
    history_chars: int = 240  # 턴당 글자 수 상한
    log_sinks: list[str] = Field(default_factory=lambda: ["ltm"])  # ltm | stm (복수 가능)
    composer: str = "default"  # default | interpretation_only — 메인 프롬프트 조립 전략


class OpenLoopConfig(BaseModel):
    """Open-loop 추적 영속화 설정 (Tier 2)."""

    model_config = ConfigDict(extra="ignore")

    backend: Literal["jsonl", "in_memory", "postgres"] = "jsonl"
    path: str = "~/.ash/openloops.jsonl"  # jsonl 백엔드 경로
    postgres_dsn: str | None = None  # None이면 session/memory DSN fallback
    expire_after_sec: int = 21_600  # 기한이 이만큼 지나면 expired 로 닫는다(6시간)
    max_age_sec: int = 604_800  # 기한 없는 약속의 수명(7일). 0 이면 기한 없는 약속은 닫지 않는다


class UserModelConfig(BaseModel):
    """User Model 설정 (Tier 3 D1). ThoughtConfig.enabled가 선행 조건."""

    model_config = ConfigDict(extra="ignore")

    enabled: bool = True
    backend: Literal["jsonl", "in_memory"] = "jsonl"
    path: str = "~/.ash/user_model.json"
    build_source_limit: int = 30  # /usermodel build 시 증류에 쓸 최근 기억 개수


class ProactiveConfig(BaseModel):
    """Proactive 설정 (Tier 1). 기본 on. ThoughtConfig.enabled가 선행 조건."""

    model_config = ConfigDict(extra="ignore")

    enabled: bool = True  # Dual-Channel(요청 시 filler+백그라운드) 마스터 스위치
    # daemon 발화 게이팅 임계치. 성찰 지시문은 확신도를 0.9 이상(분명), 0.6~0.9(이미 알 수도), 0.6 미만(애매)으로
    # 매기게 한다. 개발용 사례에서 gpt-4o-mini, gemma4:e4b 모두 0.85 에서 오경보 0 이었다(블라인드 시험에서는 0.2).
    # 사용자에 맞추는 것은 피드백 학습이 한다. decision model 을 쓰면 decision_threshold 를 쓴다
    confidence_threshold: float = 0.85
    cooldown_sec: int = 300  # 세션별 proactive 발화 쿨다운
    # 🔔 뒤 답이 없으면 다시 말하지 않는다. 이만큼 답이 없으면 그 발화를 한 번 약한 무시로 학습
    ignore_after_sec: int = 600
    # 답을 끝내 못 받은 🔔 의 대기를 이만큼 지나면 푼다. 풀지 않으면 그 세션은 메일, 일정 알림을 영영 못 받는다
    awaiting_expire_sec: int = 1800
    daemon_enabled: bool = True  # B3 백그라운드 성찰 루프 (기본 on, false로 끔)
    daemon_interval_sec: int = 120  # 성찰 주기(초) — interval 트리거용. 로컬과 배포 모두 이 값
    # 성찰 트리거: interval(주기) | idle(조용해지면) | both(둘 중 먼저)
    daemon_trigger: Literal["interval", "idle", "both"] = "interval"
    daemon_idle_sec: int = 180  # idle 트리거 — 이만큼 조용하면 1회 성찰
    # 성찰의 "먼저 말할까" 를 decision model(System One API, 예: Ollama 의 tev1, nimble)의 확률로 정한다.
    # 비우면 사고 모델의 결정과 확신도를 그대로 쓴다
    decision_model: str = ""
    decision_base_url: str = "http://localhost:11434"
    # decision model 을 쓸 때의 임계치. 확률 척도가 사고 모델의 확신도와 달라 따로 둔다
    # (tev1 은 0.6 에서 개발용 오경보 0, 블라인드 시험 0.3)
    decision_threshold: float = 0.6
    # Dual-Channel: 사람이 기다리는 대화의 턴이 이만큼 지나도 안 끝나면 작은 모델(사고 모델)이 쓴 선응답으로 턴을
    # 닫고 코어 모델은 뒤에서 이어 돈다. 0 이면 끈다. enabled 와 상관없이 모든 에이전트에 쓴다
    detach_after_sec: float = Field(default=7.5, ge=0.0)
    # 선응답을 떼어 낼 시각보다 이만큼 먼저 쓰기 시작한다. 제때 못 쓰면 정해 둔 문장으로 낸다
    # gpt-4o-mini 가 선응답 한두 문장에 2.6초(실측)라 여유를 둔다
    ack_lead_sec: float = Field(default=3.5, ge=0.0)

    def effective_threshold(self) -> float:
        """정책과 피드백 학습이 출발할 임계치. decision model 을 쓰면 그 모델의 임계치다."""
        return self.decision_threshold if self.decision_model else self.confidence_threshold


class ExternalTriggerConfig(BaseModel):
    """외부 트리거 설정 (Proactive Phase 3). 소스 YAML이 없으면 전 구간 no-op."""

    model_config = ConfigDict(extra="ignore")

    enabled: bool = True
    sources_dir: str = "~/.ash/external_sources"
    seen_backend: Literal["jsonl", "in_memory"] = "jsonl"
    seen_path: str = "~/.ash/external_seen.jsonl"
    seen_ttl_sec: int = 604_800  # 7일 — dedup 키 보관 기간
    seen_max_keys: int = 10_000  # dedup 스토어 상한(무한 증식 방지)
    max_events_per_tick: int = 20  # 한 번의 성찰에 실을 이벤트 상한
    inbox_max_events: int = 200  # inbox 상한 — 초과분은 드롭 건수를 로그로 노출
    detail_max_chars: int = 500  # 프라이버시·토큰 상한(원문 절단)
    store_detail_in_log: bool = False  # 사고 로그(LTM)에 원문 detail 저장 여부


class ProcedureConfig(BaseModel):
    """절차 학습. 도구를 여러 번 써서 성공한 작업을 세션 종료 때 절차 초안으로 남기고, 승인하면 도구가 된다."""

    model_config = ConfigDict(extra="ignore")

    enabled: bool = True
    dir: str = "~/.ash/procedures"
    min_tool_calls: int = 3  # 이보다 적게 도구를 쓴 작업은 절차로 볼 가치가 없다
    # 유휴 통합 때 실패한 턴을 반성해 절차 개정이나 작업 패턴 초안을 만든다. 끄면 LLM 반성 호출이 없다
    reflect: bool = True


class NotifyConfig(BaseModel):
    """외부 알림 채널. 열린 UI 가 없어도 스케줄 결과와 proactive 발화가 닿는 곳."""

    model_config = ConfigDict(extra="ignore")

    slack_webhook_url: SecretStr | None = None  # 비우면 그 채널로 보내지 않는다
    discord_webhook_url: SecretStr | None = None  # https://discord.com/api/webhooks/{id}/{token}
    # 에이전트 아바타 폴더 주소. <주소>/<에이전트 id>.png 를 디스코드가 받아 간다. 비우면 webhook 기본 그림
    avatar_base_url: str = ""
    # reminder(스케줄 결과) | proactive(먼저 건넨 말) | spoken(Web HUD 가 소리 내어 읽은 말)
    kinds: list[str] = Field(default_factory=lambda: ["reminder", "proactive", "spoken"])
    # 디스코드 봇. 셋 다 있으면 discord_user_id 가 들어가 있는 음성 채널에서 알림을 읽고, 없으면 webhook 글로 보낸다
    discord_bot_token: SecretStr | None = None
    discord_guild_id: int | None = None
    discord_user_id: int | None = None
    # 음성으로 읽는 종류. spoken 은 화면이 이미 소리 내어 읽은 말이라 글로만 보낸다
    discord_voice_kinds: list[str] = Field(default_factory=lambda: ["reminder", "proactive"])
    # 앱(iOS 홈 화면 웹앱) Web Push. 키 둘과 subject 가 다 있고 세션 저장소가 Postgres 일 때만 켠다.
    # 키는 `npx web-push generate-vapid-keys` 로 한 번 만든다. 바꾸면 기존 구독이 전부 무효가 된다
    webpush_vapid_public_key: str = ""
    webpush_vapid_private_key: SecretStr | None = None
    webpush_subject: str = ""  # mailto:<주소>. Apple 푸시 서비스가 요구한다
    # 음성 채널에서 읽을 한국어 TTS. 화면의 tts_provider(기본 browser)와 따로 둔다.
    # 영어 문장은 voice 의 english_tts 설정을 따른다
    discord_tts_provider: str = "supertonic"
    # 보낸 알림 키(채널, 내용, 시각 버킷의 해시). 같은 키는 다시 보내지 않고, 실패는 retries 번 더 보낸다
    sent_path: str = "~/.ash/notify_sent.jsonl"
    retries: int = Field(default=2, ge=0, le=5)


class FocusConfig(BaseModel):
    """Focus 모드: 한 작업에 sub-agent 넷(조사, 기록, 분석, 진행)을 붙인다. Web HUD 의 /focus 로 켠다."""

    model_config = ConfigDict(extra="ignore")

    enabled: bool = True
    model: str = ""                  # sub-agent 넷의 모델. 비우면 메인 모델
    dir: str = "~/.ash/focus"     # 작업마다 기록(log.md), 조사(references.md), 분석, 상태를 남긴다
    ready_timeout_sec: float = 30.0  # 시작할 때 첫 분석과 단계 계획을 기다리는 상한


# HUD 안 단축키 형식. 수정키(Ctrl, Alt, Shift, Meta)를 + 로 잇고 끝에 KeyboardEvent.key 이름 하나.
# 화면(static/app/shortcut-combo.js)의 COMBO 와 같은 식이다. 바꾸면 둘을 같이 바꾼다
SHORTCUT_PATTERN = (
    r"^(?:(?:Ctrl|Alt|Shift|Meta)\+){0,4}"
    r"(?:[A-Za-z0-9]|F[1-9]|F1[0-2]|Enter|Escape|Space|Tab|Backspace|Delete|Home|End|PageUp|PageDown"
    r"|ArrowUp|ArrowDown|ArrowLeft|ArrowRight)$"
)
SHORTCUT_MODIFIERS = ("Ctrl", "Alt", "Shift", "Meta")


def canonical_shortcut(combo: str) -> str:
    """수정키 순서와 글자 대소문자를 맞춘 꼴. Shift+Ctrl+a 와 Ctrl+Shift+A 를 같은 키로 본다."""
    *mods, key = combo.split("+")
    ordered = [m for m in SHORTCUT_MODIFIERS if m in mods]
    return "+".join([*ordered, key.upper() if len(key) == 1 else key])


class ShortcutsConfig(BaseModel):
    """Web HUD 창에 포커스가 있을 때만 듣는 단축키. 데스크톱 전역 단축키와는 따로다."""

    model_config = ConfigDict(extra="ignore")

    voice_start: str = Field(default="Ctrl+Shift+Enter", pattern=SHORTCUT_PATTERN)
    voice_stop: str = Field(default="Escape", pattern=SHORTCUT_PATTERN)
    agent_prev: str = Field(default="Ctrl+Shift+ArrowLeft", pattern=SHORTCUT_PATTERN)
    agent_next: str = Field(default="Ctrl+Shift+ArrowRight", pattern=SHORTCUT_PATTERN)

    @model_validator(mode="after")
    def _distinct(self) -> "ShortcutsConfig":
        # 같은 키에 동작이 둘이면 화면은 앞의 것만 하므로 저장 단계에서 막는다
        seen: dict[str, str] = {}
        for name in type(self).model_fields:
            combo = canonical_shortcut(getattr(self, name))
            if combo in seen:
                raise ValueError(f"단축키가 겹칩니다: {seen[combo]} 와 {name} 이 모두 {combo}")
            seen[combo] = name
        return self


class VoiceConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    stt_provider: str = "browser"    # browser | whisper
    # 브라우저 인식(Web Speech API)이 없거나 실패할 때 화면이 녹음해 보낼 서버 STT. 비우면 폴백 없음.
    # 모델은 처음 받아 적을 때 불러온다. faster-whisper(voice extra)가 없으면 화면에 알리지 않는다
    stt_fallback: Literal["", "whisper"] = "whisper"
    tts_provider: str = "browser"    # browser | supertonic
    whisper_model_size: str = "base"
    # whisper 가 비슷한 소리로 잘못 적는 이름(에이전트 이름, 웨이크워드). 비우면 쓰지 않는다
    whisper_hotwords: str = ""
    supertonic_model: str = "supertonic-3"  # supertonic 패키지가 받는 모델 이름(HuggingFace 경로가 아니다)
    tts_lang: str = "ko"
    english_tts_provider: str = ""   # 비우면 영어 문장도 tts_provider 가 읽는다. piper | qwen
    # main 이 소리 내는 한국어 글을 소리로만 영어로 옮겨 english_tts 로 읽는다. 화면 글은 한국어
    speak_english: bool = False
    # 영어로 옮길 때의 말투(번역 프롬프트에 들어간다)와 고정 문장. 비우면 코드의 기본값
    english_style: str = ""
    english_fallback: str = ""
    english_unclear: str = ""
    piper_model: str = "~/.ash/voices/en-voice.onnx"  # 같은 자리에 .onnx.json 이 있어야 한다
    piper_noise_scale: float = 0.4   # 낮을수록 음정 떨림이 줄고 말투가 단조로워진다. Piper 기본은 0.667
    # qwen: Mac 호스트에서 도는 합성 서버(services/qwen_tts). 닿지 않으면 위 piper_model 로 읽는다
    qwen_url: str = "http://host.docker.internal:8770"
    # 미리 녹음한 읽기 문구(phrases.json 과 wav). 비우면 문구를 재생하지 않는다
    phrases_dir: str = ""
    # 웨이크워드 모델 디렉터리(wake_model_file 과 openWakeWord 특징 모델 둘). 비우면 끈다
    wake_model_dir: str = ""
    wake_model_file: str = "wake.onnx"
    wake_threshold: float = 0.5
    # 녹음 하나가 이보다 길거나(초) 받아 적은 글이 이보다 길면(글자) 에이전트에게 한 말이 아닌 주변 대화로 보고 버린다.
    # 회의 중 잘못 깨어나 남의 말을 요청으로 받아 답하던 것을 막는다(11-17 실측: 30초 녹음, 120자 넘는 글)
    command_max_sec: float = 12.0
    command_max_chars: int = 120
    stt_lang: str = "ko-KR"

    def stt_options(self) -> dict[str, object]:
        """stt_provider 팩토리에 넘길 생성 옵션."""
        return self._whisper_options() if self.stt_provider == "whisper" else {}

    def stt_fallback_options(self) -> dict[str, object]:
        """stt_fallback 팩토리에 넘길 생성 옵션."""
        return self._whisper_options() if self.stt_fallback == "whisper" else {}

    def _whisper_options(self) -> dict[str, object]:
        return {"model_size": self.whisper_model_size, "hotwords": self.whisper_hotwords}

    def tts_options(self, provider: str = "") -> dict[str, object]:
        """provider(비우면 tts_provider) 팩토리에 넘길 생성 옵션."""
        return {"model_name": self.supertonic_model} if (provider or self.tts_provider) == "supertonic" else {}

    def english_tts_options(self) -> dict[str, object]:
        """english_tts_provider 팩토리에 넘길 생성 옵션."""
        if self.english_tts_provider == "qwen":
            return {"url": self.qwen_url, "piper_model": self.piper_model, "noise_scale": self.piper_noise_scale}
        if self.english_tts_provider != "piper":
            return {}
        return {"model_path": self.piper_model, "noise_scale": self.piper_noise_scale}


class CreativeConfig(BaseModel):
    """크리에이티브 워크스페이스. compose 가 ASH_CREATIVE_DIR 를 여기 마운트하고 미디어 워커가 같은 폴더를 쓴다."""

    model_config = ConfigDict(extra="ignore")

    dir: str = "/data/creative"


class DocsConfig(BaseModel):
    """행정문서 폴더. compose 가 ASH_DOCS_DIR 를 여기 읽기 전용으로 마운트하고 docs MCP 서버가 같은 폴더를 쓴다."""

    model_config = ConfigDict(extra="ignore")

    dir: str = "/data/documents"
    # 채팅 첨부(<dir>/uploads, compose 는 호스트 임시 폴더를 붙인다)를 마지막으로 올린 뒤 이만큼 지나면 지운다
    upload_ttl_hours: float = 24.0


class AshSettings(BaseSettings):
    """
    최상위 설정 — .env 또는 환경변수에서 자동 로딩.
    중첩 오버라이드: ASH__LLM__API_KEY=...
    """

    model_config = SettingsConfigDict(
        env_prefix="ASH_",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    llm: LLMProviderConfig = Field(default_factory=LLMProviderConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    session: SessionConfig = Field(default_factory=SessionConfig)
    ui: UIConfig = Field(default_factory=UIConfig)
    brand: BrandConfig = Field(default_factory=BrandConfig)
    plugin: PluginConfig = Field(default_factory=PluginConfig)
    scheduler: SchedulerConfig = Field(default_factory=SchedulerConfig)
    workflow: WorkflowConfig = Field(default_factory=WorkflowConfig)
    agents: AgentConfig = Field(default_factory=AgentConfig)
    team: TeamConfig = Field(default_factory=TeamConfig)
    voice: VoiceConfig = Field(default_factory=VoiceConfig)
    focus: FocusConfig = Field(default_factory=FocusConfig)
    shortcuts: ShortcutsConfig = Field(default_factory=ShortcutsConfig)
    thought: ThoughtConfig = Field(default_factory=ThoughtConfig)
    proactive: ProactiveConfig = Field(default_factory=ProactiveConfig)
    openloop: OpenLoopConfig = Field(default_factory=OpenLoopConfig)
    user_model: UserModelConfig = Field(default_factory=UserModelConfig)
    external: ExternalTriggerConfig = Field(default_factory=ExternalTriggerConfig)
    procedures: ProcedureConfig = Field(default_factory=ProcedureConfig)
    notify: NotifyConfig = Field(default_factory=NotifyConfig)
    creative: CreativeConfig = Field(default_factory=CreativeConfig)
    docs: DocsConfig = Field(default_factory=DocsConfig)
    web_search: WebSearchConfig = Field(default_factory=WebSearchConfig)
    mcp_servers: list[MCPServerConfig] = Field(default_factory=list)
    debug: bool = False
    log_level: str = "INFO"

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # compose 는 .env 를 컨테이너 환경변수로 넣는다. 화면에서 고친 값이 이기려면 yaml 이 env 보다 앞이어야 한다
        yaml_source = YamlConfigSettingsSource(settings_cls, yaml_file=settings_file_path())
        sources: list[PydanticBaseSettingsSource] = [init_settings, yaml_source]
        profile = os.environ.get(PROFILE_SETTINGS_FILE_ENV)
        if profile:
            sources.append(YamlConfigSettingsSource(settings_cls, yaml_file=Path(profile).expanduser()))
        return (*sources, env_settings, dotenv_settings, file_secret_settings)


def settings_file_path() -> Path:
    """화면에서 고친 설정을 읽고 쓰는 yaml 경로."""
    return Path(os.environ.get(SETTINGS_FILE_ENV) or DEFAULT_SETTINGS_FILE).expanduser()


_settings: AshSettings | None = None


def get_settings() -> AshSettings:
    global _settings
    if _settings is None:
        _settings = AshSettings()
    return _settings


def reset_settings() -> None:
    """테스트에서 설정을 초기화할 때 사용."""
    global _settings
    _settings = None
