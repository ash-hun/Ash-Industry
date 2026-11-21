---
sidebar_position: 1
title: 서비스 설정 값
---

# 서비스 설정 값

Ash Industry 가 읽는 설정을 영역별로 정리한다. 바꾸려는 기능의 절(LLM, Inner Thought, 메모리, 음성 등)을 찾아 코드 블록에서 키를 고르면 되고, 줄 끝 주석이 값의 범위와 비웠을 때의 동작이다.

코드를 고치지 않고 모델, 저장소, 음성, 화면을 바꿀 수 있도록 모든 설정은 환경변수로 준다. 이름은 `ASH_` 접두사로 시작하고, 중첩 단계는 `__` 로 구분한다. main 은 `.env` 파일을 읽되, 같은 이름의 환경변수가 있으면 환경변수를 쓴다.

환경변수 대신 `~/.ash/settings.yaml`(경로는 `ASH_SETTINGS_FILE` 로 바꾼다)에 같은 키를 중첩 YAML 로 적어도 된다. 이 파일이 환경변수와 `.env` 보다 앞서고, SET 화면에서 고친 값도 여기에 쌓인다. 브랜드, 말투, 음성 문구처럼 저장소에 올리지 않을 개인 설정은 이 파일에 둔다.

```yaml
# ~/.ash/settings.yaml
brand:
  name: "M.A.X."
  persona: |
    너는 짧고 정확하게 말하는 운영 담당자다.
voice:
  wake_model_file: max.onnx
  whisper_hotwords: "Max"
  english_style: "calm, concise British English"
```

:::note

설정의 정본은 레포의 `.env.example` 과 `src/ash_industry/ash_config.py` 다.

:::

## LLM

```bash
ASH_LLM__PROVIDER=anthropic        # anthropic | openai | gemini | ollama | vllm
ASH_LLM__MODEL=claude-sonnet-4-5
ASH_LLM__API_KEY=
ASH_LLM__BASE_URL=                 # Ollama, vLLM, OpenAI 호환 주소. OpenAI 는 비우면 기본 주소
ASH_LLM__MAX_TOKENS=4096
ASH_LLM__TEMPERATURE=0.7
ASH_LLM__TIMEOUT=120               # 초
```

## Inner Thought 와 Proactive Dialogue

```bash
ASH_THOUGHT__ENABLED=true
ASH_THOUGHT__MODEL=                     # 비우면 메인 모델. 사고 전용 모델을 따로 둘 때
ASH_THOUGHT__PROVIDER=                  # 비우면 메인 provider 상속(api_key, base_url 도 같이)
ASH_THOUGHT__API_KEY=                   # 사고 provider 를 따로 둘 때. 비우면 메인 키
ASH_THOUGHT__BASE_URL=                  # 비우면 메인 base_url
ASH_THOUGHT__REQUEST_TIMING=race        # before | race | after
ASH_THOUGHT__WAIT_SEC=3.0               # race 에서 사고를 기다리는 상한
ASH_THOUGHT__ROUTER_MODEL=              # 지정하면 REQUEST_TIMING 대신 router 가 요청마다 사고 여부를 정한다
ASH_THOUGHT__ROUTER_BASE_URL=http://localhost:11435
ASH_THOUGHT__ROUTER_THRESHOLD=0.2       # P(think) 가 이 이상이면 think
ASH_THOUGHT__ROUTER_TIMEOUT_SEC=1.0     # 넘기면 think 로 둔다
ASH_THOUGHT__HISTORY_TURNS=8            # 사고 프롬프트에 넣는 최근 턴 수
ASH_THOUGHT__HISTORY_CHARS=240          # 턴당 글자 상한
ASH_THOUGHT__PROMPT_PATH=~/.ash/inner_thought.md
ASH_THOUGHT__REFLECTION_PROMPT_PATH=~/.ash/inner_thought_reflection.md
ASH_THOUGHT__LOG_SINKS=["ltm"]          # ltm | stm
ASH_THOUGHT__COMPOSER=default           # default | interpretation_only

ASH_PROACTIVE__ENABLED=true
ASH_PROACTIVE__CONFIDENCE_THRESHOLD=0.85  # decision model 을 쓰면 대신 DECISION_THRESHOLD 를 쓴다
ASH_PROACTIVE__COOLDOWN_SEC=300
ASH_PROACTIVE__IGNORE_AFTER_SEC=600  # 🔔 뒤 답이 없으면 이만큼 지나 약한 무시로 학습
ASH_PROACTIVE__DAEMON_ENABLED=true
ASH_PROACTIVE__DAEMON_TRIGGER=interval  # interval | idle | both
ASH_PROACTIVE__DAEMON_INTERVAL_SEC=120
ASH_PROACTIVE__DAEMON_IDLE_SEC=180
ASH_PROACTIVE__DECISION_MODEL=          # 비우면 사고 모델이 정한다. 예: tev1, nimble (Ollama decision model)
ASH_PROACTIVE__DECISION_BASE_URL=http://localhost:11434   # 컨테이너에서는 http://host.docker.internal:11434
ASH_PROACTIVE__DECISION_THRESHOLD=0.6   # decision model 을 쓸 때의 임계치. 모델의 확률 척도에 맞춘다
```

### 사고 모델 고르기

사고 프레임은 JSON 이다. 사고 모델이 형식을 지키지 못하면 프레임이 버려지고, 먼저 건네는 말은 끝내 뜨지 않는다.

- 메인 모델이 클라우드에 있으면 사고는 더 싼 모델(`claude-haiku-4-5` 등)로 분리한다
- 로컬 Ollama 에서는 `gemma4:e2b-it-qat` 로 검증했다. Ollama 프로바이더는 사고 호출에 JSON 스키마를 `format` 으로 강제한다. 0.8b 급 모델은 스키마를 줘도 형식을 지키지 못했다. qwen3.5 계열은 Ollama 0.40 에서 `format` 자체가 501 을 돌려주므로 사고가 통째로 생략된다
- `~/.ash/inner_thought.md` 로 템플릿을 직접 쓸 때도 `utterance` 키는 있어야 한다. 없으면 daemon 이 항상 침묵한다

### 요청 사고 시점

`ASH_THOUGHT__REQUEST_TIMING` 은 요청마다 도는 사고를 응답과 어떤 순서로 돌릴지 정한다.

| 값 | 동작 | 언제 |
|---|---|---|
| `before` | 사고를 끝내고 응답. 해석이 이번 응답의 시스템 프롬프트에 섞인다 | 사고가 빠를 때 |
| `race` | `WAIT_SEC` 까지만 기다리고 늦으면 응답을 먼저 시작. 늦은 사고는 💭, 사고 기록에만 쓰인다 | 사고와 메인이 다른 곳에서 돌 때(클라우드) |
| `after` | 응답이 끝난 뒤 사고 | 사고와 메인이 같은 GPU 를 나눠 쓸 때(로컬 Ollama) |

로컬 GPU 한 장에서 실측했을 때, `race` 는 두 모델이 GPU 를 나눠 써서 첫 글자가 21초 뒤에 나왔고 `after` 는 12.8초 뒤에 나왔다.

`ASH_THOUGHT__ROUTER_MODEL` 을 지정하면 이 값 대신 [Thought Router](../concepts/conversation/inner-thought.md#thought-router) 가 요청마다 사고할지 정한다. 약속(open loop) 판단은 시점 설정과 상관없이 요청마다 사고와 따로 돈다.

## Focus 모드

```bash
ASH_FOCUS__ENABLED=true
ASH_FOCUS__MODEL=                   # sub-agent 넷의 모델(예: gpt-4o-mini). 비우면 메인 모델
ASH_FOCUS__DIR=~/.ash/focus
ASH_FOCUS__READY_TIMEOUT_SEC=30     # 시작할 때 첫 분석과 단계 계획을 기다리는 상한
```

쓰는 법은 [Focus Mode](../concepts/mode/focus-mode.md) 에 있다.

## 메모리와 세션

```bash
ASH_MEMORY__BACKEND=postgres            # in_memory | postgres
ASH_MEMORY__POSTGRES_DSN=               # 비우면 SESSION__POSTGRES_DSN 을 쓴다
ASH_MEMORY__STM_TURNS=3               # 모델에 넣는 최근 턴 수. 그 밖은 턴마다 쓴 일화에서 회상
ASH_MEMORY__CONSOLIDATE_ON_IDLE=true    # PROACTIVE__DAEMON_IDLE_SEC 넘게 조용한 daemon 틱마다 사실 추출과 절차 정제(트리거 종류 무관)
ASH_MEMORY__EMBEDDING_PROVIDER=         # openai | ollama | vllm. 비우면 키워드 검색만. 약속 중복 판정도 이 설정을 쓴다
ASH_MEMORY__EMBEDDING_MODEL=bge-m3      # 한국어는 bge-m3. 비우면 provider 기본값(ollama 는 nomic-embed-text)
ASH_MEMORY__EMBEDDING_DIMENSIONS=1024   # bge-m3 는 1024. vllm 은 필수
ASH_MEMORY__EMBEDDING_API_KEY=          # 비우면 LLM API 키
ASH_MEMORY__EMBEDDING_BASE_URL=         # 비우면 provider 기본값

ASH_SESSION__PERSISTENCE_BACKEND=jsonl  # jsonl | postgres
ASH_SESSION__SESSIONS_DIR=~/.ash/sessions
ASH_SESSION__POSTGRES_DSN=postgresql://user:pw@host:5432/ash

ASH_OPENLOOP__BACKEND=jsonl             # jsonl | in_memory | postgres
ASH_OPENLOOP__PATH=~/.ash/openloops.jsonl
ASH_OPENLOOP__POSTGRES_DSN=             # BACKEND=postgres 일 때. 비우면 세션, 메모리 DSN 순으로 쓴다
ASH_OPENLOOP__EXPIRE_AFTER_SEC=21600    # 기한 뒤 이만큼 지나면 expired 로 닫음(6시간)
ASH_OPENLOOP__MAX_AGE_SEC=604800        # 기한 없는 약속의 수명(7일). 0 이면 닫지 않음
ASH_USER_MODEL__ENABLED=true
ASH_USER_MODEL__BACKEND=jsonl           # jsonl | in_memory
ASH_USER_MODEL__PATH=~/.ash/user_model.json
ASH_USER_MODEL__BUILD_SOURCE_LIMIT=30   # /usermodel build 가 증류에 쓰는 최근 기억 수
```

## 보안

```bash
ASH_SECURITY__API_KEYS='{"<long-random-key>": {"name": "me", "roles": ["admin"]}}'
ASH_SECURITY__ALLOWED_ROLES=["user","admin"]
ASH_SECURITY__INPUT_MAX_LENGTH=10000
ASH_SECURITY__APPROVALS_PATH=~/.ash/approvals.yaml        # 공용 규칙(사람이 고친다)
ASH_SECURITY__AGENT_APPROVALS_DIR=~/.ash/approvals         # 에이전트별 규칙(<agent_id>.yaml, 항상 허용이 쌓인다)
ASH_SECURITY__REQUIRE_APPROVAL_FOR=["bash","write_file","edit_file"]  # 실행 전 승인을 묻는 도구
ASH_SECURITY__DANGEROUS_COMMANDS=[...]                          # 위험 명령 정규식. bash 의 command 에 걸리면 승인 없이 막는다. [] 이면 끈다
```

`API_KEYS` 를 비우면 Web 인증이 꺼진다. 키를 두면 `/api/*` 와 `/ws` 가 키를 요구하고, HUD 는 처음 거절될 때 접근 키 창을 띄운다([접근 키 넣기](../start/web-hud.md#접근-키-넣기)). `/api/health` 와 정적 화면 파일은 키 없이 열려 있다. 인증을 켜고 끄는 다른 스위치는 없다. `REQUIRE_AUTH` 와 `ALLOWED_ROLES` 는 설정에 있지만 읽는 코드가 없다. 실행 전 안전장치는 `REQUIRE_APPROVAL_FOR` 의 승인과 승인 규칙이다. 키가 곧 사용자 식별자이므로 길고 무작위인 값을 쓴다.

## MCP 서버

`mcp_servers` 는 목록 설정이다. 항목마다 `name`, `transport`(`stdio`, `http`, `streamable-http`), `command`, `url`, `env`, `headers`, `auth_token`, `timeout`(30)을 둔다. 항목 예시는 [Extension](../concepts/extension.md) 에 있다.

```bash
ASH_SECURITY__MCP_POLICY_PATH=~/.ash/mcp_policy.yaml  # MCP 도구별 allow, ask, deny 와 에이전트별 서버
ASH_SECURITY__MCP_AUDIT_PATH=~/.ash/mcp_audit.jsonl   # MCP 호출 판정과 결과 기록
ASH_DOCS_DIR=~/Documents/ash   # compose 전용. 문서 도구가 읽고 쓰는 폴더. ash-mcp 컨테이너의 /data/documents 로 붙는다
```

Docker Compose 의 기본 `ASH_MCP_SERVERS` 에는 Google Workspace 서버(`ash-mcp:8000`)와 문서 도구 서버 `docs`(`ash-mcp:8001`, 시간 제한 180초)가 들어 있다. `ASH_MCP_SERVERS` 를 직접 적으면 이 기본 목록을 통째로 바꾸므로 쓰려는 서버를 모두 적는다. 정책 파일의 형식은 [Tool & Approve System](../concepts/conversation/tools-and-approval.md#mcp-도구-정책), 문서 도구는 [Document Tools](../concepts/conversation/documents.md) 에 있다.

## 절차 학습, 알림, 플러그인

```bash
ASH_PROCEDURES__ENABLED=true
ASH_PROCEDURES__DIR=~/.ash/procedures
ASH_PROCEDURES__MIN_TOOL_CALLS=3

ASH_NOTIFY__SLACK_WEBHOOK_URL=
ASH_NOTIFY__DISCORD_WEBHOOK_URL=
ASH_NOTIFY__AVATAR_BASE_URL=
ASH_NOTIFY__KINDS=["reminder","proactive","spoken"]
ASH_NOTIFY__DISCORD_BOT_TOKEN=           # 셋 다 있으면 음성 채널에 있는 사용자에게 봇이 읽는다. 없으면 webhook 글
ASH_NOTIFY__DISCORD_GUILD_ID=
ASH_NOTIFY__DISCORD_USER_ID=
ASH_NOTIFY__DISCORD_VOICE_KINDS=["reminder","proactive"]
ASH_NOTIFY__DISCORD_TTS_PROVIDER=supertonic
ASH_NOTIFY__WEBPUSH_VAPID_PUBLIC_KEY=    # 모바일 앱 Web Push. 셋 다 있고 세션 저장소가 Postgres 일 때만
ASH_NOTIFY__WEBPUSH_VAPID_PRIVATE_KEY=
ASH_NOTIFY__WEBPUSH_SUBJECT=             # mailto:<주소>

ASH_PLUGIN__TOOLS_DIR=~/.ash/tools
ASH_PLUGIN__SKILLS_DIR=./examples/skills  # .env.example 값. 코드 기본은 ~/.ash/skills
ASH_PLUGIN__PLUGINS_DIR=~/.ash/plugins
ASH_PLUGIN__EXTENSIONS_DIR=~/.ash/extensions  # 에이전트 전용 도구와 슬래시 명령을 담은 확장 패키지

ASH_AGENTS__ENABLED=true                 # 서브 에이전트(멀티 에이전트 패턴)
ASH_AGENTS__AGENTS_DIR=~/.ash/agents
ASH_AGENTS__SUPERVISOR_PROMPT=           # supervisor 패턴의 감독자 지시문. 문자열이나 파일 경로. 비우면 기본 문구
ASH_TEAM__DIR=~/.ash/team             # 팀 에이전트 정의(Docker 는 /app/team). 예시는 examples/team/

ASH_SCHEDULER__ENABLED=true
ASH_SCHEDULER__SCHEDULES_DIR=~/.ash/schedules

ASH_EXTERNAL__ENABLED=true               # 외부 이벤트 소스를 읽어 사고에 넣는다
ASH_EXTERNAL__SOURCES_DIR=~/.ash/external_sources

ASH_WEB_SEARCH__BRAVE_API_KEY=           # 비우면 web_search 가 DuckDuckGo 결과 페이지를 읽는다
```

여기 없는 조정 값(메모리 반감기와 회상 개수, 외부 이벤트 한도 등)은 `src/ash_industry/ash_config.py` 의 기본값을 따른다.

`ASH_PLUGIN__WATCH_FILES`(기본 `true`)는 기동 때 있던 도구, 스킬, 플러그인 디렉터리를 지켜보다 바뀐 디렉터리만 다시 읽는다. 지운 파일의 확장과 기동 뒤에 만든 디렉터리는 재시작해야 반영된다.

## 음성

```bash
ASH_VOICE__STT_PROVIDER=browser      # browser | whisper
ASH_VOICE__WHISPER_MODEL_SIZE=base   # tiny | base | small | medium. 클수록 정확하고 느리다. 운영은 small
ASH_VOICE__TTS_PROVIDER=browser      # browser | supertonic
ASH_VOICE__SUPERTONIC_MODEL=supertonic-3  # supertonic 패키지가 받는 모델 이름
ASH_VOICE__TTS_LANG=ko
ASH_VOICE__STT_LANG=ko-KR            # 브라우저 STT 언어(connected 메시지로 화면에 간다)
ASH_VOICE__ENGLISH_TTS_PROVIDER=piper  # piper | qwen. 비우면 영어 문장도 TTS_PROVIDER 가 읽는다
ASH_VOICE__QWEN_URL=http://host.docker.internal:8770  # qwen 합성 서버. 닿지 않으면 PIPER_MODEL 로 읽는다
ASH_VOICE__SPEAK_ENGLISH=false         # true 면 main 이 소리 내는 한국어 글을 소리로만 영어로 옮겨 위 영어 TTS 로 읽는다
ASH_VOICE__PIPER_MODEL=~/.ash/voices/en-voice.onnx
ASH_VOICE__PIPER_NOISE_SCALE=0.4  # 낮을수록 음정 떨림이 줄고 말투가 단조로워진다
ASH_VOICE__PHRASES_DIR=             # 미리 녹음한 읽기 문구(phrases.json 과 wav). 비우면 끈다. Docker 는 /app/models/tts/phrases
ASH_VOICE__WAKE_MODEL_DIR=          # 웨이크워드 모델 폴더. 비우면 끈다. Docker 는 /app/models/wakeword
ASH_VOICE__WAKE_MODEL_FILE=wake.onnx  # 그 폴더 안의 웨이크워드 모델 파일 이름
ASH_VOICE__WHISPER_HOTWORDS=        # whisper 가 비슷한 소리로 잘못 적는 이름(에이전트 이름, 웨이크워드). 비우면 안 씀
ASH_VOICE__ENGLISH_STYLE=           # 영어로 옮길 때의 말투(번역 프롬프트에 들어간다). 비우면 코드 기본값
ASH_VOICE__ENGLISH_FALLBACK=        # 옮기지 못했을 때 읽을 영어 문장
ASH_VOICE__ENGLISH_UNCLEAR=         # 알아듣지 못했을 때 읽을 영어 문장
ASH_VOICE__WAKE_THRESHOLD=0.5
ASH_VOICE__STT_FALLBACK=whisper     # whisper | 빈 값. 브라우저 STT 가 없거나 실패하면(데스크톱 앱 포함) HUD 가 녹음하고 서버가 whisper 로 받아 적는다
```

영어 TTS 를 따로 두는 법은 [Voice Interface](../concepts/conversation/voice.md#영어-문장은-piper-음성으로) 에 있다. `STT_LANG` 은 브라우저 STT 만 쓴다. whisper 는 이 값을 읽지 않고 한국어로 고정돼 있다. 모델 크기를 바꾸면 처음 인식할 때 모델을 새로 받는다.

## HUD 단축키

HUD 창 안에서 쓰는 단축키다. SET 화면에서 고치면 `~/.ash/settings.yaml` 의 `shortcuts` 에 쌓인다.

```yaml
# ~/.ash/settings.yaml
shortcuts:
  voice_start: Ctrl+Shift+Enter      # 듣기 시작/토글
  voice_stop: Escape                 # 읽기 멈춤
  agent_prev: Ctrl+Shift+ArrowLeft   # 이전 에이전트
  agent_next: Ctrl+Shift+ArrowRight  # 다음 에이전트
```

형식은 `Ctrl`, `Alt`, `Shift`, `Meta` 를 `+` 로 잇고 끝에 키 이름 하나다. 넷 가운데 둘이 같으면 저장을 거절한다. 환경변수로는 `ASH_SHORTCUTS__VOICE_START` 처럼 준다. 데스크톱 앱의 전역 단축키는 이 설정이 아니라 앱 설정(SET 화면 DESKTOP 카드)에 있다. 규칙은 [Web HUD 단축키](../start/web-hud.md#단축키) 에 있다.

## 화면과 브랜드

`ash-industry` 는 플래그 없이 Web HUD 백엔드를 띄운다(`--web` 을 붙여도 같다). 바인딩할 주소와 포트는 `--host`, `--port` 로 정한다. `.env.example` 의 `ASH_UI__MODE`, `ASH_UI__THEME` 와 `ASH_UI__SHOW_THINKING` 은 설정에 있지만 읽는 코드가 없다.

```bash
TZ=Asia/Seoul                           # 스케줄과 /schedule 마감 시각의 기준 (compose 기본값)

ASH_BRAND__NAME=A.S.H.
ASH_BRAND__QUOTE=System Online
ASH_BRAND__PERSONA="..."                 # main 의 말투와 성격. 기본은 침착한 업무 비서(ash_config.py DEFAULT_PERSONA). 비우면 모델 기본 말투
ASH_BRAND__PALETTE__PRIMARY=#e6e8ea
ASH_BRAND__PALETTE__ACCENT=#f0642d
ASH_BRAND__PALETTE__BACKGROUND=#14161a
ASH_BRAND__PALETTE__NEBULA=["#ffb38a","#f0642d","#d9481a"]
```

브랜드 값은 Web HUD 의 워드마크, 명언, 링과 구체 색에 들어간다. 에이전트마다 다르게 두면 어느 에이전트와 말하고 있는지 색으로 알 수 있다.

## 로그

```bash
ASH_LOG_LEVEL=INFO   # DEBUG | INFO | WARNING | ERROR
LOG_FORMAT=console      # console(사람이 읽는 콘솔) | json(한 줄에 객체 하나)
```

두 값은 `src/ash_industry/common/logger.py` 가 프로세스 환경변수에서 직접 읽는다. 설정 모델을 거치지 않으므로 로컬 실행에서 `.env` 에만 적으면 반영되지 않는다. 셸에서 `export` 하거나 Docker 처럼 `env_file` 로 컨테이너 환경에 넣는다. `LOG_FORMAT` 에는 `ASH_` 접두사가 없다. 로그는 stdout 으로 나가고, `password`, `token`, `api_key`, `authorization`, `cookie`, `secret` 같은 키의 값은 `***` 로 가린다. `ASH_DEBUG` 는 설정에 있지만 읽는 코드가 없다.

## 호스트 Ollama 팁

사고와 메인을 호스트의 Ollama 하나로 돌리면, 성찰이 도는 동안 사용자 요청이 줄을 선다. Ollama 를 brew 서비스로 띄웠다면 동시 처리 수를 늘린다.

```bash
launchctl setenv OLLAMA_NUM_PARALLEL 2 && brew services restart ollama
```

:::warning

이 설정은 재부팅하면 사라진다. 재부팅한 뒤에는 위 명령을 다시 실행한다.

:::
