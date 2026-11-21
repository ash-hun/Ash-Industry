# Ash Industry 기능 정의서

| 항목 | 값 |
|---|---|
| Last Updated | 2026-11-21 |

> `Last Updated` 는 문서 내용이 실제로 바뀐 날만 적는다. 시각은 적지 않는다.

---

## 서비스 개요

여러 AI 에이전트를 한 곳에서 운영하는 플랫폼이다. 브라우저(Web HUD)와 그 HUD 를 창 하나로 띄우는 데스크톱 앱(Electron)에서 같은 백엔드로 대화하고, 에이전트는 도구를 쓰고, 장기 기억과 약속(open loop)을 쌓고, 요청이 없어도 먼저 말을 건네고, 스케줄과 목표를 대화 밖에서 돌린다. 최상위 에이전트(main 과 정의 파일로 더하는 팀 에이전트)가 서로 일을 맡기고 묻는다.

에이전트의 정체성과 전용 도구는 플랫폼 밖에 둔다. main 의 이름, 말투, 음성은 프로필 설정(`ASH_PROFILE_SETTINGS_FILE`), 팀 에이전트는 정의 파일(`ASH_TEAM__DIR`), 전용 도구와 명령은 확장(`ASH_PLUGIN__EXTENSIONS_DIR`)이 맡는다. 저장소에는 예시(`examples/`)만 있다.

범위 밖: 여러 사용자의 계정 관리, 모바일 앱 빌드 결과(`/m/`)의 소스는 이 저장소의 `src/` 에 없다.

---

## 기능 목록

기능 ID 알파벳순.

| 기능 ID | 기능 | 진입점 | 상태 |
|---|---|---|---|
| `agent_conversation` | 최상위 에이전트끼리 일을 맡기고 되묻는 대화. 담당 에이전트가 있는 일은 먼저 위임한다 | `ask_agent` 도구, 모든 에이전트의 시스템 프롬프트 끝 팀 규칙 | 구현됨 |
| `agent_loop` | 한 턴의 LLM 호출과 도구 실행 반복 | ws `user_message` | 구현됨 |
| `agent_registry` | 정의 파일로 최상위 에이전트를 더하고 화면 브랜드를 바꾼다 | `GET /api/agents`, `GET /brand.js`, `ash-industry --agent <id>` | 구현됨 |
| `approval` | 위험한 도구 실행 전 사용자 승인과 "항상 허용" 규칙 | ws `approval_request` / `approval_response` | 구현됨 |
| `cli` | `ash-industry` 명령으로 Web HUD 백엔드를 띄우고 시작 세션을 고른다 | `ash-industry [--session <id>] [--agent <id>] [--host] [--port]`, `ash-industry --list-sessions` | 구현됨 |
| `desktop` | HUD 를 창 하나로 띄우고 트레이 상주, 전역 단축키, OS 알림을 맡는 Electron 셸. GitHub Release 의 dmg 로 받는다 | `cd desktop && npm start`, Release 의 `AshIndustry-<버전>-<arch>.dmg`, 트레이 메뉴, 전역 단축키 | 구현됨 |
| `docparse` | 행정문서(DOCX, XLSX)를 id 가 붙은 구조로 읽고, 서식을 유지한 채 지정한 곳만 고치고, 렌더하는 독립 파서 패키지 | `packages/docparse`(`docparse.inspect`, `apply`, `render`) | 구현 중 |
| `docs_mcp` | 행정문서 MCP 서버. 문서 폴더의 문서를 읽고 편집 계획을 보인 뒤 승인된 계획만 새 파일로 저장한다. 어느 에이전트가 쓸지는 MCP 정책이 정한다 | docs MCP 서버의 `list_documents`, `inspect_document`, `plan_edit`, `apply_edit`, `render_document` | 구현 중 |
| `extension` | 확장 디렉터리의 파이썬 패키지가 에이전트 전용 도구와 슬래시 명령을 등록한다. 개인 도구를 플랫폼 밖에 둔다 | `~/.ash/extensions/<이름>/__init__.py` 의 `register(ctx)`, `ASH_PLUGIN__EXTENSIONS_DIR` | 구현됨 |
| `external` | 캘린더, 메일 같은 외부 변화를 주기적으로 읽어 성찰에 먹인다 | `~/.ash/external_sources/*.yaml` | 구현됨 |
| `focus` | 한 작업을 네 sub-agent 의 도움으로 끝까지 수행하는 모드 | `/focus <작업>` (Web HUD) | 구현됨 |
| `goal` | 맡긴 목표를 대화 밖에서 한 단계씩 진행하고 알릴 것만 알린다 | `/goal`, `goal` 도구 | 구현됨 |
| `ion` | 백엔드 밖의 컨테이너 Ion 이 플랫폼을 지켜보다 사고를 알리고(푸시, HUD ION 띠, 데스크톱 OS 알림) 답에 따라 재기동한다. 모바일 푸시의 버튼 답은 앱 저장소 쪽 | `GET /api/platform/metrics`, `GET /ion/status`, `POST /ion/incidents/{id}/respond`, `GET /ion/events` | 구현 중 |
| `journal` | 사고 로그를 성찰해 저널로 남긴다 | `/journal` | 구현됨 |
| `mcp` | MCP 서버의 툴을 에이전트 도구로 등록 | 설정 `mcp_servers` | 구현됨 |
| `mcp_policy` | MCP 도구마다 allow, ask, deny, 인자 고정, 시간당 상한, 에이전트 제한과 호출 기록 | `~/.ash/mcp_policy.yaml`, `/api/mcp/policy`, SET 화면 MCP 표 | 구현됨 |
| `memory` | 범위를 아는 장기 기억과 작업 기억의 저장, 회상, 공고화 | `/remember`, `/compact`, `recall_episodes` 도구 | 구현됨 |
| `memory_eval` | 메모리 기능별 평가와 외부 벤치마크 실행, RAG 대비 순이득(benefit, tax) 비교 | `uv run python -m ash_industry.memory.eval`, `scripts/experiments/memory_net_value.py` | 구현됨 |
| `migration` | jarvis-agent 로 쌓인 상태(`~/.jarvis`, `.env`, docker 볼륨, Postgres DB, 역할, 테이블 이름)를 새 이름으로 옮긴다 | `uv run python scripts/migrate_from_jarvis.py [--step ...] [--apply]` | 구현됨 |
| `multi_agent` | 서브 에이전트를 패턴(supervisor, hierarchical, market, blackboard)으로 조율 | `/orchestrate`, `orchestrate` 도구 | 구현됨 |
| `notify` | 먼저 건넨 말과 스케줄 결과를 슬랙, 디스코드, Web Push 로도 보낸다 | `GET /api/push/vapid`, `PUT /api/push/subscriptions`, `DELETE /api/push/subscriptions`, ws `voice_spoken` | 구현됨 |
| `openloop` | 대화에서 흘린 약속과 미완 작업을 추적하는 AGENDA | `GET /api/agenda`, `POST /api/openloops/{loop_id}`, `/openloop` | 구현됨 |
| `plugins` | 턴과 도구 호출 앞뒤에 끼우는 플러그인 훅 | `~/.ash/plugins/*.py` | 구현됨 |
| `policy` | 입력 검증, 인증, 정책, 샌드박스 4단계 보안 파이프라인과 접근 키 | `/api/*`, `/ws` 의 `Authorization` 헤더 또는 `token` 쿼리 | 구현됨 |
| `proactive` | 요청 없이 성찰해 먼저 말을 건네고 반응으로 임계치를 학습 | ws `proactive_message`, `proactive_feedback` | 구현됨 |
| `proactive_eval` | "먼저 말해야 했나" 사례로 proactive 정책을 잰다 | `uv run python -m ash_industry.core.proactive.eval` | 구현됨 |
| `procedures` | 성공한 작업을 작업 종류당 절차 하나로 증류하고 실패는 반성해 개정 초안으로 고치며, 승인된 절차를 도구와 스킬로 노출 | `/procedures` | 구현됨 |
| `release` | develop 을 main 에 머지하면 커밋 제목으로 다음 버전을 정해 버전 파일, 태그, GitHub Release 를 만든다 | develop 에서 main 으로 PR 머지, `uv run python scripts/release_version.py plan \| apply <버전>` | 구현됨 |
| `scheduler` | cron 반복 작업과 한 번 실행 작업을 돌리고 결과를 알린다 | `/schedule`, `schedule` 도구, `POST /api/schedules/{name}`, ws `reminder` | 구현됨 |
| `scorecard` | 벤치마크 9개를 모델별로 돌려 레이더 그림 하나로 main 에이전트 성능을 보인다 | `uv run python -m scripts.experiments.ash_scorecard --polygon <id>` | 구현됨 |
| `session` | 세션 목록, 만들기, 분기, 삭제, 이력, 내보내기, 비용 보고, 옛 데이터 정리 | `GET /api/sessions`, `POST /api/sessions`, `POST /api/sessions/{session_id}/branch`, `DELETE /api/sessions/{session_id}`, `GET /api/sessions/{session_id}/messages`, `/sessions`, `/branch`, `/export`, `/cost`, `/cleanup` | 구현됨 |
| `settings` | 화면에서 고칠 수 있는 설정 허용 목록을 settings.yaml 에 저장하고 비밀값을 가려 적용값을 보인다 | `GET /api/settings`, `PUT /api/settings`, `GET /api/health`, HUD `SET` 화면 | 구현됨 |
| `skills` | Markdown/YAML 명령 매크로를 `/스킬 인자` 로 펼친다 | `/<스킬 이름> <인자>`, `~/.ash/skills/*.md` | 구현됨 |
| `send_now` | 일하는 동안 보낸 말을 같은 턴(도구 결과 뒤)이나 다음 턴으로 건네고, 지금 보내기로 하던 일을 뒤로 넘기거나 멈춘다. 모든 에이전트 공통 | ws `user_message`(일하는 중), `send_now`, `queue_take`, HUD Ctrl(Cmd)+Enter, ↑, Esc | 구현됨 |
| `task_pattern` | 사용자가 알려 준 일하는 방식을 그 에이전트만 기억한다 | `remember_task_pattern` 도구, `/patterns` | 구현됨 |
| `thought` | 요청 시점과 성찰 시점의 inner thought, router 판정, 짧은 답 분류 | ws `inner_thought`, `thought_route`, `thought_end`, `reply_classify` | 구현됨 |
| `tools` | 파일, 셸, 검색, 웹 내장 도구와 파일 기반 사용자 도구 | `GET /api/tools`, `/tools`, `~/.ash/tools/` | 구현됨 |
| `turn_detach` | Dual-Channel: 오래 걸리는 턴은 작은 모델의 선응답으로 먼저 닫고 코어 모델은 뒤에서 이어 돌아 끝나면 답한다. 도는 작업은 HUD 리액터 둘레의 별로 보인다 | ws `user_message`(7.5초 넘는 턴), `connected.background_tasks`, ws `background_tasks` | 구현됨 |
| `usermodel` | 누적 기억에서 사용자 모델을 증류한다 | `/usermodel` | 구현됨 |
| `voice` | 서버와 브라우저 STT/TTS, 읽기 문구, 웨이크워드 | ws `voice_tts_request`, `voice_stt_submit`, 바이너리 프레임, `GET /api/voice/phrases/{name}` | 구현됨 |
| `web_hud` | 브라우저 HUD 화면 셸, 화면 전환(HUD, FLOW, SET), FastAPI 앱 기동 | `ash-industry`, `/` 화면 | 구현됨 |
| `workflow` | 에이전트 사이 위임을 관계 그래프로, 지금 세션의 위임을 시간과 토큰이 적힌 에이전트 지도로, 백그라운드 작업의 마지막 실행을 접힌 표로 보인다 | `GET /api/workflow?session=`, `GET /api/jobs`, ws `workflow_changed`, `job_changed`, HUD `FLOW` 화면 | 구현됨 |

---

## 기능별 상세

### agent_conversation: 최상위 에이전트 간 대화

**설명**: 최상위 에이전트가 다른 최상위 에이전트에게 일을 맡기거나 물어보고, 에이전트 쌍마다 이어지는 대화 세션에서 답을 받는다. 팀이 둘 이상이면 모든 에이전트의 시스템 프롬프트 끝에 위임 규칙(`TEAM_RULE`)과 자기를 뺀 팀 명단(id, 이름, 담당 설명)이 붙는다. 요청을 받으면 담당 에이전트가 있는지 먼저 보고, 있으면 직접 하지 않고 `ask_agent` 로 맡긴 뒤 답을 전한다(예: main 에게 문서 수정을 시키면 문서 담당에게). MCP 정책 `agents.<id>.servers` 가 막은 서버의 도구는 그 에이전트의 도구 목록에서도 빠져(`McpGate.hidden_tools`), 직접 하려다 막히는 대신 담당에게 맡긴다.

**입력과 결과**

| 입력 | 결과 |
|---|---|
| `ask_agent` 도구 호출(받는 에이전트, 질문) | 받는 쪽의 `peer-<부른 쪽>-<받는 쪽>` 세션에서 한 턴을 돌린 답. Web HUD 에서는 그 세션이 세션 목록에 열린다 |

**처리 흐름**: `AgentRegistry` 가 프로필을 모두 모은 뒤 `agent_profile.team_rule` 로 에이전트마다 규칙과 명단을 만들어 `AgentProfile.with_team` 으로 붙이고(같은 규칙은 한 번만), `SessionBuilder.tool_registry` 가 정책이 막은 MCP 도구를 `never` 와 같이 뺀다. 위임 호출은 `agent_conversation.AskAgentTool` 에서 받을 수 있는 질문 규칙과 깊이 제한을 확인하고, 쌍 세션을 열어(Web 은 `WebState.open_peer_session`, 스케줄은 `AgentRegistry.open_peer_session`) 받는 쪽 `AgentSession.prompt` 순.

**구현 파일**

| 파일 | 층 | 역할 |
|---|---|---|
| `src/ash_industry/app/agent_conversation.py` | app | `ask_agent` 도구와 에이전트 쌍 대화 세션 규칙 |
| `src/ash_industry/app/agent_profile.py` | app | 위임 규칙 `TEAM_RULE`, 팀 명단 `team_rule`, 프로필에 붙이는 `with_team` |
| `src/ash_industry/core/policy/mcp_gate.py` | core | `hidden_tools`: 에이전트가 어떤 인자로도 못 쓰는 MCP 도구 |

**테스트**

| 종류 | 파일 |
|---|---|
| 단위 | `tests/unit/test_agent_conversation_agent_conversation.py` |
| 단위 | `tests/unit/test_agent_registry_agent_profile.py`(팀 규칙), `tests/unit/test_agent_registry_agent_registry.py`(정책으로 숨김) |
| 통합 | `tests/integ/test_agent_conversation.py` |

**제약과 미구현**: 에이전트끼리의 대화 세션은 Web HUD 세션 목록에 다른 세션처럼 보인다(`docs/view_spec.md`).

---

### agent_loop: 에이전트 턴 실행

**설명**: 사용자 입력 하나에 대해 LLM 호출과 도구 실행을 `max_turns` 안에서 반복하고, 스트리밍 이벤트를 화면에 보낸다.

**입력과 결과**

| 입력 | 결과 |
|---|---|
| ws `user_message{text}` | `agent_start`, `message_update`, `tool_execution_start`, `tool_execution_end`, `agent_end` 이벤트와 세션에 저장된 메시지 |
| ws `abort`, `ctrl+k` | 진행 중인 루프 중단 |
| 모델이 출력 상한(`max_tokens`)에 잘림(`stop_reason=length`) | 잘린 도구 호출은 실행하지 않고 "답이 출력 한도에 걸려 잘렸어요…" 를 답으로 내고 턴을 끝낸다. 말없이 빈 턴으로 끝나던 것(11-17 실측) |
| `uv run python -m scripts.experiments.tau2_bench --model M [--judge-model J] [--limit N] [--seed S]` | τ²-bench(airline, retail) 점수(스코어카드 Tool Use 꼭짓점). `run_vertex()` 가 `{score, n, raw, detail, errors}` 를 돌려주고 CLI 는 출력만 한다. 같은 (모델, 시뮬레이터, 과제, 설정)은 `~/.ash/benchmarks/tau2/cache/` 를 읽어 다시 부르지 않는다 |

**처리 흐름**: `ws_router` 에서 `AgentSession.prompt` 로, 보안 파이프라인, 스킬 확장, router 판정, 사고와 AGENDA 판단 띄우기, `AgentHarness.run`, `run_agent_loop`, `model_layer.stream`, 도구 실행기 순. 프로바이더나 저장소가 예외를 던져도 `AgentHarness.run` 이 `finally` 에서 실행 표시(`is_running`)를 풀어, 다음 턴이 실행 중으로 막히지 않는다.

**프롬프트 배치**: 루프는 세션 동안 고정인 지시문(`system_prompt`)과 턴마다 바뀌는 덧붙임(`system_suffix`: 속생각 블록, 목표 규칙, 승인 규칙, Focus 덧붙임)을 `LLMContext` 의 다른 필드로 넘긴다. Anthropic 은 고정 지시문 블록에만 `cache_control` 을 두고 덧붙임을 그 뒤 캐시 없는 블록으로 보내, 속생각이 바뀌는 턴에도 도구 정의와 지시문 캐시가 살아 있다(전에는 한 문자열로 합쳐 턴마다 깨졌다). 시스템 메시지를 하나만 받는 OpenAI, Ollama, vLLM, Gemini 는 `full_system_prompt()` 로 고정 지시문 뒤에 덧붙임을 이어 보낸다(접두 캐시가 고정 부분까지 맞는다). 메모리 블록(`[핵심 사실]`, `[장기 기억]`)은 최근 턴 창 앞의 user 메시지라 턴마다 바뀌지만, 창(`stm_turns`)이 턴마다 미끄러져 메시지 접두는 어차피 바뀐다. 한 턴 안의 도구 호출 반복에서는 블록이 같아 캐시가 맞는다(운영 로그 gpt-4o-mini 14회 중 12회 적중, 미적중 둘은 세션 첫 호출).

**호출 측정**: 루프는 LLM 호출마다 `[Loop] llm call` 로그 한 줄을 남긴다. 필드는 모델, 첫 출력(글자, 생각, 도구 호출 조각)까지 걸린 초 `first_output_sec`, 전체 초 `total_sec`, `input_tokens`, `cache_read`, 부분별 글자 수 `prompt_chars` 다. `prompt_chars` 는 프롬프트에 놓이는 순서대로 `system`, `inner_thought`, `tools`, 메모리가 붙인 블록(`[핵심 사실]`, `[장기 기억]` 같은 첫 줄 머리말), role(`user`, `assistant`, `tool_result`)이다. OpenAI 는 `prompt_tokens` 에서 캐시 적중분(`prompt_tokens_details.cached_tokens`)을 빼 `input` 에, 적중분을 `cache_read` 에 둔다(Anthropic 과 같은 뜻).

**넘침 이어가기**: `max_turns` 의 마지막 차례까지 도구를 부르고 끝나면(다음 차례를 기다리는 도구 결과로 끝남) 루프가 바로 끊지 않는다. 도구 정의 없이 "한 것, 남은 단계, 지금까지의 답" 을 정리하는 LLM 호출을 한 번 하고, 그 정리를 기록에 남지 않는 지시로 매 호출 끝에 붙여 `max(1, max_turns // 2)` 차례를 더 돈다. 이어간 구간에서도 또 넘치면 두 번째 정리문을 답으로 돌려준다. 정리문은 화면에 흘리지 않고(두 번째만 답으로 보냄), 정리 호출이 실패하거나 비면 부른 도구 이름으로 만든 기본 정리문을 쓴다. 정리와 이어가기 지시는 항목 이름(한 것, 남은 단계, 지금까지의 답)만 고정하고, 내용과 답은 원래 요청의 언어와 답 형식을 따르게 한다(두 번째 정리문이 그대로 답이 되므로, 예전 문구로는 영어 요청에도 한국어 답이 나왔다). 중단 신호는 정리 호출 뒤에도 확인한다. 한 턴의 LLM 호출은 차례 `max_turns + max_turns // 2` 개(빈 답 재촉 포함 차례당 최대 두 번)와 정리 두 번이 상한이다. `agent_end.overflows` 가 넘친 횟수를 알리고, 하네스는 넘친 턴의 턴 일화 metadata 에 `overflow: true` 를 남긴다(실패 반성의 근거). `AgentLoopConfig.overflow_resume=False` 면 예전처럼 그 자리에서 끊는다. EMMA(arXiv 2610.35966) 의 overflow decomposition 을 한 에이전트 루프에 맞게 줄였다.

**구현 파일**

| 파일 | 층 | 역할 |
|---|---|---|
| `src/ash_industry/agent_layer/loop.py` | agent_layer | LLM 호출과 툴 실행을 반복하는 루프 본체 |
| `src/ash_industry/agent_layer/loop_overflow.py` | agent_layer | 넘침 판단, 이어갈 예산, 정리 지시와 기본 정리문(순수 함수) |
| `src/ash_industry/agent_layer/prompt_measure.py` | agent_layer | LLM 호출 입력을 시스템, 사고, 도구, 메모리 블록, role 별 글자 수로 나눔(순수 함수) |
| `src/ash_industry/agent_layer/harness.py` | agent_layer | 세션 이력, 작업 기억 변환, 이벤트 구독을 묶어 한 턴을 돌리는 래퍼 |

**테스트**

| 종류 | 파일 |
|---|---|
| 단위 | `tests/unit/test_agent_loop_agent_types.py` |
| 단위 | `tests/unit/test_agent_loop_anthropic.py` |
| 단위 | `tests/unit/test_agent_loop_gemini.py` |
| 단위 | `tests/unit/test_agent_loop_harness.py` |
| 단위 | `tests/unit/test_agent_loop_loop.py` |
| 단위 | `tests/unit/test_agent_loop_loop_overflow.py` |
| 단위 | `tests/unit/test_agent_loop_model_registry.py` |
| 단위 | `tests/unit/test_agent_loop_model_types.py` |
| 단위 | `tests/unit/test_agent_loop_ollama.py` |
| 단위 | `tests/unit/test_agent_loop_openai.py` |
| 단위 | `tests/unit/test_agent_loop_prompt_measure.py` |
| 단위 | `tests/unit/test_agent_loop_provider_base.py` |
| 단위 | `tests/unit/test_agent_loop_session.py` |
| 단위 | `tests/unit/test_agent_loop_stream.py` |
| 단위 | `tests/unit/test_agent_loop_vllm.py` |
| 통합 | `tests/integ/test_agent_loop.py`(넘친 턴이 이어가서 답하고 턴 일화에 `overflow` 를 남김). ws 턴 루프는 `tests/integ/test_web_hud.py` 시나리오가 함께 돈다 |
| 실험 | `scripts/experiments/loop_overflow.py`(KramaBench archeology, legal 과제로 이어가기 전후 비교) |
| 실험 | `scripts/experiments/tau2_bench.py`, `tau2_score.py`, `tau2_tools.py`(τ²-bench 꼭짓점). 단위 테스트 `tests/unit/test_scorecard_tau2.py` |

**τ²-bench 꼭짓점**: sierra-research/tau2-bench v2.0.0(MIT) 의 airline, retail 데이터(DB, 과제, 정책)를 `~/.ash/benchmarks/tau2/src/tau2-bench-main/` 에 받는다(공식 저장소 tarball 에서 `data/tau2/domains/{airline,retail}` 과 `src/tau2` 만 풀었다). 표본은 공식 test split(airline 20, retail 40)에서 도메인마다 id 순 정렬 뒤 `random.Random(seed).sample` 로 20 개를 고르고 도메인을 번갈아 늘어놓는다(`--limit` 은 앞에서 자른다). 도메인 도구 30 개는 공식 코드를 평가 전용으로 옮긴 것이고(`tau2_tools.py`, 운영 도구 목록에는 없다), 큰 DB 를 과제마다 복사하지 않으려고 공유 DB 위에 바뀐 레코드만 복사하는 덮어쓰기 층에서 돈다. 에이전트는 운영 루프(`run_agent_loop`, `AgentLoopConfig()` 기본값, 넘침 이어가기 켬)에 공식 에이전트 지시문과 정책을 시스템 프롬프트로 주고, 사용자 시뮬레이터는 `judge_model`(기본 gpt-4o, temperature 0)이 공식 텍스트 지시문으로 말한다. 대화는 공식 첫 인사로 시작해 사용자가 `###STOP###`, `###TRANSFER###`, `###OUT-OF-SCOPE###` 를 말하면 끝나고, 공식 상한(200 단계, 도구 오류 10 회)에 닿으면 0 점이다. 보상은 공식처럼 끝난 DB 와 정답 행동을 적용한 DB 의 일치에 필요한 값의 전달을 곱한다. 공식과 다른 점은 셋이다. 전달 여부를 공식 기본(의미 판정 LLM) 대신 공식이 함께 두는 substring 방식으로 본다. retail 의 NL_ASSERTION(LLM 판정)은 짝을 이룬 `communicate_info` 값의 substring 으로 대신 본다. 시뮬레이터에 v2 언어 팩의 persona 문구를 넣지 않는다. score = pass^1 × 100, `detail` 에 도메인별 pass^1 과 문항당 LLM 호출 수, 입력, 출력 토큰(메인 모델과 시뮬레이터 따로)을 둔다.

**제약과 미구현**: 스케줄 작업(gpt-4o)의 첫 호출은 매시 캐시가 식은 뒤라 늘 미적중이고(둘째 호출만 적중), 이는 프롬프트 배치로 줄지 않는다. `/cost` 는 `cache_read` 를 비용에 넣지 않는다.

---

### agent_registry: 최상위 에이전트 등록

**설명**: `~/.ash/team/*.yaml` 정의 파일 한 장이 최상위 에이전트 하나가 된다. 에이전트마다 이름, 명언, 색, 모델, 개성, 도구 목록, 도구 경계(`ask`, `never`), 층별 기억 읽기 정책(`memory.read`)을 갖고, 비운 항목은 main 설정을 이어받는다. `model` 은 모델 이름만 바꾸고 프로바이더, 키, 주소는 main 것을 쓴다. `max_tokens` 는 한 번의 답(도구 호출 인자 포함) 출력 상한을 main 값 대신 쓴다(Kiri 는 16000. 설명 영상의 장면 코드 여럿이 4096 에 잘렸다). `provider` 가 main 과 다르면 main 의 키와 주소를 넘기지 않고 그 SDK 의 환경변수 키(`OPENAI_API_KEY` 등)와 기본 주소를 쓴다(`agent_model`). Web HUD 는 세션 에이전트의 브랜드로 칠해진다.

**입력과 결과**

| 입력 | 결과 |
|---|---|
| `GET /api/agents` | 최상위 에이전트 목록(main 먼저) |
| `GET /brand.js`, `GET /manifest.json` | main 에이전트의 워드마크, 명언, 색 |
| ws `?agent=<id>`, `ash-industry --agent <id>` | 그 에이전트가 맡는 새 세션. 모르는 에이전트면 ws 는 `4404`, 화면은 재접속하지 않고 `default` 로 한 번 옮긴다 |
| 루프 시작, 끝 | ws `agent_activity{active[]}` |
| 일하는 중에 다른 에이전트로 전환했다가 돌아옴 | 턴은 백엔드에서 계속 돈다. 다시 붙으면 `connected.in_flight` 로 진행 중인 턴(글, 도구 흔적)을 이력 뒤에 다시 그리고 끝날 때까지 입력을 막는다 |

**처리 흐름**: `agent_registry` 가 정의 파일을 읽어 에이전트마다 `AgentProfile` 과 `SessionBuilder` 를 들고, `agent_router` 와 `brand_router` 가 화면에 내주고, `agent_activity` 가 일하는 에이전트 변화를 방송하는 순. 전환할 때는 `turn_replay` 가 세션마다 진행 중인 루트 턴의 이벤트(연속 글 조각은 하나로 합침)를 들고 있다가 다시 붙은 연결의 `connected` 에 싣고, 화면은 이력을 다 그린 뒤 그것을 재생하고 그사이 온 라이브 이벤트를 잇는다.

**구현 파일**

| 파일 | 층 | 역할 |
|---|---|---|
| `src/ash_industry/app/agent_registry.py` | app | 정의 파일을 읽어 에이전트별 프로필과 세션 빌더를 드는 레지스트리. 에이전트별 도구 레지스트리(`tool_registry`)도 준다 |
| `src/ash_industry/ui/web/router/agent_router.py` | ui | `GET /api/agents` |
| `src/ash_industry/ui/web/router/brand_router.py` | ui | `GET /brand.js`, `GET /manifest.json` 브랜드 주입 |
| `src/ash_industry/ui/web/agent_activity.py` | ui | 일하는 에이전트 집계와 `agent_activity` 방송 |
| `src/ash_industry/ui/web/turn_replay.py` | ui | 세션별 진행 중인 턴 이벤트를 모아 다시 붙은 화면에 `in_flight` 로 준다 |
| `src/ash_industry/ui/web/static/app/agents.js` | ui | 에이전트 목록, 전환 화살표의 일하는 중 표시, 세션 표식 색 |
| `src/ash_industry/ui/web/static/app/agent-nav.js` | ui | 구체 좌우 화살표와 구체 밀기로 에이전트 전환, 밀려 나가고 들어오는 애니메이션 |
| `src/ash_industry/ui/web/static/app/brand.js` | ui | 세션 에이전트의 이름, 명언, 색 적용 |
| `src/ash_industry/ui/web/static/app/session.js` | ui | 전환과 재접속 때 이력 뒤에 `in_flight` 재생, 그동안 온 이벤트를 붙잡았다 잇기 |

**테스트**

| 종류 | 파일 |
|---|---|
| 단위 | `tests/unit/test_agent_registry_agent_activity.py` |
| 단위 | `tests/unit/test_web_hud_turn_replay.py` |
| 단위 | `tests/unit/test_agent_registry_agent_profile.py` |
| 단위 | `tests/unit/test_agent_registry_agent_registry.py` |
| 단위 | `tests/unit/test_agent_registry_brand_router.py` |
| 단위 | `tests/unit/test_agent_registry_infra_builder.py` |
| 통합 | `tests/integ/test_agent_registry.py` |
| 통합 | `tests/integ/test_approval.py`(일하는 중에 다른 세션으로 옮겼다 돌아오면 `in_flight` 와 기다리던 승인을 받고 턴을 끝낸다) |

**제약과 미구현**: 구체 색 섞기는 두 색까지다. HUD 의 AGENDA, ACTIVITY, SESSIONS 는 지금 보는 에이전트의 것만 보이고, 모든 에이전트를 한꺼번에 보는 보기는 FLOW 뿐이다(`docs/view_spec.md`). 턴 하나의 재생 이벤트는 1000건까지 모은다(넘으면 재생이 중간에서 멈춘다). 루프가 `agent_end` 를 보낸 뒤 답을 저장하기 전의 짧은 틈에 다시 붙으면 그 답은 새로고침 전까지 보이지 않는다.

---

### approval: 도구 실행 승인

**설명**: 승인이 필요한 도구를 실행하기 전에 사용자에게 묻고, "항상 허용"한 (도구, 패턴)은 에이전트별 규칙 파일에 남겨 다시 묻지 않는다.

**입력과 결과**

| 입력 | 결과 |
|---|---|
| 승인 필요 도구 호출 | ws `approval_request{id, command, reason, always_pattern}` 을 세션의 연결 전부에 보낸다 |
| ws `approval_response{id, approved, always}` | 먼저 온 답 하나만 채택, `approval_resolved`. `always=true` 면 `approvals/<agent_id>.yaml` 에 패턴 저장 |
| 120초 무응답 | 거부로 처리, `approval_resolved{timeout:true}` |
| 요청 때 붙은 연결이 없음 | 화면이 한 번이라도 붙었던 세션(다른 에이전트로 옮겨 감)이면 기다리고, 돌아온 연결에 요청을 보낸다. 다른 세션을 보는 HUD 에는 `approval_waiting` 으로 "승인 대기 · 이동" 띠를 띄운다. 화면이 붙은 적 없는 세션(스케줄, 헤드리스)은 바로 거부 |
| `command` 가 `security.dangerous_commands` 에 걸리는 호출 | 묻지 않고 막는다. "항상 허용" 규칙보다 먼저 본다. 스케줄 작업과 목표 차례도 같다 |

**처리 흐름**: 도구 실행기에서 `sandbox.decide` 로, 위험 명령 검사, `approval_rules` 대조, `SessionApprovals` 가 연결 전부에 요청, 첫 답 채택, `approval_rules` 저장 순.

**구현 파일**

| 파일 | 층 | 역할 |
|---|---|---|
| `src/ash_industry/core/policy/approval_rules.py` | core | "항상 허용" 규칙 YAML 저장과 대조 |
| `src/ash_industry/ui/web/approvals.py` | ui | 세션 하나의 승인 요청을 연결 전부에 보내고 먼저 온 답을 쓴다 |
| `src/ash_industry/ui/web/static/app/approval.js` | ui | 승인 모달과 음성 답 해석(`parseApprovalAnswer`) |
| `src/ash_industry/ui/web/web_state.py` | ui | 세션별 브로커 생성, 승인 대기 목록(`waiting_approvals`)과 `approval_waiting` 방송 |
| `src/ash_industry/ui/web/static/app/approval-wait.js` | ui | 다른 세션의 승인 대기 띠, 누르면 그 세션으로 이동 |

**테스트**

| 종류 | 파일 |
|---|---|
| 단위 | `tests/unit/test_approval_approval_rules.py` |
| 단위 | `tests/unit/test_approval_approvals.py` |
| 단위 | `tests/unit/test_policy_sandbox.py` |
| 통합 | `tests/integ/test_approval.py` |

**제약과 미구현**: 음성 승인 답에 부정어가 있으면 분류 없이 거부한다. 에어팟에서 승인 되읽기가 들리는지 실기기 확인 전이다(`TODO.md`).

---

### cli: 명령줄 진입점

**설명**: `ash-industry` 명령 인자를 `StartupPlan` 하나로 정규화하고, 시작 세션을 고른 뒤 Web HUD 백엔드(uvicorn)를 띄운다. 화면은 브라우저나 데스크톱 앱이 연다.

**입력과 결과**

| 입력 | 결과 |
|---|---|
| `ash-industry [--host] [--port]` | Web HUD 백엔드 기동(기본 `127.0.0.1:7777`). 예전 플래그 `--web` 도 받는다 |
| `ash-industry --session <id>` | 그 세션으로 연다. 세션을 만든 에이전트로 열린다 |
| `ash-industry --agent <id>` | 그 에이전트의 기본 세션(`default-<id>`, main 은 `default`)으로 연다. 모르는 에이전트면 목록을 출력하고 끝낸다 |
| `ash-industry --list-sessions` | 저장된 세션 목록 출력 |
| `ash-industry --help`, `ash-industry --version` | 도움말, 버전 |

**처리 흐름**: `cli_startup.parse_startup_plan` 에서 `build_app` 으로, `resolve_start_session` 이 세션 메타를 만들거나 읽고(`repo.create` 는 있으면 그대로), `web.startup.run_web` 순. 두 번 실행해도 같은 세션에 붙는다.

**구현 파일**

| 파일 | 층 | 역할 |
|---|---|---|
| `src/ash_industry/ui/cli/cli_startup.py` | ui | 인자 정규화, 시작 세션 결정, 백엔드 기동 |
| `src/ash_industry/ui/web/startup.py` | ui | uvicorn 실행 |

**테스트**

| 종류 | 파일 |
|---|---|
| 단위 | `tests/unit/test_cli_cli_startup.py` |
| 통합 | 없음. 기동은 `tests/integ/test_web_hud.py` 의 앱 조립이 대신 본다 |

**제약과 미구현**: 터미널 화면(TUI)은 없앴다. 터미널에서 대화하려면 브라우저나 데스크톱 앱을 쓴다.

---

### desktop: 데스크톱 앱

**설명**: Electron 셸이 Web HUD 를 창 하나로 띄운다. 백엔드는 그대로 docker compose 의 `ash-backend` 이고, 셸은 떠 있는지만 본다. 띄우는 것은 사용자(`docker compose --profile web up -d`)와 재기동은 Ion 의 몫이라 앱은 docker 를 모르고, 그래서 저장소 밖의 앱 번들로 받아 쓸 수 있다. 백엔드가 없으면 5초마다 다시 보다가 뜨면 붙는다. 창을 닫으면 트레이로 숨어 ws 를 열어 둬서 🔔 와 리마인더를 OS 알림으로 받는다. 전체 화면 창이면 전체 화면을 먼저 풀고 숨긴다(바로 숨기면 macOS 에 검은 전체 화면 공간이 남는다). 전역 단축키로 창을 앞으로 가져와 듣기를 연다.

**입력과 결과**

| 입력 | 결과 |
|---|---|
| GitHub Release 의 `AshIndustry-<버전>-<arch>.dmg` | Applications 에 끌어 넣고 처음 한 번 Gatekeeper 를 푼다(README). Apple Silicon 은 arm64, Intel 은 x64 |
| `cd desktop && npm install && npm start` | 저장소에서 바로 띄우기. 두 번째 실행은 첫 창을 앞으로 가져온다 |
| `cd desktop && npm run dist` | 이 기계에서 dmg, zip 빌드(`desktop/dist/`, 서명 없음) |
| 전역 단축키(기본 `CommandOrControl+Shift+J`) | 창을 앞으로, HUD 로 돌아가 듣기 토글 |
| 트레이 메뉴 | 열기, 듣기 시작, 종료 |
| HUD `SET` 화면의 Desktop 카드 | 단축키, 로그인 때 자동 실행, 백엔드 주소(루프백만) 저장 |
| HUD `SET` 화면의 RESTART BACKEND | 저장했지만 반영되지 않은 설정이 있을 때 Ion(`POST /ion/restart`)으로 백엔드 재시작. 브라우저에서도 된다 |

**처리 흐름**: `main.js` 에서 `BackendProbe.alive`(`/api/health`)가 참이 될 때까지 5초마다 보고(그동안 `loading.html` 부팅 화면. 단계는 `desktop:boot-stage` IPC 로 보내고, 백엔드가 응답하면 `boot_sequence.planExit` 대로 처음 뜬 뒤 2초가 될 때까지 머문 뒤 0.6초 어두워지고 주소를 연다. 움직임 줄이기면 기다리지 않는다), `BrowserWindow` 가 백엔드 주소를 열고 `preload.js` 가 `window.ashDesktop` 만 넘기는 순. 화면 쪽은 `desktop.js` 가 단축키 신호를 `voice-ui.listenNow` 로 잇는다. 배포는 `release.yml` 이 Release 를 만든 뒤 `desktop.yml` 을 불러(workflow_call. 워크플로 토큰이 만든 Release 는 `on: release` 를 깨우지 않는다) macOS 러너에서 electron-builder 로 arm64, x64 dmg 와 zip 을 만들어 같은 Release 에 올리고 설치 안내를 한 번 붙인다. 손으로는 Actions 의 Desktop 에서 태그를 넣어 돌린다.

**구현 파일**

| 파일 | 층 | 역할 |
|---|---|---|
| `desktop/main.js` | desktop | 창, 트레이, 단일 인스턴스, 전역 단축키, 권한(마이크와 알림은 백엔드 출처만), 이동 제한 |
| `desktop/window_hide.js` | desktop | 창 닫기를 트레이로 숨기기로. 전체 화면이면 풀린 뒤 숨긴다 |
| `desktop/preload.js` | desktop | `window.ashDesktop` 브리지(contextIsolation, sandbox) |
| `desktop/backend_probe.js` | desktop | 백엔드 응답 확인(`/api/health`, 3초 제한) |
| `desktop/desktop_settings.js` | desktop | 셸 설정 검증과 원자적 저장(`userData/settings.json`) |
| `desktop/loading.html` | desktop | 부팅 화면(로고, 단계별 부팅 로그, SYSTEM ONLINE)과 실패 안내 |
| `desktop/boot_sequence.js` | desktop | 부팅 단계 순서와 최소 표시, 어두워지는 시간 계산(순수) |
| `desktop/userdata_migration.js` | desktop | 이름이 바뀐 앱의 설정 파일을 옛 userData(`Jarvis`, `jarvis-desktop`)에서 한 번만 복사(덮어쓰지 않음) |
| `desktop/icons/icon.svg`(원본), `icon.png`, `trayTemplate.png`, `trayTemplate@2x.png` | desktop | 앱(Dock) 아이콘은 Ash 심볼, 트레이는 macOS 템플릿 이미지(단색) |
| `desktop/package.json`, `desktop/package-lock.json` | desktop | Electron 과 electron-builder 버전 고정, `build` 블록(appId, dmg와 zip, 아이콘, 서명 없음, 마이크 문구) |
| `.github/workflows/desktop.yml` | ci | `release.yml` 이 workflow_call 로 불러(또는 손으로 태그를 넣어) dmg, zip 을 빌드해 Release 에 올린다 |
| `src/ash_industry/ui/web/static/app/desktop.js` | ui | 브리지가 있을 때만 단축키를 듣기로 잇는다 |

**테스트**

| 종류 | 파일 |
|---|---|
| 단위 | `desktop/test/desktop_settings.test.js` (`npm test`) |
| 단위 | `desktop/test/window_hide.test.js` (`npm test`) |
| 단위 | `desktop/test/backend_probe.test.js` (`npm test`) |
| 단위 | `desktop/test/boot_sequence.test.js` (`npm test`) |
| 단위 | `desktop/test/userdata_migration.test.js` (`npm test`) |
| 통합 | 없음. 창, 트레이, 단축키는 손으로 확인한다 |

**제약과 미구현**: Apple Developer Program 에 가입하지 않아 서명과 공증이 없다. 받은 앱은 처음 한 번 `xattr -dr com.apple.quarantine "/Applications/Ash Industry.app"` 이나 시스템 설정의 "그래도 열기"로 푼다(`# ponytail`, 가입하면 공증 단계만 더한다). 자동 업데이트는 없고 새 dmg 로 덮는다. 앱은 백엔드를 띄우지 않는다. Web Push(서비스 워커)는 Electron 에서 돌지 않아 앱이 떠 있을 때만 알림을 받는다. Electron 의 브라우저 음성 인식은 Google 키가 없어 `network` 오류로 끝나고, 그때 서버 STT 로 넘어간다(`voice`). 이동 제한 때문에 창 안의 바깥 링크는 기본 브라우저로 열린다.

---

### docparse: 행정문서 파서
| 단위 | `desktop/test/window_hide.test.js` (`npm test`) |

**설명**: 행정문서를 포맷과 무관한 구조(IR)로 읽고, 편집 계획을 서식을 유지한 채 적용하고, 결과를 검증하고, HTML, PDF, PNG 로 렌더하는 파서. uv workspace 의 독립 패키지(`packages/docparse`, 자기 버전과 테스트)라 ash_industry 를 모르고, 에이전트와 MCP 서버는 공개 API(`inspect`, `apply`, `preview`, `verify_edit`, `render`, `to_html`)와 IR 만 본다. 포맷을 더할 때는 `FormatAdapter`(inspect, replace, to_html) 하나를 더하고 `parser_registry` 에 적는다. 지금은 DOCX 와 XLSX.

**입력과 결과**

| 입력 | 결과 |
|---|---|
| `inspect(path)` | `Document`: 본문 문단 `p<n>`(run 포함), 표 `t<i>`, 셀 `t<i>r<r>c<c>`, 셀 안 문단 `t<i>r<r>c<c>p<k>`. 같은 파일은 같은 id. XLSX 는 시트 하나가 표 하나이고 셀에 주소(`B3`)가 붙는다 |
| `preview(document, plan)` | 바뀔 곳(before, after)과 문제(없는 대상, 같은 대상 두 번, 변화 없음, 항목 없음). 순수 함수 |
| `apply(path, plan, out_path)` | 계획을 적용해 `out_path` 에 저장하고 다시 읽은 구조. 원본은 두고, 같은 입력이면 같은 결과. DOCX 는 첫 run 에 글을 넣고 나머지 run 을 지워 글꼴과 굵기를 남기고, 셀 전체 치환은 첫 문단만 남긴다. XLSX 는 숫자였던 칸에 숫자 꼴 글이 오면 숫자로 둔다 |
| `verify_edit(before, after, plan)` | 대상마다 계획한 글이 들어갔는가, 계획 밖이 바뀌지 않았는가(셀과 그 안 문단은 한 묶음), id 가 사라지지 않았는가, `{{` 가 남지 않았는가 |
| `render(path, "html" \| "pdf" \| "png", out_dir)` | html 은 어댑터(DOCX 는 mammoth, XLSX 는 표. 본문 이스케이프), pdf 는 LibreOffice headless, png 는 pdftoppm. 만든 파일 경로 목록. 프로그램이 없으면 `RenderUnavailable` |

**처리 흐름**: `parser_registry` 에서 확장자로 어댑터 고르기, 어댑터의 `inspect` / `replace` / `to_html`, `render_service` 의 LibreOffice 와 poppler 호출(한 번에 하나, 프로필 디렉터리 분리), `verify_service` 대조 순.

**구현 파일**

| 파일 | 층 | 역할 |
|---|---|---|
| `packages/docparse/pyproject.toml` | docparse | 패키지 정의와 의존(python-docx, openpyxl, mammoth, pypdf) |
| `packages/docparse/src/docparse/__init__.py` | api | 공개 API |
| `packages/docparse/src/docparse/document_model.py` | schema | IR(Document, Table, Cell, Paragraph, Run)과 id 규칙 |
| `packages/docparse/src/docparse/edit_plan.py` | schema | 편집 계획, 미리보기(순수) |
| `packages/docparse/src/docparse/parser_protocol.py` | schema | `FormatAdapter` 계약 |
| `packages/docparse/src/docparse/parser_registry.py` | service | 확장자로 어댑터 선택, `inspect`, `apply`, `to_html`, `render` |
| `packages/docparse/src/docparse/adapters/docx_adapter.py` | service | DOCX(python-docx, mammoth) |
| `packages/docparse/src/docparse/adapters/xlsx_adapter.py` | service | XLSX(openpyxl) |
| `packages/docparse/src/docparse/render/render_service.py` | client | LibreOffice, pdftoppm 호출과 쪽 수 |
| `packages/docparse/src/docparse/verify/verify_service.py` | service | 편집 결과 검증(순수) |

**테스트**

| 종류 | 파일 |
|---|---|
| 단위 | `packages/docparse/tests/test_docx_adapter.py` |
| 단위 | `packages/docparse/tests/test_xlsx_adapter.py` |
| 단위 | `packages/docparse/tests/test_edit_plan.py` |
| 단위 | `packages/docparse/tests/test_verify_service.py` |
| 단위 | `packages/docparse/tests/test_render_service.py` |

**제약과 미구현**: 템플릿 채우기(`fill`), 빈 칸 탐지(`detect_fields`), HWPX(python-hwpx 로 수정, rhwp-python 으로 렌더), PPTX, PDF 는 다음 단계다. DOCX 의 중첩 표는 읽지 않고, 하이퍼링크 안의 run 은 치환하지 않는다(`# ponytail`). XLSX 는 openpyxl 이 차트와 그림을 저장하지 않는다(`# ponytail`). 테스트는 코드로 만든 작은 파일로 왕복하고, LibreOffice 렌더는 프로그램이 없는 경우만 검사한다(실제 렌더는 ash-mcp 컨테이너에서 수동 확인).

---

### docs_mcp: 행정문서 MCP 서버

**설명**: 에이전트가 문서 폴더(`ASH_DOCS_DIR`, 기본 `~/Documents/ash`)의 행정문서를 docs MCP 서버의 도구로 읽고 고친다. 서버(`packages/docs_mcp`)는 `ash-mcp` 컨테이너에서 `docparse` 만 불러 돌고, 문서 폴더 밖 경로는 거부하며, 결과는 원본 옆 `<이름>.edited-<시각>.<확장자>` 로 저장해 원본을 덮어쓰지 않는다. 수정은 `plan_edit`(미리보기) 과 `apply_edit`(적용) 둘로 나뉘어 사용자가 바뀔 곳을 본 뒤 적용하고, `apply_edit` 는 MCP 정책의 쓰기 도구(ask)라 승인 모달을 거친다.

**입력과 결과**

| 입력 | 결과 |
|---|---|
| `list_documents(subdir)` | 폴더 안 DOCX, XLSX 목록(상대 경로, 크기, 수정 시각). 숨김 폴더(`.render`)는 뺀다 |
| `inspect_document(path, include_empty)` | id 가 붙은 문단과 표 셀. 빈 문단은 기본으로 뺀다. 항목 2000개 넘으면 문단만 앞부분 |
| `plan_edit(path, replacements[{target, text}])` | `plan_id`, 바뀔 곳, 문제. 같은 원본 상태와 같은 계획이면 같은 `plan_id` |
| `apply_edit(plan_id)` | 새 파일 경로와 검증 결과. 문제가 있는 계획, 모르는 id, 계획 뒤 바뀐 원본은 `error`. 같은 `plan_id` 를 다시 부르면 처음 결과를 그대로 돌려준다 |
| `render_document(path, html \| pdf \| png)` | html 은 본문 문자열, pdf 와 png 는 `.render/<이름>/` 아래 파일 경로 |
| 사용자 "출장신청서 기간을 12월 3일에서 5일로 바꿔" | 에이전트가 inspect 로 id 를 고르고 plan_edit 결과를 "대상 id: 전 → 후" 로 보인 뒤, 사용자가 맞다고 하면 apply_edit |

**처리 흐름**: `DocsPaths` 경로 검사, `docparse.inspect`, `preview` 로 `PlanStore` 에 계획 보관, 승인 뒤 `docparse.apply` 와 `verify_edit`, 결과 보관 순. 20MB 넘는 파일은 열지 않는다.

**구현 파일**

| 파일 | 층 | 역할 |
|---|---|---|
| `packages/docs_mcp/src/docs_mcp/docs_server.py` | api | MCPServer 와 도구 다섯 개(`DocsService`), 주석(readOnlyHint) |
| `packages/docs_mcp/src/docs_mcp/docs_paths.py` | common | 문서 폴더 안 경로 검사, 결과와 렌더 파일 자리, 목록 |
| `packages/docs_mcp/src/docs_mcp/plan_store.py` | repository | 편집 계획 보관(원본 크기와 수정 시각으로 id) |
| `mcp/servers.yaml`, `mcp/Dockerfile` | mcp(컨테이너) | `docs` 항목(포트 8001), LibreOffice, poppler, 나눔 글꼴, workspace 설치 |
| `docker-compose.yml` | infra | `ASH_DOCS_DIR` 를 `/data/documents` 로, 백엔드 `ASH_MCP_SERVERS` 에 docs |
| `src/ash_industry/core/tools/mcp_loader.py` | core | 도구 주석을 와이어 이름(readOnlyHint)으로 넘긴다(mcp 2.x 모델은 snake_case) |

**테스트**

| 종류 | 파일 |
|---|---|
| 단위 | `packages/docs_mcp/tests/test_docs_paths.py` |
| 단위 | `packages/docs_mcp/tests/test_docs_server.py` |
| 단위 | `tests/unit/test_mcp_mcp_loader.py`, `tests/unit/test_policy_mcp_policy.py`(주석 이름) |

**보안**: 경로는 문서 폴더 안만(`..`, 절대 경로, `~` 거부). 문서 본문은 데이터이고 에이전트 지시문이 본문 속 지시를 따르지 않게 한다. 어느 에이전트가 docs 도구를 쓰는지는 MCP 정책 `agents.<id>.servers` 로 가른다(로컬 정책 파일). 호출 기록에는 인자가 60자까지 남으므로 개인정보가 든 긴 값은 잘린다.

**제약과 미구현**: 편집 계획은 서버 메모리에만 있어 ash-mcp 가 다시 뜨면 `plan_edit` 부터 다시 한다(`# ponytail`). HUD 에 파일 올리기와 미리보기 화면이 없어 파일은 문서 폴더에 직접 두고 결과도 거기서 연다. 렌더 PNG 는 경로만 돌려주고 에이전트가 그림을 보지는 않는다. 템플릿 레지스트리(`list_templates`, `get_template_schema`, `register_template`, `fill_template`)와 HWPX, PPTX, PDF 는 다음 단계다.

---

### extension: 확장

**설명**: 에이전트 전용 도구와 슬래시 명령을 플랫폼 밖 패키지로 둔다. `ASH_PLUGIN__EXTENSIONS_DIR`(기본 `~/.ash/extensions`, Docker 는 프로필 디렉터리의 `extensions/`) 아래 `<이름>/__init__.py` 마다 `register(ctx)` 를 이름순으로 부른다. 확장이 등록한 도구는 에이전트 전용 풀(`AppContext.agent_tools`)에 들어가 팀 정의의 `tools` 에 이름을 적은 에이전트만 쓰고 main 의 레지스트리에는 없다. 명령은 디스패처를 만든 뒤 에이전트 범위 명령으로 붙는다.

**입력과 결과**

| 입력 | 결과 |
|---|---|
| `register(ctx)` 의 `ctx.agent_tools.register(tool)` | 에이전트 전용 도구 하나 |
| `ctx.add_command(name, handler, description)` | `/<name>` 명령. handler 는 `(args, scope) -> str` |
| `ctx.memory`, `ctx.loops` | 사용자 기억과 약속 저장소. 없으면 None 이고 확장이 그 도구를 빼면 된다 |
| 확장 하나가 import 나 `register` 에서 실패 | 경고 로그 `extension_failed` 만 남기고 다음 확장을 읽는다. 기동은 막지 않는다 |
| 디렉터리가 없음 | 아무것도 읽지 않는다 |

**처리 흐름**: `InfraBuilder.build_agent_tools` 가 `ExtensionLoader.load` 로 패키지를 `ash_ext_<이름>` 모듈로 import 하고 `register` 를 부른다. 결과의 도구 풀과 명령 목록을 `AppContext` 에 싣고, `register_commands` 가 명령을 붙인다.

**구현 파일**

| 파일 | 층 | 역할 |
|---|---|---|
| `src/ash_industry/app/extension_loader.py` | app | `ExtensionContext`, `ExtensionCommand`, `ExtensionLoader`, `import_extension` |
| `src/ash_industry/app/infra_builder.py` | app | `build_agent_tools`, `register_commands` 의 확장 명령 등록 |
| `src/ash_industry/app/app_context.py` | app | `agent_tools`, `extension_commands` |

**테스트**

| 종류 | 파일 |
|---|---|
| 단위 | `tests/unit/test_extension_extension_loader.py` |
| 단위 | `tests/unit/test_agent_registry_infra_builder.py`(확장 도구가 main 레지스트리에 없음, 기억이 있을 때만 생기는 도구) |

**보안**: 확장은 백엔드 프로세스 안에서 도는 신뢰하는 코드다. 사용자 도구와 플러그인처럼 본인이 둔 디렉터리만 읽는다. 확장 도구도 승인 규칙과 MCP 정책 밖의 일반 도구 경계(`ask`, `never`)를 따른다.

**제약과 미구현**: 기동 때 한 번 읽고 파일을 바꿔도 다시 읽지 않는다(`# ponytail`, 도구 디렉터리처럼 감시가 필요해지면 `ExtensionWatcher` 에 더한다). 확장의 의존성은 플랫폼 환경에 있어야 한다.

---

### external: 외부 트리거

**설명**: 선언한 외부 소스(MCP 서버의 툴)를 소스별 주기로 훑어 새 사실만 inbox 에 쌓고 성찰을 깨워, 에이전트가 외부 변화를 근거로 먼저 말하게 한다.

**입력과 결과**

| 입력 | 결과 |
|---|---|
| `~/.ash/external_sources/*.yaml` | 소스별 주기 폴링, 이미 본 이벤트는 `~/.ash/external_seen.jsonl` 로 걸러 재발화 없음 |
| 새 외부 이벤트 | 성찰 트리거가 깨어나고 세션이 inbox 를 한 번 비워 사고 요청에 싣는다. 사고가 실패했거나 게이트(쿨다운, 답 대기, 화면에 못 보냄)에 막혔거나 사고가 지난 말을 되풀이하면 inbox 앞에 되돌린다 |

**처리 흐름**: `external_loader` 에서 `poller` 로, `mcp_source.poll`, `dedup`(틱 상한 안의 것만 본 것으로 적는다), `inbox` 적재, `ExternalTrigger` 깨우기, `AgentSession.reflect` 의 `_drain_external_events`, 말하지 못하면 `inbox.put_back` 순.

**구현 파일**

| 파일 | 층 | 역할 |
|---|---|---|
| `src/ash_industry/core/external/external_loader.py` | core | 외부 소스 YAML 을 `ExternalSourceSpec` 목록으로 |
| `src/ash_industry/core/external/external_protocol.py` | core | 외부 소스 기본 클래스 |
| `src/ash_industry/core/external/external_types.py` | core | 외부 사실 1건의 모델 |
| `src/ash_industry/core/external/mcp_source.py` | core | MCP 툴 원문을 외부 이벤트로 바꾸는 소스 |
| `src/ash_industry/core/external/dedup.py` | core | 원문을 이벤트로 쪼개고 이미 본 것을 거른다 |
| `src/ash_industry/core/external/inbox.py` | core | 앱 레벨 외부 이벤트 큐 |
| `src/ash_industry/core/external/poller.py` | core | 소스별 주기 폴링과 성찰 트리거 깨우기 |

**테스트**

| 종류 | 파일 |
|---|---|
| 단위 | `tests/unit/test_external_dedup.py` |
| 단위 | `tests/unit/test_external_external_loader.py` |
| 단위 | `tests/unit/test_external_external_protocol.py` |
| 단위 | `tests/unit/test_external_external_types.py` |
| 단위 | `tests/unit/test_external_inbox.py` |
| 단위 | `tests/unit/test_external_mcp_source.py` |
| 단위 | `tests/unit/test_external_poller.py` |
| 통합 | `tests/integ/test_external.py` |

**제약과 미구현**: 상한을 넘은 항목은 소스가 다음 조회 때 다시 줄 때만 들어온다. inbox 가 200건을 넘으면 오래된 것부터 버린다. 성찰이 꺼낸 뒤 사고가 실패하거나 게이트에 막힌 이벤트는 inbox 앞에 되돌려 전할 때까지 성찰마다 다시 오른다(`# ponytail`).

---

### focus: Focus 모드

**설명**: 세션마다 작업 하나를 열고, 매 턴 분석, 기록, 진행, 조사 sub-agent 를 돌려 Web HUD 의 네 영역(REFERENCE, LOG, ANALYSIS, PROGRESS)을 채우고 메인 에이전트의 시스템 프롬프트에 작업 맥락을 붙인다.

**입력과 결과**

| 입력 | 결과 |
|---|---|
| `/focus <작업>`, 음성 "포커스 모드 <작업>" | 작업 시작, 첫 분석과 단계 계획을 `ASH_FOCUS__READY_TIMEOUT_SEC` 까지 기다린 뒤 작업 문장으로 첫 응답. 이미 작업이 있으면 거절 |
| `/focus stop` (`off`, `종료`) | 종료, `focus_state{active:false}`. 두 번째부터는 아무것도 하지 않음 |
| `/focus` | 진행률과 단계 텍스트 |
| 매 턴 | `focus_panel{area, markdown, busy}`, `focus_state{state}` |
| 조사 지시에 무엇을 찾을지 없음("레퍼런스 검색") | 레퍼런스 일꾼을 부르지 않고 `[주제 필요]` 한 줄을 레퍼런스에 남긴다(`focus_types.topicless`, 순수). 메인 에이전트 덧붙임이 그 줄을 보면 기억으로 주제를 짐작하지 않고 한 번 묻는다. 일꾼 지시문에도 같은 규칙이 있어 걸러지지 않은 지시도 짐작하지 않는다 |

**처리 흐름**: `ws_router` 가 디스패처보다 먼저 `focus_types` 로 명령을 해석하고 `FocusService.handle` 로, `focus_store` 의 활성 표시 배타 생성, `prompts` 로 sub-agent 지시문 조립, 턴 훅(`before_turn`, `after_turn`)에서 sub-agent 실행, `focus_panel` / `focus_state` 전송 순. 영역 일꾼(REFERENCE, ANALYSIS, LOG, PROGRESS)은 장기 기억 없이(`AgentMemoryPolicy(ltm=False)`) 돈다. 요청에 작업과 지시가 다 들어 있고, 사용자 프로필 같은 고정 기억이 짧은 지시("레퍼런스 검색")를 엉뚱한 주제로 끌었기 때문이다.

**구현 파일**

| 파일 | 층 | 역할 |
|---|---|---|
| `src/ash_industry/core/focus/focus_service.py` | core | 세션별 작업 열고 닫기, 턴마다 sub-agent 넷 실행과 화면 전송 |
| `src/ash_industry/core/focus/focus_store.py` | core | `~/.ash/focus/` 파일 기록과 세션당 활성 작업 하나 보증 |
| `src/ash_industry/core/focus/focus_types.py` | core | 상태, 진행률, 예상 시간, 명령 해석 순수 함수 |
| `src/ash_industry/core/focus/prompts.py` | core | sub-agent 역할 지시문과 메인 에이전트 맥락 조립 |
| `src/ash_industry/ui/web/static/app/focus.js` | ui | Focus 레이아웃과 네 영역 렌더, 음성 키워드 해석 |

**테스트**

| 종류 | 파일 |
|---|---|
| 단위 | `tests/unit/test_focus_focus_service.py` |
| 단위 | `tests/unit/test_focus_focus_store.py` |
| 단위 | `tests/unit/test_focus_focus_types.py` |
| 통합 | `tests/integ/test_focus.py` |

**제약과 미구현**: Web HUD 에서만 쓸 수 있다(ws 밖의 디스패처는 안내만 돌려준다). Focus 동안 🔔 는 보내지 않는다. 분석 결과는 이번 응답이 아니라 다음 응답에 들어간다(첫 지시만 기다린다).

---

### goal: 목표

**설명**: 대화 중에 맡긴 목표를 기록하고 스케줄러에 차례를 걸어, 대화 밖에서 에이전트가 한 단계씩 진행하고 새로 알릴 것만 알린다.

**입력과 결과**

| 입력 | 결과 |
|---|---|
| `/goal <문장>`, `goal` 도구(맡기기) | `~/.ash/goals/<id>.json` 저장, 스케줄 `goal-<목표 id>` 등록. 같은 목표는 하나 |
| `/goal` | 목표 목록 |
| `/goal stop <문장>` | 그 목표의 차례를 멈춘다 |
| 차례마다 | 새로 알릴 항목이 있을 때만 ws `reminder{kind:"goal", label:"목표: ..."}` |
| 에이전트가 `완료: 예` 로 답한 차례 | 목표는 열린 채로 두고 "그만 챙길까요?" 를 `ask-done` 항목으로 한 번만 알린다. 닫는 것은 `/goal stop` 이나 `goal` 도구 멈추기뿐이다 |

**처리 흐름**: `goal_cmd` 또는 `GoalTool` 에서 `goals_store` 저장과 `SchedulerService` 등록으로, 차례마다 `runner` 가 프롬프트를 짓고 경계 안의 도구로 에이전트를 돌려 `goals_types` 로 답을 읽고 알릴 항목을 고르는 순.

**구현 파일**

| 파일 | 층 | 역할 |
|---|---|---|
| `src/ash_industry/core/goals/goals_store.py` | core | id 마다 JSON 파일 하나인 목표 저장소 |
| `src/ash_industry/core/goals/goals_types.py` | core | 목표 모델, 자연 키, 답 해석, 알릴 항목 고르기 |
| `src/ash_industry/core/goals/runner.py` | core | 목표 한 차례 실행 |
| `src/ash_industry/core/goals/tool.py` | core | `goal` 도구(맡기기, 목록, 멈추기) |
| `src/ash_industry/core/slash/goal_cmd.py` | core | `/goal` 핸들러 |

**테스트**

| 종류 | 파일 |
|---|---|
| 단위 | `tests/unit/test_goal_goal_cmd.py` |
| 단위 | `tests/unit/test_goal_goals_store.py` |
| 단위 | `tests/unit/test_goal_goals_types.py` |
| 단위 | `tests/unit/test_goal_runner.py` |
| 단위 | `tests/unit/test_goal_tool.py` |
| 통합 | `tests/integ/test_goal.py`(정각 차례부터 대화 전달과 정산, 같은 결과면 침묵, 지나친 정각 따라잡기, 못 건넨 항목 재시도) |

**제약과 미구현**: 알린 직후 정산 전에 죽으면 다음 차례에 같은 항목을 한 번 더 알린다(`# idempotent`). 결과가 바뀐 차례는 도구를 두 번 부른다(`# ponytail`).

---

### ion: Ion

**설명**: 백엔드와 별개의 컨테이너 `ash-ion` 가 백엔드 프로세스와 에이전트별 작업 상태를 지켜보다, 백엔드가 죽거나 멈추거나 한 에이전트가 조용히 실패하면 사고를 열어 한 번 알리고(Web Push, SSE), 답에 따라 재기동하거나 작업을 멈춘다. 재기동 권한은 Docker 소켓 프록시(조회와 restart, stop 만)를 거친다. `/ion/*` HTTP 는 공개 API 라 확장(예: 감시 담당 에이전트의 도구)이 대화로 사고를 읽고 답할 수 있다. 에이전트가 오래 조용한 것은 사고가 아니다(에이전트는 하루 넘게 말이 없을 수 있다). Ion 은 조용히 지켜보다 오류와 중단에만 움직인다. 사고 제목은 지표의 `name`(브랜드 이름)으로 쓰고 사고 id 와 `target` 은 에이전트 id 다. Ion 컨테이너에는 LLM 이 없어 백엔드가 죽어 있는 동안은 띠와 푸시가 전부다.

**입력과 결과**

| 입력 | 결과 |
|---|---|
| `GET /api/platform/metrics` | 프로세스 자원(psutil), 이벤트 루프 지연(1초 하트비트의 최근 60초 최대), 에이전트별 작업 수, 연속 실패, 마지막 성공, 열린 세션 수, 켜진 스케줄 유무, 마지막 활동 시각(세션 updated_at), 화면에 보일 이름(`name`) |
| 관측값의 흐름(`health_rules.evaluate`) | 신호: 백엔드 무응답(3회 연속), 재시작 루프(10분 3회), 루프 정지(5초 2회), 메모리(limit 85% 5분), 에이전트 연속 실패(3회), 스케줄 정체(9~21시, 직전 예정 시각 뒤 성공이 없고 2시간 지남. 예정 시각을 모르는 옛 백엔드는 마지막 성공에서 2시간). 하루 1회 스케줄은 그날 차례가 성공했으면 조용하다. 장기 침묵은 신호가 아니다(#238) |
| 신호와 시각(`incident_id`) | `종류:대상:연 시각`. 같은 신호에 열린 사고가 있으면 새로 열지 않는다 |
| `IncidentStore` | `~/.ash/ion/incidents.json`. 같은 id 는 하나, 알림과 답은 처음 값만 남는다 |
| 감시 루프(15초, 지표와 컨테이너 통계는 60초) | 사고 열기와 알림 한 번, 신호가 사라지면 닫기 |
| `GET /ion/status`, `GET /ion/events` | 상태 한 장, 사고 이벤트 SSE |
| `GET /ion/incidents?closed=1&limit=N`, `GET /ion/logs?since_ms&until_ms&lines` | 닫힌 사고까지 최신순, 백엔드 컨테이너 로그(프록시의 logs, 다중화 프레임을 풀어 글로) |
| `POST /ion/incidents/{id}/respond` `{action}` | `restart`, `stop`, `pause`, `ignore`. 사고당 한 번만 행동 |
| HUD ION 띠와 끼어들기(`src/ash_industry/ui/web/static/app/ion.js`) | 열린 사고를 헤더 아래 한 줄씩, 그리고 지금 보는 어느 에이전트의 대화에든 ION 카드로 보이고 버튼으로 답한다. 심각도(`severity`: critical 은 무응답, 재시작 루프, 멈춤. warning 은 메모리, 연속 실패, 정체)로 구체 뒤 배경을 물들인다. SSE 로 바로 갱신, 데스크톱 앱이면 OS 알림. `docs/view_spec.md` |
| `~/.ash/ion/subscriptions.json` | Postgres 의 푸시 구독을 60초마다 복사. DB 가 죽어도 알림이 나간다 |

**처리 흐름**: 백엔드는 `JobBoard` 기록(연속 실패 수 `fail_streak` 포함)과 스케줄 작업의 에이전트, 열린 세션, `LoopLagMonitor` 를 `PlatformMetricsService` 가 한 장으로 접어 `platform_router` 가 낸다. Ion 쪽은 `watch_service` 가 `backend_client`(health, metrics, jobs)와 `docker_client`(inspect, stats)로 관측해 `health_rules` 에 넣고, 신호마다 `incident_store` 에 사고 하나를 열어 알림(`ion_cli` 의 푸시, `ion_app` 의 SSE)을 한 번 보내며, 답(`respond`)은 처음 것만 행동으로 옮긴다. 앱은 nginx 의 `/ion/` 로 붙는다.

**구현 파일**

| 파일 | 층 | 역할 |
|---|---|---|
| `src/ash_industry/core/platform/metrics_service.py` | core | 에이전트별 작업 지표와 프로세스 지표 |
| `src/ash_industry/core/platform/loop_lag.py` | core | 이벤트 루프 지연 하트비트 |
| `src/ash_industry/ui/web/router/platform_router.py` | ui | `GET /api/platform/metrics` |
| `src/ash_industry/core/workflow/job_board.py` | core | `fail_streak` 기록 |
| `src/ash_industry/ion/health_rules.py` | ion | 관측값 → 신호. 순수 함수 |
| `src/ash_industry/ion/incident_store.py` | ion | 사고 기록 파일 |
| `src/ash_industry/ion/ion_config.py` | ion | 설정(`ASH_ION__*`, 푸시 키와 DSN 은 백엔드 변수 되쓰기) |
| `src/ash_industry/ion/watch_service.py` | ion | 감시 루프, 사고 열고 닫기, 답에 따른 행동 |
| `src/ash_industry/ion/docker_client.py` | ion | 소켓 프록시 클라이언트. 허용 서비스만. `logs` 와 `demux_logs` |
| `src/ash_industry/ion/backend_client.py` | ion | 백엔드 health, metrics, jobs, 작업 끄기 |
| `src/ash_industry/ion/push_cache.py` | ion | 푸시 구독 파일 복사 |
| `src/ash_industry/ion/ion_app.py` | ion | `/ion/*` HTTP 와 SSE. `POST /ion/restart` 는 사고 없이 백엔드를 재기동한다(SET 화면 RESTART BACKEND) |
| `src/ash_industry/ion/ion_cli.py`, `__main__.py` | ion | 조립과 기동(`python -m ash_industry.ion`, 설치 뒤에는 `ash-ion`) |
| `docker-compose.yml`, `nginx/nginx.conf` | ion | `docker-socket-proxy`, `ash-ion` 서비스와 `/ion/` 경로 |
| `src/ash_industry/ui/web/static/app/ion.js` | ui | HUD ION 띠(상태 읽기, SSE, 버튼 응답, OS 알림) |

**테스트**

| 종류 | 파일 |
|---|---|
| 단위 | `tests/unit/test_platform_metrics_service.py` |
| 단위 | `tests/unit/test_platform_loop_lag.py` |
| 단위 | `tests/unit/test_ion_health_rules.py` |
| 단위 | `tests/unit/test_ion_incident_store.py` |
| 단위 | `tests/unit/test_workflow_job_board.py`(`fail_streak`) |
| 단위 | `tests/unit/test_ion_ion_config.py`, `test_ion_docker_client.py`(logs, demux), `test_ion_backend_client.py`, `test_ion_push_cache.py`, `test_ion_watch_service.py`, `test_ion_health_rules.py`, `test_ion_incident_store.py`(recent) |
| 통합 | `tests/integ/test_platform.py`(지표 API), `tests/integ/test_ion.py`(무응답 → 사고 → 답 → 재기동 한 번, 접근 키) |

**제약과 미구현**: 모바일 푸시의 버튼 답은 모바일 앱 저장소의 서비스 워커가 맡아야 해서 아직 없다. 폰에서는 푸시를 받고 HUD(`/m/` 또는 `/`)를 열어 띠에서 답한다. 데스크톱 OS 알림은 HUD 페이지가 띄우므로 앱 창이 닫혀(트레이) 있어도 오지만 앱 자체가 꺼져 있으면 없다. 메모리 신호는 컨테이너에 memory limit 이 없으면 Docker 가 호스트 전체를 한도로 줘 거의 켜지지 않는다. 프로필별 메모리는 한 프로세스라 못 나눈다(`# ponytail`, Tavu 가 별도 워커로 분리될 때). Docker Desktop 자체가 죽으면 Ion 도 같이 죽는다.

### journal: 자기 성찰 저널

**설명**: 장기 기억에 쌓인 최근 사고 로그를 LLM 으로 성찰해 저널 항목(`source=journal`)으로 남기고 보여 준다.

**입력과 결과**

| 입력 | 결과 |
|---|---|
| `/journal` | 최근 저널 |
| `/journal write` | 새 저널 항목 작성 |

**처리 흐름**: `journal_cmd` 에서 `ReflectionJournaler` 로, `MemoryService` 의 사고 로그 조회, LLM 성찰, 저널 항목 저장 순.

**구현 파일**

| 파일 | 층 | 역할 |
|---|---|---|
| `src/ash_industry/agent_layer/journal/journaler.py` | agent_layer | 사고 로그 성찰과 저널 항목 저장 |
| `src/ash_industry/core/slash/journal_cmd.py` | core | `/journal` 핸들러 |

**테스트**

| 종류 | 파일 |
|---|---|
| 단위 | `tests/unit/test_journal_journal_cmd.py` |
| 단위 | `tests/unit/test_journal_journaler.py` |
| 통합 | 없음. 실제 저장소에 사고 로그를 쌓아 저널을 쓰는 시나리오가 아직 없다 |

**제약과 미구현**: 사고(`thought.enabled`)가 꺼져 있으면 `/journal` 이 등록되지 않는다.

---

### mcp: MCP 도구

**설명**: 설정한 MCP 서버의 툴을 열거해 `AshTool` 로 감싸 도구 레지스트리에 등록하고 호출을 중계한다.

**입력과 결과**

| 입력 | 결과 |
|---|---|
| 설정 `mcp_servers`(`ASH_MCP_SERVERS` JSON 배열) | 서버마다 툴이 에이전트 도구로 보인다. `transport` 는 `stdio`, `http`(SSE), `streamable-http`(`/mcp`) |
| 에이전트의 MCP 툴 호출 | MCP 서버 응답을 도구 결과로 |
| Docker: `mcp/servers.yaml` | `ash-mcp` 컨테이너가 항목마다 프로세스 하나를 포트 하나에 띄운다(`mcp/mcp_launcher.py`, 죽으면 2, 5, 15, 30초 backoff 로 다시). 백엔드는 `http://ash-mcp:<포트>/mcp` 로 붙는다. 첫 항목은 Google Workspace(`workspace-mcp` 2.5.0, Gmail 과 Calendar), 둘째는 행정문서 `docs`(`packages/docs_mcp`, 포트 8001, `evi` 절) |
| Docker: `mcp/external_sources/*.yaml` | 백엔드의 `~/.ash/external_sources` 에 읽기 전용으로 붙어 `external` 기능의 주기 조회가 된다. 개인 값(라벨, 계정)이 들어가 `*.yaml` 은 git 에 올리지 않고 `google.yaml.example` 을 복사해 쓴다(안 읽은 메일 5분, 다가오는 일정 10분) |

**처리 흐름**: `InfraBuilder` 에서 `MCPToolLoader` 로, `_open_session`(transport 별 연결과 초기화), 툴 열거, `MCPToolWrapper` 등록, 호출 중계 순. 열거와 호출이 같은 세션 열기를 쓴다.

**구현 파일**

| 파일 | 층 | 역할 |
|---|---|---|
| `src/ash_industry/core/tools/mcp_loader.py` | core | MCP 툴 열거, 래핑, 등록, 호출 중계. transport 셋 |
| `mcp/mcp_launcher.py` | mcp(컨테이너) | servers.yaml 의 서버를 자식 프로세스로 띄우고 다시 띄운다. 환경변수 치환은 순수 함수 |
| `mcp/servers.yaml`, `mcp/Dockerfile` | mcp(컨테이너) | 서버 목록과 이미지(uv, node). Python 서버는 `uv tool install` 에 버전을 박는다 |
| `mcp/external_sources/google.yaml.example` | mcp(컨테이너) | Gmail, Calendar 주기 조회 선언 예시. 복사본 `google.yaml` 은 git 밖 |

**테스트**

| 종류 | 파일 |
|---|---|
| 단위 | `tests/unit/test_mcp_mcp_loader.py` |
| 단위 | `tests/unit/test_mcp_mcp_launcher.py` |
| 통합 | `tests/integ/test_mcp.py` |

**보안**: MCP 컨테이너의 포트는 `127.0.0.1` 에만 열고(Google OAuth 콜백 때문에 `MCP_GOOGLE_PORT`, 기본 8808 하나), 인증 토큰은 볼륨 `mcp_data` 에만 남는다. Google 자격증명은 `.env` 에서 컨테이너 환경으로만 간다. Google 쓰기 도구(send, draft, manage, modify 계열)의 승인, 도구별 허용, 인자 고정은 MCP 정책(`mcp_policy`)이 정한다. 쓰기 계열의 기본은 ask 다.

**제약과 미구현**: 서버마다 포트 하나라 `ASH_MCP_SERVERS` 도 서버마다 한 항목이다. 한 엔드포인트로 모으는 게이트웨이는 서버가 다섯 개쯤 넘을 때(`# ponytail`). MCP 서버에는 자체 인증이 없어 호스트 안의 아무 프로세스나 그 포트로 Gmail 도구를 부를 수 있다(단일 사용자 로컬 전제). 첫 Google 로그인은 브라우저에서 사람이 한 번 해야 한다.

---

### mcp_policy: MCP 도구 권한

**설명**: MCP 도구 호출마다 정책(서버, 도구, 에이전트)과 도구 종류로 allow, ask, deny 를 판정하고, ask 는 기존 승인 띠로 묻고, 모든 판정과 결과를 기록한다. Zapier MCP 의 액션별 켜고 끄기, 실행 전 확인, 인자 고정, 호출 기록에 해당한다.

**입력과 결과**

| 입력 | 결과 |
|---|---|
| `~/.ash/mcp_policy.yaml`(`security.mcp_policy_path`) | `defaults`(종류별 기본: read allow, write ask, unknown ask), `servers.<서버>.lock`(그 서버 모든 도구에 거는 인자 고정, 예: `{user_google_email: [계정]}`), `servers.<서버>.tools.<도구>` 의 `mode`, `lock`(인자 고정, `{to: [허용 값]}`. 같은 인자는 도구 쪽이 이긴다), `calls_per_hour`, `agents.<에이전트>` 의 `servers`(쓸 수 있는 서버)와 `deny`(막는 도구). 없으면 기본값. 개인 값이 들어가므로 볼륨 안에만 있고 git 에 올리지 않는다 |
| 도구 종류 | 서버의 도구 주석(`readOnlyHint`, `destructiveHint`)으로, 없으면 이름 앞머리(`get_`, `list_`, `search_` ... 는 read, `send_`, `manage_`, `delete_` ... 는 write, 그 밖은 unknown)로 가른다 |
| 호출 판정 순서 | 인자 고정 위반 → 도구 `deny` → 에이전트 제한 → 시간당 상한(기록의 지난 한 시간 allow, ask 수) → 도구 `mode` → 종류별 기본값. deny 는 묻지 않고 도구 결과에 이유를 적어 돌려준다(`policy` 판정). ask 는 승인 띠에 `google.send_gmail_message(to=…)` 와 이유를 보이고 "항상 허용"은 그 도구 전체(`*`)로 에이전트 승인 규칙에 남는다(인자 고정은 그 뒤에도 먼저 본다). allow 는 바로 실행 |
| 스케줄, 목표 작업 | 같은 문을 쓴다. 물을 사람이 없어 ask 도구는 실행하지 않고 로그에 남긴다 |
| `GET /api/mcp/policy`, `PUT /api/mcp/policy`, `GET /api/mcp/audit` | 정책 문서와 도구별 지금 판정, 정책 통째 교체(검증 뒤 파일에 쓰고 바로 적용), 최근 호출 기록(`docs/api_spec.md`) |
| SET 화면 MCP 표 | 도구마다 모드, 시간당 상한, 인자 고정을 고치고 SAVE. 아래에 최근 호출 50건(`docs/view_spec.md`) |
| `~/.ash/mcp_audit.jsonl`(`security.mcp_audit_path`) | 판정 줄(`call`: 시각, 에이전트, 서버, 도구, 판정, 이유, 인자 요약)과 결과 줄(`result`: 성공 여부, 오류 200자). 비밀값처럼 보이는 인자는 `***`. 최근 500줄을 메모리에 두고 파일은 1000줄에서 500줄로 다시 쓴다 |
| HUD TOOLS 목록과 `/api/tools` 의 `approval` | MCP 도구는 정책 판정이 ask 일 때 🔒 |

**처리 흐름**: `MCPToolLoader` 가 도구를 `McpGate` 에 색인(서버, 종류), 세션별 `DefaultSandbox.decide` 가 위험 명령 검사 다음에 `McpGate.evaluate`(순수 `mcp_policy.decide` + 기록), deny 면 `policy`, ask 면 기존 승인 흐름, allow 면 실행, `MCPToolWrapper` 가 결과를 기록 순. `PUT` 은 `mcp_router` 가 pydantic 으로 검증해 `McpGate.update`(저장 + 적용).

**구현 파일**

| 파일 | 층 | 역할 |
|---|---|---|
| `src/ash_industry/core/policy/mcp_policy.py` | core | 정책 모델, 도구 종류, 판정, 설명 한 줄, 정책 왕복(순수) |
| `src/ash_industry/core/policy/mcp_policy_store.py` | core | 정책 YAML 읽기와 임시 파일 뒤 교체 쓰기 |
| `src/ash_industry/core/policy/mcp_audit.py` | core | 호출 기록 jsonl, 최근 조회, 시간당 호출 수 |
| `src/ash_industry/core/policy/mcp_gate.py` | core | 도구 색인, 판정과 기록, 화면용 판정, 정책 갱신 |
| `src/ash_industry/core/policy/sandbox.py` | core | 위험 명령 뒤 MCP 문에 묻고 ask 는 승인 흐름으로 |
| `src/ash_industry/ui/web/router/mcp_router.py` | ui | 정책과 기록 REST |
| `src/ash_industry/ui/web/static/app/settings.js` | ui | SET 화면 MCP 표와 호출 기록 |

**테스트**

| 종류 | 파일 |
|---|---|
| 단위 | `tests/unit/test_policy_mcp_policy.py` |
| 단위 | `tests/unit/test_policy_mcp_audit.py` |
| 단위 | `tests/unit/test_policy_mcp_gate.py` |
| 단위 | `tests/unit/test_policy_sandbox.py` |
| 단위 | `tests/unit/test_mcp_mcp_loader.py` |
| 통합 | `tests/integ/test_mcp_policy.py` |

**멱등**: 같은 정책을 두 번 저장해도 파일은 같고, 같은 호출의 판정은 같다(기록만 한 줄 더). 정책 파일이 없으면 기본값으로 돈다.

**보안**: 인자 고정은 승인과 "항상 허용"보다 먼저 본다. 기록에는 인자 요약만 남고 token, secret, password 가 든 이름의 값은 가린다. REST 는 다른 `/api/*` 와 같은 접근 키 검사를 받는다.

**제약과 미구현**: 도구 종류를 이름 앞머리로 가르는 것은 추정이라 새 서버의 낯선 이름은 unknown(묻는다)으로 간다. "항상 허용"은 도구 단위라 인자별 허용은 `lock` 으로만 좁힌다. 에이전트별 정책은 파일로만 고친다(화면은 서버, 도구 표만). 시간당 상한은 메모리의 최근 500줄로 세어 아주 잦은 도구는 상한이 느슨해질 수 있다.

---

### memory: 에이전트 메모리

**설명**: (사용자, 에이전트, 세션) 범위를 아는 장기 기억(일화, 의미, 절차)과 세션 작업 기억(STM 최근 턴 창)을 두고, 턴 전 회상, 쓰기, 조용할 때의 공고화를 맡는다.

**입력과 결과**

| 입력 | 결과 |
|---|---|
| 매 턴 | 최근 `stm_turns` 턴 가운데 마지막 메시지에서 `stm_max_age_hours`(기본 24시간) 안의 턴만 창에 두고(마지막 턴은 늘 둔다. 며칠 전 대화가 창에 남으면 "목록 보여줘" 같은 짧은 말이 그 대화로 이어졌다), 빠진 턴은 일화 회상으로만 돌아온다. 범위 규칙으로 고른 기억을 프롬프트에 싣고(회상 블록은 추출 사실의 출처 턴까지 후보에 넣어 질의 관련도로 다시 매김), 턴 일화(EDM)를 남긴다. 답이 1,000자를 넘으면 나머지를 조각 일화(최대 2개)로 남긴다 |
| `/remember <내용>`, `/remember list`, `/remember search <키워드>`, `/remember forget <id>` | 장기 기억 저장, 나열, 검색, 삭제 |
| `/compact` | 현재 세션을 요약해 장기 기억에 저장 |
| `recall_episodes` 도구 | 부른 에이전트의 지난 턴 일화를 작업 종류, 성패, 기간으로 회상 |
| 사용자가 조용할 때 | daemon 틱에 얹혀 활성 세션의 일화에서 "주제: 값" 사실 추출(사실마다 내용이 가장 많이 겹치는 턴을 출처로 남김), 같은 작업 종류의 성공 턴 일화가 3번 쌓이면 절차 초안 정제(`procedures`) |

**처리 흐름**: `MemoryService.observe` 에서 `working.window` 와 `deixis` 로 창과 지칭을 정하고, `scope` 와 `access` 로 읽을 범위를 계산해 `stores` 조회, `retrieval.scoring` 과 `cues` 로 순위, `remember` 쓰기는 `long_term` 정책 적용, 공고화는 `consolidation.idle` 에서 `semantic_extract` 순.

**커버리지 재검색**(`memory.coverage_recall`, 기본 꺼짐): 회상 블록을 고를 때 사고 모델이 질문에서 기억으로 찾을 대상(사람, 장소, 물건, 일)을 최대 4개 뽑는다. 1차 회상과 함께 돌고 1.5초를 넘기거나 실패하면 1차 결과만 쓴다. 대상 이름이 회상 항목 글에 없고 벡터 유사도도 0.6 미만이면 빠진 것으로 보고, 빠진 대상마다 그 이름으로 한 번 더 찾아 창 안의 턴과 이미 보인 항목을 거른 첫 항목을 1차 결과의 뒷순위와 바꾼다. 회상 개수는 늘지 않고 1차 1순위는 늘 남는다. NVIDIA auto-ontology 의 entity coverage(질문 대상 추출, 후보 검색, 덮였는지 채점)를 옮겼고, 채점은 LLM 대신 글자와 벡터로 한다. 실서비스 조건(k=3, 답과 판정 gpt-4o-mini)에서 기준선(`turns+src`) 대비 이김과 짐은 LongMemEval-s 1 대 0, PersonaMem-v2 7 대 4(p=0.55), MINT-Eval 0 대 0 이다. 노린 multi-session(0.11)과 multi-hop(0.12)은 그대로라 기본은 꺼 둔다(`memory_net_value --coverage`, results.json `memory_net_value.coverage`).

**대상 타임라인**(`memory.timeline_recall`, 기본 꺼짐, 커버리지 재검색이 켜져 있어야 돈다): 질문이 세기, 순서, 기간, n번째를 물으면(`is_aggregate`, 정규식) 커버리지가 뽑은 대상마다 그 이름이 글자로 나오는 일화만 모아 날짜, 세션 안 턴 번호, 조각 번호 순으로 늘어놓은 `[대상 타임라인] 이름: 언급 n건` 블록을 회상 블록 뒤에 붙인다. 개수는 코드가 세고, 대상 하나에 40줄(줄마다 이름 둘레 100자)을 넘으면 최근 것만 남기고 그렇다고 적는다. 벡터로만 비슷한 일화는 넣지 않는다(세는 질문에 다른 대상이 섞이지 않게). 별칭("엄마"와 "어머니")은 합치지 않는다(`# ponytail`). 저장소에서 읽은 시각은 로컬(naive)로 되돌린다. 예전에는 UTC 로 돌려 회상 블록의 날짜가 9시간 앞당겨졌다. 커버리지 재검색 대비 이김과 짐은 LongMemEval-s 1 대 0, PersonaMem-v2 1 대 0, MINT-Eval 1 대 1 이고 temporal-reasoning(0.0), counting(0.0), ordering(0.0)은 그대로라 기본은 꺼 둔다. 타임라인이 붙은 문항은 LongMemEval-s 60 중 19, MINT-Eval 40 중 12 다. MINT-Eval 순서 문항은 뽑은 대상 이름이 일화 글과 맞지 않아 블록이 비었고, LongMemEval-s 시간 문항은 블록이 붙어도 답 모델이 날짜 계산을 못 해 "모름" 으로 답했다(`memory_net_value --timeline`, results.json `memory_net_value.timeline`).

**정정 되먹이기**: 턴이 끝날 때 사용자 발화가 정정 표현("아니", "그게 아니라", "틀렸어", "이제는", "actually", "no," 등, `is_correction`)이고 이번 턴에 의미 사실이 회상돼 있었으면, 그 턴만 바로 사실 추출에 넣는다. 추출기에 `[정정 전 사실]` 을 함께 보여 같은 주제 이름을 쓰게 하고, `remember` 의 같은 주제 대체로 옛 사실을 `superseded_by` 로 잇는다. 뽑은 턴은 추출 완료로 표시해 공고화가 다시 뽑지 않는다. 예전에는 조용한 틱의 공고화까지 틀린 사실이 계속 회상됐다. auto-ontology 의 "certified corrections fold back" 을 옮겼다.

**구현 파일**

| 파일 | 층 | 역할 |
|---|---|---|
| `src/ash_industry/memory/memory_service.py` | memory | observe, recall, recent, remember, 공고화 |
| `src/ash_industry/memory/memory_types.py` | memory | 기억 종류와 항목 모델 |
| `src/ash_industry/memory/scope.py` | memory | 메모리 범위와 읽기 상속 규칙 |
| `src/ash_industry/memory/access.py` | memory | 에이전트별 층 읽기 정책 |
| `src/ash_industry/memory/consolidation/compaction.py` | memory | 메시지 묶음 요약기(`/compact`) |
| `src/ash_industry/memory/consolidation/idle.py` | memory | 유휴 공고화 |
| `src/ash_industry/memory/consolidation/semantic_extract.py` | memory | 일화에서 사실 추출 |
| `src/ash_industry/memory/long_term/episodic.py` | memory | 일화 기억 정책 |
| `src/ash_industry/memory/long_term/semantic.py` | memory | 의미 기억 대체와 간섭 후보 |
| `src/ash_industry/memory/long_term/correction_detect.py` | memory | 사용자 발화가 사실을 바로잡는 말인지 가리기(순수 함수) |
| `src/ash_industry/memory/long_term/fact_source.py` | memory | 추출 사실의 출처 턴 고르기와 출처 발췌(발췌는 평가 비교군만, 순수 함수) |
| `src/ash_industry/memory/long_term/procedural.py` | memory | 스킬 파일을 읽기 전용 절차 기억으로 노출 |
| `src/ash_industry/memory/retrieval/cues.py` | memory | 단서 겹침 점수 |
| `src/ash_industry/memory/retrieval/coverage_extract.py` | memory | 질문에서 기억으로 찾을 대상을 뽑는 LLM 경계 |
| `src/ash_industry/memory/retrieval/coverage_grade.py` | memory | 대상이 회상 항목에 덮였는지 가리기, 같은 개수 안에 섞기(순수 함수) |
| `src/ash_industry/memory/retrieval/timeline_build.py` | memory | 집계형 질문 가리기, 대상별 일화 시간순 블록(순수 함수) |
| `src/ash_industry/memory/retrieval/scoring.py` | memory | recency, importance, relevance 합성 점수 |
| `src/ash_industry/memory/stores/store_protocol.py` | memory | 장기 기억 저장소 기본 클래스 |
| `src/ash_industry/memory/stores/in_memory.py` | memory | 프로세스 메모리 저장소 |
| `src/ash_industry/memory/stores/postgres.py` | memory | PostgreSQL 장기 기억 저장소 |
| `src/ash_industry/memory/working/state.py` | memory | 작업 기억 상태와 저장소 기본 클래스 |
| `src/ash_industry/memory/working/window.py` | memory | 최근 턴 창(턴 수와 나이로 자름, tool 짝 보존) |
| `src/ash_industry/memory/working/deixis.py` | memory | 상대 지칭 해석 |
| `src/ash_industry/memory/working/in_memory.py` | memory | 작업 기억 메모리 저장소 |
| `src/ash_industry/memory/working/postgres.py` | memory | 작업 기억 PostgreSQL 저장소 |
| `src/ash_industry/core/tools/episodes.py` | core | `recall_episodes` 도구 |
| `src/ash_industry/core/slash/remember_cmd.py` | core | `/remember` 핸들러 |

**테스트**

| 종류 | 파일 |
|---|---|
| 단위 | `tests/unit/test_memory_access.py` |
| 단위 | `tests/unit/test_memory_compaction.py` |
| 단위 | `tests/unit/test_memory_correction_detect.py` |
| 단위 | `tests/unit/test_memory_coverage_extract.py` |
| 단위 | `tests/unit/test_memory_coverage_grade.py` |
| 단위 | `tests/unit/test_memory_timeline_build.py` |
| 단위 | `tests/unit/test_memory_cues.py` |
| 단위 | `tests/unit/test_memory_deixis.py` |
| 단위 | `tests/unit/test_memory_embeddings.py` |
| 단위 | `tests/unit/test_memory_episodes.py` |
| 단위 | `tests/unit/test_memory_episodic.py` |
| 단위 | `tests/unit/test_memory_fact_source.py` |
| 단위 | `tests/unit/test_memory_idle.py` |
| 단위 | `tests/unit/test_memory_memory_service.py` |
| 단위 | `tests/unit/test_memory_memory_types.py` |
| 단위 | `tests/unit/test_memory_ops_cmd.py` |
| 단위 | `tests/unit/test_memory_procedural.py` |
| 단위 | `tests/unit/test_memory_remember_cmd.py` |
| 단위 | `tests/unit/test_memory_scope.py` |
| 단위 | `tests/unit/test_memory_scoring.py` |
| 단위 | `tests/unit/test_memory_semantic.py` |
| 단위 | `tests/unit/test_memory_semantic_extract.py` |
| 단위 | `tests/unit/test_memory_state.py` |
| 단위 | `tests/unit/test_memory_store_protocol.py` |
| 단위 | `tests/unit/test_memory_window.py` |
| 통합 | `tests/integ/test_memory.py`(커버리지 재검색이 1차 회상에서 빠진 대상의 기억을 되찾음, 타임라인이 대상의 모든 언급을 시간순으로 늘어놓음, 정정한 턴이 공고화 전에 옛 사실을 대체함 포함) |

**제약과 미구현**: 항목 낱말이 답에 절반 넘게 나와야 쓰였다고 본다. 이력이 줄어 턴 번호를 다시 세면 옛 턴 일화를 덮는다. 조사 목록 휴리스틱으로 명사를 자른다. main 에이전트는 정의 파일이 없어 기본 정책(자기 것만)이다. 긴 답은 조각 2개(약 3,000자)까지만 남긴다. 출처 회상을 켜면 회상 블록이 최근성과 중요도를 쓰지 않는다(모두 `# ponytail`). 출처 회상은 `MemoryService(source_recall=...)` 로 끄고 켜며 기본은 켜짐이다(LongMemEval-s 실서비스 블록 조건 정답률 0.28 → 0.50). Memory Tax(He et al. 2026)의 recursive memory 와 미래 수요 예측은 범위 밖이다.

---

### memory_eval: 메모리 평가

**설명**: jsonl 사례를 in-memory 대상에 넣고 질의해 기능별 지표를 내고, LongMemEval, LoCoMo, PersonaMem-v2, MINT-Eval 원본으로 비교군(rag, raw, turns, turns+src, turns+excerpt)별 증거 재현율, 정답률, RAG 대비 benefit 과 tax 를 잰다.

**입력과 결과**

| 입력 | 결과 |
|---|---|
| `uv run python -m ash_industry.memory.eval [--suite S] [--summarizer extractive\|llm] [--judge llm\|contains] [--json] [-v]` | 스위트별 지표 |
| `--benchmark longmemeval\|locomo\|personamem\|minteval --path <json> [--limit] [--seed] [--k] [--budget 글자] [--mode rag\|raw\|turns\|turns+src\|turns+excerpt] [--extract llm] [--embedder fake\|config] [--judge llm\|contains]` | 외부 벤치마크 재현율과 정답 판정 |
| `uv run python -m scripts.experiments.memory_net_value [--only ...] [--dry-run]` | 세 벤치마크 층화 표본 × 네 비교군, RAG 대비 benefit, tax, net, 턴 일화 구성 손실(MT-3)을 `results.json` 의 `memory_net_value` 에 쓴다. 임베딩, 사실 추출, 판정은 `~/.ash/benchmarks/cache/` 에 캐시해 다시 돌리면 부르지 않는다 |

**처리 흐름**: `__main__` 에서 `eval_schema` 로 사례 로드, `runner` 가 사례마다 저장소를 비우고 `target` 에 재생, `metrics` 집계 순. 벤치마크는 `adapters` 에서 `benchmark` 로(대화 묶음마다 새 메모리 또는 `rag_baseline` 색인, 노출 글자 예산으로 자름), 선택적으로 `judge`, `probe`, 비교는 `net_value`, 구성 손실은 `turn_loss`, 캐시는 `eval_cache` 순.

**구현 파일**

| 파일 | 층 | 역할 |
|---|---|---|
| `src/ash_industry/memory/eval/__main__.py` | memory | 평가 CLI |
| `src/ash_industry/memory/eval/eval_schema.py` | memory | 사례 형식과 로더 |
| `src/ash_industry/memory/eval/runner.py` | memory | 사례 재생과 판정 |
| `src/ash_industry/memory/eval/target.py` | memory | 평가 대상 어댑터 |
| `src/ash_industry/memory/eval/metrics.py` | memory | 판정과 스위트별 집계 |
| `src/ash_industry/memory/eval/faithfulness.py` | memory | 요약 뒤 사실 보존율 |
| `src/ash_industry/memory/eval/fake_embedder.py` | memory | 결정론 임베더 |
| `src/ash_industry/memory/eval/benchmark.py` | memory | 외부 벤치마크 실행, 비교군, 층화 표본, 노출 예산 |
| `src/ash_industry/memory/eval/rag_baseline.py` | memory | naive RAG 비교군(원문 턴 조각, 코사인 top-k) |
| `src/ash_industry/memory/eval/net_value.py` | memory | RAG 대비 benefit, tax, net |
| `src/ash_industry/memory/eval/turn_loss.py` | memory | 정답 턴의 턴 일화 구성 손실 |
| `src/ash_industry/memory/eval/eval_cache.py` | memory | 임베딩(sqlite), 사실 추출, 판정(jsonl) 캐시 |
| `src/ash_industry/memory/eval/judge.py` | memory | 회상 증거로 답 생성과 정답 판정(객관식은 기호 일치). 답하는 모델과 판정 모델을 따로 줄 수 있다 |
| `src/ash_industry/memory/eval/probe.py` | memory | LLM 호출 횟수 계측 |
| `src/ash_industry/memory/eval/adapters/locomo.py` | memory | LoCoMo 어댑터 |
| `src/ash_industry/memory/eval/adapters/longmemeval.py` | memory | LongMemEval 어댑터 |
| `src/ash_industry/memory/eval/adapters/personamem.py` | memory | PersonaMem-v2 text 어댑터(128k 이력, 객관식) |
| `src/ash_industry/memory/eval/adapters/minteval.py` | memory | MINT-Eval 어댑터(jsonl 로 바꾼 네 영역) |
| `scripts/experiments/memory_net_value.py` | scripts | Memory Tax 벤치마크 셋 비교 실험 |
| `src/ash_industry/memory/eval/datasets/` | memory | 기능별 평가 사례 jsonl |

**테스트**

| 종류 | 파일 |
|---|---|
| 단위 | `tests/unit/test_memory_eval_benchmark.py` |
| 단위 | `tests/unit/test_memory_eval_eval_cache.py` |
| 단위 | `tests/unit/test_memory_eval_faithfulness.py` |
| 단위 | `tests/unit/test_memory_eval_judge.py` |
| 단위 | `tests/unit/test_memory_eval_locomo.py` |
| 단위 | `tests/unit/test_memory_eval_longmemeval.py` |
| 단위 | `tests/unit/test_memory_eval_metrics.py` |
| 단위 | `tests/unit/test_memory_eval_minteval.py` |
| 단위 | `tests/unit/test_memory_eval_net_value.py` |
| 단위 | `tests/unit/test_memory_eval_personamem.py` |
| 단위 | `tests/unit/test_memory_eval_probe.py` |
| 단위 | `tests/unit/test_memory_eval_runner.py` |
| 단위 | `tests/unit/test_memory_eval_rag_baseline.py` |
| 단위 | `tests/unit/test_memory_eval_target.py` |
| 단위 | `tests/unit/test_memory_eval_turn_loss.py` |
| 통합 | `tests/integ/test_memory_eval.py` |

**제약과 미구현**: 벤치마크 원본 데이터는 레포 밖에 둔다. RAG 비교군은 논문의 BM25 와 재순위기를 빼고 임베딩 코사인만 본다. MINT-Eval 은 정답 맥락 라벨이 없어 증거 재현율을 내지 않는다. 추출기 캐시는 API 오류로 생긴 빈 결과도 캐시한다(`# ponytail`).

---

### migration: jarvis-agent 에서 옮기기

**설명**: 이름을 바꾸기 전(jarvis-agent)에 쌓인 상태를 새 이름으로 옮기는 스크립트. 기본은 계획만 출력하고 `--apply` 를 줘야 바꾼다. 단계마다 이미 끝났는지 보고 넘어가서 어디서 멈춰도 다시 돌리면 된다.

**입력과 결과**

| 단계 | 결과 | 두 번째 실행 |
|---|---|---|
| `home` | `~/.ash` 가 없을 때만 `~/.jarvis` 를 `~/.ash.migrating` 에 복사한 뒤 이름을 바꾼다 | 할 일 없음 |
| `env` | 새 저장소에 `.env` 가 없을 때만 옛 `.env` 의 `JARVIS_` 키, DSN, 경로, 서비스 주소를 바꿔 쓴다(권한 600, 내용은 출력하지 않음) | 할 일 없음 |
| `volumes` | 옛 스택이 떠 있으면 멈춘다. `jarvis_agent_{jarvis_data,postgres_data,mcp_data}` 를 새 프로젝트의 `{ash_data,postgres_data,mcp_data}` 로 복사한다. 새 볼륨에 이미 데이터가 있으면 건너뛴다 | 할 일 없음 |
| `postgres` | 새 스택의 postgres 만 띄운 상태에서 DB `jarvis` 를 `ash` 로, 역할 `jarvis` 를 `ash`(암호 `ash`)로, public 스키마의 `jarvis` 가 든 테이블, 인덱스, 시퀀스 이름을 바꾼다. 임시 역할 `ash_migrator` 는 지운다 | 할 일 없음 |

**구현 파일**

| 파일 | 층 | 역할 |
|---|---|---|
| `scripts/migrate_from_jarvis.py` | scripts | 순수 계산(`rename_env_text`, `relation_renames`, `volume_plan`), 파일 복사(`copy_home`, `copy_env`), docker 와 psql 호출(`DockerMigration`) |

**테스트**

| 종류 | 파일 |
|---|---|
| 단위 | `tests/unit/test_migration_migrate_from_jarvis.py` |

**보안**: 명령은 리스트 인자로만 부른다. DB 에서 읽은 관계 이름은 `^[a-z_][a-z0-9_]{0,62}$` 일 때만 SQL 에 넣는다. `.env` 내용은 출력하지 않는다.

**제약과 미구현**: 데스크톱 앱의 설정 파일은 앱이 처음 뜰 때 스스로 옮긴다(`desktop`). HUD 의 접근 키 저장 이름이 바뀌어 처음 한 번 다시 넣는다. 녹음 문구 이름 `persona_jarvis` 는 `phrases.json` 에서 `persona_main` 으로 바꾼다.

---

### multi_agent: 멀티 에이전트 오케스트레이션

**설명**: `agents.agents_dir`(`~/.ash/agents/*.yaml`, Docker 는 프로필 디렉터리의 `team/agents/`)의 서브 에이전트를 노드로 감싸 supervisor, hierarchical, market, blackboard 패턴(과 그 파이프라인 합성)으로 일을 나눠 맡기고, `parent` 를 적은 정의는 최상위 에이전트의 기능 담당이 된다.

**입력과 결과**

| 입력 | 결과 |
|---|---|
| `/orchestrate <pattern> [--agents a,b] [--promote] <작업>` | 지정한 패턴으로 서브 에이전트를 조율한 결과 |
| `orchestrate` 도구 | 메인 LLM 이 고른 패턴과 참여 에이전트로 실행 |
| 서브 에이전트 위임 도구(`AgentNodeTool`) | LLM 이 tool_call 로 서브 에이전트 하나에 위임 |
| 정의의 `parent: <최상위 id>` | 그 에이전트의 기능 담당. 세션은 부모 세션마다 하나(`agent_<이름>__<부모 세션>`, `memory.stm: per_parent_session`)로 파생되고, 지시문 앞에 부모의 `persona`(어투)가 붙고, 모델은 부모의 `provider`, `model`(정의의 `model_override` 가 있으면 그것), 기억은 부모의 에이전트 id 로 읽고 쓰며(부모가 저장한 사실이 그대로 보인다), 도구는 메인 풀에 더해 최상위 에이전트 전용 풀(확장이 등록한 도구)에서도 고른다. 부모 정의는 `tools` 에 `agent_<이름>` 을 적어 맡긴다. |

**처리 흐름**: `orchestrate_cmd` 또는 `orchestrate_tool` 에서 `OrchestrationService` 로, `multi_agent_loader` 정의, `factory` 가 부모 범위를 물려받은 자식 세션 노드 생성, 토폴로지 조립, 오케스트레이터 dispatch, `blackboard` 와 작업 공유 메모리로 결과 전달 순.

**구현 파일**

| 파일 | 층 | 역할 |
|---|---|---|
| `src/ash_industry/core/multi_agent/multi_agent_service.py` | core | 패턴 이름과 작업으로 조립해 실행하는 공통 뒷단 |
| `src/ash_industry/core/multi_agent/multi_agent_loader.py` | core | 에이전트 YAML 을 `AgentDefinition` 으로 |
| `src/ash_industry/core/multi_agent/multi_agent_protocol.py` | core | 노드, 토폴로지, 오케스트레이터 기반 클래스 |
| `src/ash_industry/core/multi_agent/factory.py` | core | 격리된 자식 세션 노드 생성과 `memory.stm` 수명 관리. `memory.ltm: false` 면 장기 기억을 읽지도 쓰지도 않는다. `parent` 필드 |
| `src/ash_industry/app/subagent_builder.py` | app | 정의를 세션으로. `parent` 가 있으면 어투, 모델, 기억 범위(`memory_agent`), 도구 풀 상속 |
| `src/ash_industry/core/multi_agent/node.py` | core | `AgentNode`, `LazyAgentNode` |
| `src/ash_industry/core/multi_agent/task.py` | core | 같은 입력이면 같은 `task_id` 인 `AgentTask`, `AgentResult` |
| `src/ash_industry/core/multi_agent/tool.py` | core | `AgentNodeTool` |
| `src/ash_industry/core/multi_agent/orchestrate_tool.py` | core | `orchestrate` 도구 |
| `src/ash_industry/core/multi_agent/blackboard.py` | core | 공유 블랙보드 저장소 |
| `src/ash_industry/core/multi_agent/orchestrators/orchestrator_base.py` | core | 오케스트레이터 공통 동작 |
| `src/ash_industry/core/multi_agent/orchestrators/supervisor.py` | core | supervisor 오케스트레이터 |
| `src/ash_industry/core/multi_agent/orchestrators/hierarchical.py` | core | hierarchical 오케스트레이터 |
| `src/ash_industry/core/multi_agent/orchestrators/market.py` | core | market 오케스트레이터 |
| `src/ash_industry/core/multi_agent/orchestrators/blackboard.py` | core | blackboard 오케스트레이터 |
| `src/ash_industry/core/multi_agent/orchestrators/pipeline.py` | core | 오케스트레이터 순차 합성 |
| `src/ash_industry/core/multi_agent/topologies/topology_base.py` | core | 토폴로지 공통 노드 관리 |
| `src/ash_industry/core/multi_agent/topologies/supervisor.py` | core | 1:N flat 토폴로지 |
| `src/ash_industry/core/multi_agent/topologies/hierarchical.py` | core | 레벨 트리 토폴로지 |
| `src/ash_industry/core/multi_agent/topologies/p2p.py` | core | full-mesh P2P 토폴로지 |
| `src/ash_industry/core/multi_agent/topologies/blackboard.py` | core | 블랙보드 토폴로지 |
| `src/ash_industry/core/slash/orchestrate_cmd.py` | core | `/orchestrate` 핸들러 |
| `src/ash_industry/app/subagent_builder.py` | app | 서브 에이전트 세션과 위임 도구 조립 |

**테스트**

| 종류 | 파일 |
|---|---|
| 단위 | `tests/unit/test_multi_agent_blackboard.py` |
| 단위 | `tests/unit/test_multi_agent_factory.py` |
| 단위 | `tests/unit/test_multi_agent_market.py` |
| 단위 | `tests/unit/test_multi_agent_multi_agent_loader.py` |
| 단위 | `tests/unit/test_multi_agent_multi_agent_protocol.py` |
| 단위 | `tests/unit/test_multi_agent_multi_agent_service.py` |
| 단위 | `tests/unit/test_multi_agent_node.py` |
| 단위 | `tests/unit/test_multi_agent_orchestrate_cmd.py` |
| 단위 | `tests/unit/test_multi_agent_orchestrator_base.py` |
| 단위 | `tests/unit/test_multi_agent_orchestrators_blackboard.py` |
| 단위 | `tests/unit/test_multi_agent_orchestrators_hierarchical.py` |
| 단위 | `tests/unit/test_multi_agent_p2p.py` |
| 단위 | `tests/unit/test_multi_agent_pipeline.py` |
| 단위 | `tests/unit/test_multi_agent_subagent_builder.py` |
| 단위 | `tests/unit/test_multi_agent_task.py` |
| 단위 | `tests/unit/test_multi_agent_tool.py` |
| 단위 | `tests/unit/test_multi_agent_topologies_hierarchical.py` |
| 단위 | `tests/unit/test_multi_agent_topology_base.py` |
| 통합 | `tests/integ/test_multi_agent.py` |

**제약과 미구현**: 서브 에이전트가 하나도 없으면 `/orchestrate` 와 `orchestrate` 도구가 등록되지 않는다.

---

### notify: 외부 알림

**설명**: 먼저 건넨 말, 스케줄 결과, 화면이 소리 내어 읽은 말을 열린 화면 밖(슬랙, 디스코드 글 또는 음성 채널, iOS 홈 화면 웹앱 Web Push)으로도 보낸다.

**입력과 결과**

| 입력 | 결과 |
|---|---|
| `proactive_message`, `reminder` 이벤트 | 설정된 채널마다 한 번 전송. 채널, 종류, id, 에이전트, 글, 10분 시각 버킷의 해시가 전송 키 |
| ws `voice_tts_request{source}`, `voice_spoken{phrase}` | 읽은 글을 `spoken` 으로 전송. 같은 세션의 같은 글은 10초 안에 한 번 |
| 전송 실패(네트워크 오류, 타임아웃, 5xx) | 0.5초, 1초 뒤 두 번 더 보낸다(`ASH_NOTIFY__RETRIES`). 그래도 실패면 로그 한 줄. 4xx 는 바로 로그 |
| 전송 성공 | 키를 `~/.ash/notify_sent.jsonl` 에 바로 적는다. 같은 키는 다시 보내지 않는다 |
| `GET /api/push/vapid` | VAPID 공개키 |
| `PUT /api/push/subscriptions`, `DELETE /api/push/subscriptions` | 구독 등록(endpoint 로 upsert), 해제 |

**처리 흐름**: `events` 에서 보낼 것만 골라 payload 로, `dedupe` 로 잠깐 사이 중복 제거, `slack`, `discord` 또는 `discord_voice`, `webpush` 로 fan out 하는 순. 채널마다 `delivery` 가 키를 만들어 `sent_store` 에 있으면 건너뛰고, 없으면 보내고 성공 직후 적는다. Web Push 는 구독마다 키를 따로 둔다.

**구현 파일**

| 파일 | 층 | 역할 |
|---|---|---|
| `src/ash_industry/core/notify/events.py` | core | 밖으로 보낼 이벤트 고르기와 payload 변환 |
| `src/ash_industry/core/notify/dedupe.py` | core | 짧은 시간 안 같은 말 한 번만 |
| `src/ash_industry/core/notify/delivery.py` | core | 전송 키(순수 함수), 같은 키 한 번만, 실패 backoff 재시도 |
| `src/ash_industry/core/notify/sent_store.py` | core | 보낸 키 jsonl 기록(상한 5000, TTL 7일, 두 배에 닿으면 압축) |
| `src/ash_industry/core/notify/webhook.py` | core | webhook 채널 공통 payload 해석과 POST |
| `src/ash_industry/core/notify/slack.py` | core | 슬랙 incoming webhook |
| `src/ash_industry/core/notify/discord.py` | core | 디스코드 webhook |
| `src/ash_industry/core/notify/discord_voice.py` | core | 디스코드 음성 채널에서 읽기, 없으면 글 |
| `src/ash_industry/core/notify/webpush.py` | core | Web Push 구독 저장과 전송 |
| `src/ash_industry/ui/web/router/push_router.py` | ui | Web Push REST |

**테스트**

| 종류 | 파일 |
|---|---|
| 단위 | `tests/unit/test_notify_dedupe.py` |
| 단위 | `tests/unit/test_notify_delivery.py` |
| 단위 | `tests/unit/test_notify_discord.py` |
| 단위 | `tests/unit/test_notify_discord_voice.py` |
| 단위 | `tests/unit/test_notify_events.py` |
| 단위 | `tests/unit/test_notify_notify.py` |
| 단위 | `tests/unit/test_notify_sent_store.py` |
| 단위 | `tests/unit/test_notify_slack.py` |
| 단위 | `tests/unit/test_notify_webpush.py` |
| 통합 | `tests/integ/test_notify.py` |

**멱등**: 같은 payload 를 같은 채널에 두 번 보내도 한 번만 간다(키는 내용의 해시, 보낸 키는 jsonl). 재시도 중 프로세스가 죽어도 성공한 전송은 그 직후 적혀 다시 가지 않고, 못 보낸 전송은 적히지 않아 다음 호출이 다시 보낸다. 시계와 sleep 은 `Delivery` 생성자로 주입한다.

**제약과 미구현**: 전송 키에 10분 버킷이 들어 있어, id 없는 알림(`spoken`)이 버킷 경계를 넘어 다시 오면 두 번 간다. 디스코드 429 는 4xx 라 다시 보내지 않는다(`Retry-After` 미지원). 디스코드 음성 채널 읽기(`discord_voice`)에는 키와 재시도가 없고 실패하면 글로 넘긴다.

---

### openloop: 약속 추적(AGENDA)

**설명**: 매 요청 턴에 따로 도는 AGENDA 판단이 새 약속과 끝난 약속을 가려 저장하고, 열린 약속을 사고에 주입하며, Web HUD AGENDA 카드에 스케줄과 함께 보인다.

**입력과 결과**

| 입력 | 결과 |
|---|---|
| 매 요청 턴 | 새 약속 저장(같은 약속은 병합, 기한 갱신), 끝났거나 취소된 약속 닫기, ws `agenda_changed` |
| `GET /api/agenda` | 스케줄, 열린 약속(20개까지), 최근 닫힌 약속 |
| `POST /api/openloops/{loop_id}` `{status}` | done, dismissed 로 닫기, open 으로 되살리기. 기한이 지난 약속은 되살리지 않음(409) |
| `/openloop`, `/openloop done <id>`, `/openloop dismiss <id>` | 나열, 완료, 무시 |

**처리 흐름**: `AgentSession._spawn_loop_judge` 에서 `judge` 로, `openloop_types` 의 같은 약속 판정과 병합, `openloop_store` (jsonl 또는 Postgres) 저장, 기한 지난 항목 만료, `agenda_router` 조회 순. 임베딩 판정에 쓴 벡터는 약속 레코드(`embedding`, `embedding_model`)에 함께 저장하고(jsonl 은 레코드 줄에, Postgres 는 `embedding DOUBLE PRECISION[]` 열에) 모델 이름이 같을 때만 다시 쓴다. 벡터가 없거나 다른 모델의 것인 약속은 후보가 될 때 한 번 임베딩해 채운다.

**구현 파일**

| 파일 | 층 | 역할 |
|---|---|---|
| `src/ash_industry/agent_layer/openloop/judge.py` | agent_layer | AGENDA 판단 LLM 호출 |
| `src/ash_industry/agent_layer/openloop/openloop_types.py` | agent_layer | 모델, 기한 해석, 같은 약속 판정, 병합, 만료 규칙 |
| `src/ash_industry/agent_layer/openloop/openloop_store.py` | agent_layer | 저장소 기본 클래스와 기한 지난 항목 닫기 |
| `src/ash_industry/agent_layer/openloop/jsonl_store.py` | agent_layer | JSONL append 저장소 |
| `src/ash_industry/agent_layer/openloop/postgres_store.py` | agent_layer | PostgreSQL 저장소 |
| `src/ash_industry/core/slash/openloop_cmd.py` | core | `/openloop` 핸들러 |

**테스트**

| 종류 | 파일 |
|---|---|
| 단위 | `tests/unit/test_openloop_jsonl_store.py` |
| 단위 | `tests/unit/test_openloop_judge.py` |
| 단위 | `tests/unit/test_openloop_openloop_cmd.py` |
| 단위 | `tests/unit/test_openloop_openloop_store.py` |
| 단위 | `tests/unit/test_openloop_openloop_types.py` |
| 단위 | `tests/unit/test_openloop_postgres_store.py` |
| 통합 | `tests/integ/test_openloop.py` |

**제약과 미구현**: 임베딩 모델을 바꾸면 저장된 벡터는 버리고 후보가 될 때 다시 임베딩한다. 조회는 전부 읽어 고른다(`# ponytail`). 뜻이 멀게 바꾼 약속은 따로 쌓이고, 입력과 글자가 거의 겹치지 않는 새 약속은 저장하지 않는다. 약속 수정은 없다(`docs/view_spec.md`).

---

### plugins: 플러그인 훅

**설명**: 디렉터리의 `.py` 파일에서 플러그인 클래스를 찾아 `before_agent_start`, `before_tool_call`, `after_tool_call`, `on_message_end`, `transform_context` 훅을 오류 격리와 체인 적용으로 실행한다.

**입력과 결과**

| 입력 | 결과 |
|---|---|
| `~/.ash/plugins/*.py` | 등록된 플러그인 훅이 턴과 도구 호출 앞뒤에서 돈다 |
| `plugin.watch_files=true` 일 때 도구, 스킬, 플러그인 파일 변경 | 바뀐 디렉터리만 다시 읽는다. 같은 이름은 덮어써 하나로 남는다 |

**처리 흐름**: `plugins_loader` 에서 `PluginRunner` 등록으로, `AgentSession` 이 훅 시점마다 `runner.emit_*` 순. 파일 감시는 `InfraBuilder.build_extension_watcher` 가 만들고 Web 기동(`web_lifecycle`)이 켠다.

**구현 파일**

| 파일 | 층 | 역할 |
|---|---|---|
| `src/ash_industry/core/plugins/plugins_protocol.py` | core | `AshPlugin` 기반 클래스와 `HookResult` |
| `src/ash_industry/core/plugins/plugins_loader.py` | core | 디렉터리에서 플러그인 클래스 찾기 |
| `src/ash_industry/core/plugins/runner.py` | core | 훅 실행(오류 격리, 체인) |
| `src/ash_industry/app/extension_watcher.py` | app | 확장 디렉터리 감시와 바뀐 디렉터리만 다시 읽기 |

**테스트**

| 종류 | 파일 |
|---|---|
| 단위 | `tests/unit/test_plugins_extension_watcher.py` |
| 단위 | `tests/unit/test_plugins_plugins_loader.py` |
| 단위 | `tests/unit/test_plugins_plugins_protocol.py` |
| 단위 | `tests/unit/test_plugins_runner.py` |
| 통합 | `tests/integ/test_tools.py`(파일 감시로 도구 싣기). 플러그인 파일을 두고 앱을 띄우는 시나리오는 아직 없다 |

**제약과 미구현**: 파일을 지운 도구와 스킬은 재시작 전까지 남고, 기동 뒤에 만든 디렉터리는 감시하지 않는다(`# ponytail`).

---

### policy: 보안 파이프라인과 접근 키

**설명**: 모든 입력을 검증, 인증, 정책, 샌드박스 4단계로 통과시키고, 사용자별 rate limit 을 건다. Web HUD 는 `ASH_SECURITY__API_KEYS` 가 있으면 `/api/*` 와 `/ws` 에 키를 요구한다.

**입력과 결과**

| 입력 | 결과 |
|---|---|
| 사용자 입력 | 길이, 금지 패턴 검증과 정규화, 인증 컨텍스트, 정책 결과, 위험 명령 차단 |
| `/api/*` 요청 | 키가 없거나 틀리면 401 |
| `/ws?token=` | 키가 틀리면 close `4401` |

**처리 흐름**: `AgentSession._prompt` 에서 `SecurityPipeline.run` 으로, `validator`, `authenticator`, `policy`, `sandbox` 순. Web 은 `server` 미들웨어와 `ws_router` 에서 `web_auth` 로 사용자를 찾는다.

**구현 파일**

| 파일 | 층 | 역할 |
|---|---|---|
| `src/ash_industry/core/policy/pipeline.py` | core | 4단계 파이프라인 타입, 예외, 단계 기반 클래스 |
| `src/ash_industry/core/policy/validator.py` | core | 입력 검증기 |
| `src/ash_industry/core/policy/authenticator.py` | core | 익명 통과, API key 인증기 |
| `src/ash_industry/core/policy/policy.py` | core | 전부 허용, 역할 기반 정책 엔진 |
| `src/ash_industry/core/policy/sandbox.py` | core | 위험 명령 차단과 승인 흐름 |
| `src/ash_industry/ui/web/web_auth.py` | ui | Bearer 헤더와 `token` 쿼리로 사용자 찾기 |

**테스트**

| 종류 | 파일 |
|---|---|
| 단위 | `tests/unit/test_policy_app_services.py` |
| 단위 | `tests/unit/test_policy_authenticator.py` |
| 단위 | `tests/unit/test_policy_pipeline.py` |
| 단위 | `tests/unit/test_policy_policy.py` |
| 단위 | `tests/unit/test_policy_sandbox.py` |
| 단위 | `tests/unit/test_policy_validator.py` |
| 단위 | `tests/unit/test_policy_web_auth.py` |
| 통합 | `tests/integ/test_policy.py` |

**제약과 미구현**: 정적 셸(`/`, js, css)은 키 없이 항상 열려 있다(`docs/api_spec.md`). 위험 명령은 `command` 인자만 보고 파일 내용은 보지 않는다.

---

### proactive: 먼저 말 걸기

**설명**: 요청 없이 트리거(주기, 유휴, 외부 이벤트)가 깨울 때 활성 세션을 성찰시켜 말할지 정하고, 오래 걸리는 요청의 선응답과 뒤로 넘기기는 `turn_detach` 가 맡는다. 먼저 건넨 말에 대한 사용자의 다음 말을 반응으로 읽어 발화 임계치를 조정한다.

**입력과 결과**

| 입력 | 결과 |
|---|---|
| 트리거 깨움 | ws `proactive_message{kind:"proactive"}`, 세션 기록에 assistant 메시지 |
| 오래 걸리는 요청 | `turn_detach` 참고. 끝난 답은 `proactive_message{kind:"answer"}` |
| 먼저 건넨 말 뒤의 첫 `user_message` | accept, dismiss, 약한 무시로 학습 |
| ws `proactive_feedback{id, accepted}` | 수락, 무시 학습(연결당 같은 `id` 한 번) |

**처리 흐름**: `daemon` 이 `triggers` 를 기다려 `AgentSession.reflect` 로, `situation_facts` 가 약속과 외부 이벤트마다 남은 시간과 처리 신호를 계산해 요청에 붙이고, 성찰 사고, `ProactivityCore` 의 `policy` 게이팅, `_emit_proactive`, `feedback` 학습 순. `_emit_proactive` 가 답하는 중이나 Focus 중이라 🔔 를 버리면 `policy.withdraw` 가 쿨다운과 응답 대기를 통과 전으로 되돌려, 버린 말은 무시로 세지 않는다. 요청 시점에는 `ProactivityCore.plan_request` 가 사고가 미리 본 계획만 알려 주고, 실행은 `TurnDetach` 가 한다.

**구현 파일**

| 파일 | 층 | 역할 |
|---|---|---|
| `src/ash_industry/core/proactive/daemon.py` | core | 백그라운드 성찰 루프 |
| `src/ash_industry/core/proactive/triggers.py` | core | 주기, 유휴, 외부, 합성 트리거 |
| `src/ash_industry/core/proactive/policy.py` | core | Dual-Channel 계획과 자율 발화 게이팅 |
| `src/ash_industry/core/proactive/proactive_core.py` | core | 정책, push 조율, 요청 계획(`plan_request`) |
| `src/ash_industry/core/proactive/proactive_types.py` | core | 발화 메시지, 응답 계획, 게이팅 판정 |
| `src/ash_industry/core/proactive/feedback.py` | core | 수락, 무시, 무응답 누적과 임계치 조정 |
| `src/ash_industry/core/proactive/situation_facts.py` | core | 약속과 이벤트 글에서 남은 시간, 처리 신호 계산(정규식, 순수 함수) |

**테스트**

| 종류 | 파일 |
|---|---|
| 단위 | `tests/unit/test_proactive_daemon.py` |
| 단위 | `tests/unit/test_proactive_feedback.py` |
| 단위 | `tests/unit/test_proactive_policy.py` |
| 단위 | `tests/unit/test_proactive_proactive_core.py` |
| 단위 | `tests/unit/test_proactive_situation_facts.py` |
| 단위 | `tests/unit/test_proactive_triggers.py` |
| 통합 | `tests/integ/test_proactive.py` |
| e2e | `scripts/e2e/hud_flow.py`(스크립트 프로바이더 `scripts/e2e/launch_hud.py`). 약속을 말하면 AGENDA 에 열리고, 2초 주기 성찰이 🔔 로 먼저 말하고, 다음 말 "아니오" 가 무시 피드백(`proactive_ack`)으로 남고, 그 뒤 성찰은 💭 만 남기고 🔔 를 되풀이하지 않는다. 승인 규칙은 `approvals/<agent>.yaml` 에 남는 것까지 본다 |

**제약과 미구현**: 🔔 가 되풀이인지 볼 때 마지막 답 하나만 본다(`# ponytail`). 같은 대상의 이벤트(초대와 수락)를 잇지 않고 줄마다 사실을 따로 계산한다. 시각은 "10:30", "오후 2시", "9시 반", 날짜는 "2026-01-02", "1월 3일", "오늘/내일" 만 읽고 영문 날짜는 모름으로 둔다. e2e 는 성찰 프레임을 스크립트로 고정하므로 사고 모델의 판단 품질은 재지 않는다(`ash_industry.core.proactive.eval` 이 잰다).

---

### proactive_eval: proactive 평가

**설명**: "이 상황에서 먼저 말해야 했나"를 jsonl 사례로 적어, 사례마다 새 정책과 고정 시계로 판정하고 지표로 요약한다. 사례에는 3단 라벨(`must`, `can`, `must_not`)을 달 수 있고, recall 은 must 에서, 오경보는 must_not 에서만, AUC 는 must 대 must_not 을 사고 프레임의 확신도로 잰다. 먼저 건넨 말은 블라인드 판정자가 누출 라벨(인사뿐, 답 재진술, 분석문 누출, 구체 알림, 불명)과 근거 구간으로 분류한다(평가 전용).

**입력과 결과**

| 입력 | 결과 |
|---|---|
| `uv run python -m ash_industry.core.proactive.eval [--suite S] [--engine none\|llm] [--json] [-v]` | 스위트별 판정 지표. `--engine none` 이면 정책만, `llm` 이면 사고 엔진까지 |
| `uv run python -m scripts.experiments.proactivebench_vertex --model M [--limit N] [--seed S]` | ProactiveBench 시험 세트 점수(스코어카드 Proactivity 꼭짓점). `run_vertex()` 가 `{score, n, raw, detail, errors}` 를 돌려주고 CLI 는 출력만 한다. 같은 (모델, 프롬프트)는 `~/.ash/benchmarks/proactivebench/cache/` 를 읽어 다시 부르지 않는다 |

**처리 흐름**: `__main__` 에서 `eval_schema` 로 사례 로드, `runner` 가 사례마다 정책을 새로 만들어 판정, 지표 집계 순.

**구현 파일**

| 파일 | 층 | 역할 |
|---|---|---|
| `src/ash_industry/core/proactive/eval/__main__.py` | core | 평가 CLI |
| `src/ash_industry/core/proactive/eval/eval_schema.py` | core | 사례 형식 |
| `src/ash_industry/core/proactive/eval/runner.py` | core | 판정과 지표 요약. `facts_now` 를 주면 상황에 계산한 사실을 붙인다 |
| `src/ash_industry/core/proactive/eval/label_metrics.py` | core | 3단 라벨의 recall, 오경보, AUC |
| `src/ash_industry/core/proactive/eval/utterance_judge.py` | core | 🔔 누출 판정자(pydantic 스키마, 근거 구간 확인, 라벨별 일치율) |
| `src/ash_industry/core/proactive/eval/datasets/` | core | `policy`, `situation`(개발용, 3단 라벨) 사례 jsonl |
| `scripts/experiments/datasets/situation_test.jsonl` | scripts | 시험용 사례(블라인드, 3단 라벨) |
| `scripts/experiments/datasets/situation_label_review.csv` | scripts | 3단 라벨 사람 검수 시트 |
| `scripts/experiments/datasets/utterance_label_review.csv` | scripts | 🔔 누출 라벨 사람 검수 시트(실제 발화 30건) |
| `scripts/experiments/datasets/utterance_label_synthetic.csv` | scripts | 사람이 라벨마다 쓴 발화 예시. 실제 발화는 7할이 concrete_notice 라 다른 라벨의 일치율을 여기서 따로 잰다 |
| `scripts/experiments/proactive_decision_first.py` | scripts | 성찰 순서, 앵커, 사실 계산 비교 실험 |
| `src/ash_industry/core/proactive/eval/proactivebench.py` | core | ProactiveBench 사건을 성찰 요청(외부 이벤트)과 3단 라벨로 바꾸고, (장면 종류, 라벨) 층화 표본과 꼭짓점 점수를 계산한다 |
| `scripts/experiments/proactivebench_vertex.py` | scripts | 시험 세트 받기(없을 때만), decision model 없는 기본 구성(`build("no_decision")`, 임계치 `ProactiveConfig().confidence_threshold`)으로 실행, 캐시, 채점 |

**테스트**

| 종류 | 파일 |
|---|---|
| 단위 | `tests/unit/test_proactive_eval_eval_schema.py` |
| 단위 | `tests/unit/test_proactive_eval_label_metrics.py` |
| 단위 | `tests/unit/test_proactive_eval_main.py` |
| 단위 | `tests/unit/test_proactive_eval_runner.py` |
| 단위 | `tests/unit/test_proactive_eval_utterance_judge.py` |
| 단위 | `tests/unit/test_scorecard_proactivebench.py` |
| 통합 | 없음. 평가 도구 자체라 CLI 를 끝까지 돌리는 테스트를 두지 않았다 |

**제약과 미구현**: 3단 라벨과 🔔 누출 라벨은 블라인드 에이전트와 LLM 판정자가 단 초안이다. 사람 검수 시트가 채워지기 전까지 판정자 수치는 "검증 전" 이다.

**ProactiveBench 시험 세트**: thunlp/ProactiveAgent(Apache-2.0) `dataset/test_data/` 의 12 개 흐름, 233 사건(코딩 6, 글쓰기 6. 일상은 학습 세트에만 있다)을 `~/.ash/benchmarks/proactivebench/test_data/` 에 받는다. 사건 하나를 그 흐름 처음부터 그 사건까지의 영문 이벤트 로그(지금 기준 몇 초 전)로 바꿔 `external_events` 에 넣고, 최근 대화와 열린 약속은 비운다. 라벨 대응은 다음과 같다.

| 원래 라벨 | 3단 라벨 | 이유 |
|---|---|---|
| `task_status` 참 | must | 사람이 도움이 필요하다고 보고 제안을 받아들였다 |
| `task_status` 거짓, `candidate_task` 있음 | must_not | 사람 셋이 제안을 보고 모두 거절했다 |
| `task_status` 거짓, `candidate_task` 비었음 | can | 사람 판정이 없는 사건이다. 점수에서 뺀다 |

표본은 must 와 must_not 사건(132 건)에서만 (장면 종류, 라벨) 층에 비례해 최대 100 건을 seed 로 고른다. 점수는 (must recall + (1 − must_not 오경보율)) / 2 × 100 이고, 실패한 문항은 오답(must 는 침묵, must_not 은 발화)으로 센다. 공식 채점은 공개되지 않은 보상 모델이 제안마다 수락을 판정하지만, 여기서는 사람 라벨로 말할지만 잰다. 제안 내용의 질은 재지 않는다. 보상 모델 시험 데이터(`rm_test.jsonl`)는 라벨 뜻이 달라 쓰지 않는다.

**임계치 보정**: 확신도의 눈금이 모델마다 달라(gpt-4o-mini 는 가장 높아도 0.8) 운영 기본 0.85 로 고정하면 판단력이 아니라 눈금이 맞는지를 재게 된다. 그래서 시험 표본에 들지 않은 나머지 must, must_not 사건(32 건)을 보정 분할로 돌려, `SWEEP` 임계치 가운데 recall 빼기 오경보가 가장 큰 값(같으면 높은 쪽)을 그 모델의 임계치로 정하고 시험 표본 100 건에 적용한다. 보정 분할에 두 라벨이 다 없으면 0.85 를 쓴다. `detail.calibration` 에 보정 분할 크기와 규칙, `detail.fixed_threshold` 에 0.85 로 잰 점수를 함께 남긴다.

---

### procedures: 절차 학습

**설명**: 같은 작업 종류로 성공한 턴 일화가 쌓이면 (에이전트, 작업 종류)당 절차 파일 하나로 증류하고 다음 세대는 그 파일의 개정 초안으로 붙인다. 실패한 턴 일화는 유휴 통합 때 reflector LLM 이 범위 하나로 분류해 절차 개정 초안이나 작업 패턴 초안을 내고, 코드 거름망을 통과한 것만 초안으로 남긴다. 승인된 절차는 LLM 도구와 슬래시 스킬로 노출한다. 설계는 EMMA(Niu et al., 2026, https://arxiv.org/abs/2610.35966)의 bounded growth 와 scoped, guarded update 를 옮겼다.

**입력과 결과**

| 입력 | 결과 |
|---|---|
| `/procedures` | 명령을 친 에이전트의 절차와 초안 목록. 개정 초안과 작업 패턴 초안은 상태 옆에 적는다 |
| `/procedures learn [session_id]` | 세션에서 절차 초안 학습(같은 출처는 한 번만). 절차는 명령을 친 에이전트의 것이 된다 |
| `/procedures approve <name>` | 초안은 승인(도구와 스킬로 등록), 개정 초안이 있으면 본문을 개정으로 교체하고 도구를 다시 올린다, 작업 패턴 초안은 그 에이전트의 작업 패턴(`task_pattern`)으로 옮기고 파일을 지운다 |
| `/procedures reject <name>`, `show <name>` | 개정 초안이 있으면 개정만 버리고(그 세대는 검토한 것으로 남는다), 없으면 삭제. `show` 는 본문과 개정 초안을 함께 보인다 |
| 공고화(세션 종료, 유휴 틱) | 옛 세대 파일 수렴, 성공 3회마다 한 세대 증류, 실패 반성(틱당 2묶음) |

**처리 흐름**: 공고화의 refiner 콜백(`ProcedureLearner.refine`)이 `converge` 로 옛 파일을 모으고, `refine.candidates` 의 성공 묶음을 `distill` (LLM) 로 증류해 `procedures_store` 에 쓰고, `refine.failures` 의 실패 묶음을 `reflect` (LLM 1회, 거부되면 한 번 더) 에 보여 `update_guard` 를 통과한 제안만 초안으로 쓴다. 승인 시 `tool` 이 도구와 스킬로 등록, 실행 계획은 `plan` 순.

**구현 파일**

| 파일 | 층 | 역할 |
|---|---|---|
| `src/ash_industry/core/procedures/detect.py` | core | 성공한 다단계 작업 구간 찾기 |
| `src/ash_industry/core/procedures/distill.py` | core | 구간을 절차 초안으로 증류 |
| `src/ash_industry/core/procedures/learner.py` | core | 증류 결과와 반성 결과를 초안이나 개정으로 저장, 에이전트당 상한, 틱당 반성 상한 |
| `src/ash_industry/core/procedures/converge.py` | core | 옛 세대 파일을 (에이전트, 작업 종류)당 하나로 모으는 계획(순수) |
| `src/ash_industry/core/procedures/reflect.py` | core | 실패 묶음을 reflector 프롬프트로, 출력은 pydantic `Reflection`(scope, action, 내용) |
| `src/ash_industry/core/procedures/update_guard.py` | core | 범위-행동 일치, 정답과 원문 누출, 크기, 상한 거름망(순수) |
| `src/ash_industry/core/procedures/plan.py` | core | 실행 계획 읽기, 검사, 채우기 |
| `src/ash_industry/core/procedures/procedures_store.py` | core | `~/.ash/procedures/<name>.md` 저장소, 개정 승인, 보관 |
| `src/ash_industry/core/procedures/tool.py` | core | 승인된 절차를 도구와 스킬로 노출 |
| `src/ash_industry/core/slash/procedures_cmd.py` | core | `/procedures` 핸들러 |
| `src/ash_industry/memory/long_term/refine.py` | memory | 턴 일화에서 성공 후보와 반성할 실패 묶음 고르기, 잇단 거부 세기 |

**테스트**

| 종류 | 파일 |
|---|---|
| 단위 | `tests/unit/test_procedures_converge.py` |
| 단위 | `tests/unit/test_procedures_detect.py` |
| 단위 | `tests/unit/test_procedures_distill.py` |
| 단위 | `tests/unit/test_procedures_learner.py` |
| 단위 | `tests/unit/test_procedures_procedures_cmd.py` |
| 단위 | `tests/unit/test_procedures_procedures_store.py` |
| 단위 | `tests/unit/test_procedures_reflect.py` |
| 단위 | `tests/unit/test_procedures_refine.py` |
| 단위 | `tests/unit/test_procedures_tool.py` |
| 단위 | `tests/unit/test_procedures_update_guard.py` |
| 통합 | `tests/integ/test_procedures.py` |

**에이전트 범위**: 승인된 절차는 그 절차를 배운 에이전트에게만 `procedure_<name>` 도구, `/<name>` 스킬, 기억의 절차 블록으로 보인다. `memory.read` 정책과 상관없다. 에이전트가 적히지 않은 예전 절차는 main 의 것으로 본다. 서브 에이전트와 스케줄 작업도 같은 규칙을 따른다.

**멱등**: 출처 `edm:<에이전트>:<작업 종류>` 가 자연 키라 같은 (에이전트, 작업 종류)는 파일 하나이고, 이미 다룬 세대(`generation`, 대기 중인 개정 포함)는 LLM 을 부르지 않는다. 반성한 실패 일화에는 `reflected` 표시가 남아 다시 반성하지 않는다. 옛 출처 `edm:<에이전트>:<작업 종류>:<세대>` 파일은 통합 때 하나로 모으고 밀려난 파일은 `~/.ash/procedures/.archive/` 로 옮긴다(지우지 않는다). 다 모은 저장소에서는 아무것도 바꾸지 않는다.

**제약과 미구현**: EMMA 의 routing, missing_capability 범위(컨트롤러 기억, 새 에이전트 생성)와 에이전트 프롬프트 자동 수정은 없다. agent_behavior 는 프롬프트 대신 작업 패턴 초안으로 간다. 실패 신호는 도구나 모델 오류와 사용자의 교정(`thought` 의 `correction` 분류)뿐이라, 사용자가 말없이 넘어간 틀린 답은 실패로 남지 않는다. 같은 작업 종류의 반성이 두 번 잇달아 거부되면 그 종류는 새 성공이 올 때까지 반성하지 않는다. 개정 초안 칸은 하나라 새 개정이 옛 개정을 덮는다. 세션 구간 학습(`/procedures learn`)은 여전히 구간마다 파일이다.

---

### release: 브랜치와 릴리즈

**설명**: 기능 PR 은 `develop`(기본 브랜치)으로 올려 squash 머지한다. 릴리즈는 `develop` 에서 `main` 으로 PR 을 올려 merge commit 으로 머지한다(squash 로 머지하면 두 브랜치 이력이 갈라져 다음 릴리즈 PR 이 충돌한다). `main` 에 들어가면 워크플로가 지난 태그 뒤 커밋 제목으로 다음 버전을 정해 릴리즈한다. 릴리즈, 데스크톱 빌드, 문서 사이트 워크플로는 이 저장소(`ash-hun/Ash-Industry`)에서만 돌고, 포크나 다른 저장소에서는 건너뛴다. 버전은 `pyproject.toml` 한 곳이 정본이고, CLI(`--version`)와 `GET /api/health` 는 설치된 패키지 버전을 읽는다.

**입력과 결과**

| 입력 | 결과 |
|---|---|
| `main` push(develop 머지) | 다음 버전이 있으면 `pyproject.toml`, `uv.lock`, `desktop/package.json`, `desktop/package-lock.json` 을 올린 `Release: vX.Y.Z` 커밋, `vX.Y.Z` 태그, GitHub Release(커밋 제목 목록), main 을 develop 에 되돌려 합침 |
| 커밋 제목 머리말 | `Feat` 은 minor, `Fix`, `Refactor` 같은 나머지와 머리말 없는 제목은 patch, `Feat!:` 처럼 `!` 나 `BREAKING CHANGE` 는 major. `Docs`, `Test`, `Chore`, `CI`, `Style`, `Build`, `Release` 만 있으면 릴리즈하지 않는다. 대소문자는 가리지 않는다 |
| `scripts/release_version.py plan [--since <태그>]` | 다음 버전. 올릴 게 없으면 빈 줄 |
| `scripts/release_version.py apply <버전>` | 버전 파일을 그 버전으로 맞추고 바뀐 파일을 출력. 이미 그 버전이면 아무 파일도 쓰지 않는다 |

**처리 흐름**: `release.yml` 에서 `git describe` 로 지난 태그를 찾고, `release_version.plan` 이 그 뒤 커밋 제목(머지 커밋 제외)으로 버전을 정하고, `apply`, 커밋, 태그, push, `gh release create`, develop 동기화 순. 새 커밋이 없으면 올릴 버전이 없어 아무것도 하지 않는다.

**구현 파일**

| 파일 | 층 | 역할 |
|---|---|---|
| `scripts/release_version.py` | scripts | 커밋 제목에서 다음 버전 계산, 버전 파일 맞추기 |
| `.github/workflows/release.yml` | ci | main push 에서 버전, 태그, Release, develop 동기화 |
| `.github/workflows/ci.yml` | ci | develop, main push 와 모든 PR 에서 검사 |
| `src/ash_industry/common/app_version.py` | common | 설치된 패키지 버전(CLI `--version`, `GET /api/health`) |

**테스트**

| 종류 | 파일 |
|---|---|
| 단위 | `tests/unit/test_release_release_version.py` |
| 단위 | `tests/unit/test_common_app_version.py` |
| 통합 | 없음. 워크플로는 첫 릴리즈에서 확인한다. 버전 응답은 `tests/integ/test_settings.py` 가 본다 |

**제약과 미구현**: 문서 사이트는 `main` push 때만 배포해 develop 에 쌓인 문서는 릴리즈 뒤에 공개된다. 릴리즈 커밋과 develop 동기화는 `GITHUB_TOKEN` 으로 올려 그 push 에서는 CI 가 다시 돌지 않는다. develop 이 그사이 버전 파일을 고쳤으면 동기화 머지가 충돌하고 워크플로가 실패한다.

---

### scheduler: 스케줄러

**설명**: cron 반복 작업과 정한 시각 한 번 실행 작업을 새 세션에서 돌리고 결과를 열린 화면, 대화 세션, 외부 알림 채널로 알린다.

**입력과 결과**

| 입력 | 결과 |
|---|---|
| `/schedule <시각>에 <내용>` | 한 번 실행 작업 등록. LLM 이 알림(reminder)과 작업(task)을 가른다 |
| `/schedule YYYY.MM.DD 오전/오후 N시까지 <프롬프트>` | 반복 작업 등록 |
| `schedule` 도구 | 대화 중 "1분 뒤에 알려줘" 를 같은 규칙으로 등록 |
| `~/.ash/schedules/*.yaml` | cron 작업 정의. `kind` 는 `reminder`(문구 그대로), `task`(에이전트 실행), `tool`(도구를 `args` 로 바로 부르기), `goal`(목표 한 차례) 중 하나이고, `agent` 가 작업을 돌릴 최상위 에이전트다 |
| `POST /api/schedules/{name}` `{enabled}` | 켜기, 끄기 |
| 실행 시각 | ws `reminder`, 열린 화면이 없으면 최근 20건을 보류 큐에 두고 다음 접속 때 `missed:true` 로. `scheduler.notice_backend=postgres` 면 보류 큐가 `ash_pending_notices` 테이블에 있어 재시작해도 이어진다(알림 `id` 로 upsert). `deliver: conversation` 이면 최근 대화 세션에 `proactive_message` |

**처리 흐름**: `schedule_cmd` 또는 `tool` 에서 `classify` 로, `scheduler_loader` 저장, `SchedulerService` 루프가 때가 된 `ScheduledTask` 를 새 세션에서 실행, 알림 순. `run_until` 이 지난 작업은 `set_enabled` 로 꺼서 저장 파일에도 남기므로 재시작해도 다시 켜지지 않는다. cron 작업은 마지막으로 돌린 슬롯보다 뒤인 슬롯이 보이면 경과 시간과 무관하게 한 번 돌린다. 호스트 절전으로 정각을 여럿 지나쳐도 깨어난 뒤 가장 최근 슬롯 하나만 따라잡는다. 기동 직후(아직 돌린 적 없음)에는 60초 안의 슬롯만 돌려 켤 때마다 모든 작업이 터지지 않게 한다.

**구현 파일**

| 파일 | 층 | 역할 |
|---|---|---|
| `src/ash_industry/core/scheduler/scheduler_service.py` | core | 스케줄 루프와 실행, 알림 |
| `src/ash_industry/core/scheduler/scheduler_loader.py` | core | YAML 읽기, 저장, enabled 토글, 끝난 작업 정리 |
| `src/ash_industry/core/scheduler/task.py` | core | 작업 정의 |
| `src/ash_industry/core/scheduler/classify.py` | core | reminder, task 분류 |
| `src/ash_industry/core/scheduler/notice_store.py` | core | 알림 보류 큐 기본 클래스(메모리), 자연 키 |
| `src/ash_industry/core/scheduler/notice_postgres_store.py` | core | 알림 보류 큐 PostgreSQL 저장소 |
| `src/ash_industry/core/scheduler/tool.py` | core | `schedule` 도구 |
| `src/ash_industry/core/slash/schedule_cmd.py` | core | `/schedule` 핸들러와 한국어 시각 해석 |

**테스트**

| 종류 | 파일 |
|---|---|
| 단위 | `tests/unit/test_scheduler_classify.py` |
| 단위 | `tests/unit/test_scheduler_dispatcher.py` |
| 단위 | `tests/unit/test_scheduler_notice_store.py` |
| 단위 | `tests/unit/test_scheduler_notice_postgres_store.py` |
| 단위 | `tests/unit/test_scheduler_schedule_cmd.py` |
| 단위 | `tests/unit/test_scheduler_scheduler_loader.py` |
| 단위 | `tests/unit/test_scheduler_scheduler_service.py` |
| 단위 | `tests/unit/test_scheduler_task.py` |
| 단위 | `tests/unit/test_scheduler_tool.py` |
| 통합 | `tests/integ/test_scheduler.py` |

**제약과 미구현**: `schedule` 도구를 같은 요청으로 두 번 부르면 알림도 두 개다(`# idempotent`). `reminder` 보류 큐는 기본(`in_memory`)이면 재시작할 때 사라지고, postgres 백엔드에서도 상한 20건을 넘는 오래된 알림은 버린다. 화면에서는 켜고 끄기만 되고 만들기와 지우기는 `/schedule` 로 한다(`docs/api_spec.md`, `docs/view_spec.md`).

---

### scorecard: 성능 스코어카드

**설명**: 벤치마크 9개를 꼭짓점으로, 능력 축 6개를 바깥 호로, 메인 LLM 마다 다각형 하나를 그리는 레이더 그림으로 main 에이전트의 대표 성능을 보인다. 꼭짓점 실험은 기존 실험과 이식한 벤치마크를 그대로 부르는 얇은 층이고, 모든 다각형이 같은 표본, 같은 판정자(gpt-4o), 같은 기억 생성 모델(gpt-4o-mini)을 쓴다.

**입력과 결과**

| 입력 | 결과 |
|---|---|
| `--polygon gpt gemma` | 그 다각형의 꼭짓점을 돌리고 `~/.ash/benchmarks/scorecard/<다각형>/<꼭짓점>.json` 에 점수, 원래 지표, Wilson 95% 구간, 모델별 토큰 사용량, 예산 비용을 남긴다. 이미 있는 꼭짓점은 캐시를 읽는다 |
| `--vertex <id>...` | 그 꼭짓점만 |
| `--quote --polygon claude` | 돌리지 않고 기준 다각형(gpt) 실측 토큰을 Claude 단가로 옮긴 꼭짓점별 견적 |
| 인자 없음 | 꼭짓점 기록을 모아 `results.json` 의 `scorecard` 키에 쓴다 |

**꼭짓점과 축**

| 축 | 꼭짓점 | 모델 역할 | 점수 |
|---|---|---|---|
| Personalization | PersonaMem-v2 | 메인 | 실서비스 조건(turns+src) 정확도 |
| Proactivity | ProactiveBench, Custom Scenario Test | 사고 | (must recall + (1 − must_not 오경보율)) / 2. decision model 없는 기본 구성. ProactiveBench 는 모델별 보정 임계치, Custom Scenario Test 는 0.85 |
| Tool Use | τ²-bench, GAIA | 메인 | pass^1, 정답 일치율 |
| Long-Horizon | KramaBench | 메인 | 공식 채점 평균. 운영 기본 max_turns, 넘침 이어가기 |
| Self-Evolving | BBEH-mini | 메인 | 실패 반성(guarded) 뒤 held-out 정확도 |
| Memory Performance | LongMemEval-s, MINT-Eval | 메인 | 실서비스 조건(turns+src) 정확도 |

**예산**: Anthropic 호출만 상한(`scorecard_config.json` 의 `budget.cap_usd`)이 있다. 예산 provider 의 다각형은 꼭짓점마다 기준 다각형의 실측 토큰으로 견적을 내(캐시 할인 없이, 여유 배율을 곱해) 누적 비용과 더해 상한을 넘으면 그 꼭짓점을 건너뛴다. 꼭짓점 도중 실제 비용이 상한에 닿으면 `BudgetExhausted` 로 멈추고 그 꼭짓점은 기록하지 않는다(실험의 `except Exception` 에 삼켜져 오답으로 캐시되지 않게 `BaseException` 을 잇는다).

**넘침 문구와 캐시**: GAIA 와 KramaBench 의 문항 캐시는 넘친 풀이에 넘침 문구의 해시(`OVERFLOW_PROMPT`)를 남긴다. 문구가 바뀌면 넘친 풀이만 다시 풀고, 넘치지 않은 풀이는 그 문구를 본 적이 없어 캐시를 그대로 쓴다.

**판정자 편향 확인**: `uv run python -m scripts.experiments.scorecard_judge_bias` 는 판정 LLM 을 쓰는 꼭짓점(LongMemEval-s, MINT-Eval)의 답을 다른 계열 판정자(claude-sonnet-5-5)로 다시 채점해, 다각형마다 두 판정의 정답률, 일치율, Cohen's kappa, 뒤집힌 수를 `results.json` 의 `scorecard_judge_bias` 키에 쓴다. 객관식과 기권은 코드가 채점해 다시 부르지 않고, 새 판정은 `~/.ash/benchmarks/cache/judge_bias.jsonl` 에 캐시해 다시 돌리면 읽기만 한다. 스코어카드와 같은 Anthropic 상한을 쓴다. τ²-bench 의 사용자 시뮬레이터(gpt-4o)는 다시 돌려야 해서 이 확인에 넣지 않았다.

**구현 파일**

| 파일 | 층 | 역할 |
|---|---|---|
| `scripts/experiments/ash_scorecard.py` | scripts | 꼭짓점 실행, 캐시, 예산 판정, results.json 쓰기 |
| `scripts/experiments/scorecard_points.py` | scripts | 점수 변환, Wilson 구간, 비용과 견적, 예산 판정, 두 판정의 비교와 kappa(순수 함수) |
| `scripts/experiments/scorecard_judge_bias.py` | scripts | 기억 꼭짓점 답을 다른 계열 판정자로 다시 채점 |
| `scripts/experiments/scorecard_meter.py` | scripts | provider 스트림 끝에서 모델별 토큰 사용량 계량 |
| `scripts/experiments/scorecard_config.json` | scripts | 다각형(메인, 사고 모델, 색), 꼭짓점, 축 색, 판정자, 단가, 예산 |
| `scripts/experiments/models.py` | scripts | 모델 이름으로 provider 와 키 선택(Claude 는 `ANTHROPIC_API_KEY`) |
| `scripts/docs_experiment_figures.py` | scripts | `exp_scorecard` 레이더 그림 |

**테스트**

| 종류 | 파일 |
|---|---|
| 단위 | `tests/unit/test_scorecard_points.py` |
| 단위 | `tests/unit/test_scorecard_proactivebench.py` |
| 단위 | `tests/unit/test_scorecard_tau2.py` |
| 단위 | `tests/unit/test_scorecard_gaia.py` |
| 통합 | `tests/integ/test_scorecard.py` |

**제약과 미구현**: 단가는 설정 파일의 가정값이다. 견적은 기준 다각형과 모델별 호출 수가 같다고 보므로, 차례를 더 쓰는 모델은 견적보다 많이 쓸 수 있다. decision model 별 Proactivity 비교는 아직 없다.

---

### session: 세션 관리

**설명**: 세션 메타와 메시지를 jsonl 또는 PostgreSQL 에 영속하고, 목록, 새로 만들기, 분기, 삭제, 이력 조회, 대화 내보내기, 토큰 비용 보고, 옛 데이터 정리를 제공한다.

**입력과 결과**

| 입력 | 결과 |
|---|---|
| `GET /api/sessions`, `/sessions` | 세션 목록 |
| `POST /api/sessions {agent}` | 새 세션 |
| `POST /api/sessions/{session_id}/branch`, `/branch [session_id]` | 분기 세션(에이전트 유지). `/branch` 인자가 없으면 명령을 친 세션 |
| `DELETE /api/sessions/{session_id}` | 삭제(그 세션의 장기 기억과 작업 기억도). 연결이 붙은 세션은 거절. 연결 확인과 삭제는 세션 잠금 안에서 한다 |
| `GET /api/sessions/{session_id}/messages` | 텍스트 이력 |
| `/export md\|json` | 명령을 친 세션의 대화 파일 내보내기 |
| `/cost` | 명령을 친 세션의 모델별 토큰 사용량과 추정 비용 |
| `/cleanup agents\|stm\|tests [confirm]` | 옛 데이터 현황, `confirm` 이 있을 때만 삭제(per_agent 세션은 보존) |

**처리 흐름**: `session_router` 또는 슬래시 핸들러에서 `SessionRegistry` 와 세션 저장소(`JsonlSessionRepo`, `PostgresSessionRepo`)로, 메타와 메시지 append 순.

**구현 파일**

| 파일 | 층 | 역할 |
|---|---|---|
| `src/ash_industry/agent_layer/session/session_protocol.py` | agent_layer | 저장소 기본 클래스, 세션 엔트리, 메타 모델 |
| `src/ash_industry/agent_layer/session/jsonl.py` | agent_layer | 세션별 JSONL 저장소 |
| `src/ash_industry/agent_layer/session/postgres.py` | agent_layer | PostgreSQL 세션 저장소 |
| `src/ash_industry/ui/web/router/session_router.py` | ui | 세션 REST |
| `src/ash_industry/core/slash/export_cmd.py` | core | `/export` 핸들러 |
| `src/ash_industry/core/slash/cost_cmd.py` | core | `/cost` 핸들러 |
| `src/ash_industry/core/slash/cleanup_cmd.py` | core | `/cleanup` 핸들러 |
| `src/ash_industry/ui/web/static/app/session.js` | ui | 세션 목록, 전환, 분기, 생성, 재연결 |
| `src/ash_industry/ui/web/static/app/usage.js` | ui | SYSTEM 카드(SET 화면) 토큰, 비용 집계 |

**테스트**

| 종류 | 파일 |
|---|---|
| 단위 | `tests/unit/test_session_cleanup_cmd.py` |
| 단위 | `tests/unit/test_session_cost_cmd.py` |
| 단위 | `tests/unit/test_session_export_cmd.py` |
| 단위 | `tests/unit/test_session_ash_config.py` |
| 단위 | `tests/unit/test_session_jsonl.py` |
| 단위 | `tests/unit/test_session_session_protocol.py` |
| 단위 | `tests/unit/test_session_session_registry.py` |
| 통합 | `tests/integ/test_session.py` |

**제약과 미구현**: Web HUD 세션 목록은 프로세스가 띄운 것만 보인다. Postgres 저장소에서 분기는 히스토리가 복사되지 않은 빈 새 세션이다(`docs/view_spec.md`).

---

### settings: 설정 화면

**설명**: 화면에서 고칠 수 있는 설정(voice, proactive, thought, focus 의 일부)을 `~/.ash/settings.yaml` 에 저장하고 같은 요청 안에서 지금 프로세스에 쓴다. 이 파일은 설정 원천 중 가장 앞(yaml, 환경변수, `.env` 순)이라 compose 가 넣은 환경변수도 이기고, 다음 기동도 같은 값으로 뜬다. 바로 쓸 수 없는 키(`thought.enabled`)만 재시작 대기로 남고, 재시작은 SET 화면의 버튼이 Ion 또는 백엔드 자기 재시작으로 한다. 전체 적용값은 이름이 비밀값처럼 보이는 항목(`*_key`, `*_token`, `*_dsn`, `*webhook*` 등)을 `***` 로 가려 보인다.

**입력과 결과**

| 입력 | 결과 |
|---|---|
| `GET /api/settings` | `fields`(고칠 수 있는 항목의 형식과 범위), `editable`(그 항목의 적용값), `pending`(저장했지만 아직 반영되지 않은 값), `effective`(가린 전체 적용값), `path` |
| `PUT /api/settings {voice?, proactive?, thought?, focus?}` | 허용 목록 밖 필드와 범위 밖 값은 422. 바뀐 게 있으면 yaml 을 원자적으로 쓰고 `changed: true`. 프로세스에 쓴 키는 `applied`, 못 쓴 키는 `restart_required: true` 와 `restart_keys` |
| `POST /api/restart` | 열린 HUD 전부에 `restarting` 을 보내고 프로세스가 정상 종료(exit 0)해 Docker 의 `restart: unless-stopped` 가 다시 띄운다. 컨테이너 밖이면 409 |
| `GET /api/health` | `{ok: true}`. 데스크톱 셸과 Ion 이 백엔드 확인에 쓴다 |
| HUD `SET` 화면 | 폼을 `fields` 로 그리고 바뀐 값만 보낸다. 반영된 키와 재시작 대기 키를 상태 줄에, 대기 항목은 행에 표시. RESTART BACKEND 는 `/ion/restart` 가 안 되면 `/api/restart` |

**처리 흐름**: `settings_router` 에서 `SettingsPatch` 검증으로, `SettingsOverlay.apply` 가 저장된 yaml 위에 patch 를 얹고(`merge_patch`), 합친 결과가 `AshSettings` 로 읽히는지 본 뒤 임시 파일을 바꿔 끼우고, `SettingsApplier.apply` 가 지금 적용값과 다른 키만(`changed_values`) 아래 표대로 쓰는 순. 기동 때는 `AshSettings.settings_customise_sources` 가 yaml 을 읽는다. 재시작은 `ProcessRestart` 가 응답이 나간 뒤 자기에게 SIGTERM 을 보내 uvicorn 의 종료 훅(세션 저장)을 돌리고, 10초를 넘기면 바로 끝낸다(`docker restart` 의 t 와 같다).

**키별 반영 방식**: 설정 객체(`AshSettings` 의 하위 모델)는 프로세스에 하나라 값을 쓰면 읽는 쪽이 바로 본다. 만들 때 값을 복사한 객체는 다시 만들거나 제공자(provider)로 매번 읽게 했다.

| 키 | 값을 보는 객체 | 방식 |
|---|---|---|
| `voice.stt_provider`, `stt_fallback`, `tts_provider`, `whisper_model_size` | `WebState.voice_service`(`VoiceService.from_config`), `translate_english` | `WebState.rebuild_voice` 로 재생성(모델 적재가 있어 스레드에서). 열린 연결은 접속 인사가 모드를 정하므로 화면이 다시 붙는다 |
| `voice.stt_lang`, `voice.tts_lang` | `ws_router` 가 접속과 TTS 요청마다 `settings.voice` 에서 읽음 | 공유 객체. `stt_lang` 은 화면이 다시 붙어야 쓴다 |
| `voice.wake_threshold` | `WebState.wake` 팩토리가 감지기를 만들 때 읽음 | 공유 객체. 화면이 다시 붙을 때 새 감지기 |
| `voice.command_max_sec`, `voice.command_max_chars` | `ws_router` 가 녹음을 받을 때마다 `settings.voice` 에서 읽어 `run_stt` 에 넘김 | 공유 객체. 다음 녹음부터 |
| `proactive.enabled` | 세션 조립(`AgentProfile.proactivity_factory`) | 공유 객체 + 열린 세션은 `AgentSession.set_proactivity` 로 코어를 다시 묶음 |
| `proactive.daemon_enabled`, `daemon_trigger`, `daemon_interval_sec`, `daemon_idle_sec` | `IntervalTrigger`, `IdleTrigger`(복사), `ProactivityDaemon` | `WebLifecycle.restart_daemon` 이 트리거를 다시 만들고 daemon 을 다시 띄움(끄면 내림) |
| `proactive.confidence_threshold` | `FeedbackLearner`(출발 임계치 복사) | 에이전트마다 `FeedbackLearner.reset` 으로 새 출발점. 학습한 값은 버린다 |
| `proactive.cooldown_sec` | `DefaultProactivityPolicy`(세션마다, 복사) | `cooldown_provider` 로 매번 설정에서 읽음 |
| `thought.router_threshold` | `ThoughtRouter`(세션마다, 복사) | `threshold_provider` 로 매번 설정에서 읽음 |
| `thought.enabled` | open loop 저장소, 사고 엔진, 답 분류기, `/journal` 명령 등 기동 때 구조 | 재시작 대기(`restart_required`) |
| `focus.enabled` | `WebState.focus` | `WebState.rebuild_focus` 로 만들거나 내려놓음 |

정의 파일이 `proactive` 를 고정한 팀 에이전트는 설정 사본을 들므로 그 사본에도 같은 값을 쓴다(`enabled` 는 정의대로 둔다).

**구현 파일**

| 파일 | 층 | 역할 |
|---|---|---|
| `src/ash_industry/app/settings_overlay.py` | app | 허용 목록(`SettingsPatch`), 필드 정의 유도, 비밀값 가림, yaml 읽기와 쓰기 |
| `src/ash_industry/ash_config.py` | config | yaml 원천(`ASH_SETTINGS_FILE`, 기본 `~/.ash/settings.yaml`) |
| `src/ash_industry/ui/web/settings_applier.py` | ui | 저장값을 프로세스 객체에 쓰기(`changed_values`, `SettingsApplier`), 재시작 대기 키 |
| `src/ash_industry/ui/web/process_restart.py` | ui | 자기 재시작(`ProcessRestart`): Docker 아래에서만, 응답 뒤 SIGTERM, 10초 상한 |
| `src/ash_industry/ui/web/web_lifecycle.py` | ui | `restart_daemon`: 트리거 재생성과 daemon 재기동 |
| `src/ash_industry/ui/web/web_state.py` | ui | `rebuild_voice`, `rebuild_focus` |
| `src/ash_industry/core/proactive/policy.py`, `feedback.py`, `src/ash_industry/agent_layer/thought/router.py` | core, agent | `cooldown_provider`, `reset`, `threshold_provider` |
| `src/ash_industry/core/session.py` | core | `set_proactivity` |
| `src/ash_industry/app/agent_profile.py`, `session_builder.py`, `app_context.py`, `infra_builder.py` | app | 제공자 주입(`cooldown_provider`, `threshold_provider`), `ctx.external_trigger` 보관(트리거 재생성용) |
| `src/ash_industry/ui/web/router/settings_router.py` | ui | `GET /api/settings`, `PUT /api/settings`, `POST /api/restart`, `GET /api/health` |
| `src/ash_industry/ui/web/static/app/settings.js` | ui | 설정 폼, 반영과 재시작 대기 표시, 데스크톱 카드, 재시작 버튼(Ion 먼저, 백엔드 자기 재시작으로 폴백) |
| `src/ash_industry/ui/web/static/app/events.js`, `shell.js` | ui | `restarting` 이벤트로 `연결 끊김 — 재시작 중` 표시 |

**테스트**

| 종류 | 파일 |
|---|---|
| 단위 | `tests/unit/test_settings_settings_overlay.py` |
| 단위 | `tests/unit/test_settings_settings_applier.py` |
| 단위 | `tests/unit/test_settings_process_restart.py` |
| 단위 | `tests/unit/test_proactive_policy.py`(cooldown provider, learner reset), `tests/unit/test_thought_router.py`(threshold provider) |
| 통합 | `tests/integ/test_settings.py` |

**제약과 미구현**: `thought.enabled` 는 재시작해야 반영된다. 허용 목록 밖(LLM, 메모리 백엔드, 비밀값)은 `.env` 로만 고친다. 음성 키는 서버는 바로 바뀌지만 화면은 접속 인사가 모드를 정하므로 저장 뒤 다시 붙는다(대화 화면이 새로 그려진다). `focus.enabled` 를 끄면 새 `/focus` 는 막히지만 진행 중이던 작업은 끝까지 돈다. 자기 재시작은 `/.dockerenv` 로 컨테이너 안인지 보고 받으므로 restart 정책 없이 띄운 컨테이너에서는 종료가 곧 끝이다(compose 는 `unless-stopped`). 자기 재시작은 Docker 의 RestartCount 를 올리므로 10분 안에 3번 누르면 Ion 이 `restart_loop` 사고를 연다(Ion 의 `docker restart` 는 올리지 않아 그쪽이 먼저다). Ion 은 15초마다 health 를 보고 3회 연속 실패(약 30~45초)면 `backend_down` 사고를 여는데, 종료 훅과 기동이 그 안에 끝나야 하고 넘기면 사고가 열린다.

---

### skills: 스킬(명령 매크로)

**설명**: Markdown/YAML 스킬 파일을 읽어 이름과 별칭으로 찾고, `/스킬 인자` 입력을 프롬프트로 펼친다. 승인된 절차도 스킬로 등록된다.

**입력과 결과**

| 입력 | 결과 |
|---|---|
| `~/.ash/skills/*.md`, `*.yaml` | 스킬 등록 |
| `/<스킬 이름> <인자>` | 스킬 본문으로 펼친 프롬프트가 에이전트에 들어간다 |

**처리 흐름**: `AgentSession._prompt` 에서 `SkillRegistry.expand` 로, 이름과 별칭 조회, 인자 치환 순.

**구현 파일**

| 파일 | 층 | 역할 |
|---|---|---|
| `src/ash_industry/core/skills/skills_registry.py` | core | 스킬 로드, 조회, 입력 확장 |

**테스트**

| 종류 | 파일 |
|---|---|
| 단위 | `tests/unit/test_skills_skills_registry.py` |
| 통합 | `tests/integ/test_skills.py` |

**제약과 미구현**: 없음.

---

### send_now: 일하는 동안 말 보내기

**설명**: 에이전트가 일하는 동안 사용자가 보낸 말을 턴을 끊지 않고 대기열에 담는다. 그 턴이 도구 결과를 받으면 다음 모델 호출 전에 같은 턴의 사용자 메시지로 붙이고, 턴이 끝났는데 남았으면 보낸 순서대로 다음 턴으로 보낸다. 지금 보내기는 도구가 도는 턴을 뒤로 넘기고(`turn_detach`) 글만 쓰는 턴은 멈춰, 대기 중인 말에 바로 답하게 한다. 아직 건네지 않은 말은 되가져올 수 있다. Claude Code 의 대기 메시지와 `chat:sendNow`(Ctrl+Enter) 동작을 따랐다(`code.claude.com/docs/en/interactive-mode`).

**입력과 결과**

| 입력 | 결과 |
|---|---|
| 일하는 중 ws `user_message{text, id}` | 대기열에 담고 `queue_changed`. 같은 `id` 는 한 번 |
| 그 턴의 도구 결과 뒤 | 대기 말을 빈 줄로 이어 사용자 메시지 하나로 붙이고 `queue_delivered`. 기록에도 그 자리에 남는다 |
| 턴이 끝났는데 대기 말이 남음 | `queue_delivered` 뒤 그 말로 다음 턴(떼어 낼 수 있는 턴) |
| ws `send_now`, 도구 실행 중 | 턴을 선응답 `하던 작업은 뒤에서 이어 할게요. 끝나면 알려 드릴게요.` 로 떼어 내고 대기 말이 다음 턴 |
| ws `send_now`, 글만 쓰는 중 | 그 단계를 멈추고(한 데까지는 기록) 대기 말이 다음 턴 |
| ws `abort` | 위와 같이 멈추고 대기 말이 다음 턴 |
| ws `queue_take` | 대기 말을 되가져와 그 연결에 `queue_taken`, 대기열은 빈다 |
| 대화는 한가하고 그 세션에 뒤에서 도는 작업이 있을 때 ws `user_message` | 작은 모델(`SteerRouter`)이 "도는 작업에 대한 지시인가, 새 요청인가" 를 한 번 가른다. 지시면 그 작업의 대기열에 넣고 대화에는 사용자 말과 선응답(`proactive_message{kind:"filler"}`, 예: `진행 중인 영상에 반영할게요.`)이 바로 붙으며 그 작업의 별에 `지시 N건 대기`. 그 작업의 다음 도구 결과 뒤에 같은 턴으로 붙고, 그때 별은 `지시 N건 반영` 으로 바뀌어 작업이 끝날 때까지 남는다. 새 요청이면 새 턴. 작은 모델이 실패하면 작업이 하나일 때만 그 작업으로 |
| ws `background_stop{task_id, session_id}`(별 메시지의 멈추기) | 그 작업만 멈춘다. 도는 도구 호출이 끝난 뒤 다음 확인 자리에서 멈추고, 한 데까지는 기록에 남으며 답은 `작업을 멈췄어요.`. 그 작업이 읽지 못한 지시는 대화의 다음 턴이 된다 |
| 에이전트 사이 위임, 스케줄, Focus | 대기열을 쓰지 않는다(지금처럼 3초 기다린 뒤 거절) |

**처리 흐름**: `ws_router` 가 `AgentSession.enqueue` 로 바쁠 때만 `TurnInbox` 에 담고, `AgentHarness.run` 이 그 턴의 꺼내기 함수(뒤로 넘긴 턴이면 꺼내지 않음)를 `run_agent_loop` 에 넘겨 `_deliver_queued` 가 도구 결과 뒤에 붙인다. `prompt` 가 끝나면 `_flush_queue` 가 남은 말로 다음 턴을 띄운다. `send_now` 는 `TurnChannel.tools_running` 을 보고 `request_detach`(`TurnDetach` 가 시계를 기다리지 않고 떼어 냄) 또는 `abort` 를 고른다.

**구현 파일**

| 파일 | 층 | 역할 |
|---|---|---|
| `src/ash_industry/agent_layer/turn_inbox.py` | agent_layer | 세션별, 작업별 대기열. 순서, 같은 id 한 번, 꺼내면 비움 |
| `src/ash_industry/agent_layer/thought/steer_router.py` | agent_layer | 뒤에서 작업이 돌 때 온 말을 작업 지시와 새 요청으로 가르는 작은 모델, 실패 규칙 |
| `src/ash_industry/agent_layer/loop.py` | agent_layer | 도구 결과 뒤 대기 말 붙이기(`_deliver_queued`) |
| `src/ash_industry/agent_layer/harness.py` | agent_layer | 턴마다 꺼내기 함수. 뒤로 넘긴 턴은 꺼내지 않는다 |
| `src/ash_industry/agent_layer/turn_channel.py` | agent_layer | 도는 도구 수, 지금 떼어 내기 요청 |
| `src/ash_industry/core/turn/turn_detach.py` | core | 지금 떼어 내기 요청이 오면 시계를 기다리지 않는다 |
| `src/ash_industry/core/session.py` | core | `enqueue`, `take_back`, `send_now`, 턴이 끝나면 다음 턴으로(`_flush_queue`) |
| `src/ash_industry/ui/web/router/ws_router.py` | ui | `user_message` 의 대기, `send_now`, `queue_take`, `connected.queued` |
| `src/ash_industry/ui/web/static/app/queue.js` | ui | 대기 목록, 건네진 말을 대화에 붙이기, 되가져오기 |
| `src/ash_industry/ui/web/static/app/composer.js` | ui | 일하는 중 입력을 막지 않음, Ctrl(Cmd)+Enter, ↑, Esc |

**테스트**

| 종류 | 파일 |
|---|---|
| 단위 | `tests/unit/test_send_now_turn_inbox.py` |
| 단위 | `tests/unit/test_send_now_loop.py` |
| 단위 | `tests/unit/test_send_now_steer_router.py` |
| 단위 | `tests/unit/test_turn_turn_detach.py`(지금 떼어 내기), `tests/unit/test_turn_turn_channel.py`(도는 도구 수) |
| 통합 | `tests/integ/test_send_now.py`(도구 중 대기는 같은 턴, 남은 말은 다음 턴, 지금 보내기의 떼어 내기와 멈춤, 되가져오기, 뒤로 넘긴 작업에 지시 보내기, 새 요청은 새 턴, 작업 멈추기와 읽지 못한 지시의 다음 턴) |

**제약과 미구현**: 대기 말은 프로세스 메모리라 재시작하면 사라진다. 글만 쓰는 중(도구 없이 답만 쓰는 턴)에 보낸 말은 그 턴이 끝난 뒤 다음 턴이 된다. 화면 하나가 되가져오면 다른 화면의 대기 목록도 빈다. 뒤에서 도는 작업으로 간 지시는 그 작업이 다음 도구 결과를 받을 때까지 읽히지 않는다(되가져오기는 대화 대기열만). 작업 멈추기는 도는 도구 호출(미디어 워커의 렌더 잡 등)을 끊지 않고 그 호출이 끝난 뒤 멈춘다. 작은 모델의 판정이 틀리면 지시가 엉뚱한 작업이나 새 턴으로 갈 수 있다(별의 멈추기로 바로잡는다).

### task_pattern: 작업 패턴 기억

**설명**: 사용자가 알려 준 일하는 방식(언제, 어떻게)을 부른 에이전트 전용 절차 기억으로 저장하고, 같은 종류 요청에서 그 에이전트에게만 떠올려 되묻지 않게 한다.

**입력과 결과**

| 입력 | 결과 |
|---|---|
| `remember_task_pattern` 도구 | 부른 에이전트 범위로 패턴 저장 |
| `/patterns` | 지금 에이전트의 작업 패턴 목록 |
| `/patterns forget <이름>` | 삭제 |
| 실패 반성의 작업 패턴 초안(`procedures`) | `/procedures approve pattern-<이름>` 으로 승인하면 그 에이전트의 작업 패턴으로 저장 |

**처리 흐름**: `task_pattern` 도구에서 `memory.long_term.task_pattern` 변환으로, `MemoryService.remember` 저장, 회상 때 질의 맞추기 순.

**구현 파일**

| 파일 | 층 | 역할 |
|---|---|---|
| `src/ash_industry/memory/long_term/task_pattern.py` | memory | 작업 방식을 절차 기억으로 바꾸고 질의에 맞추기 |
| `src/ash_industry/core/tools/task_pattern.py` | core | `remember_task_pattern` 도구 |
| `src/ash_industry/core/slash/patterns_cmd.py` | core | `/patterns` 핸들러 |

**테스트**

| 종류 | 파일 |
|---|---|
| 단위 | `tests/unit/test_task_pattern_patterns_cmd.py` |
| 단위 | `tests/unit/test_task_pattern_task_pattern.py` |
| 통합 | `tests/integ/test_procedures.py`(반성 초안을 승인한 패턴이 다음 요청에 들어감) |

**제약과 미구현**: 반성이 낸 작업 패턴은 승인 전까지 `~/.ash/procedures/` 의 초안 파일이고 기억에 들어가지 않는다.

---

### thought: inner thought

**설명**: 요청 시점과 성찰 시점에 별도 LLM 호출로 해석, 결정, 확신도를 담은 `ThoughtFrame` 을 만들어 메인 턴 프롬프트에 끼우고 로그로 남긴다. router decision model 이 켜져 있으면 요청마다 사고를 돌릴지 정한다. 키워드로 판정이 안 되는 짧은 답(🔔 피드백, 음성 승인)을 분류한다.

**입력과 결과**

| 입력 | 결과 |
|---|---|
| 요청 턴 | ws `thought_route{think, p_think}`(router 가 켜졌을 때), `inner_thought`, `thought_end`. think 면 사고 결과가 다음 턴 시스템 프롬프트에 한 번 들어간다 |
| 성찰 | `DecisionGatedEngine` 이 decision model 을 먼저 묻고(전체 판단, 항목별 판단), 문턱 아래면 사고 LLM 을 부르지 않는다. 넘으면 가장 높은 항목을 앵커로 사고를 돌리고, 말에 앵커 낱말이 없으면 침묵한다(`anchor missing`) |
| ws `reply_classify{kind, id, text, context, has_always}` | `reply_classified{verdict}`. 모델이 없거나 6초 안에 답하지 못하면 `other`, `unclear` |
| 🔔 답이 아닌 보통 말(명령 제외) | 세션이 뒤에서 `correction` 분류(직전 답, 다음 말)를 한 번 돌려 `correction` 이면 그 답의 턴 일화를 `outcome=failure` 로 바꾸고 교정 글을 `correction` 에 남긴다. 반성(`procedures`)이 "사용자가 바로잡은 말" 로 읽는다. 응답을 막지 않는다 |

**처리 흐름**: `AgentSession._route` 에서 `router` (`model_layer.decision`) 로, `engine` 이 `prompt` 템플릿과 회상 콜백으로 `ThoughtFrame` 생성, `composer` 조립, `log` 싱크 저장 순. 분류는 `ws_tasks` 에서 `reply.ReplyClassifier` 순.

**구현 파일**

| 파일 | 층 | 역할 |
|---|---|---|
| `src/ash_industry/agent_layer/thought/engine.py` | agent_layer | 기본 inner thought 엔진 |
| `src/ash_industry/agent_layer/thought/thought_protocol.py` | agent_layer | 엔진 기본 클래스와 회상 콜백 타입 |
| `src/ash_industry/agent_layer/thought/thought_types.py` | agent_layer | `ThoughtRequest`, `ThoughtFrame`, 행동 후보 |
| `src/ash_industry/agent_layer/thought/prompt.py` | agent_layer | 프롬프트 템플릿 로드와 채우기 |
| `src/ash_industry/agent_layer/thought/composer.py` | agent_layer | 프레임을 메인 프롬프트 텍스트로 |
| `src/ash_industry/agent_layer/thought/log.py` | agent_layer | 프레임을 LTM, 작업 기억 메모 싱크로 |
| `src/ash_industry/agent_layer/thought/router.py` | agent_layer | think, direct 판정 |
| `src/ash_industry/agent_layer/thought/decision_gate.py` | agent_layer | 성찰에서 decision model 을 사고보다 먼저 묻고, 항목별 판단과 앵커를 정한다 |
| `src/ash_industry/agent_layer/thought/anchor_check.py` | agent_layer | 말이 앵커의 숫자, 이름, 핵심 낱말을 담았는지(순수 함수) |
| `src/ash_industry/agent_layer/thought/reply.py` | agent_layer | 짧은 답 분류기 |
| `src/ash_industry/model_layer/decision.py` | model_layer | decision model(System One API) 클라이언트 |
| `src/ash_industry/ui/web/static/app/reply.js` | ui | 화면에서 `reply_classify` 요청 |

**테스트**

| 종류 | 파일 |
|---|---|
| 단위 | `tests/unit/test_thought_anchor_check.py` |
| 단위 | `tests/unit/test_thought_composer.py` |
| 단위 | `tests/unit/test_thought_decision.py` |
| 단위 | `tests/unit/test_thought_decision_gate.py` |
| 단위 | `tests/unit/test_thought_engine.py` |
| 단위 | `tests/unit/test_thought_log.py` |
| 단위 | `tests/unit/test_thought_prompt.py` |
| 단위 | `tests/unit/test_thought_reply.py` |
| 단위 | `tests/unit/test_thought_router.py` |
| 단위 | `tests/unit/test_thought_session_builder.py` |
| 단위 | `tests/unit/test_thought_thought_protocol.py` |
| 단위 | `tests/unit/test_thought_thought_types.py` |
| 통합 | `tests/integ/test_thought.py` |

**제약과 미구현**: 클라우드 provider 에서 race(병렬) 타이밍이 맞는지 미측정이다(`TODO.md`). router 가 direct 로 판정한 턴에는 사고와 💬 filler 가 없다(`docs/view_spec.md`).

---

### tools: 내장 도구와 사용자 도구

**설명**: 파일 읽기, 쓰기, 고치기, 목록, glob, grep, 셸, 웹 가져오기, 웹 검색 내장 도구와, 디렉터리의 `.py` / `.yaml` 사용자 도구를 레지스트리에 등록한다. 화면은 세션 에이전트의 도구와 승인 필요 여부를 보인다.

**입력과 결과**

| 입력 | 결과 |
|---|---|
| 에이전트의 tool_call | `bash`, `read_file`, `write_file`, `edit_file`, `list_dir`, `glob`, `grep`, `web_fetch`, `web_search` 실행 결과 |
| `~/.ash/tools/*.py`, `*.yaml` | 기동 때 사용자 도구 등록. 같은 이름의 내장 도구를 덮어쓴다 |
| `GET /api/tools?session_id=`, `/tools` | 도구 목록(`approval` 표시) |
| `uv run python -m scripts.experiments.gaia_bench --model M [--limit N] [--seed S] [--concurrency C]` | GAIA validation 점수(스코어카드 Tool Use 꼭짓점). 첨부 없는 Level 1, 2 문항을 `web_search`, `web_fetch` 만 준 운영 루프(`max_turns` 20, 넘침 이어가기)로 풀고 공식 scorer 로 채점한다. `run_vertex()` 가 `{score, n, raw, detail, errors}` 를 돌려주고 CLI 는 점수만 출력한다(문항과 정답은 찍지 않는다). 같은 (모델, 문항, 설정)은 `~/.ash/benchmarks/gaia/cache/` 를 읽어 다시 부르지 않는다 |

**처리 흐름**: `InfraBuilder` 에서 내장 도구와 `tools_loader` 로 `ToolRegistry` 등록, 세션 에이전트 경계로 거르기, 도구 실행기 순.

**구현 파일**

| 파일 | 층 | 역할 |
|---|---|---|
| `src/ash_industry/core/tools/builtin/bash.py` | core | `bash` |
| `src/ash_industry/core/tools/builtin/read_file.py` | core | `read_file` |
| `src/ash_industry/core/tools/builtin/write_file.py` | core | `write_file` |
| `src/ash_industry/core/tools/builtin/edit_file.py` | core | `edit_file` |
| `src/ash_industry/core/tools/builtin/list_dir.py` | core | `list_dir` |
| `src/ash_industry/core/tools/builtin/glob.py` | core | `glob` |
| `src/ash_industry/core/tools/builtin/grep.py` | core | `grep` |
| `src/ash_industry/core/tools/builtin/web_fetch.py` | core | `web_fetch` |
| `src/ash_industry/core/tools/builtin/web_search.py` | core | `web_search`(Brave, 키 없으면 DuckDuckGo) |
| `src/ash_industry/core/tools/tools_loader.py` | core | 파일 기반 도구 로딩 |
| `src/ash_industry/ui/web/static/app/tools.js` | ui | SYSTEM 카드(SET 화면) 도구 목록 |
| `scripts/experiments/gaia_bench.py` | scripts | GAIA 표본(레벨 비례 층화 40, seed), 웹 도구 실행기(사설 주소와 GAIA 사본 주소 차단, 검색 4 초 간격), 캐시, `run_vertex` |
| `scripts/experiments/gaia_score.py` | scripts | GAIA 공식 `question_scorer` 이식(Apache-2.0)과 `FINAL ANSWER` 파싱(순수 함수) |

**테스트**

| 종류 | 파일 |
|---|---|
| 단위 | `tests/unit/test_tools_bash.py` |
| 단위 | `tests/unit/test_tools_edit_file.py` |
| 단위 | `tests/unit/test_tools_glob.py` |
| 단위 | `tests/unit/test_tools_grep.py` |
| 단위 | `tests/unit/test_tools_list_dir.py` |
| 단위 | `tests/unit/test_tools_read_file.py` |
| 단위 | `tests/unit/test_tools_tools_loader.py` |
| 단위 | `tests/unit/test_tools_tools_registry.py` |
| 단위 | `tests/unit/test_tools_web_fetch.py` |
| 단위 | `tests/unit/test_tools_web_search.py` |
| 단위 | `tests/unit/test_tools_write_file.py` |
| 단위 | `tests/unit/test_scorecard_gaia.py` |
| 통합 | `tests/integ/test_tools.py` |

**제약과 미구현**: 사용자 도구 파일은 `plugin.watch_files` 가 켜져 있을 때 다시 읽는다(plugins 기능). 에이전트 정의의 `tools` 로 골라 복사한 레지스트리는 재시작해야 새 도구를 본다. GAIA 데이터는 Hugging Face `gaia-benchmark/GAIA` 의 `2023/validation/metadata.parquet`(접근 승인 필요)를 받아 `uvx --with pyarrow` 로 `~/.ash/benchmarks/gaia/validation.jsonl` 로 바꾼다. 데이터셋 조건(공개 웹에 다시 올리지 않기)에 따라 문항과 정답은 저장소, 문서, 로그에 남기지 않는다. DuckDuckGo 는 연속 검색 7 번쯤에서 막혀(202, 이어서 403) 검색을 한 줄로 세우고 4 초 간격을 둔다.

---

### turn_detach: 오래 걸리는 턴 떼어 내기(Dual-Channel)

**설명**: 보통의 대화는 코어 모델(메인 모델)이 그 자리에서 답한다. 사람이 HUD 에서 기다리는 턴이 `proactive.detach_after_sec`(기본 7.5초)를 넘기면, 작은 모델(사고 모델)이 요청과 진행 상황(부른 도구, 흘린 글)을 보고 그 에이전트 말투로 쓴 선응답 한두 문장으로 턴을 닫는다. 코어 모델은 같은 턴을 뒤에서 이어 돌고, 끝나면 그 답을 대화에 그 에이전트의 말로 남기고 알린다. 그동안 사용자는 같은 에이전트와 계속 대화한다. 모든 에이전트에 같다(에이전트 정의와 도구와 무관하다). 사고가 요청 전에 미리 오래 걸린다고 봤으면(`needs_background`, 사고 타이밍이 before 나 race 일 때만) 시간을 기다리지 않고 사고의 filler 로 바로 떼어 낸다.

**입력과 결과**

| 입력 | 결과 |
|---|---|
| ws `user_message`, 턴이 7.5초 안에 끝남 | 지금과 같다 |
| ws `user_message`, 턴이 7.5초를 넘김 | 그 순간 스트림에 선응답이 붙고 `agent_end{final_message: 선응답}` 으로 턴이 닫히며 입력이 풀린다. 선응답은 4초(`detach_after_sec - ack_lead_sec`)에 쓰기 시작하고, 7.5초까지 못 쓰면 고정 문장 `시간이 조금 걸리는 작업이라 뒤에서 이어서 할게요. 끝나면 바로 알려 드릴게요.` 를 쓴다. 열린 HUD 전부에 `background_tasks` 가 가 리액터 위와 좌우에 별이 뜨고(마우스를 올리면 옆에 `<에이전트> · <요청>`), FLOW 작업 표에 `background` 작업이, FLOW 의 AGENT MAP 과 그래프에 `background` 위임(받는 쪽 `background:<에이전트>`, 화면 이름 "뒤에서 이어 하기")이 진행 중으로 생긴다 |
| 뒤에서 돈 턴이 끝남 | 그 턴의 메시지(도구 호출과 결과, 답)가 대화 기록 끝에 남고 `proactive_message{kind:"answer"}` 가 대화에 붙으며 외부 알림 채널로도 간다. 별은 한 번 밝아졌다 사라진다(실패면 붉게) |
| 뒤에서 도는 턴의 승인 요청 | 그 세션의 승인 창으로 간다. 다른 세션을 보고 있으면 승인 대기 띠(`approval_waiting`) |
| 에이전트 사이 위임(`ask_agent`), 스케줄, Focus | 떼어 내지 않는다. 답을 받아 써야 하는 쪽이라 끝까지 기다린다 |

**처리 흐름**: `ws_tasks.run_prompt` 가 `AgentSession.prompt(detach=True)` 로, `ProactivityCore.plan_request` 가 사고 프레임의 미리 본 계획을 주고, `TurnDetach.run` 이 턴(`run_main`)과 시계를 함께 돌린다. 시간이 되면 `AckWriter` 가 쓴 선응답으로 `TurnChannel.detach()` 가 그 턴의 이벤트를 화면에서 떼고, 세션의 `_hand_off` 가 선응답을 스트림과 기록에 남기고 바쁨을 푼다. `AgentHarness` 는 뗀 턴의 메시지를 기록하지 않고 `channel.produced` 에 두며, `_finish_background` 가 그 세션이 다른 턴을 끝낼 때까지 기다렸다가 기록에 남기고 `answer` 와 `background_task` 이벤트를 낸다. `BackgroundBoard` 가 그 이벤트로 FLOW 작업과 HUD 별 목록을 갱신한다.

**설정**: `ASH_PROACTIVE__DETACH_AFTER_SEC`(기본 7.5, 0 이면 끔), `ASH_PROACTIVE__ACK_LEAD_SEC`(기본 3.5. gpt-4o-mini 가 선응답에 2.6초 걸렸다). 먼저 말 걸기(`proactive.enabled`, 에이전트 정의의 `proactive`)와 상관없이 모든 에이전트에 쓴다(Kiri, Evi, Ion 처럼 먼저 말 걸기를 끈 에이전트도). `thought.enabled` 가 꺼져 있으면 선응답은 늘 고정 문장이다.

**구현 파일**

| 파일 | 층 | 역할 |
|---|---|---|
| `src/ash_industry/core/turn/turn_detach.py` | core | 턴과 시계를 함께 돌려 제때 끝나면 답, 넘기면 선응답과 함께 `Detached` |
| `src/ash_industry/agent_layer/turn_channel.py` | agent_layer | 한 턴의 이벤트 길. 떼어 내기 전에는 화면으로, 뗀 뒤에는 보내지 않음. 진행 상황 요약 |
| `src/ash_industry/agent_layer/thought/ack_writer.py` | agent_layer | 작은 모델로 선응답 쓰기, 지시문 자르기, 출력 다듬기, 고정 문장 |
| `src/ash_industry/agent_layer/harness.py` | agent_layer | 뗀 턴의 메시지를 기록 대신 `channel.produced` 에, 다음 턴용 중단 신호를 새로(`detach_foreground`) |
| `src/ash_industry/core/session.py` | core | `prompt(detach)`, 선응답으로 턴 닫기(`_hand_off`), 뒤 턴의 답 남기기와 알림(`_finish_background`) |
| `src/ash_industry/core/proactive/proactive_core.py` | core | 사고가 미리 본 요청 계획(`plan_request`) |
| `src/ash_industry/app/agent_profile.py` | app | 에이전트 설정으로 `TurnDetach` 조립(`turn_detach`) |
| `src/ash_industry/ui/web/background_board.py` | ui | 도는 작업 목록, FLOW 작업 기록, `background_tasks` 방송 |
| `src/ash_industry/ui/web/static/app/task-stars.js` | ui | 리액터 둘레의 작업 별. 자리는 작업 id 로 정하고, 누르면 그 세션으로 이동 |

**테스트**

| 종류 | 파일 |
|---|---|
| 단위 | `tests/unit/test_turn_turn_detach.py` |
| 단위 | `tests/unit/test_turn_turn_channel.py` |
| 단위 | `tests/unit/test_turn_ack_writer.py` |
| 단위 | `tests/unit/test_web_hud_background_board.py` |
| 단위 | `tests/unit/test_agent_registry_agent_profile.py`(먼저 말 걸기를 끈 에이전트도 떼어 내기를 갖는다) |
| 통합 | `tests/integ/test_turn_detach.py`(선응답으로 닫힘, 그동안 다음 말에 답함, 끝난 답의 기록 순서, HUD 의 별과 답) |
| 통합 | `tests/integ/test_proactive.py`(사고가 미리 길다고 본 턴은 filler 로 바로 떼어 냄) |

**제약과 미구현**: 백엔드가 재시작되면 뒤에서 돌던 턴은 답 없이 사라지고 FLOW 에 멈춘 작업으로 남는다. 뒤에서 도는 턴은 별 메시지의 멈추기(`background_stop`)로 멈춘다(`abort` 는 지금 대화 턴만 멈춘다). 뗀 턴의 도구 호출과 결과는 끝난 뒤에 기록에 남으므로, 그 사이 다음 턴의 모델은 그 작업이 무엇을 했는지 선응답만 보고 안다. 한 세션에서 동시에 뒤에서 도는 턴의 수에 상한이 없다.

### usermodel: 사용자 모델

**설명**: 누적 기억을 LLM 으로 증류해 안정적인 사용자 모델을 만들고, 사고 프롬프트에 블록으로 싣는다.

**입력과 결과**

| 입력 | 결과 |
|---|---|
| `/usermodel` | 지금 사용자 모델 |
| `/usermodel build` | 최근 기억으로 갱신(실패하면 이전 모델 유지), `~/.ash/user_model.json` 스냅샷 |

**처리 흐름**: `usermodel_cmd` 에서 `UserModelBuilder` 로, `MemoryService` 최근 기억 조회, LLM 증류, `usermodel_store` 저장 순.

**구현 파일**

| 파일 | 층 | 역할 |
|---|---|---|
| `src/ash_industry/agent_layer/usermodel/builder.py` | agent_layer | 기억을 사용자 모델로 증류 |
| `src/ash_industry/agent_layer/usermodel/usermodel_store.py` | agent_layer | 메모리, JSON 파일 저장소 |
| `src/ash_industry/agent_layer/usermodel/usermodel_types.py` | agent_layer | 사용자 모델과 프롬프트 블록 변환 |
| `src/ash_industry/core/slash/usermodel_cmd.py` | core | `/usermodel` 핸들러 |

**테스트**

| 종류 | 파일 |
|---|---|
| 단위 | `tests/unit/test_usermodel_builder.py` |
| 단위 | `tests/unit/test_usermodel_usermodel_cmd.py` |
| 단위 | `tests/unit/test_usermodel_usermodel_store.py` |
| 단위 | `tests/unit/test_usermodel_usermodel_types.py` |
| 통합 | `tests/integ/test_usermodel.py` |

**제약과 미구현**: 없음.

---

### voice: 음성

**설명**: 서버 STT(faster-whisper)와 TTS(Piper, Supertonic, Qwen3-TTS), 브라우저 Web Speech 위임, 마크다운을 읽을 문장으로 바꾸기, main 의 영어 음성용 번역, 미리 녹음한 읽기 문구, 웨이크워드 감지를 제공한다. 영어 말투와 고정 문장(`voice.english_style`, `english_fallback`, `english_unclear`), 웨이크워드 모델 파일(`voice.wake_model_file`), whisper 표기 힌트(`voice.whisper_hotwords`)는 설정으로 정한다.

**입력과 결과**

| 입력 | 결과 |
|---|---|
| ws `voice_tts_request{text, id, source, part, full_text, stream}` | `voice_tts_audio`(조각 스트림 가능). 서버 TTS 가 없으면 빈 `data` 로 브라우저가 읽는다 |
| ws `voice_stt_submit{data, mime, sample_rate}` | `voice_stt_result`. 말소리가 `voice.command_max_sec`(기본 12초)보다 길거나 글이 `voice.command_max_chars`(기본 120자)보다 길면 에이전트에게 한 말이 아니라 주변 대화(회의)로 보고 `ambient` 와 앞 80자 `heard` 만 보내며 아무 말도 하지 않는다(확신도보다 먼저 본다). 문장이 하나도 안 나오면(소음만 녹음) `silent` 만 보내고 되묻지 않는다. 확신도가 낮으면 `unclear` 와 되묻는 말. whisper 는 한국어와 영어 중 감지한 언어로 받아 적고(그 밖으로 감지되면 둘 중 확률이 높은 쪽으로 다시), 말 끝 무음은 VAD 로 잘라 낸다 |
| ws 바이너리 프레임(16kHz PCM) | 점수가 임계치 이상이면 `voice_wake{score}` |
| `GET /api/voice/phrases/{name}` | 녹음 문구 wav |
| Web HUD 구체 클릭, 웨이크워드, 데스크톱 전역 단축키 | 음성 입력. 말로 시작하면 음성 대화가 열려 답을 읽고 다시 듣는다. 말이 없거나 타이핑하거나 읽기를 멈추면 끝난다. 서버가 `ambient` 를 돌려주면 대화를 끝내고 다시 듣지 않으며, 웨이크워드는 2분 쉰다(거듭되면 두 배씩, 최대 15분. 진짜 요청이 들어오면 바로 푼다). 회의 중 잘못 깨어나 남의 말에 답하고 그 반응에 또 답하던 되풀이를 막는다(11-17 실측) |
| 설정 `voice.stt_fallback`(기본 `whisper`) | `stt_provider` 가 browser 일 때 브라우저 인식이 없거나 `network` 같은 오류로 끝나면 화면이 녹음해 서버 STT 로 보낸다. 모델은 처음 받아 적을 때 불러온다 |

**처리 흐름**: `ws_tasks` 에서 `speech_text` 로 기호 제거와 금액 한글화, 필요하면 `english` 번역, `VoiceService` 가 `voice_registry` 로 고른 프로바이더 합성 또는 전사 순. 웨이크워드는 `ws_router` 에서 `WakeDetector` 순.

**구현 파일**

| 파일 | 층 | 역할 |
|---|---|---|
| `src/ash_industry/voice/voice_service.py` | voice | STT, TTS 파이프라인 |
| `src/ash_industry/voice/voice_registry.py` | voice | 이름으로 프로바이더 지연 생성 |
| `src/ash_industry/voice/voice_protocol.py` | voice | 프로바이더 기본 클래스(브라우저 위임) |
| `src/ash_industry/voice/speech_text.py` | voice | 마크다운을 읽을 문장으로 |
| `src/ash_industry/voice/english.py` | voice | 한국어 글을 짧은 영어 구어체로 |
| `src/ash_industry/voice/phrases.py` | voice | 읽기 문구 폴더 로드 |
| `src/ash_industry/voice/wake.py` | voice | 웨이크워드 감지기 |
| `src/ash_industry/voice/providers/browser.py` | voice | 브라우저 위임 프로바이더 |
| `src/ash_industry/voice/providers/whisper.py` | voice | faster-whisper STT |
| `src/ash_industry/voice/providers/piper.py` | voice | Piper TTS |
| `src/ash_industry/voice/providers/supertonic.py` | voice | Supertonic-3 TTS |
| `src/ash_industry/voice/providers/qwen.py` | voice | Qwen3-TTS, 실패하면 Piper |
| `src/ash_industry/ui/web/router/voice_router.py` | ui | 읽기 문구 wav REST |
| `src/ash_industry/ui/web/static/voice.js` | ui | `VoiceManager` |
| `src/ash_industry/ui/web/static/app/voice-ui.js` | ui | 음성 입출력 배선과 음성 대화(말로 이어 가기) 흐름 |
| `src/ash_industry/ui/web/static/app/phrases.js` | ui | 읽기 문구 재생 |
| `src/ash_industry/ui/web/static/app/wake.js` | ui | 웨이크워드 오디오 송신 |
| `src/ash_industry/ui/web/static/wake-worklet.js` | ui | 80ms PCM 캡처 AudioWorklet |

**테스트**

| 종류 | 파일 |
|---|---|
| 단위 | `tests/unit/test_voice_english.py` |
| 단위 | `tests/unit/test_voice_phrases.py` |
| 단위 | `tests/unit/test_voice_piper.py` |
| 단위 | `tests/unit/test_voice_qwen.py` |
| 단위 | `tests/unit/test_voice_speech_text.py` |
| 단위 | `tests/unit/test_voice_supertonic.py` |
| 단위 | `tests/unit/test_voice_voice_protocol.py` |
| 단위 | `tests/unit/test_voice_voice_registry.py` |
| 단위 | `tests/unit/test_voice_voice_service.py` |
| 단위 | `tests/unit/test_voice_wake.py` |
| 단위 | `tests/unit/test_voice_whisper.py` |
| 통합 | `tests/integ/test_voice.py` |

**제약과 미구현**: 영어 문장 나누기가 약어 마침표에서도 나뉜다(`# ponytail`). 웨이크워드는 설정한 모델(`voice.wake_model_file`)의 낱말만 알아듣고 16kHz AudioContext 를 쓸 수 있는 브라우저에서만 돈다. 읽기가 겹치면 소리가 겹친다(`docs/view_spec.md`). 에어팟에서 승인 되읽기 확인이 남아 있다(`TODO.md`).

---

### web_hud: Web HUD

**설명**: FastAPI 앱이 정적 HUD 셸(리액터 캔버스, 입자 구, 카드, 입력 독)과 REST, WebSocket 라우터를 묶어 띄우고, 기동 때 첫 세션, 스케줄러, 성찰 daemon, 외부 폴러, 확장 파일 감시를 켠다.

**입력과 결과**

| 입력 | 결과 |
|---|---|
| `ash-industry [--host] [--port]` | uvicorn 으로 Web HUD 기동(기본 `127.0.0.1:7777`, `cli`) |
| 헤더 `HUD` / `FLOW` / `SET`, `Esc` | 화면 전환. 고른 화면은 이 브라우저에 기억한다. `Esc` 는 HUD 로 |
| `/` 화면 | HUD 셸, 접속하면 `default` 세션(main) |
| 종료 | 세션마다 공고화와 저장 |

**처리 흐름**: `cli_startup` 에서 `build_app` 과 `server.create_app` 으로, `web_lifecycle` 기동, 라우터 등록, `StaticFiles` 셸 서빙 순.

**구현 파일**

| 파일 | 층 | 역할 |
|---|---|---|
| `src/ash_industry/ui/web/server.py` | ui | FastAPI 앱 조립과 인증 미들웨어 |
| `src/ash_industry/ui/web/startup.py` | ui | uvicorn 실행 |
| `src/ash_industry/ui/web/web_lifecycle.py` | ui | 기동과 종료 |
| `src/ash_industry/ui/web/static/index.html` | ui | HUD 셸 |
| `src/ash_industry/ui/web/static/styles.css` | ui | 스타일 |
| `src/ash_industry/ui/web/static/hud.js` | ui | 리액터 캔버스(링, 눈금, 별) |
| `src/ash_industry/ui/web/static/sphere.js` | ui | three.js 입자 구 |
| `src/ash_industry/ui/web/static/sw.js` | ui | 셸 프리캐시와 오프라인 폴백 |
| `src/ash_industry/ui/web/static/manifest.json` | ui | PWA manifest 원본 |
| `src/ash_industry/ui/web/static/icons/` | ui | 앱 아이콘 |
| `src/ash_industry/ui/web/static/vendor/three/` | ui | three.js 벤더 파일 |
| `src/ash_industry/ui/web/static/app/main.js` | ui | HUD 진입점 |
| `src/ash_industry/ui/web/static/app/shell.js` | ui | 헤더 시각과 연결 점, 작업 상태, 캡션, ACTIVITY, 카드 접기, 드로어 |
| `src/ash_industry/ui/web/static/app/header.js` | ui | 헤더 가운데 묶음을 리액터 구체 중심에 맞춘다 |
| `src/ash_industry/ui/web/static/app/artifact.js` | ui | 큰 코드블록 아티팩트 패널 |
| `src/ash_industry/ui/web/static/app/view.js` | ui | `body[data-view]` 화면 전환과 카드가 빠지고 들어오는 전환 애니메이션 |

**테스트**

| 종류 | 파일 |
|---|---|
| 단위 | `tests/unit/test_web_hud_adapter.py` |
| 단위 | `tests/unit/test_web_hud_logger.py` |
| 단위 | `tests/unit/test_web_hud_ws_tasks.py` |
| 통합 | `tests/integ/test_web_hud.py` |

**제약과 미구현**: 오른쪽 여백(헤더와 스테이지가 창보다 좁게 보임) 사용자 보고가 재현되지 않아 열려 있다(`TODO.md`). 입력창은 한 줄이다. 아티팩트 패널은 응답 하나에 코드블록 하나만 보인다(`docs/view_spec.md`).

---

### workflow: 에이전트 관계 그래프와 백그라운드 작업

**설명**: HUD `FLOW` 화면. 왼쪽 큰 카드는 에이전트 지식 그래프다. 최상위 에이전트를 허브로 두고, 그 에이전트만 가진 능력(세션이 쓰는 도구, 위임하는 sub-agent, Focus 영역, orchestrate)을 바깥쪽 세로 줄의 잎으로 두어 허브에서 직선으로 잇고, 여럿이 함께 쓰는 도구를 아래 상자에 두고 주인들과 잇는다. 잎이 많으면 그림이 자라고 휠과 끌기로 확대, 축소, 이동한다. 위임은 (부른 쪽, 받는 쪽) 쌍마다 하나의 간선(허브 사이는 맨 위 띠로 올라가는 아치)으로 그린다. 진행 중 위임은 흐르는 점선, 마지막 위임이 실패한 쌍은 빨간 선이다. 오른쪽은 지금 세션의 에이전트 지도다. 보는 세션의 에이전트가 뿌리 카드(이름, 모델, 마지막 턴이 읽은 토큰)이고, 그 세션에서 나간 위임이 오른쪽 열의 카드(상태 점, 맡긴 일, 받는 쪽, 걸린 시간, 받는 쪽이 쓴 토큰), 받는 쪽이 다시 맡긴 것은 다음 열이다. `ask` 카드를 누르면 받는 쪽 세션으로 간다. 아래는 스케줄, 성찰 daemon, 기억 정리, 외부 조회의 마지막 실행 표인데 기본으로 접혀 있고 머리줄에 개수와 실행 중, 실패 수만 보인다.

**입력과 결과**

| 입력 | 결과 |
|---|---|
| `GET /api/workflow?session=<id>` | `agents`, `subagents`, `capabilities`(도구마다 그 도구를 쓰는 에이전트, 한 에이전트만 가진 것이 먼저), `edges`(최근 위임 200개, 오래된 것부터. 간선마다 `session_id` 와 받는 쪽이 쓴 `tokens`. `workflow.backend=postgres` 면 기동 때 저장소에서 읽어 온 지난 위임도 든다), `root`(세션을 줬을 때. 그 세션의 에이전트, 모델, `context_tokens`) |
| `GET /api/jobs` | `jobs`(스케줄은 돈 적 없는 것도, 그 뒤에 다른 작업), `daemon`(성찰 주기 설정) |
| ws `workflow_changed{edge}` | 위임이 열리거나 닫힐 때 한 건 |
| ws `job_changed{job}` | 작업이 시작하거나 끝날 때 한 건 |

**처리 흐름**: 위임은 `SessionRegistry.on_open` 이 세션마다 구독한 이벤트를 `WorkflowTracker.observe` 가 읽는다. `ask_agent`, `agent_<이름>`, `orchestrate` 도구 호출의 시작과 끝, Focus `focus_panel` 의 busy 신호가 간선이 된다(부른 세션 id 를 간선에 적는다). 받는 쪽 세션(`peer-<부른 쪽>-<받는 쪽>`)의 턴이 끝나면 루프가 `agent_end` 에 그 턴의 사용량 합(`usage`)을 실어 보내고, tracker 가 그 세션으로 열려 있는 `ask` 간선에 토큰을 더한다(받는 쪽의 `agent_end` 가 부른 쪽의 `tool_execution_end` 보다 먼저 온다). 작업은 `SchedulerService._run`, `ExternalEventPoller.tick`(조회할 소스가 있을 때만), `web_lifecycle` 의 daemon 대상(성찰, 기억 정리)이 `JobBoard` 에 시작과 끝을 적는다. 바뀔 때마다 `WebState.broadcast_live` 로 열린 HUD 전부에 보내고 `WorkflowStore` 에 적는다(간선은 `edge_id`, 작업은 `job_id` 로 upsert). 기동 때 `WebLifecycle.start` 가 작업이 돌기 전에 저장소의 최근 간선 200개와 작업 기록을 읽어 와 `runs` 가 이어진다. 재시작 때 끝나지 않은 간선과 돌던 작업은 끝을 볼 수 없어 결과 모름으로 닫는다.

**구현 파일**

| 파일 | 층 | 역할 |
|---|---|---|
| `src/ash_industry/core/workflow/workflow_types.py` | core | `DelegationEdge`, `JobRecord` |
| `src/ash_industry/core/workflow/workflow_store.py` | core | 간선과 작업 기록 저장소 기본 클래스(메모리) |
| `src/ash_industry/core/workflow/workflow_postgres_store.py` | core | PostgreSQL 저장소(`ash_workflow_edges`, `ash_workflow_jobs`) |
| `src/ash_industry/core/workflow/workflow_tracker.py` | core | 세션 이벤트를 위임 간선으로 |
| `src/ash_industry/core/workflow/job_board.py` | core | 작업별 마지막 실행 기록과 변경 알림 |
| `src/ash_industry/ui/web/router/workflow_router.py` | ui | `GET /api/workflow`(에이전트별 능력 `capability_map` 포함), `GET /api/jobs` |
| `src/ash_industry/ui/web/static/app/workflow.js` | ui | SVG 그래프, 세션의 에이전트 지도(`mapTree` 가 간선을 세션과 받는 쪽 세션으로 잇는다), 접히는 작업 표 |
| `src/ash_industry/agent_layer/loop.py` | agent | 턴의 LLM 호출 사용량을 더해 `AgentEndEvent.usage` 로 |

**테스트**

| 종류 | 파일 |
|---|---|
| 단위 | `tests/unit/test_workflow_workflow_tracker.py` |
| 단위 | `tests/unit/test_workflow_job_board.py` |
| 단위 | `tests/unit/test_workflow_workflow_store.py` |
| 단위 | `tests/unit/test_workflow_workflow_postgres_store.py` |
| 통합 | `tests/integ/test_workflow.py` |

**제약과 미구현**: 기본(`in_memory`)이면 재시작할 때 그래프가 비고 `runs` 가 0 부터 다시 센다. postgres 백엔드도 간선은 최근 1000개까지만 남긴다. sub-agent 세션 안에서 다시 맡긴 위임은 보이지 않는다(그 세션은 Web 세션 목록 밖에서 만든다). 지도의 토큰은 받는 쪽 세션이 따로 있는 `ask` 에만 붙고 in-process sub-agent, orchestrate, Focus 는 시간만 보인다. 이 필드가 생기기 전의 간선은 세션을 몰라 지도에 안 나온다. 잎 줄이 길거나 허브가 많으면 그림이 커져 기본 배율에서 글자가 작아진다(휠로 확대한다. 끌어서 옮긴 자리는 브라우저 `localStorage` 에만 남는다). 공통 능력은 아래 상자에 줄지어 겹치지 않는다(`docs/view_spec.md`). `goal` 은 스케줄(`goal-<id>`)로만 보인다.

---

## 공통 모듈

여러 기능이 함께 쓰는 파일.

| 파일 | 역할 | 쓰는 기능 |
|---|---|---|
| `src/ash_industry/ash_config.py` | `settings.yaml`, env, `.env` 에서 읽는 전체 설정 | 전체 |
| `src/ash_industry/common/logger.py` | structlog 로거 설정. 출력 형식은 `LOG_FORMAT`(`console` 기본, `json`), 레벨은 `ASH_LOG_LEVEL`(기본 `INFO`) | 전체 |
| `src/ash_industry/core/session.py` | `AgentSession`: 보안, 플러그인, 스킬, 사고, proactive 를 묶어 한 턴과 성찰 실행 | 전체 |
| `src/ash_industry/agent_layer/agent_types.py` | 루프 이벤트, 실행 컨텍스트, 루프 설정 | 전체 |
| `src/ash_industry/app/app_assembly.py` | 기동 한 번의 조립 결과 | 전체 |
| `src/ash_industry/app/app_context.py` | 화면이 붙잡는 앱 단위 인프라 묶음 | 전체 |
| `src/ash_industry/app/app_services.py` | 세션 생성 때 넘기는 앱 단위 서비스 묶음 | 전체 |
| `src/ash_industry/app/infra_builder.py` | 도구, 메모리, 저장소, 보안, 스케줄러, proactive, 슬래시 명령 조립 | 전체 |
| `src/ash_industry/app/session_builder.py` | `AgentProfile` 과 서비스로 `AgentSession` 조립 | 전체 |
| `src/ash_industry/app/agent_profile.py` | 에이전트 한 명분 정체성, 모델, 사고와 proactive 설정 | agent_registry, thought, proactive |
| `src/ash_industry/core/tools/tools_registry.py` | `AshTool` 기반 클래스와 `ToolRegistry` | tools, mcp, extension, goal, scheduler, memory, task_pattern, multi_agent, agent_conversation, procedures |
| `src/ash_industry/core/slash/dispatcher.py` | 텍스트의 `/command` 를 핸들러로 실행하고 `/help` 제공 | 모든 슬래시 명령 기능 |
| `src/ash_industry/core/slash/ops_cmd.py` | `/sessions`, `/branch`, `/tools`, `/compact` 핸들러 | session, tools, memory |
| `src/ash_industry/model_layer/model_types.py` | 메시지, 콘텐츠 블록, 스트림 이벤트, 모델 설정 타입 | 전체 |
| `src/ash_industry/model_layer/model_registry.py` | 이름으로 LLM 프로바이더 등록과 조회 | 전체 |
| `src/ash_industry/model_layer/stream.py` | 프로바이더 스트리밍과 메시지 수집 | agent_loop, thought, openloop, journal, usermodel, procedures, memory, focus |
| `src/ash_industry/model_layer/providers/provider_base.py` | 프로바이더 기본 클래스 | agent_loop |
| `src/ash_industry/model_layer/providers/anthropic.py` | Anthropic 스트리밍(프롬프트 캐싱) | agent_loop |
| `src/ash_industry/model_layer/providers/openai.py` | OpenAI 스트리밍 | agent_loop |
| `src/ash_industry/model_layer/providers/gemini.py` | Gemini 스트리밍 | agent_loop |
| `src/ash_industry/model_layer/providers/ollama.py` | Ollama NDJSON 스트리밍. id 없이 온 도구 호출에는 `{이름}_{순번}` id 를 붙여, 같은 도구를 두 번 불러도 호출이 합쳐지지 않는다 | agent_loop |
| `src/ash_industry/model_layer/providers/vllm.py` | vLLM SSE 스트리밍 | agent_loop |
| `src/ash_industry/model_layer/embeddings.py` | 임베딩 프로바이더 | memory, openloop |
| `src/ash_industry/ui/ui_protocol.py` | 화면이 이벤트, 스트림, 승인, 오류를 받는 기본 어댑터 | web_hud |
| `src/ash_industry/ui/web/web_state.py` | Web 라우터가 같이 보는 실행 상태 | web_hud, focus, voice, notify, agent_conversation, thought, workflow |
| `src/ash_industry/ui/web/router/ws_router.py` | `/ws` 연결 수명과 메시지 분기 | agent_loop, approval, focus, proactive, thought, voice, notify |
| `src/ash_industry/ui/web/ws_tasks.py` | ws 메시지가 띄우는 프롬프트, STT, TTS, 분류 작업 | agent_loop, voice, thought, proactive |
| `src/ash_industry/ui/web/adapter.py` | 에이전트 이벤트를 연결 하나로 보내는 어댑터 | web_hud 의 모든 ws 이벤트 |
| `src/ash_industry/ui/web/session_registry.py` | Web 세션 생성, 조회, 삭제, 스케줄 결과를 건넬 세션 고르기 | session, scheduler, agent_registry, web_hud |
| `src/ash_industry/ui/web/web_schema.py` | REST 요청 본문 모델 | session, openloop, scheduler, notify |
| `src/ash_industry/ui/web/router/agenda_router.py` | `GET /api/agenda`, `POST /api/openloops/{loop_id}`, `POST /api/schedules/{name}` | openloop, scheduler, goal |
| `src/ash_industry/ui/web/router/tool_router.py` | `GET /api/tools`, `GET /api/slash-commands` | tools, 모든 슬래시 명령 기능 |
| `src/ash_industry/ui/web/static/app/api.js` | REST 호출과 접근 키 저장 | web_hud, policy, session, openloop, tools, agent_registry, voice |
| `src/ash_industry/ui/web/static/app/ws.js` | WebSocket 전송 | web_hud 전체 |
| `src/ash_industry/ui/web/static/app/events.js` | 서버 이벤트를 화면 변화로 | web_hud 전체 |
| `src/ash_industry/ui/web/static/app/messages.js` | CONVERSATION 메시지 DOM | agent_loop, thought, proactive, scheduler |
| `src/ash_industry/ui/web/static/app/markdown.js` | 의존 없는 마크다운 렌더 | agent_loop, focus, scheduler, proactive |
| `src/ash_industry/ui/web/static/app/composer.js` | 입력창, 슬래시 자동완성, Ctrl+K 중단 | agent_loop, 모든 슬래시 명령 기능, voice |
| `src/ash_industry/ui/web/static/app/agenda.js` | AGENDA 카드와 스케줄 알림 | openloop, scheduler, goal |
