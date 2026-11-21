---
sidebar_position: 0
title: main 에이전트
---

# main 에이전트

main 은 처음부터 있는 기본 에이전트다(id `main`). 사용자의 기본 대화 상대이면서, 팀 에이전트가 더 잘하는 일은 나눠 맡기는 창구다. 묻는 말에 답하는 데서 그치지 않고, 묻기 전에 먼저 생각하고 필요하면 먼저 말을 건다. 기본 브랜드 이름은 `A.S.H.` 이고 설정으로 바꾼다.

![main 세션의 Web HUD. 리액터 구체와 AGENDA, ACTIVITY, SYSTEM, SESSIONS, CONVERSATION 카드](/img/agents/ash-hud.png)

## 맡은 일

- 사용자의 요청에 답하고, 앱에 등록된 도구(파일, 셸, 웹 검색, 알림 예약, 목표, MCP, 절차 도구)를 쓴다
- 요청마다 판단을 남기고([Inner Thought](../concepts/conversation/inner-thought.md)), 요청이 없는 시간에는 성찰해서 먼저 말을 건넨다([Proactive Dialogue](../concepts/conversation/proactive.md))
- 대화에서 흘린 약속을 기억했다가 챙긴다([Open loop](../concepts/conversation/open-loop.md))
- 팀 에이전트가 더 잘하는 일은 `ask_agent` 로 맡긴다([팀 에이전트 추가하기](./new-agent.md))

## 설정

main 은 정의 파일 없이 환경 변수나 `~/.ash/settings.yaml` 로 설정한다. `team/` 에 `main.yaml` 을 두어도 읽지 않는다.

| 항목 | 환경 변수 | settings.yaml | 기본값 |
|---|---|---|---|
| 이름 | `ASH_BRAND__NAME` | `brand.name` | `A.S.H.` |
| 명언 | `ASH_BRAND__QUOTE` | `brand.quote` | `System Online` |
| 메인 색 | `ASH_BRAND__PALETTE__PRIMARY` | `brand.palette.primary` | `#e6e8ea` |
| 보조 색 | `ASH_BRAND__PALETTE__ACCENT` | `brand.palette.accent` | `#f0642d` |
| 말투 | `ASH_BRAND__PERSONA` | `brand.persona` | `ash_config.py` 의 `DEFAULT_PERSONA` |
| 모델 | `ASH_LLM__*` | `llm.*` | [Quick Start](../start/install.md)에서 고른 프로바이더 |

기본 말투는 침착한 업무 비서다. 결론과 숫자를 먼저 말하고, 문서 서식 없이 구어체로 답하며, 모르는 것은 추측하지 않는다. 말투는 대화 답변, 먼저 건네는 말, filler 에 같이 쓰인다.

```yaml
# ~/.ash/settings.yaml
brand:
  name: "M.A.X."
  quote: "Ready"
  persona: |
    너는 짧고 정확하게 말하는 운영 담당자다.
```

settings.yaml 이 환경 변수보다 앞선다. 팀 에이전트는 비운 항목을 main 설정에서 이어받는다. 전체 설정 키는 [서비스 설정 값](../reference/configuration.md)에 있다.

## 도구

main 은 정의 파일이 없어 도구 목록이 비어 있고, 그래서 앱 레지스트리에 등록된 도구 전체를 쓴다. 팀 에이전트는 정의 파일의 `tools` 에 적은 도구만 받으므로, 셸과 파일 쓰기처럼 권한이 큰 도구를 기본으로 가진 에이전트는 main 하나다.

### 내장 도구

서버가 뜰 때 항상 등록된다(`app/infra_builder.py` 의 `build_tool_registry`).

| 도구 | 하는 일 | 승인 |
|---|---|---|
| `bash` | 셸 명령. 기본 타임아웃 30초 | 필요 |
| `write_file` | 파일 쓰기. 부모 디렉토리 생성, 덮어쓰기 | 필요 |
| `edit_file` | 문자열 정밀 교체 | 필요 |
| `read_file` | 라인 범위 읽기 | |
| `glob` | 패턴으로 파일 찾기, 최근 수정순 | |
| `grep` | 정규식 검색, 바이너리 건너뜀 | |
| `list_dir` | 디렉토리 나열 | |
| `web_search` | Brave(키 있으면) 또는 DuckDuckGo | |
| `web_fetch` | URL 본문을 텍스트로 | |

승인이 필요한 도구에서 **항상 허용** 을 고르면 규칙이 `~/.ash/approvals/main.yaml` 에 쌓인다. 대조 방식은 [Tool & Approve System](../concepts/conversation/tools-and-approval.md#승인-기억)에 있다.

### 설정과 실행 중에 붙는 도구

| 도구 | 언제 붙나 | 자세히 |
|---|---|---|
| `agent_<name>`, `orchestrate` | 서브 에이전트 정의가 있을 때 | [Orchestration Pattern](../concepts/multi-agent-orchestration/orchestration-pattern.md) |
| `schedule` | 스케줄러가 켜져 있을 때(`ASH_SCHEDULER__ENABLED`, 기본 켜짐) | [Scheduling](../concepts/conversation/scheduling.md) |
| `goal` | 스케줄러가 켜져 있을 때. 계속 맡길 목표를 맡기고, 목록을 보고, 멈춘다 | [Goals](../concepts/conversation/goals.md) |
| `procedure_<name>` | 여러 도구로 성공한 작업을 절차로 승인했을 때 | [Memory Management](../concepts/memory.md) |
| MCP 서버의 도구 | MCP 서버를 연결했을 때 | [Extension](../concepts/extension.md#mcp-서버) |
| 사용자 도구 | `~/.ash/tools/` 에 도구 파일을 두었을 때 | [Extension](../concepts/extension.md#도구) |

사용자 도구와 MCP 도구는 같은 이름의 내장 도구를 덮어쓴다. 확장 패키지가 등록한 에이전트 전용 도구는 main 레지스트리에 들어가지 않는다. 정의 파일의 `tools` 에 그 이름을 적은 팀 에이전트만 받는다([Extension](../concepts/extension.md#확장-패키지)).

### 모든 에이전트가 함께 쓰는 도구

| 도구 | 하는 일 |
|---|---|
| `ask_agent` | 다른 최상위 에이전트에게 일을 맡긴다. 에이전트가 둘 이상일 때만 있다([Multi agent Orchestration](../concepts/multi-agent-orchestration/index.md#에이전트끼리-대화)) |
| `remember_task_pattern` | 사용자가 알려 준 작업 방식을 부른 에이전트의 작업 패턴으로 저장한다([Memory Management](../concepts/memory.md#작업-패턴)) |
| `recall_episodes` | 최근 3턴보다 앞의 지난 턴을 작업 종류, 성패, 기간으로 골라 읽는다([Memory Management](../concepts/memory.md#턴마다-일어나는-일)) |

## 부르는 방법

- `ash-industry` 로 띄우고 Web HUD 나 데스크톱 앱을 열면 main 과 대화한다
- 에이전트가 둘 이상이면 Web HUD 리액터 구체 양옆의 화살표를 누르거나 구체를 좌우로 밀어 main 으로 돌아온다
