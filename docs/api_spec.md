# Ash Industry Web HUD API 명세

| 항목 | 값 |
|---|---|
| Last Updated | 2026-11-03 |
| Base URL | `http://localhost:7777` (Docker `web` 프로파일, nginx 가 `/api/`, `/ws`, `/brand.js`, `/manifest.json` 을 백엔드로 프록시하고 `/m/` 에서 모바일 앱 빌드 결과를 서빙. 포트는 127.0.0.1 에만 열리고 밖에서는 `tailscale serve` 로 들어온다) |
| 데이터 포맷 | JSON (UTF-8) |
| 인증 | 기본 없음. `ASH_SECURITY__API_KEYS` 가 비어 있지 않으면 `/api/*` 와 `/ws` 가 키를 요구한다 |

> `Last Updated`는 **문서 내용이 실제로 바뀐 날**만 적는다. 코드가 그대로인 채로 문서를
> 다시 생성했다면 이 값도 그대로다. 시각은 적지 않는다.

---

## 목차

1. [개요](#개요)
2. [공통 규약](#공통-규약)
3. [세부 API 명세](#세부-api-명세)
   - [GET /api/auto-approve](#get-apiauto-approve)
   - [PUT /api/auto-approve/{agent}](#put-apiauto-approveagent)
   - [GET /api/agents](#get-apiagents)
   - [GET /api/agenda](#get-apiagenda)
   - [GET /api/health](#get-apihealth)
   - [GET /api/jobs](#get-apijobs)
   - [POST /api/openloops/{loop_id}](#post-apiopenloopsloop_id)
   - [GET /api/platform/metrics](#get-apiplatformmetrics)
   - [GET /ion/status](#get-ionstatus)
   - [POST /ion/incidents/{incident_id}/respond](#post-ionincidentsincident_idrespond)
   - [POST /ion/restart](#post-ionrestart)
   - [GET /ion/incidents](#get-ionincidents)
   - [GET /ion/logs](#get-ionlogs)
   - [GET /ion/events](#get-ionevents)
   - [GET /api/push/vapid](#get-apipushvapid)
   - [PUT /api/push/subscriptions](#put-apipushsubscriptions)
   - [DELETE /api/push/subscriptions](#delete-apipushsubscriptions)
   - [POST /api/schedules/{name}](#post-apischedulesname)
   - [GET /api/sessions](#get-apisessions)
   - [POST /api/sessions](#post-apisessions)
   - [GET /api/sessions/{session_id}/messages](#get-apisessionssession_idmessages)
   - [DELETE /api/sessions/{session_id}](#delete-apisessionssession_id)
   - [POST /api/sessions/{session_id}/branch](#post-apisessionssession_idbranch)
   - [GET /api/settings](#get-apisettings)
   - [PUT /api/settings](#put-apisettings)
   - [POST /api/restart](#post-apirestart)
   - [GET /api/slash-commands](#get-apislash-commands)
   - [GET /api/tools](#get-apitools)
   - [POST /api/uploads](#post-apiuploads)
   - [GET /api/docs/structure](#get-apidocsstructure)
   - [POST /api/docs/plan](#post-apidocsplan)
   - [POST /api/docs/apply](#post-apidocsapply)
   - [GET /api/docs/fields](#get-apidocsfields)
   - [POST /api/docs/templates](#post-apidocstemplates)
   - [GET /api/voice/phrases/{name}](#get-apivoicephrasesname)
   - [GET /api/workflow](#get-apiworkflow)
   - [GET /api/workflow/layout](#get-apiworkflowlayout)
   - [PUT /api/workflow/layout](#put-apiworkflowlayout)
   - [GET /api/mcp/policy](#get-apimcppolicy)
   - [PUT /api/mcp/policy](#put-apimcppolicy)
   - [GET /api/mcp/audit](#get-apimcpaudit)
   - [GET /brand.js](#get-brandjs)
   - [GET /manifest.json](#get-manifestjson)
   - [WS /ws](#ws-ws)
4. [데이터 모델](#데이터-모델)

---

## 개요

Web HUD(`src/ash_industry/ui/web/static/`)가 쓰는 백엔드 인터페이스다. 대화는 전부 WebSocket `/ws` 로 오가고, REST 는 화면 옆 카드(세션 목록, AGENDA, 도구 목록)를 채우거나 상태를 바꾸는 데만 쓴다. 정본은 백엔드의 세션 저장소(Postgres 또는 jsonl), 스케줄러, open loop 저장소이고 이 API 는 그 투영이다. 카드는 변경 알림 이벤트가 따로 없어서 프론트가 접속 직후, 응답이 끝날 때, 조작 직후, 그리고 1분마다 REST 를 다시 부른다. Workflow 화면만 ws `workflow_changed`, `job_changed` 로 바뀐 한 건씩을 받는다.

소스: 앱 조립과 인증 미들웨어 `src/ash_industry/ui/web/server.py`, 접근 키 확인 `web_auth.py`, 요청 본문 모델 `web_schema.py`, REST 라우터 `router/agent_router.py`, `agenda_router.py`, `brand_router.py`, `push_router.py`, `session_router.py`, `settings_router.py`, `tool_router.py`, `voice_router.py`, `workflow_router.py`, WebSocket 라우터 `router/ws_router.py`(메시지가 띄우는 작업은 `ws_tasks.py`, 이벤트 전송은 `adapter.py`, 승인은 `approvals.py`). 경로는 모두 `src/ash_industry/ui/web/` 아래다.

---

## 공통 규약

**에러 응답**

핸들러가 판정한 오류는 아래 모양이다.

```json
{ "error": "사람이 읽을 수 있는 메시지" }
```

422 만 FastAPI 기본 모양 `{"detail": [{"type", "loc", "msg", "input", ...}]}` 이다.

| 상태 코드 | 언제 |
|---|---|
| 200 | 정상 |
| 400 | 본문 값이 허용 범위 밖 (`status`, `enabled`) |
| 401 | 인증이 켜져 있는데 키가 없거나 틀림 (`/api/*`). 본문 `{"error": "unauthorized"}` |
| 404 | 대상 없음 (open loop, 스케줄, 읽기 문구) |
| 422 | 본문 모델이 있는 엔드포인트(`POST /api/openloops/{loop_id}`, `POST /api/schedules/{name}`, `POST /api/sessions`, `PUT /api/settings`)에서 FastAPI 가 본문을 JSON 으로 못 읽거나, 본문이 필수인데 없음 |

**인증**: `ASH_SECURITY__API_KEYS` 에 키가 등록돼 있을 때만. `Authorization: Bearer <key>` 헤더 또는 `?token=<key>` 쿼리. `/ws` 는 쿼리만 받고 틀리면 close code `4401` 로 끊는다. 정적 셸(`/`, js, css)은 항상 열려 있다.

**페이지네이션**: 없음. 목록이 전부 작다. open loop 는 20개까지만 돌려준다.

**공통 헤더**: 없음. 서버 미들웨어가 `/api/` 로 시작하지 않는 모든 응답(정적 셸, `/brand.js`, `/manifest.json`)에 `Cache-Control: no-cache` 를 붙인다(응답에 이미 있으면 그대로 둔다). `/api/*` 에는 붙지 않는다.

---

## 세부 API 명세

경로 알파벳순.

### GET /api/auto-approve

최상위 에이전트마다 auto mode(승인 자동 허용)가 켜졌는지. HUD 입력 독의 AUTO 와 SET 의 AUTO MODE 카드가 받는다.

#### Endpoint

```
GET /api/auto-approve
```

#### 호출 규약

| 항목 | 값 |
|---|---|
| Method | `GET` |
| 인증 | 설정 시 필요 |
| 응답 Content-Type | `application/json` |

#### Response Body

| 필드 | 타입 | 설명 |
|---|---|---|
| `agents` | object[] | `{id, name, enabled}`. 순서는 `/api/agents` 와 같다 |

#### 호출 예시

```bash
$ curl -s http://localhost:7777/api/auto-approve
{"agents":[{"id":"main","name":"A.S.H.","enabled":false},{"id":"evi","name":"E.V.I.","enabled":true}]}
```

#### 특이사항

**재호출**: 상태를 바꾸지 않는다.

---

### PUT /api/auto-approve/{agent}

그 에이전트의 auto mode 를 켜거나 끈다. `~/.ash/auto_approve.yaml`(`ASH_SECURITY__AUTO_APPROVE_PATH`)에 저장하고 열린 세션도 다음 도구 호출부터 따른다. 켜진 에이전트는 승인 모달이 뜰 호출(`security.require_approval_for`, MCP ask)을 묻지 않고 실행한다. 위험 명령, MCP 정책 deny, 프로필 `never` 는 켜도 막힌다. 스케줄과 목표 같은 무인 실행에는 적용하지 않는다.

#### Endpoint

```
PUT /api/auto-approve/{agent}
```

#### 호출 규약

| 항목 | 값 |
|---|---|
| Method | `PUT` |
| 인증 | 설정 시 필요 |
| 요청 Content-Type | `application/json` |
| 응답 Content-Type | `application/json` |

#### Request Body

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `enabled` | boolean | 예 | 켤지. `"yes"` 같은 글은 받지 않는다(strict) |

#### 응답 코드

| 코드 | 의미 | 본문 |
|---|---|---|
| `200` | 저장함 | `GET` 과 같은 스키마 |
| `404` | 모르는 에이전트 | `{"error": "unknown agent: <id>"}` |
| `422` | `enabled` 가 bool 이 아니거나 모르는 필드 | FastAPI 검증 오류 |

#### 호출 예시

```bash
$ curl -s -X PUT http://localhost:7777/api/auto-approve/evi -H 'Content-Type: application/json' -d '{"enabled":true}'
{"agents":[{"id":"main","name":"A.S.H.","enabled":false},{"id":"evi","name":"E.V.I.","enabled":true}]}
```

#### 특이사항

**재호출**: 같은 값을 다시 보내면 파일과 응답이 같다.

---

### GET /api/agents

이 서버에 뜬 최상위 에이전트 목록. main 이 첫 번째이고, 나머지는 정의 파일(`ASH_TEAM__DIR/<id>.yaml`) 이름순.

#### Endpoint

```
GET /api/agents
```

#### 호출 규약

| 항목 | 값 |
|---|---|
| Method | `GET` |
| 인증 | 설정 시 필요 |
| 요청 Content-Type | 없음 (본문 없음) |
| 응답 Content-Type | `application/json` |
| 필수 헤더 | 없음 |

#### Request Body

없음.

#### Query / Path 파라미터

| 파라미터 | 위치 | 타입 | 필수 | 기본값 | 설명 |
|---|---|---|---|---|---|
| 없음 | | | | | |

#### Response Body

| 필드 | 타입 | 널 허용 | 설명 |
|---|---|---|---|
| `agents` | `Agent[]` | 아니오 | [Agent](#agent) 목록. 최소 main 하나 |

#### 응답 코드

| 코드 | 의미 | 본문 |
|---|---|---|
| `200` | 정상 | 위 스키마 |

#### 호출 예시

```bash
$ curl -s http://localhost:7777/api/agents
{"agents":[{"id":"main","name":"A.S.H.","description":"","quote":"System Online","palette":{"primary":"#e6e8ea","accent":"#f0642d","background":"#14161a","nebula":["#ffb38a","#f0642d","#d9481a"]},"main":true},{"id":"scribe","name":"S.C.R.I.B.E.",...,"main":false}]}
```

#### 특이사항

**재호출**: 상태를 바꾸지 않는다. 정의 파일은 기동 때 한 번 읽는다. 파일을 고치면 서버를 다시 띄워야 목록이 바뀐다. 모델과 시스템 프롬프트는 내보내지 않는다.

---

### GET /api/agenda

AGENDA 카드가 보여줄 스케줄 작업, 열린 open loop, 최근 닫힌 open loop.

#### Endpoint

```
GET /api/agenda
```

#### 호출 규약

| 항목 | 값 |
|---|---|
| Method | `GET` |
| 인증 | 설정 시 필요 |
| 요청 Content-Type | 없음 (본문 없음) |
| 응답 Content-Type | `application/json` |
| 필수 헤더 | 없음 |

#### Request Body

없음.

#### Query / Path 파라미터

| 파라미터 | 위치 | 타입 | 필수 | 기본값 | 설명 |
|---|---|---|---|---|---|
| 없음 | | | | | |

#### Response Body

| 필드 | 타입 | 널 허용 | 설명 |
|---|---|---|---|
| `schedules` | `Schedule[]` | 아니오 | 스케줄러가 없으면 빈 배열. 다음 실행이 가까운 순, 다음 실행이 없는 것(꺼짐, 만료)은 뒤 |
| `open_loops` | `OpenLoop[]` | 아니오 | 상태가 `open` 인 것만, 최신순 최대 20개. 기한이 지난 것은 응답 전에 닫혀 빠진다 |
| `closed_loops` | `ClosedLoop[]` | 아니오 | 상태가 `done`, `dismissed`, `expired` 인 것, 마지막으로 바뀐 순 최대 10개. 항목은 `id`, `description`, `status`, `updated_at`(epoch ms), `due_ms`, `agent`. 저장소가 꺼져 있으면 빈 배열 |

#### 응답 코드

| 코드 | 의미 | 본문 |
|---|---|---|
| `200` | 정상 | 위 스키마 |

#### 호출 예시

```bash
$ curl -s http://localhost:7777/api/agenda
{"schedules": [], "open_loops": [{"id": "e17dc364ae404c6c9d341b69a3a12b79", "description": "내일 오전 10시 회의의 구체적인 아젠다 및 발표 범위 확정", "due_ms": null, "created_at": 1791613276663, "origin_session": "default", "agent": "main"}], "closed_loops": [{"id": "a03c5e1f", "description": "보고서 보내기", "status": "done", "updated_at": 1791613276663, "due_ms": null, "agent": "main"}]}
```

#### 특이사항

**재호출**: 응답 전에 기한이 지난 open loop 를 `expired` 로 닫는다. 기한 뒤 `ASH_OPENLOOP__EXPIRE_AFTER_SEC`(기본 6시간)가 지났거나, 기한 없이 `ASH_OPENLOOP__MAX_AGE_SEC`(기본 7일)보다 오래된 것이다. 이미 닫힌 건 다시 보지 않으므로 몇 번 불러도 결과가 같다. 그 밖의 상태는 바꾸지 않는다. `next_run` 은 호출 시각 기준으로 계산하므로 같은 요청이라도 값이 흘러간다.

`next_run`, `run_until` 은 서버 로컬 시간대 오프셋이 붙은 ISO 8601 이다. 컨테이너의 `TZ` 를 따른다.

---

### GET /api/health

백엔드가 떠 있는지와 패키지 버전. 데스크톱 셸(`desktop/backend_launcher.js`)이 백엔드를 띄울지 정할 때 쓴다.

#### Endpoint

```
GET /api/health
```

#### 호출 규약

| 항목 | 값 |
|---|---|
| Method | `GET` |
| 인증 | 설정 시 필요 |
| 요청 Content-Type | 없음 (본문 없음) |
| 응답 Content-Type | `application/json` |
| 필수 헤더 | 없음 |

#### Request Body

없음.

#### Query / Path 파라미터

| 파라미터 | 위치 | 타입 | 필수 | 기본값 | 설명 |
|---|---|---|---|---|---|
| 없음 | | | | | |

#### Response Body

| 필드 | 타입 | 널 허용 | 설명 |
|---|---|---|---|
| `ok` | boolean | 아니오 | 늘 `true` |
| `version` | string | 아니오 | 설치된 `ash-industry` 패키지 버전(`pyproject.toml`). 설치하지 않고 돌리면 `0.0.0` |

#### 응답 코드

| 코드 | 의미 | 본문 |
|---|---|---|
| `200` | 정상 | 위 스키마 |
| `401` | 인증이 켜져 있는데 키가 없음 | `{"error": "unauthorized"}` |

#### 호출 예시

```bash
$ curl -s http://localhost:7777/api/health
{"ok":true,"version":"0.2.0"}
```

#### 특이사항

**재호출**: 상태를 바꾸지 않는다. 접근 키를 켜도 키 없이 200 이다(데스크톱 셸이 키 없이 살아 있는지 본다).

---

### GET /api/jobs

백그라운드 작업(스케줄, 성찰 daemon, 기억 정리, 외부 조회)의 마지막 실행. Workflow 화면의 표가 쓴다.

#### Endpoint

```
GET /api/jobs
```

#### 호출 규약

| 항목 | 값 |
|---|---|
| Method | `GET` |
| 인증 | 설정 시 필요 |
| 요청 Content-Type | 없음 (본문 없음) |
| 응답 Content-Type | `application/json` |
| 필수 헤더 | 없음 |

#### Request Body

없음.

#### Query / Path 파라미터

| 파라미터 | 위치 | 타입 | 필수 | 기본값 | 설명 |
|---|---|---|---|---|---|
| 없음 | | | | | |

#### Response Body

| 필드 | 타입 | 널 허용 | 설명 |
|---|---|---|---|
| `jobs` | `Job[]` | 아니오 | [Job](#job). 스케줄이 먼저(이름순, 돈 적 없는 것도 `runs: 0` 으로), 그 뒤 다른 작업(`job_id` 순) |
| `daemon` | object | 아니오 | `enabled`, `trigger`(`interval`/`idle`/`both`), `interval_sec`, `idle_sec`. 성찰 주기 설정 |

#### 응답 코드

| 코드 | 의미 | 본문 |
|---|---|---|
| `200` | 정상 | 위 스키마 |

#### 호출 예시

```bash
$ curl -s http://localhost:7777/api/jobs
{"jobs":[{"job_id":"schedule:morning","kind":"schedule","label":"아침 브리핑","runs":3,"running":false,"last_started_ms":1791613276663,"last_ended_ms":1791613281000,"last_ok":true,"last_error":"","enabled":true,"next_run":"2026-11-04T09:00:00+09:00","agent":"main"}],"daemon":{"enabled":true,"trigger":"interval","interval_sec":120,"idle_sec":180}}
```

#### 특이사항

**재호출**: 상태를 바꾸지 않는다. 실행 기록은 `ASH_WORKFLOW__BACKEND=postgres` 면 `ash_workflow_jobs` 에 남아 재시작 뒤에도 `runs` 가 이어진다. 기본(`in_memory`)이면 재시작하면 `runs` 가 0 부터 다시 세고 `last_*` 가 null 이 된다. 재시작 때 돌던 작업은 `running: false`, `last_ok: null` 로 돌아온다. 성찰과 기억 정리는 세션이 여럿이어도 작업 하나(`proactive:reflect`, `memory:consolidate`)로 센다. 외부 조회는 실제로 조회할 소스가 있을 때만 센다.

---

### GET /api/platform/metrics

백엔드 프로세스 자원, 이벤트 루프 지연, 에이전트별 작업 상태. Ion 가 밖에서 주기적으로 읽어 사고를 판정한다.

#### Endpoint

```
GET /api/platform/metrics
```

#### 호출 규약

| 항목 | 값 |
|---|---|
| Method | `GET` |
| 인증 | 설정 시 필요 |
| 요청 Content-Type | 없음 (본문 없음) |
| 응답 Content-Type | `application/json` |
| 필수 헤더 | 없음 |

#### Request Body

없음.

#### Query / Path 파라미터

| 파라미터 | 위치 | 타입 | 필수 | 기본값 | 설명 |
|---|---|---|---|---|---|
| 없음 | | | | | |

#### Response Body

| 필드 | 타입 | 널 허용 | 설명 |
|---|---|---|---|
| `at_ms` | integer | 아니오 | 읽은 시각(epoch ms) |
| `process` | object | 아니오 | `pid`, `rss_bytes`, `cpu_percent`(직전 호출부터의 구간 평균), `threads`, `open_fds`(못 재면 null), `asyncio_tasks`, `uptime_sec` |
| `loop_lag` | object | 아니오 | `last_ms`, `max_ms`(최근 60초 최대), `samples`. 1초마다 잠들고 늦게 깬 만큼 |
| `agents` | object[] | 아니오 | 에이전트 id 순. `agent`, `jobs`, `running`, `fail_streak`(그 에이전트 작업 중 가장 긴 연속 실패. 알릴 것이 없어 빈 글로 끝난 차례는 성공이고, 실패는 결과를 못 만들었거나 만든 결과를 못 건넨 차례만이다), `last_ok_ms`, `last_error`, `open_sessions`, `scheduled`(켜진 스케줄 작업이 있는지. 작업 기록과 달리 재기동 직후에도 목록에서 바로 안다), `last_active_ms`(그 에이전트 세션의 마지막 `updated_at`. 세션 저장소가 못 답하면 null), `name`(화면에 보일 이름. A.S.H., S.C.R.I.B.E. 처럼 프로필의 브랜드 이름이고 `shared` 는 id 그대로), `last_due_ms`(켜진 스케줄 중 가장 최근에 지난 예정 시각. cron 의 직전 시각이고 스케줄이 없으면 null). 스케줄 작업은 그 작업의 에이전트로, 성찰과 기억 정리와 외부 조회는 `shared` 로 센다. 작업이 없는 에이전트도 0 으로 나온다 |

#### 응답 코드

| 코드 | 의미 | 본문 |
|---|---|---|
| `200` | 정상 | 위 스키마 |

#### 호출 예시

```bash
$ curl -s http://localhost:7777/api/platform/metrics
{"at_ms":1794500000000,"process":{"pid":1,"rss_bytes":231735296,"cpu_percent":1.5,"threads":12,"open_fds":48,"asyncio_tasks":9,"uptime_sec":86400.0},"loop_lag":{"last_ms":0.4,"max_ms":12.0,"samples":60},"agents":[{"agent":"scribe","jobs":1,"running":0,"fail_streak":0,"last_ok_ms":1794499200000,"last_error":"","open_sessions":0,"scheduled":true},{"agent":"main","jobs":0,"running":0,"fail_streak":0,"last_ok_ms":null,"last_error":"","open_sessions":1,"scheduled":false},{"agent":"shared","jobs":2,"running":0,"fail_streak":0,"last_ok_ms":1794499980000,"last_error":"","open_sessions":0,"scheduled":false}]}
```

#### 특이사항

**재호출**: 상태를 바꾸지 않는다. `cpu_percent` 는 직전 호출 이후 구간의 평균이라 첫 호출은 기동 이후 평균이고, 두 호출 사이가 짧으면 0 에 가깝다. 작업 기록은 `ASH_WORKFLOW__BACKEND=in_memory`(기본)면 재시작할 때 `fail_streak` 와 `last_ok_ms` 가 비워지고, `postgres` 면 이어진다. 프로필별 메모리는 한 프로세스라 못 나누며 `process` 가 전체다.

---

### GET /ion/status

Ion(별도 컨테이너)가 본 플랫폼 상태. 백엔드가 죽어도 nginx 의 `/ion/` 로 닿는다.

#### Endpoint

```
GET /ion/status
```

#### 호출 규약

| 항목 | 값 |
|---|---|
| Method | `GET` |
| 인증 | `ASH_ION__ACCESS_KEY` 가 설정돼 있으면 `Authorization: Bearer <키>` 또는 `?token=<키>` 필수 |
| 요청 Content-Type | 없음 (본문 없음) |
| 응답 Content-Type | `application/json` |
| 필수 헤더 | 없음 |

#### Request Body

없음.

#### Query / Path 파라미터

| 파라미터 | 위치 | 타입 | 필수 | 기본값 | 설명 |
|---|---|---|---|---|---|
| 없음 | | | | | |

#### Response Body

| 필드 | 타입 | 널 허용 | 설명 |
|---|---|---|---|
| `at_ms` | integer | 아니오 | 응답 시각 |
| `backend_ok` | boolean | 예 | 마지막 관측에서 `GET /api/health` 가 200 이었는지. 아직 관측 전이면 null |
| `observed_ms` | integer | 예 | 마지막 관측 시각 |
| `container` | object | 예 | `id`, `service`, `status`, `restart_count`, `memory_usage`, `memory_limit`. Docker 프록시에서 못 읽으면 null |
| `loop_lag_ms` | number | 예 | 백엔드 이벤트 루프 지연(최근 60초 최대) |
| `agents` | object | 아니오 | 에이전트 id → `fail_streak`, `last_ok_ms`, `scheduled`(백엔드 지표의 `scheduled`. 없는 옛 백엔드면 기록된 작업 수로 짐작), `last_due_ms`(백엔드 지표의 값. 없는 옛 백엔드면 null), `last_active_ms`, `name`(표시 이름. 사고 제목은 이 이름으로 쓰고 `target` 과 사고 id 는 에이전트 id 그대로다) |
| `incidents` | object[] | 아니오 | 열린 사고. `id`, `kind`, `target`, `detail`, `opened_ms`, `notified_ms`, `response`, `responded_ms`, `action_result`, `closed_ms` 에 화면용 `title`, `actions`, `severity`(`critical` 또는 `warning`), `url` 을 붙인다 |

#### 응답 코드

| 코드 | 의미 | 본문 |
|---|---|---|
| `200` | 정상 | 위 스키마 |
| `401` | 키 없음 또는 틀림 | `{"error": "unauthorized"}` |

#### 호출 예시

```bash
$ curl -s http://localhost:7777/ion/status
{"at_ms":1794500000000,"backend_ok":true,"observed_ms":1794499990000,"container":{"id":"abc","service":"ash-backend","status":"running","restart_count":0,"memory_usage":1030000000,"memory_limit":8000000000},"loop_lag_ms":8.0,"agents":{"scribe":{"fail_streak":0,"last_ok_ms":1794499200000,"scheduled":true},"main":{"fail_streak":0,"last_ok_ms":null,"scheduled":false}},"incidents":[]}
```

#### 특이사항

**재호출**: 상태를 바꾸지 않는다. 관측은 15초마다, 지표와 컨테이너 통계는 60초마다 갱신된다.

---

### POST /ion/incidents/{incident_id}/respond

사고에 답한다. 답은 사고당 한 번만 받고, 그때만 행동한다(같은 답을 두 번 보내도 행동은 한 번).

#### Endpoint

```
POST /ion/incidents/{incident_id}/respond
```

#### 호출 규약

| 항목 | 값 |
|---|---|
| Method | `POST` |
| 인증 | `GET /ion/status` 와 같다 |
| 요청 Content-Type | `application/json` |
| 응답 Content-Type | `application/json` |
| 필수 헤더 | 없음 |

#### Request Body

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `action` | string | 예 | `restart`(백엔드 재기동), `stop`(백엔드 멈춤, 재시작 루프용), `pause`(대상 에이전트의 켜진 스케줄 작업 끄기), `ignore` |

#### Query / Path 파라미터

| 파라미터 | 위치 | 타입 | 필수 | 기본값 | 설명 |
|---|---|---|---|---|---|
| `incident_id` | path | string | 예 | | 사고 id(`종류:대상:연 시각 ms`) |

#### Response Body

| 필드 | 타입 | 널 허용 | 설명 |
|---|---|---|---|
| `incident` | object | 아니오 | 갱신된 사고. `action_result` 에 행동 결과 한 줄(`재기동함`, `작업 1개 멈춤`, `무시`) |

#### 응답 코드

| 코드 | 의미 | 본문 |
|---|---|---|
| `200` | 정상 | 위 스키마 |
| `400` | `action` 이 넷 중 하나가 아님 | `{"error": "..."}` |
| `404` | 모르는 사고 | `{"error": "unknown incident"}` |
| `401` | 키 없음 또는 틀림 | `{"error": "unauthorized"}` |

#### 호출 예시

```bash
$ curl -s -X POST http://localhost:7777/ion/incidents/backend_down:backend:498472/respond -H 'Content-Type: application/json' -d '{"action":"restart"}'
{"incident":{"id":"backend_down:backend:498472","kind":"backend_down","target":"backend","detail":"health 실패 3회 연속","opened_ms":1794500000000,"notified_ms":1794500000000,"response":"restart","responded_ms":1794500030000,"action_result":"재기동함","closed_ms":null}}
```

#### 특이사항

**재호출**: 첫 답이 남고 뒤의 답은 그 사고를 그대로 돌려준다. 재기동은 Docker 소켓 프록시의 `restart` 로 가며 두 번 눌러도 결과는 "떠 있음" 하나다. 사고는 신호가 사라질 때 감시 루프가 닫는다.

---

### POST /ion/restart

사고와 무관하게 백엔드 컨테이너를 재기동한다. HUD SET 화면의 RESTART BACKEND 가 먼저 부른다(저장했지만 재시작해야 반영되는 설정, 지금은 `thought.enabled`). 컨테이너 재기동이라 Docker 의 RestartCount 가 오르지 않는다. Ion 이 없거나 거절하면 화면은 [POST /api/restart](#post-apirestart)(백엔드 자기 재시작)로 넘어간다.

#### Endpoint

```
POST /ion/restart
```

#### 호출 규약

| 항목 | 값 |
|---|---|
| Method | `POST` |
| 인증 | `ASH_ION__ACCESS_KEY` 가 있으면 `Authorization: Bearer <키>` 또는 `?token=` |
| 요청 Content-Type | 없음 (본문 없음) |
| 응답 Content-Type | `application/json` |
| 필수 헤더 | 없음 |

#### Request Body

없음.

#### Query / Path 파라미터

| 파라미터 | 위치 | 타입 | 필수 | 기본값 | 설명 |
|---|---|---|---|---|---|
| 없음 | | | | | |

#### Response Body

| 필드 | 타입 | 널 허용 | 설명 |
|---|---|---|---|
| `ok` | boolean | 아니오 | 프록시가 재기동을 받았는지 |
| `result` | string | 아니오 | `재기동함` 또는 `재기동 실패` |

#### 응답 코드

| 코드 | 의미 | 본문 |
|---|---|---|
| `200` | 재기동 요청됨 | `{"ok": true, "result": "재기동함"}` |
| `401` | 키 불일치 | `{"error": "unauthorized"}` |
| `502` | 프록시가 거절했거나 닿지 않음 | `{"ok": false, "result": "재기동 실패"}` |

#### 호출 예시

```bash
$ curl -s -X POST http://localhost:7777/ion/restart
{"ok": true, "result": "재기동함"}
```

#### 특이사항

**재호출**: 부를 때마다 한 번 재기동한다(멱등하지 않다. 재시작 자체가 요청한 행동이다). 재기동 중에는 `/api/*` 가 잠시 502 이고 Ion 의 health 가 3회 연속 실패하기 전에 보통 돌아오므로 사고는 열리지 않는다. 뜨는 데 45초를 넘기면 `backend_down` 사고가 열린다.

---

### GET /ion/incidents

사고 목록. 기본은 열린 사고만이고 `closed=1` 이면 닫힌 사고까지 연 시각이 늦은 순으로 낸다. Ion 프로필의 `ion_incidents`, `ion_report` 가 쓴다.

#### Endpoint

```
GET /ion/incidents?closed=1&limit=20
```

#### 호출 규약

| 항목 | 값 |
|---|---|
| Method | `GET` |
| 인증 | `ASH_ION__ACCESS_KEY` 가 있으면 `Authorization: Bearer <키>` 또는 `?token=` |
| 요청 Content-Type | 없음 (본문 없음) |
| 응답 Content-Type | `application/json` |
| 필수 헤더 | 없음 |

#### Request Body

없음.

#### Query / Path 파라미터

| 파라미터 | 위치 | 타입 | 필수 | 기본값 | 설명 |
|---|---|---|---|---|---|
| `closed` | query | int | 아니오 | `0` | `1` 이면 닫힌 사고도 |
| `limit` | query | int | 아니오 | `20` | 최대 건수(1~100) |

#### Response Body

| 필드 | 타입 | 널 허용 | 설명 |
|---|---|---|---|
| `incidents` | object[] | 아니오 | `GET /ion/status` 의 `incidents` 와 같은 꼴. `closed=1` 이면 `closed_ms` 가 있는 사고가 섞인다 |

#### 응답 코드

| 코드 | 의미 | 본문 |
|---|---|---|
| `200` | 정상 | 위 스키마 |
| `401` | 키 불일치 | `{"error": "unauthorized"}` |

#### 호출 예시

```bash
$ curl -s 'http://localhost:7777/ion/incidents?closed=1&limit=2'
{"incidents": [{"id": "agent_failing:scribe:1794535268462", "kind": "agent_failing", "target": "scribe", "detail": "연속 실패 3회", "opened_ms": 1794535268462, "notified_ms": 1794535268462, "response": null, "responded_ms": null, "action_result": "", "closed_ms": 1794536470454, "title": "Ion: scribe 의 작업이 계속 실패해요", "actions": ["pause", "ignore"], "severity": "warning", "url": "/"}]}
```

#### 특이사항

**재호출**: 상태를 바꾸지 않는다. 같은 저장소면 같은 목록이다.

---

### GET /ion/logs

백엔드 컨테이너 로그. 소켓 프록시의 `containers/{id}/logs` 를 읽어 다중화 프레임을 풀어 글로 낸다. Ion 프로필의 `ion_report` 가 사고 전후 구간을 읽는다.

#### Endpoint

```
GET /ion/logs?since_ms=1794535000000&until_ms=1794536470454&lines=200
```

#### 호출 규약

| 항목 | 값 |
|---|---|
| Method | `GET` |
| 인증 | `ASH_ION__ACCESS_KEY` 가 있으면 `Authorization: Bearer <키>` 또는 `?token=` |
| 요청 Content-Type | 없음 (본문 없음) |
| 응답 Content-Type | `application/json` |
| 필수 헤더 | 없음 |

#### Request Body

없음.

#### Query / Path 파라미터

| 파라미터 | 위치 | 타입 | 필수 | 기본값 | 설명 |
|---|---|---|---|---|---|
| `since_ms` | query | int | 아니오 | 없음 | 이 시각(epoch ms)부터. 초 단위로 내려 프록시에 준다 |
| `until_ms` | query | int | 아니오 | 없음 | 이 시각까지 |
| `lines` | query | int | 아니오 | `200` | 마지막 몇 줄(1~1000) |

#### Response Body

| 필드 | 타입 | 널 허용 | 설명 |
|---|---|---|---|
| `text` | string | 아니오 | 로그 원문. 컨테이너를 못 찾거나 프록시가 못 답하면 빈 글 |
| `lines` | int | 아니오 | `text` 의 줄 수 |

#### 응답 코드

| 코드 | 의미 | 본문 |
|---|---|---|
| `200` | 정상 | 위 스키마 |
| `401` | 키 불일치 | `{"error": "unauthorized"}` |

#### 호출 예시

```bash
$ curl -s 'http://localhost:7777/ion/logs?lines=2'
{"text": "2026-11-13T02:00:50.366808Z [info     ] [Goal] scribe/0ee3fa5259b32a33 run=166 skipped=unchanged took=45.2s [ash_industry.core.goals.runner]\n2026-11-13T02:00:50.367152Z [info     ] [Scheduler] Tool task 'goal-0ee3fa5259b32a33' had nothing to report [ash_industry.core.scheduler.scheduler_service]\n", "lines": 2}
```

#### 특이사항

**재호출**: 상태를 바꾸지 않는다. 구간을 주면 같은 글이고, 주지 않으면 새 로그가 붙어 마지막 줄이 바뀐다. 로그는 모델에 신뢰하지 않는 입력으로 넘긴다.

---

### GET /ion/events

사고가 열리거나 답을 받을 때마다 한 건씩 보내는 Server-Sent Events. 데스크톱 앱과 HUD 의 ION 띠가 구독한다.

#### Endpoint

```
GET /ion/events
```

#### 호출 규약

| 항목 | 값 |
|---|---|
| Method | `GET` |
| 인증 | `GET /ion/status` 와 같다 |
| 요청 Content-Type | 없음 (본문 없음) |
| 응답 Content-Type | `text/event-stream` |
| 필수 헤더 | 없음 |

#### Request Body

없음.

#### Query / Path 파라미터

| 파라미터 | 위치 | 타입 | 필수 | 기본값 | 설명 |
|---|---|---|---|---|---|
| 없음 | | | | | |

#### Response Body

이벤트 줄. `event:` 는 종류, `data:` 는 JSON.

| 종류 | data |
|---|---|
| `hello` | `{"type":"hello"}`. 연결 직후 한 번 |
| `incident` | 사고 알림. `id`, `kind`, `target`, `severity`, `title`, `body`, `tag`, `url`, `actions`(버튼 순서, 첫 번째가 추천) |
| `incident_update` | 답을 받은 사고. `incident` |

#### 응답 코드

| 코드 | 의미 | 본문 |
|---|---|---|
| `200` | 스트림 | 위 이벤트 |
| `401` | 키 없음 또는 틀림 | `{"error": "unauthorized"}` |

#### 호출 예시

```bash
$ curl -N http://localhost:7777/ion/events
event: hello
data: {"type": "hello"}

event: incident
data: {"type": "incident", "id": "backend_down:backend:498472", "kind": "backend_down", "target": "backend", "title": "Ion: 백엔드가 응답하지 않아요", "body": "health 실패 3회 연속", "tag": "backend_down:backend:498472", "url": "/", "actions": ["restart", "ignore"]}
```

#### 특이사항

**재호출**: 연결마다 큐 하나(100건). 느린 연결은 오래된 이벤트부터 버린다. 끊긴 동안의 사고는 `GET /ion/status` 의 `incidents` 로 다시 본다.

---

### POST /api/openloops/{loop_id}

open loop 하나를 완료 또는 무시로 닫거나, 닫힌 것을 다시 연다.

#### Endpoint

```
POST /api/openloops/{loop_id}
```

#### 호출 규약

| 항목 | 값 |
|---|---|
| Method | `POST` |
| 인증 | 설정 시 필요 |
| 요청 Content-Type | `application/json` |
| 응답 Content-Type | `application/json` |
| 필수 헤더 | `Content-Type` |

#### Request Body

| 필드 | 타입 | 필수 | 기본값 | 설명 |
|---|---|---|---|---|
| `status` | `"done" \| "dismissed" \| "open"` | 예 | 없음 | 바꿀 상태. `open` 은 닫힌 약속을 되살린다 |

#### Query / Path 파라미터

| 파라미터 | 위치 | 타입 | 필수 | 기본값 | 설명 |
|---|---|---|---|---|---|
| `loop_id` | path | string | 예 | 없음 | `GET /api/agenda` 의 `open_loops[].id` 또는 `closed_loops[].id` |

#### Response Body

| 필드 | 타입 | 널 허용 | 설명 |
|---|---|---|---|
| `id` | string | 아니오 | 요청한 id |
| `status` | string | 아니오 | 바뀐 상태 |

#### 응답 코드

| 코드 | 의미 | 본문 |
|---|---|---|
| `200` | 정상 | `{"id", "status"}` |
| `400` | `status` 가 셋 중 하나가 아님 | `{"error": "status must be 'done', 'dismissed' or 'open'"}` |
| `404` | id 없음, 또는 open loop 저장소가 꺼져 있음 | `{"error": "open loop not found"}` |
| `409` | `open` 인데 기한이 `ASH_OPENLOOP__EXPIRE_AFTER_SEC` 넘게 지났거나, 기한 없이 `ASH_OPENLOOP__MAX_AGE_SEC` 보다 오래됨. 열자마자 다시 만료되므로 상태를 바꾸지 않는다 | `{"error": "open loop is past its due or age"}` |
| `422` | 본문이 없거나 JSON 이 아님 | `{"detail": [...]}` |

#### 호출 예시

```bash
$ curl -s -X POST -H 'Content-Type: application/json' -d '{"status":"dismissed"}' http://localhost:7777/api/openloops/e17dc364ae404c6c9d341b69a3a12b79
{"id":"e17dc364ae404c6c9d341b69a3a12b79","status":"dismissed"}

$ curl -s -X POST -H 'Content-Type: application/json' -d '{"status":"maybe"}' http://localhost:7777/api/openloops/x
{"error":"status must be 'done', 'dismissed' or 'open'"}

$ curl -s -X POST -H 'Content-Type: application/json' -d '{"status":"done"}' http://localhost:7777/api/openloops/nope
{"error":"open loop not found"}

$ curl -s -X POST http://localhost:7777/api/openloops/x
{"detail":[{"type":"missing","loc":["body"],"msg":"Field required","input":null}]}
```

#### 특이사항

**재호출**: 멱등. 같은 id 에 같은 status 를 다시 보내도 결과가 같고 `updated_at` 만 갱신된다. 이미 `done` 인 것을 `dismissed` 로 바꾸는 것도 허용된다(마지막 호출이 이긴다). `open` 도 같다. 이미 열린 것을 다시 열어도 그대로 열려 있다. 되살린 약속은 기한과 생성 시각을 그대로 두므로 만료 규칙도 원래 기한 기준이다.

jsonl 저장소는 append-only 라 호출마다 한 줄이 붙고 읽을 때 마지막 줄이 이긴다.

---

### GET /api/push/vapid

모바일 앱(iOS 홈 화면 웹앱)이 Web Push 를 구독할 때 쓰는 VAPID 공개키.

#### Endpoint

```
GET /api/push/vapid
```

#### 호출 규약

| 항목 | 값 |
|---|---|
| Method | `GET` |
| 인증 | 설정 시 필요 |
| 요청 Content-Type | 없음 (본문 없음) |
| 응답 Content-Type | `application/json` |
| 필수 헤더 | 없음 |

#### Request Body

없음.

#### Query / Path 파라미터

| 파라미터 | 위치 | 타입 | 필수 | 기본값 | 설명 |
|---|---|---|---|---|---|
| 없음 | | | | | |

#### Response Body

| 필드 | 타입 | 널 허용 | 설명 |
|---|---|---|---|
| `public_key` | string | 아니오 | base64url(패딩 없음), 65바이트 P-256 비압축 공개키 |

#### 응답 코드

| 코드 | 의미 | 본문 |
|---|---|---|
| `200` | 정상 | `{"public_key"}` |
| `404` | 푸시가 꺼져 있음. `ASH_NOTIFY__WEBPUSH_VAPID_PUBLIC_KEY`, `..._PRIVATE_KEY`, `..._SUBJECT` 중 하나가 없거나 세션 저장소가 Postgres 가 아니다 | `{"error": "push disabled"}` |

#### 호출 예시

```bash
$ curl -s http://localhost:7777/api/push/vapid
{"public_key":"BEl62iUYgUivxIkv69yViEuiBIa-Ib9-SkvMeAtA3LFgDzkrxZJjSgSnfckjBJuBkr3qBUYIHBQFLXYp5Nksh8U"}
```

#### 특이사항

**재호출**: 상태를 바꾸지 않는다. 키를 바꾸면 기존 구독이 전부 무효가 된다.

---

### PUT /api/push/subscriptions

Web Push 구독을 등록한다. 앱은 "알림 켜기"를 누를 때마다 다시 보낸다.

#### Endpoint

```
PUT /api/push/subscriptions
```

#### 호출 규약

| 항목 | 값 |
|---|---|
| Method | `PUT` |
| 인증 | 설정 시 필요 |
| 요청 Content-Type | `application/json` |
| 응답 Content-Type | `application/json` |
| 필수 헤더 | `Content-Type` |

#### Request Body

브라우저 `PushSubscription.toJSON()` 을 그대로 보낸다.

| 필드 | 타입 | 필수 | 기본값 | 설명 |
|---|---|---|---|---|
| `endpoint` | string | 예 | 없음 | 푸시 서비스 주소. `https://` 로 시작한다 |
| `expirationTime` | number \| null | 아니오 | null | 받기만 하고 쓰지 않는다 |
| `keys.p256dh` | string | 예 | 없음 | 본문 암호화 공개키 |
| `keys.auth` | string | 예 | 없음 | 본문 암호화 인증 비밀 |

#### Query / Path 파라미터

| 파라미터 | 위치 | 타입 | 필수 | 기본값 | 설명 |
|---|---|---|---|---|---|
| 없음 | | | | | |

#### Response Body

| 필드 | 타입 | 널 허용 | 설명 |
|---|---|---|---|
| `ok` | boolean | 아니오 | 항상 `true` |

#### 응답 코드

| 코드 | 의미 | 본문 |
|---|---|---|
| `200` | 정상 | `{"ok": true}` |
| `400` | 본문이 JSON 객체가 아님 | `{"error": "body must be a JSON object"}` |
| `400` | `endpoint` 가 `https://` 로 시작하지 않음 | `{"error": "endpoint must start with https://"}` |
| `400` | `keys.p256dh` 나 `keys.auth` 가 비었음 | `{"error": "keys.p256dh and keys.auth are required"}` |
| `404` | 푸시가 꺼져 있음 | `{"error": "push disabled"}` |

#### 호출 예시

```bash
$ curl -s -X PUT -H 'Content-Type: application/json' -d '{"endpoint":"https://web.push.apple.com/QH...","expirationTime":null,"keys":{"p256dh":"BN...","auth":"k8..."}}' http://localhost:7777/api/push/subscriptions
{"ok":true}

$ curl -s -X PUT -H 'Content-Type: application/json' -d '{"endpoint":"https://x","keys":{}}' http://localhost:7777/api/push/subscriptions
{"error":"keys.p256dh and keys.auth are required"}
```

#### 특이사항

**재호출**: `endpoint` 를 자연 키로 upsert 한다(`push_subscriptions` 테이블의 기본 키). 몇 번 보내도 행은 하나이고 키와 `updated_at` 만 갱신된다. `Authorization: Bearer` 헤더로 온 키가 등록된 키면 그 사용자 이름을 `user_id` 로 남긴다. `?token=` 쿼리로만 인증한 요청은 `user_id` 가 null 이다. 테이블은 첫 호출 때 `CREATE TABLE IF NOT EXISTS` 로 만든다.

**발송**: `ASH_NOTIFY__KINDS` 의 알림(스케줄 결과, 🔔 등)을 구독 전부에 `{"title", "body", "tag"}` 로 보낸다. `title` 은 디스코드처럼 보낸 에이전트를 보인다. 에이전트 주색에 가장 가까운 색 원 이모지와 이름이다(예: `🟢 S.C.R.I.B.E.`, `🔵 A.S.H.`). 알림 종류 표시는 `body` 앞으로 간다(예: `⏱ 오늘의 일정\n회의 2건`, `💭 회의 10분 전입니다`). 에이전트 아바타 주소가 설정돼 있으면 `icon` 도 준다(iOS 는 앱 아이콘만 보일 수 있다). `body` 는 1000자에서 자른다. 제목과 본문이 모두 비면 보내지 않는다. 푸시 서비스 TTL 은 하루(86400초)다. `tag` 는 알림 id 라 같은 알림이 두 번 가도 iPhone 에는 하나로 보인다. 푸시 서비스가 404, 410 을 주면 그 구독을 지우고, 그 밖의 실패는 로그만 남기고 다시 보내지 않는다.

---

### DELETE /api/push/subscriptions

Web Push 구독을 지운다.

#### Endpoint

```
DELETE /api/push/subscriptions
```

#### 호출 규약

| 항목 | 값 |
|---|---|
| Method | `DELETE` |
| 인증 | 설정 시 필요 |
| 요청 Content-Type | `application/json` |
| 응답 Content-Type | `application/json` |
| 필수 헤더 | `Content-Type` |

#### Request Body

| 필드 | 타입 | 필수 | 기본값 | 설명 |
|---|---|---|---|---|
| `endpoint` | string | 예 | 없음 | 지울 구독의 endpoint |

#### Query / Path 파라미터

| 파라미터 | 위치 | 타입 | 필수 | 기본값 | 설명 |
|---|---|---|---|---|---|
| 없음 | | | | | |

#### Response Body

| 필드 | 타입 | 널 허용 | 설명 |
|---|---|---|---|
| `ok` | boolean | 아니오 | 항상 `true` |

#### 응답 코드

| 코드 | 의미 | 본문 |
|---|---|---|
| `200` | 정상. 없는 endpoint 도 200 | `{"ok": true}` |
| `400` | `endpoint` 가 없다 | `{"error": "endpoint is required"}` |
| `404` | 푸시가 꺼져 있음 | `{"error": "push disabled"}` |

#### 호출 예시

```bash
$ curl -s -X DELETE -H 'Content-Type: application/json' -d '{"endpoint":"https://web.push.apple.com/QH..."}' http://localhost:7777/api/push/subscriptions
{"ok":true}

$ curl -s -X DELETE -H 'Content-Type: application/json' -d '{}' http://localhost:7777/api/push/subscriptions
{"error":"endpoint is required"}
```

#### 특이사항

**재호출**: 멱등. 이미 지운 구독을 다시 지워도 200 이다.

---

### POST /api/schedules/{name}

스케줄 작업을 켜거나 끈다.

#### Endpoint

```
POST /api/schedules/{name}
```

#### 호출 규약

| 항목 | 값 |
|---|---|
| Method | `POST` |
| 인증 | 설정 시 필요 |
| 요청 Content-Type | `application/json` |
| 응답 Content-Type | `application/json` |
| 필수 헤더 | `Content-Type` |

#### Request Body

| 필드 | 타입 | 필수 | 기본값 | 설명 |
|---|---|---|---|---|
| `enabled` | boolean | 예 | 없음 | `true` 켬, `false` 끔. 불리언이 아니면 400 |

#### Query / Path 파라미터

| 파라미터 | 위치 | 타입 | 필수 | 기본값 | 설명 |
|---|---|---|---|---|---|
| `name` | path | string | 예 | 없음 | `GET /api/agenda` 의 `schedules[].name` |

#### Response Body

| 필드 | 타입 | 널 허용 | 설명 |
|---|---|---|---|
| `name` | string | 아니오 | 요청한 이름 |
| `enabled` | boolean | 아니오 | 바뀐 값 |

#### 응답 코드

| 코드 | 의미 | 본문 |
|---|---|---|
| `200` | 정상 | `{"name", "enabled"}` |
| `400` | `enabled` 가 불리언이 아님 | `{"error": "enabled must be true or false"}` |
| `404` | 이름 없음, 또는 스케줄러가 꺼져 있음 | `{"error": "schedule not found"}` |
| `422` | 본문이 없거나 JSON 이 아님 | `{"detail": [...]}` |

#### 호출 예시

```bash
$ curl -s -X POST -H 'Content-Type: application/json' -d '{"enabled":false}' http://localhost:7777/api/schedules/nope
{"error":"schedule not found"}

$ curl -s -X POST -H 'Content-Type: application/json' -d '{"enabled":"yes"}' http://localhost:7777/api/schedules/nope
{"error":"enabled must be true or false"}
```

#### 특이사항

**재호출**: 멱등. 같은 값을 다시 보내도 상태가 같다. 메모리의 작업과 함께 저장 파일의 `enabled` 도 바꾼다(정의 YAML 에서 온 작업은 원본 파일, 그 밖에는 스케줄 폴더의 파일). 마감(`run_until`)이 지난 작업은 켜도 `next_run` 이 null 이고, 스케줄러가 다음 틱에 다시 끄고 파일에도 끈 값을 남긴다.

---

### GET /api/sessions

이 프로세스가 메모리에 들고 있는 세션 id 목록과 각 세션의 에이전트.

#### Endpoint

```
GET /api/sessions
```

#### 호출 규약

| 항목 | 값 |
|---|---|
| Method | `GET` |
| 인증 | 설정 시 필요 |
| 요청 Content-Type | 없음 (본문 없음) |
| 응답 Content-Type | `application/json` |
| 필수 헤더 | 없음 |

#### Request Body

없음.

#### Query / Path 파라미터

| 파라미터 | 위치 | 타입 | 필수 | 기본값 | 설명 |
|---|---|---|---|---|---|
| 없음 | | | | | |

#### Response Body

| 필드 | 타입 | 널 허용 | 설명 |
|---|---|---|---|
| `sessions` | `string[]` | 아니오 | 세션 id. 기동 시 `default` 하나로 시작한다 |
| `agents` | `object` | 아니오 | 세션 id → 에이전트 id. 키는 `sessions` 와 같다 |

#### 응답 코드

| 코드 | 의미 | 본문 |
|---|---|---|
| `200` | 정상 | 위 스키마 |

#### 호출 예시

```bash
$ curl -s http://localhost:7777/api/sessions
{"sessions":["default","2e076b96"],"agents":{"default":"main","2e076b96":"scribe"}}
```

#### 특이사항

**재호출**: 상태를 바꾸지 않는다.

저장소(DB)에 있는 세션이 아니라 **프로세스가 띄운 세션**만 나온다. 재시작하면 `default` 와 그 뒤 접속하거나 만든 것만 보인다. 에이전트끼리 묻는 도구(`ask_agent`)가 연 대화 세션(`peer-<부른 쪽>-<받는 쪽>`)과, 스케줄 결과를 건네려고 다시 연 대화 세션도 여기 나온다. 저장된 전체 목록은 슬래시 명령 `/sessions` 가 보여준다.

---

### POST /api/sessions

새 세션을 만든다. id 는 서버가 정하고, 세션을 맡을 에이전트는 본문으로 고른다.

#### Endpoint

```
POST /api/sessions
```

#### 호출 규약

| 항목 | 값 |
|---|---|
| Method | `POST` |
| 인증 | 설정 시 필요 |
| 요청 Content-Type | `application/json` (본문은 선택) |
| 응답 Content-Type | `application/json` |
| 필수 헤더 | 없음 |

#### Request Body

| 필드 | 타입 | 필수 | 기본값 | 제약 | 설명 |
|---|---|---|---|---|---|
| `agent` | string | 아니오 | `main` | `GET /api/agents` 의 id | 세션을 맡을 에이전트. 만든 뒤에는 바뀌지 않는다 |

#### Query / Path 파라미터

| 파라미터 | 위치 | 타입 | 필수 | 기본값 | 설명 |
|---|---|---|---|---|---|
| 없음 | | | | | |

#### Response Body

| 필드 | 타입 | 널 허용 | 설명 |
|---|---|---|---|
| `session_id` | string | 아니오 | 8자리 hex. 이 id 로 `/ws?session_id=` 에 붙는다 |
| `agent` | string | 아니오 | 세션의 에이전트 id |

#### 응답 코드

| 코드 | 의미 | 본문 |
|---|---|---|
| `200` | 정상 | `{"session_id", "agent"}` |
| `400` | 모르는 에이전트 | `{"error": "unknown agent: <id>"}` |
| `422` | 본문이 JSON 이 아님 | `{"detail": [...]}` |

#### 호출 예시

```bash
$ curl -s -X POST http://localhost:7777/api/sessions -H 'content-type: application/json' -d '{"agent":"scribe"}'
{"session_id":"2e076b96","agent":"scribe"}

$ curl -s -X POST http://localhost:7777/api/sessions -H 'content-type: application/json' -d '{"agent":"ghost"}'
{"error":"unknown agent: ghost"}
```

#### 특이사항

**재호출**: 멱등하지 않다. 부를 때마다 새 세션이 저장소와 메모리에 생긴다. 클라이언트가 재시도하면 빈 세션이 쌓이므로, 응답을 받은 뒤에만 `/ws` 에 붙이고 실패 시 다시 부르지 말 것. 지우는 것은 `DELETE /api/sessions/{session_id}`.

---

### GET /api/sessions/{session_id}/messages

세션의 대화 히스토리. CONVERSATION 복원에 쓴다.

#### Endpoint

```
GET /api/sessions/{session_id}/messages
```

#### 호출 규약

| 항목 | 값 |
|---|---|
| Method | `GET` |
| 인증 | 설정 시 필요 |
| 요청 Content-Type | 없음 (본문 없음) |
| 응답 Content-Type | `application/json` |
| 필수 헤더 | 없음 |

#### Request Body

없음.

#### Query / Path 파라미터

| 파라미터 | 위치 | 타입 | 필수 | 기본값 | 설명 |
|---|---|---|---|---|---|
| `session_id` | path | string | 예 | 없음 | 세션 id |

#### Response Body

| 필드 | 타입 | 널 허용 | 설명 |
|---|---|---|---|
| `messages` | `{role, text}[]` | 아니오 | `role` 은 `user` 또는 `assistant`. 도구 호출, 도구 결과, 빈 텍스트는 빠진다 |

#### 응답 코드

| 코드 | 의미 | 본문 |
|---|---|---|
| `200` | 정상. 없는 세션도 200 에 빈 배열 | 위 스키마 |

#### 호출 예시

```bash
$ curl -s http://localhost:7777/api/sessions/default/messages
{"messages": [{"role": "user", "text": "한 문장으로 자기소개 해줘"}, ...]}

$ curl -s http://localhost:7777/api/sessions/nope/messages
{"messages":[]}
```

#### 특이사항

**재호출**: 상태를 바꾸지 않는다.

없는 세션과 빈 세션을 구분하지 않는다. 텍스트는 마크다운 원문이고 렌더는 클라이언트 몫이다.

---

### DELETE /api/sessions/{session_id}

세션과 그 대화를 지운다. 메모리의 세션 객체, 저장소(jsonl 파일 또는 Postgres 행, 메시지는 cascade), 그 세션의 장기 기억(턴 일화, 사고 로그 등 `session_id` 가 같은 행)과 작업 기억이 함께 사라진다. 세션에 묶이지 않은 사용자 프로필 사실과 절차는 남는다. 기억을 먼저 지우고 이력을 나중에 지우므로, 중간에 실패해도 다시 호출하면 끝난다. 연결 확인과 삭제는 그 세션의 잠금 안에서 한다. 지우는 도중에 같은 세션으로 `/ws` 가 붙으면 삭제가 끝날 때까지 기다렸다가 빈 새 세션으로 열린다.

#### Endpoint

```
DELETE /api/sessions/{session_id}
```

#### 호출 규약

| 항목 | 값 |
|---|---|
| Method | `DELETE` |
| 인증 | 설정 시 필요 |
| 요청 Content-Type | 없음 (본문 없음) |
| 응답 Content-Type | `application/json` |
| 필수 헤더 | 없음 |

#### Request Body

없음.

#### Query / Path 파라미터

| 파라미터 | 위치 | 타입 | 필수 | 기본값 | 설명 |
|---|---|---|---|---|---|
| `session_id` | path | string | 예 | 없음 | 지울 세션 |

#### Response Body

| 필드 | 타입 | 널 허용 | 설명 |
|---|---|---|---|
| `deleted` | string | 아니오 | 지운 세션 id |

#### 응답 코드

| 코드 | 의미 | 본문 |
|---|---|---|
| `200` | 지웠거나 원래 없었다 | `{"deleted"}` |
| `409` | 그 세션에 붙어 있는 WebSocket 이 있다 | `{"error": "session has live connections"}` |

#### 호출 예시

```bash
$ curl -s -X DELETE http://localhost:7777/api/sessions/2e076b96
{"deleted":"2e076b96"}
```

#### 특이사항

**재호출**: 멱등하다. 없는 세션을 지워도 `200` 이고 상태는 같다. 붙어 있는 연결이 있으면 `409` 로 거절하므로, 보고 있는 세션을 지우려면 먼저 다른 세션으로 옮긴다. `default` 도 지울 수 있고, 다음 접속 때 빈 세션으로 다시 생긴다. 세션의 승인 브로커도 함께 버린다.

---

### POST /api/sessions/{session_id}/branch

세션을 분기한다.

#### Endpoint

```
POST /api/sessions/{session_id}/branch
```

#### 호출 규약

| 항목 | 값 |
|---|---|
| Method | `POST` |
| 인증 | 설정 시 필요 |
| 요청 Content-Type | 없음 (본문 없음) |
| 응답 Content-Type | `application/json` |
| 필수 헤더 | 없음 |

#### Request Body

없음.

#### Query / Path 파라미터

| 파라미터 | 위치 | 타입 | 필수 | 기본값 | 설명 |
|---|---|---|---|---|---|
| `session_id` | path | string | 예 | 없음 | 분기할 원본 세션 |

#### Response Body

| 필드 | 타입 | 널 허용 | 설명 |
|---|---|---|---|
| `session_id` | string | 아니오 | 새 세션 id |
| `parent_id` | string | 예 | jsonl 저장소면 원본 id. Postgres 저장소면 항상 `null` |

#### 응답 코드

| 코드 | 의미 | 본문 |
|---|---|---|
| `200` | 정상 | `{"session_id", "parent_id"}` |

#### 호출 예시

```bash
$ curl -s -X POST http://localhost:7777/api/sessions/nope/branch
{"session_id":"2e076b96","parent_id":null}
```

#### 특이사항

**재호출**: 멱등하지 않다. 부를 때마다 새 세션이 생긴다.

분기는 부모와 같은 에이전트의 세션이다. Postgres 저장소에서 원본 id 가 저장소에 없으면 main 에이전트의 빈 세션이 생긴다.

저장소가 Postgres(Docker 기본)면 분기가 아니라 **빈 새 세션 생성**과 같다. 원본 id 가 없어도 200 이고 히스토리를 복사하지 않는다(위 예시가 그 경우). 진짜 분기는 jsonl 저장소에서만 된다.

---

### GET /api/settings

설정 화면 내용. 고칠 수 있는 항목의 정의와 적용값, 저장했지만 아직 반영되지 않은 값, 비밀값을 가린 전체 적용값.

#### Endpoint

```
GET /api/settings
```

#### 호출 규약

| 항목 | 값 |
|---|---|
| Method | `GET` |
| 인증 | 설정 시 필요 |
| 요청 Content-Type | 없음 (본문 없음) |
| 응답 Content-Type | `application/json` |
| 필수 헤더 | 없음 |

#### Request Body

없음.

#### Query / Path 파라미터

| 파라미터 | 위치 | 타입 | 필수 | 기본값 | 설명 |
|---|---|---|---|---|---|
| 없음 | | | | | |

#### Response Body

| 필드 | 타입 | 널 허용 | 설명 |
|---|---|---|---|
| `path` | string | 아니오 | 저장 파일 경로(`ASH_SETTINGS_FILE`, 기본 `~/.ash/settings.yaml`) |
| `fields` | object | 아니오 | 섹션(`voice`, `proactive`, `thought`, `focus`, `shortcuts`) → 필드 → `{title, type, enum?, minimum?, maximum?, pattern?}`. 편집 허용 목록(`SettingsPatch`)에서 유도한다 |
| `editable` | object | 아니오 | `fields` 와 같은 모양으로 지금 프로세스의 적용값 |
| `pending` | object | 아니오 | settings.yaml 에 있지만 적용값과 다른 값. 비어 있지 않으면 백엔드를 다시 띄워야 반영된다 |
| `effective` | object | 아니오 | 전체 설정. 이름이 `key`, `token`, `secret`, `password`, `dsn` 으로 끝나거나(`_` 구분) `webhook` 이 든 값은 `***`(빈 값은 그대로) |

#### 응답 코드

| 코드 | 의미 | 본문 |
|---|---|---|
| `200` | 정상 | 위 스키마 |

#### 호출 예시

```bash
$ curl -s http://localhost:7777/api/settings
{"path":"/root/.ash/settings.yaml","fields":{"voice":{"wake_threshold":{"title":"Wake Threshold","type":"number","minimum":0.05,"maximum":0.99},...}},"editable":{"voice":{"wake_threshold":0.5,...}},"pending":{},"effective":{"llm":{"provider":"anthropic","api_key":"***",...}}}
```

#### 특이사항

**재호출**: 상태를 바꾸지 않는다. 비밀값은 어떤 경로로도 내보내지 않는다.

---

### PUT /api/settings

허용 목록 안의 설정을 settings.yaml 에 저장하고 같은 요청 안에서 지금 프로세스에 쓴다. 이 파일은 설정 원천 중 가장 앞이라 `.env` 와 compose 환경변수를 이기고 다음 기동도 같은 값으로 뜬다. 바로 쓸 수 없는 키(`thought.enabled`)는 `restart_required` 로 알린다.

#### Endpoint

```
PUT /api/settings
```

#### 호출 규약

| 항목 | 값 |
|---|---|
| Method | `PUT` |
| 인증 | 설정 시 필요 |
| 요청 Content-Type | `application/json` |
| 응답 Content-Type | `application/json` |
| 필수 헤더 | 없음 |

#### Request Body

| 필드 | 타입 | 필수 | 제약 |
|---|---|---|---|
| `voice` | object | 아니오 | `stt_provider`(`browser`/`whisper`), `stt_fallback`(`""`/`whisper`), `tts_provider`(`browser`/`supertonic`), `whisper_model_size`(`tiny`/`base`/`small`/`medium`), `stt_lang`(`ko-KR` 꼴), `tts_lang`(`ko` 꼴), `wake_threshold`(0.05~0.99), `command_max_sec`(0~120, 0 이면 끔), `command_max_chars`(0~2000, 0 이면 끔) |
| `proactive` | object | 아니오 | `enabled`, `daemon_enabled`(boolean), `daemon_trigger`(`interval`/`idle`/`both`), `daemon_interval_sec`, `daemon_idle_sec`(30~3600), `confidence_threshold`(0~1), `cooldown_sec`(0~86400) |
| `thought` | object | 아니오 | `enabled`(boolean), `router_threshold`(0~1) |
| `focus` | object | 아니오 | `enabled`(boolean) |
| `shortcuts` | object | 아니오 | HUD 안 단축키 `voice_start`(기본 `Ctrl+Shift+Enter`), `voice_stop`(기본 `Escape`), `agent_prev`(기본 `Ctrl+Shift+ArrowLeft`), `agent_next`(기본 `Ctrl+Shift+ArrowRight`). 각각 `Ctrl`, `Alt`, `Shift`, `Meta` 를 `+` 로 잇고 끝에 키 이름 하나(`A`~`Z`, `0`~`9`, `F1`~`F12`, `Enter`, `Escape`, `Space`, `Tab`, `Backspace`, `Delete`, `Home`, `End`, `PageUp`, `PageDown`, 방향키 `ArrowUp`/`ArrowDown`/`ArrowLeft`/`ArrowRight`). 지금 적용값에 얹은 넷이 서로 같으면(수정키 순서와 글자 대소문자는 무시) 422 |

모르는 섹션이나 필드는 422 다. 비운 섹션과 필드는 건드리지 않는다.

#### Query / Path 파라미터

| 파라미터 | 위치 | 타입 | 필수 | 기본값 | 설명 |
|---|---|---|---|---|---|
| 없음 | | | | | |

#### Response Body

| 필드 | 타입 | 널 허용 | 설명 |
|---|---|---|---|
| `changed` | boolean | 아니오 | 파일 내용이 바뀌었는지 |
| `applied` | string[] | 아니오 | 이 요청으로 프로세스에 바로 쓴 키(`섹션.이름`). 지금 적용값과 같은 값은 빠진다 |
| `restart_required` | boolean | 아니오 | 이 요청에 바로 쓸 수 없는 키가 있었는지 |
| `restart_keys` | string[] | 아니오 | 그 키 목록. 지금은 `thought.enabled` 뿐이다 |
| (나머지) | | | [GET /api/settings](#get-apisettings) 와 같다. 반영 뒤의 값이라 `pending` 에는 `restart_keys` 만 남는다 |

#### 응답 코드

| 코드 | 의미 | 본문 |
|---|---|---|
| `200` | 정상 | 위 스키마 |
| `401` | 인증이 켜져 있는데 키가 없음 | `{"error": "unauthorized"}` |
| `422` | 허용 목록 밖 필드, 범위나 형식 밖 값, 본문 JSON 오류 | FastAPI 기본 모양 |
| `422` | 단축키 넷 중 둘이 같음 | `{"detail": [{"type": "value_error", "loc": [], "msg": "Value error, 단축키가 겹칩니다: voice_stop 와 agent_prev 이 모두 Escape"}]}`. 파일은 건드리지 않는다 |

#### 호출 예시

```bash
$ curl -s -X PUT http://localhost:7777/api/settings -H 'Content-Type: application/json' -d '{"voice":{"wake_threshold":0.7}}'
{"changed":true,"applied":["voice.wake_threshold"],"restart_required":false,"restart_keys":[],"path":"/root/.ash/settings.yaml",...,"pending":{},...}
$ curl -s -X PUT http://localhost:7777/api/settings -H 'Content-Type: application/json' -d '{"thought":{"enabled":false}}'
{"changed":true,"applied":[],"restart_required":true,"restart_keys":["thought.enabled"],...,"pending":{"thought":{"enabled":false}},...}
$ curl -s -X PUT http://localhost:7777/api/settings -H 'Content-Type: application/json' -d '{"shortcuts":{"voice_start":"Alt+Space"}}'
{"changed":true,"applied":["shortcuts.voice_start"],"restart_required":false,...,"editable":{...,"shortcuts":{"voice_start":"Alt+Space","voice_stop":"Escape",...}},...}
$ curl -s -X PUT http://localhost:7777/api/settings -H 'Content-Type: application/json' -d '{"shortcuts":{"agent_prev":"Escape"}}'
{"detail":[{"type":"value_error","loc":[],"msg":"Value error, 단축키가 겹칩니다: voice_stop 와 agent_prev 이 모두 Escape"}]}
```

#### 특이사항

**재호출**: 같은 본문을 다시 보내면 `changed: false` 이고 파일을 건드리지 않으며 `applied` 도 비어 있다(지금 적용값과 같은 키는 쓰지 않는다). 저장은 합친 결과가 설정 모델로 읽히는지 본 뒤 임시 파일을 바꿔 끼우므로, 쓰다 죽어도 이전 파일이 남는다. 음성 프로바이더와 whisper 모델은 `VoiceService` 를 다시 만들어 쓰므로 whisper 면 모델 적재만큼 응답이 늦다. `restart_keys` 는 [POST /api/restart](#post-apirestart) 또는 [POST /ion/restart](#post-ionrestart) 뒤에 반영된다. 키별 방식은 `docs/features.md` 의 settings 절.

---

### POST /api/restart

백엔드가 스스로 정상 종료(exit 0)해 Docker 의 `restart: unless-stopped` 가 다시 띄우게 한다. HUD SET 화면의 RESTART BACKEND 가 [POST /ion/restart](#post-ionrestart) 로 안 될 때 부른다.

#### Endpoint

```
POST /api/restart
```

#### 호출 규약

| 항목 | 값 |
|---|---|
| Method | `POST` |
| 인증 | 설정 시 필요 |
| 요청 Content-Type | 없음 (본문 없음) |
| 응답 Content-Type | `application/json` |
| 필수 헤더 | 없음 |

#### Request Body

없음.

#### Query / Path 파라미터

| 파라미터 | 위치 | 타입 | 필수 | 기본값 | 설명 |
|---|---|---|---|---|---|
| 없음 | | | | | |

#### Response Body

| 필드 | 타입 | 널 허용 | 설명 |
|---|---|---|---|
| `ok` | boolean | 아니오 | 종료가 예약됐는지 |
| `result` | string | 아니오 | `restarting` 또는 `no supervisor` |

#### 응답 코드

| 코드 | 의미 | 본문 |
|---|---|---|
| `202` | 종료 예약됨. 응답 0.5초 뒤 SIGTERM | `{"ok": true, "result": "restarting"}` |
| `401` | 인증이 켜져 있는데 키가 없음 | `{"error": "unauthorized"}` |
| `409` | 컨테이너 밖(`/.dockerenv` 없음). 종료하면 다시 뜨지 않아 거절 | `{"ok": false, "result": "no supervisor"}` |

#### 호출 예시

```bash
$ curl -s -X POST http://localhost:7777/api/restart -H 'Authorization: Bearer <키>'
{"ok":true,"result":"restarting"}
```

#### 특이사항

**재호출**: 종료가 예약된 뒤 다시 불러도 종료는 한 번이다(같은 202). 응답 전에 열린 HUD 전부에 ws 로 `{"type": "restarting"}` 을 보내 화면이 `연결 끊김 — 재시작 중` 을 보이고, 소켓이 닫히면 기존 재접속 루프가 돌아온 뒤 다시 붙는다. 종료는 uvicorn 의 종료 훅(세션 저장, 기억 정리)을 돌리고 10초를 넘기면 바로 끝낸다(`docker restart` 의 t 와 같다). Docker 의 RestartCount 가 오르므로 10분 안에 3번이면 Ion 이 `restart_loop` 사고를 연다. Ion 의 health(15초 간격, 3회 연속 실패)가 지나기 전에 올라와야 `backend_down` 사고가 열리지 않는다.

---

### GET /api/slash-commands

슬래시 명령 목록. 입력창 자동완성용. 같은 목록이 WS `connected` 메시지에도 들어 있어 HUD 는 이 엔드포인트를 쓰지 않는다.

#### Endpoint

```
GET /api/slash-commands
```

#### 호출 규약

| 항목 | 값 |
|---|---|
| Method | `GET` |
| 인증 | 설정 시 필요 |
| 요청 Content-Type | 없음 (본문 없음) |
| 응답 Content-Type | `application/json` |
| 필수 헤더 | 없음 |

#### Request Body

없음.

#### Query / Path 파라미터

| 파라미터 | 위치 | 타입 | 필수 | 기본값 | 설명 |
|---|---|---|---|---|---|
| 없음 | | | | | |

#### Response Body

| 필드 | 타입 | 널 허용 | 설명 |
|---|---|---|---|
| `commands` | `{name, description}[]` | 아니오 | 이름순. 디스패처가 없으면 빈 배열 |

#### 응답 코드

| 코드 | 의미 | 본문 |
|---|---|---|
| `200` | 정상 | 위 스키마 |

#### 호출 예시

```bash
$ curl -s http://localhost:7777/api/slash-commands
{"commands": [{"name": "branch", "description": "[session_id] 세션을 분기"}, {"name": "cleanup", "description": "옛 데이터 현황과 삭제 (agents | stm, confirm 필요)"}, ...]}
```

#### 특이사항

**재호출**: 상태를 바꾸지 않는다. 승인된 절차(`/procedures approve`)가 늘면 목록도 는다.

---

### GET /api/tools

등록된 도구 목록. SET 화면 SYSTEM 카드의 TOOLS 가 쓴다.

#### Endpoint

```
GET /api/tools
```

#### 호출 규약

| 항목 | 값 |
|---|---|
| Method | `GET` |
| 인증 | 설정 시 필요 |
| 요청 Content-Type | 없음 (본문 없음) |
| 응답 Content-Type | `application/json` |
| 필수 헤더 | 없음 |

#### Request Body

없음.

#### Query / Path 파라미터

| 파라미터 | 위치 | 타입 | 필수 | 기본값 | 설명 |
|---|---|---|---|---|---|
| `session_id` | query | string | 아니오 | 없음 | 열린 세션 id. 주면 그 세션 에이전트가 쓰는 도구만(정의의 `tools`, 에이전트만 쓰는 `lh_notice` 등 포함, 늘 붙는 `ask_agent`, `remember_task_pattern`, `recall_episodes` 포함), 없거나 열리지 않은 세션이면 앱 전체(에이전트만 쓰는 도구 제외) |

#### Response Body

| 필드 | 타입 | 널 허용 | 설명 |
|---|---|---|---|
| `tools` | `{name, description, approval}[]` | 아니오 | 이름순. `description` 은 첫 줄 160자. `approval` 은 실행 전 승인이 필요한 도구(`ASH_SECURITY__REQUIRE_APPROVAL_FOR`, 기본 `bash`, `write_file`, `edit_file`) |

#### 응답 코드

| 코드 | 의미 | 본문 |
|---|---|---|
| `200` | 정상 | 위 스키마 |

#### 호출 예시

```bash
$ curl -s http://localhost:7777/api/tools
{"tools": [{"name": "bash", "description": "Execute a bash command and return stdout/stderr. Use with caution.", "approval": true}, {"name": "edit_file", "description": "Replace an exact string in a file. ...", "approval": true}, ...]}
```

#### 특이사항

**재호출**: 상태를 바꾸지 않는다. 승인된 절차는 어느 에이전트의 것이든 `procedure_<name>` 도구로 여기 나타난다. 대화에서는 그 절차를 배운 에이전트에게만 보인다.

---

### GET /api/creative/files/{path}

크리에이티브 워크스페이스(`ASH_CREATIVE__DIR`, 기본 `/data/creative`. compose 가 `ASH_CREATIVE_DIR` 를 여기 마운트한다)의 영상, 음악, 이미지 파일. HUD 의 플레이어 모달이 `tool_execution_end.artifacts` 의 `path` 로 받는다.

#### Endpoint

```
GET /api/creative/files/out/manim/circle-992298/CircleToSquare.mp4
```

#### 호출 규약

| 항목 | 값 |
|---|---|
| Method | `GET` |
| 인증 | 설정 시 필요(화면은 `apiFetch` 로 받아 blob URL 로 재생한다) |
| 응답 Content-Type | 확장자에 따라 `video/mp4`, `video/webm`, `audio/wav`, `audio/mpeg`, `image/png` 등 |

#### Query / Path 파라미터

| 파라미터 | 위치 | 타입 | 필수 | 설명 |
|---|---|---|---|---|
| `path` | path | string | 예 | 워크스페이스 기준 상대 경로. 절대 경로, `~`, `..`, 미디어가 아닌 확장자는 404 |

#### 응답 코드

| 코드 | 의미 | 본문 |
|---|---|---|
| `200` | 파일 | 파일 본문 |
| `404` | 없거나 밖이거나 미디어가 아님 | `{"error": "no such media: <path>"}` |

#### 특이사항

**재호출**: 상태를 바꾸지 않는다. 쓰기 경로는 없다(워커만 쓴다).

---

### GET /api/docs/files/{path}

행정문서 폴더(`ASH_DOCS__DIR`, 기본 `/data/documents`. compose 가 `ASH_DOCS_DIR` 를 백엔드에 읽기 전용으로 마운트한다)의 렌더 결과. docs MCP 서버의 `render_document` 가 `.render/<이름>/` 에 만든 쪽 PNG 와 PDF 만 내준다. HUD 문서 창이 `tool_execution_end.artifacts` 의 `pages` 로 받는다.

#### Endpoint

```
GET /api/docs/files/.render/출장신청서/출장신청서-1.png
```

#### 호출 규약

| 항목 | 값 |
|---|---|
| Method | `GET` |
| 인증 | 설정 시 필요(화면은 `apiFetch` 로 받아 blob URL 로 띄운다) |
| 응답 Content-Type | `image/png`, `application/pdf` (404 는 `application/json`) |

#### Query / Path 파라미터

| 파라미터 | 위치 | 타입 | 필수 | 설명 |
|---|---|---|---|---|
| `path` | path | string | 예 | 문서 폴더 기준 상대 경로. `.render/` 로 시작하고 `.png`, `.pdf` 로 끝나야 한다. 원본 문서, 템플릿(`.templates/`), `..` 로 `.render/` 밖을 가리키면 404 |

#### 응답 코드

| 코드 | 의미 | 본문 |
|---|---|---|
| `200` | 파일 | 파일 본문 |
| `404` | 없거나 `.render/` 밖이거나 png, pdf 가 아님 | `{"error": "no such render: <path>"}` |

#### 특이사항

**재호출**: 상태를 바꾸지 않는다. 백엔드는 문서 폴더에 쓰지 않는다(쓰기는 ash-mcp 의 docs 서버만. 예외는 채팅 첨부를 두는 `uploads/` 하나). 같은 문서를 다시 렌더하면 같은 경로의 파일이 새 내용으로 바뀐다.

---

### GET /api/docs/structure

HUD 문서 창의 편집 보기가 문서 구조를 받는다. 백엔드가 docs MCP 의 `inspect_document(include_empty=true)` 를 불러 결과를 그대로 준다. 아래 다섯 엔드포인트(이것과 plan, apply, fields, templates)는 같은 규약을 따른다.

- 호출 기록과 MCP 정책의 에이전트 이름은 `hud` 다.
- 정책이 `deny` 면 403 이다. `ask` 는 사용자가 버튼을 누른 것을 승인으로 보고 부른다.
- docs 서버가 설정에 없거나 답하지 않으면 503 이다(시간 제한은 그 서버 설정의 `timeout`).
- 도구가 `error` 를 돌려주면 422 이고, 본문은 도구 결과 그대로다(`error`, 있으면 `issues`).
- 입력 모양이 틀리면 docs 서버를 부르지 않고 422 다(FastAPI 검증 오류).

#### Endpoint

```
GET /api/docs/structure?path=uploads/3f2a9c1d0b7e-출장신청서.docx
```

#### 호출 규약

| 항목 | 값 |
|---|---|
| Method | `GET` |
| 인증 | 설정 시 필요 |
| 응답 Content-Type | `application/json` |

#### Query 파라미터

| 파라미터 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `path` | string | 예 | 문서 폴더 기준 상대 경로(500자까지). 폴더 밖과 숨김 이름은 docs 서버가 거절한다 |
| `table` | string | 아니오 | 표 id(`t3`)나 시트 이름. 주면 그 표의 칸만 |
| `offset` | integer | 아니오 | `table` 과 함께. 이 칸부터 2000개(기본 0) |

#### Response Body

`inspect_document` 결과. `path`, `format`, `paragraphs[{id, text, style?, readonly?}]`, `tables[{id, name?, anchor?, rows, cols, cells[{id, row, col, text, address?, row_span?, col_span?}]}]`(anchor 는 본문에서 표 앞에 오는 문단 수, DOCX 와 HWPX 만), 큰 문서는 `tables_omitted`, `truncated`, 나눠 읽을 때 `next_offset`.

```json
{"path": "uploads/3f2a9c1d0b7e-출장신청서.docx", "format": "docx",
 "paragraphs": [{"id": "p0", "text": "출장 신청서", "style": "Title"}],
 "tables": [{"id": "t0", "rows": 2, "cols": 2, "cells": [
   {"id": "t0r0c0", "row": 0, "col": 0, "text": "성명"}, {"id": "t0r0c1", "row": 0, "col": 1, "text": ""}]}]}
```

#### 응답 코드

| 코드 | 의미 | 본문 |
|---|---|---|
| `200` | 구조 | 위 |
| `403` | MCP 정책이 막음 | `{"error": "MCP 정책이 막았다: ..."}` |
| `422` | 입력 모양이 틀림, 또는 도구 오류(없는 파일, 지원하지 않는 형식) | 검증 오류, 또는 `{"error": "..."}` |
| `503` | docs 서버가 없거나 답하지 않음 | `{"error": "docs MCP 서버가 설정에 없다"}` |

#### 특이사항

**재호출**: 상태를 바꾸지 않는다. 호출 기록(`~/.ash/mcp_audit`)에 한 줄씩 쌓인다.

---

### POST /api/docs/plan

고친 곳을 저장하지 않고 미리 본다. docs MCP 의 `plan_edit`.

#### Endpoint

```
POST /api/docs/plan
```

#### Request Body

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `path` | string | 예 | 문서 폴더 기준 상대 경로 |
| `replacements` | array | 예 | 1개에서 200개. `{target, text}`. `target` 은 `p3`, `t0r1c2`, `t0r1c2p0`, `s1sh4p0` 꼴만, `text` 는 5000자까지 |

```json
{"path": "uploads/3f2a9c1d0b7e-출장신청서.docx", "replacements": [{"target": "t0r0c1", "text": "홍길동"}]}
```

#### Response Body

```json
{"plan_id": "9c1d0b7e3f2a", "path": "uploads/3f2a9c1d0b7e-출장신청서.docx", "ok": true, "issues": [],
 "changes": [{"target": "t0r0c1", "before": "", "after": "홍길동"}]}
```

`ok` 가 거짓이면 `issues` 에 이유(없는 대상, 읽기 전용, 바뀌는 것이 없음)가 오고 적용할 수 없다. 응답 코드는 structure 와 같다.

#### 특이사항

**재호출**: 같은 원본과 같은 계획이면 같은 `plan_id` 다(원본 크기와 수정 시각을 섞는다). 파일을 쓰지 않는다.

---

### POST /api/docs/apply

미리 본 계획을 적용해 원본 옆 새 파일(`.edited-<시각>`)로 저장한다. docs MCP 의 `apply_edit`. 이 버튼 누름이 사람의 승인이다.

#### Endpoint

```
POST /api/docs/apply
```

#### Request Body

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `plan_id` | string | 예 | 소문자 16진수 12자 |

#### Response Body

`apply_edit` 결과(`plan_id`, `source`, `output`, `verify`, `changes`, `preview`)에 더해, 미리보기 렌더가 있으면 `document`(문서 첨부 `{kind: "document", path, title, store: "docs", pages, source}`)를 싣는다. 화면은 이것을 문서 창에 띄운다.

#### 특이사항

**재호출**: 같은 `plan_id` 를 다시 보내면 docs 서버가 처음 결과를 그대로 돌려준다(새 파일을 더 만들지 않는다). 계획을 세운 뒤 원본이 바뀌었으면 422.

---

### GET /api/docs/fields

빈 양식의 채울 자리 후보. docs MCP 의 `detect_fields`. 저장하지 않는다.

#### Endpoint

```
GET /api/docs/fields?path=uploads/3f2a9c1d0b7e-출장신청서.docx
```

#### Response Body

`{template_id, format, candidates[{name, label, type, required, options, locator, rule, confidence}], truncated?}`

#### 특이사항

**재호출**: 같은 문서면 같은 목록과 순서. 상태를 바꾸지 않는다.

---

### POST /api/docs/templates

화면의 양식 등록 표에서 고른 필드로 빈 양식을 등록한다. docs MCP 의 `register_template(kind=blank_form)`.

#### Endpoint

```
POST /api/docs/templates
```

#### Request Body

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `path` | string | 예 | 원본 문서 |
| `template_id` | string | 예 | 한글, 영문, 숫자, `-`, `_` 64자까지 |
| `fields` | array | 예 | 1개에서 200개. `{name, type, required, options, locator}`. 모양은 docs 서버가 검사한다 |

#### Response Body

`{template_id, format, kind, source, fields, registered}`. 자리를 문서에서 찾지 못하면 422 와 `{"error", "issues"}`.

#### 특이사항

**재호출**: 같은 id 와 같은 원본이면 있던 것을 돌려주고 `registered: false`. 같은 id 가 다른 원본으로 있으면 422(새 버전 id 를 쓴다).

---

### POST /api/uploads

채팅 첨부파일 하나를 `uploads/<내용 sha256 앞 12자>-<정리한 이름>` 에 저장한다. 형식은 가리지 않는다. HUD 입력창의 📎 와 끌어다 놓기가 부르고, 받은 `id` 를 ws `user_message.attachments` 에 넣는다. compose 는 호스트 임시 폴더(`ASH_UPLOAD_DIR`, 기본 `/tmp/ash-uploads`)를 백엔드와 ash-mcp 의 `/data/documents/uploads` 에 붙인다. 마지막으로 올린 뒤 `ASH_DOCS__UPLOAD_TTL_HOURS`(기본 24)시간이 지나면 지운다(올릴 때마다, 기동 때, 1시간마다 확인).

#### Endpoint

```
POST /api/uploads
```

#### 호출 규약

| 항목 | 값 |
|---|---|
| Method | `POST` |
| 인증 | 설정 시 필요 |
| 요청 Content-Type | `multipart/form-data` |
| 응답 Content-Type | `application/json` |

#### Request Body

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `file` | file | 예 | 올릴 파일 하나. 50MB 까지. 이름은 경로 부분을 버리고 글자, 숫자, `.`, `-`, `_`, 한글 밖의 글자를 `_` 로 바꾼다 |

#### Response Body

| 필드 | 타입 | 설명 |
|---|---|---|
| `id` | string | 내용 sha256 앞 12자. 같은 내용이면 같다 |
| `name` | string | 정리한 이름 |
| `path` | string | 문서 폴더 기준 상대 경로(`uploads/<id>-<name>`). Evi 문서 도구에 그대로 넘긴다 |
| `size` | integer | 바이트 |
| `mime` | string | 브라우저가 준 형식, 없거나 `application/octet-stream` 이면 이름으로 짐작 |
| `kind` | string | `image`, `audio`, `video`, `document`(DOCX, XLSX, PPTX, HWP(X), PDF, TXT, CSV), `other` |

#### 응답 코드

| 코드 | 의미 | 본문 |
|---|---|---|
| `200` | 저장함(또는 이미 있음) | 위 스키마 |
| `413` | 50MB 초과. 받는 도중 넘으면 그때 끊는다 | `{"error": "파일이 너무 크다(최대 52,428,800바이트)"}` |
| `422` | `file` 이 없다 | FastAPI 검증 오류 |

#### 호출 예시

```bash
$ curl -s -F 'file=@출장신청서.hwpx' http://localhost:7777/api/uploads
{"id":"3f2a9c1d0b7e","name":"출장신청서.hwpx","path":"uploads/3f2a9c1d0b7e-출장신청서.hwpx","size":48213,"mime":"application/octet-stream","kind":"document"}
```

#### 특이사항

**재호출**: 같은 파일을 다시 올리면 같은 응답이고 파일을 더 만들지 않는다(이름이 내용 해시로 정해진다). 대신 보관 기한을 지금부터 다시 센다. 이름만 다르고 내용이 같으면 새 이름으로 하나 더 생긴다. 지우는 API 는 없다(기한이 지나면 저절로 지워진다).

---

### GET /api/voice/phrases/{name}

미리 녹음한 읽기 문구 하나의 wav. 화면은 이벤트(웨이크워드, 도구 시작, Focus 전환 등)에 맞춰 합성 대신 이 파일을 재생한다.

#### Endpoint

```
GET /api/voice/phrases/{name}
```

#### 호출 규약

| 항목 | 값 |
|---|---|
| Method | `GET` |
| 인증 | 공통 규약과 같다 |
| 요청 Content-Type | 없음 (본문 없음) |
| 응답 Content-Type | `audio/wav` (404 는 `application/json`) |
| 필수 헤더 | 없음 |

#### Request Body

없음.

#### Query / Path 파라미터

| 파라미터 | 위치 | 타입 | 필수 | 기본값 | 설명 |
|---|---|---|---|---|---|
| `name` | path | string | 예 | 없음 | 문구 이름. `connected.voice.phrases` 에 온 이름 중 하나 |

#### Response Body

wav 바이트. 문구 목록은 `ASH_VOICE__PHRASES_DIR` 의 `phrases.json` 이고, 목록에 있으면서 wav 파일도 있는 이름만 내준다.

#### 응답 코드

| 코드 | 의미 | 본문 |
|---|---|---|
| `200` | 정상 | wav |
| `404` | 모르는 이름이거나 문구 폴더를 설정하지 않음 | `{"error": "unknown phrase: hello"}` |

#### 호출 예시

```bash
$ curl -s -o wake_up.wav -w '%{http_code} %{content_type}\n' http://localhost:7777/api/voice/phrases/wake_up
200 audio/wav
```

#### 특이사항

**재호출**: 상태를 바꾸지 않는다. 문구 목록은 기동 때 한 번 읽으므로 파일을 바꿨으면 서버를 다시 띄운다.

---

### GET /api/workflow

에이전트 관계 그래프. Workflow 화면이 처음 열릴 때 받고, 그 뒤는 ws `workflow_changed` 로 한 건씩 더한다. `session` 을 주면 그 세션의 지도 뿌리(`root`)도 준다.

#### Endpoint

```
GET /api/workflow
GET /api/workflow?session=default
```

#### 호출 규약

| 항목 | 값 |
|---|---|
| Method | `GET` |
| 인증 | 설정 시 필요 |
| 요청 Content-Type | 없음 (본문 없음) |
| 응답 Content-Type | `application/json` |
| 필수 헤더 | 없음 |

#### Request Body

없음.

#### Query / Path 파라미터

| 파라미터 | 위치 | 타입 | 필수 | 기본값 | 설명 |
|---|---|---|---|---|---|
| `session` | query | string | 아니오 | 없음 | 지도의 뿌리를 알 세션 id(200자 이하). 주면 응답에 `root` 가 든다 |

#### Response Body

| 필드 | 타입 | 널 허용 | 설명 |
|---|---|---|---|
| `agents` | object[] | 아니오 | 최상위 에이전트 `{id, name, description, primary, main}`. main 이 첫 번째. `description` 은 정의의 설명 첫 줄 160자(화면의 호버 한 줄) |
| `subagents` | string[] | 아니오 | 위임 도구(`agent_<이름>`)로 실린 sub-agent 이름순. 팀 전용 풀의 기능 담당(`parent`)도 든다 |
| `subagent_owners` | object | 아니오 | `{<sub-agent>: <최상위 id>}`. `parent` 가 있는 기능 담당만. 그래프가 그 허브 아래에 둔다 |
| `capabilities` | object[] | 아니오 | 도구마다 `{name, description, approval, agents}`. `agents` 는 그 도구를 세션에서 쓰는 최상위 에이전트 id(정의의 `tools`, `never` 를 거른 것, 에이전트 순서). 한 에이전트만 가진 도구가 먼저, 그다음 이름순. `agent_<이름>` 위임 도구는 빠진다. `description` 은 첫 줄 160자, `approval` 은 실행 전 승인이 필요한지 |
| `edges` | `Delegation[]` | 아니오 | [Delegation](#delegation). 최근 200개, 오래된 것부터. `ASH_WORKFLOW__BACKEND=postgres` 면 기동 때 읽어 온 지난 위임도 든다 |
| `root` | object | 예 | `session` 을 줬을 때만. `{session_id, agent, name, model, context_tokens}`. `agent` 는 열린 세션이면 그 에이전트, 아니면 저장소 메타의 에이전트, 둘 다 없으면 main. `model` 은 그 에이전트 프로필의 모델 이름. `context_tokens` 는 그 세션 마지막 assistant 메시지의 입력과 캐시 읽기 토큰 합(다음 턴이 다시 읽는 양). 메시지가 없으면 0 |

#### 응답 코드

| 코드 | 의미 | 본문 |
|---|---|---|
| `200` | 정상 | 위 스키마 |

#### 호출 예시

```bash
$ curl -s 'http://localhost:7777/api/workflow?session=default'
{"agents":[{"id":"main","name":"A.S.H.","description":"","primary":"#e6e8ea","main":true}],"subagents":["notes"],"subagent_owners":{"notes":"scribe"},"capabilities":[{"name":"bash","description":"셸 명령 실행","approval":true,"agents":["main"]}],"edges":[{"edge_id":"default:call_1","kind":"ask","source":"main","target":"scribe","label":"오늘 일정 정리","started_ms":1791613276663,"ended_ms":1791613279001,"ok":true,"session_id":"default","tokens":59012}],"root":{"session_id":"default","agent":"main","name":"A.S.H.","model":"claude-sonnet-5-5","context_tokens":598400}}
```

#### 특이사항

**재호출**: 상태를 바꾸지 않는다. 간선은 기본(`in_memory`)이면 재시작하면 비고, `postgres` 면 `ash_workflow_edges` 에서 최근 200개를 읽어 온다(재시작 때 끝나지 않은 위임은 `ended_ms` 가 기동 시각, `ok` 가 null). sub-agent 세션 안에서 다시 맡긴 위임은 없다. `root` 는 세션 저장소를 읽으므로 메시지가 많은 세션은 그만큼 걸린다.

---

### GET /api/workflow/layout

Workflow 그래프에서 사용자가 옮기거나 `정렬 최적화` 가 정한 노드 자리. 설치 하나에 하나라 어느 기기, 어느 창에서 열어도 같다. 화면이 처음 열릴 때 한 번 받는다.

#### Endpoint

```
GET /api/workflow/layout
```

#### 호출 규약

| 항목 | 값 |
|---|---|
| Method | `GET` |
| 인증 | 설정 시 필요 |
| 요청 Content-Type | 없음 (본문 없음) |
| 응답 Content-Type | `application/json` |
| 필수 헤더 | 없음 |

#### Request Body

없음.

#### Query / Path 파라미터

없음.

#### Response Body

| 필드 | 타입 | 널 허용 | 설명 |
|---|---|---|---|
| `nodes` | object | 아니오 | `{<노드 키>: {x, y}}`. 키는 `agent:<id>`, `leaf:<에이전트>:<이름>`, `shared:<이름>`. 좌표는 그림(viewBox) 단위. 저장한 적 없으면 `{}` |

#### 상태 코드

| 코드 | 의미 | 본문 |
|---|---|---|
| `200` | 정상 | 위 스키마 |

#### 호출 예시

```bash
$ curl -s http://localhost:7777/api/workflow/layout
{"nodes":{"agent:main":{"x":480.0,"y":210.0},"leaf:main:bash":{"x":370.0,"y":180.0}}}
```

#### 특이사항

**재호출**: 상태를 바꾸지 않는다. 정본은 `ASH_WORKFLOW__LAYOUT_PATH`(기본 `~/.ash/workflow_layout.json`)다. 파일이 없거나 깨졌으면 `{"nodes": {}}` 를 돌려주고 화면은 기본 배치로 그린다.

---

### PUT /api/workflow/layout

노드 배치 전체를 바꾼다. HUD 는 끌기, 방향키, `정렬 최적화`, `원래대로` 뒤 0.6초 동안 더 바뀌지 않으면 그때의 배치를 보낸다.

#### Endpoint

```
PUT /api/workflow/layout
```

#### 호출 규약

| 항목 | 값 |
|---|---|
| Method | `PUT` |
| 인증 | 설정 시 필요 |
| 요청 Content-Type | `application/json` |
| 응답 Content-Type | `application/json` |
| 필수 헤더 | 없음 |

#### Request Body

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `nodes` | object | 아니오 | `{<노드 키>: {x, y}}`. 노드 2000개 이하, 키는 제어 문자 없이 1~200자, `x`, `y` 는 ±100000 안의 유한한 수. 다른 필드는 받지 않는다. 비우면(`{}`) 기본 배치로 돌아간다 |

#### Query / Path 파라미터

없음.

#### Response Body

저장한 배치. [GET /api/workflow/layout](#get-apiworkflowlayout) 과 같다.

#### 상태 코드

| 코드 | 의미 | 본문 |
|---|---|---|
| `200` | 저장함 | 위 스키마 |
| `422` | 본문 검증 실패(범위 밖 좌표, 긴 키, 노드 수 초과, 모르는 필드) | FastAPI 검증 오류 |

#### 호출 예시

```bash
$ curl -s -X PUT http://localhost:7777/api/workflow/layout -H 'Content-Type: application/json' \
    -d '{"nodes":{"agent:main":{"x":480,"y":210}}}'
{"nodes":{"agent:main":{"x":480.0,"y":210.0}}}
```

#### 특이사항

**재호출**: 합치지 않고 통째로 바꾼다. 같은 본문을 다시 보내면 같은 응답과 같은 파일이 남는다(키를 정렬해 쓴다). 쓰기는 임시 파일 뒤 교체라 중간에 죽어도 앞 배치가 남는다. 두 창이 동시에 보내면 나중에 닿은 것이 이긴다.

---

### GET /api/mcp/policy

MCP 도구 정책과 붙은 도구의 지금 판정. SET 화면의 MCP 카드가 열릴 때 받는다.

#### Endpoint

```
GET /api/mcp/policy
```

#### 호출 규약

| 항목 | 값 |
|---|---|
| Method | `GET` |
| 인증 | 설정 시 필요 |
| 요청 Content-Type | 없음 (본문 없음) |
| 응답 Content-Type | `application/json` |
| 필수 헤더 | 없음 |

#### Request Body

없음.

#### Query / Path 파라미터

| 파라미터 | 위치 | 타입 | 필수 | 기본값 | 설명 |
|---|---|---|---|---|---|
| `agent` | query | string | 아니오 | `main` | `effective` 를 계산할 에이전트 id(`^[a-z0-9][a-z0-9_-]{0,39}$`). 정책의 `agents.<id>` 가 없으면 에이전트 제한 없이 판정 |

#### Response Body

| 필드 | 타입 | 널 허용 | 설명 |
|---|---|---|---|
| `enabled` | boolean | 아니오 | `mcp_servers` 가 있어 정책 문이 있는지. false 면 `tools` 는 빈 배열, `path` 는 빈 문자열 |
| `agent` | string | 아니오 | `effective` 를 계산한 에이전트 id(쿼리 그대로) |
| `path` | string | 아니오 | 정책 파일 경로(`security.mcp_policy_path`) |
| `policy` | object | 아니오 | `{defaults: {read, write, unknown}, servers: {<서버>: {lock?, tools: {<도구>: {mode?, lock?, calls_per_hour?}}}}, agents: {<에이전트>: {servers?, deny?}}}`. `mode` 는 `allow`, `ask`, `deny`. `lock` 은 `{인자: [허용 값]}`, 서버 `lock` 은 모든 도구에 |
| `tools` | object[] | 아니오 | 붙은 MCP 도구마다 `{server, name, kind, effective, description}`. `kind` 는 `read`, `write`, `unknown`, `effective` 는 `agent` 가 인자 없이 부를 때의 판정 |

#### 응답 코드

| 코드 | 의미 | 본문 |
|---|---|---|
| `200` | 정상 | 위 스키마 |
| `422` | `agent` 형식이 틀림 | FastAPI 검증 오류 |

#### 호출 예시

```bash
$ curl -s 'http://localhost:7777/api/mcp/policy?agent=main'
{"path":"/root/.ash/mcp_policy.yaml","agent":"main","policy":{"defaults":{"read":"allow","write":"ask","unknown":"ask"},"servers":{},"agents":{}},"tools":[{"server":"google","name":"send_gmail_message","kind":"write","effective":"ask","description":"메일 보내기"}],"enabled":true}
```

#### 특이사항

**재호출**: 상태를 바꾸지 않는다.

---

### PUT /api/mcp/policy

정책 문서를 통째로 바꾼다. 검증한 뒤 파일에 쓰고 바로 적용한다.

#### Endpoint

```
PUT /api/mcp/policy
```

#### 호출 규약

| 항목 | 값 |
|---|---|
| Method | `PUT` |
| 인증 | 설정 시 필요 |
| 요청 Content-Type | `application/json` |
| 응답 Content-Type | `application/json` |
| 필수 헤더 | `Content-Type` |

#### Request Body

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `defaults` | object | 아니오 | `{read?, write?, unknown?}` 각각 `allow`, `ask`, `deny`. 빠진 종류는 기본값 |
| `servers` | object | 아니오 | `{<서버>: {lock?, tools: {<도구>: {mode?, lock?, calls_per_hour?}}}}`. 서버 `lock` 은 모든 도구에 걸린다. `calls_per_hour` 는 0 에서 10000 |
| `agents` | object | 아니오 | `{<에이전트>: {servers?: string[], deny?: string[]}}` |

모르는 필드는 거부한다(`extra=forbid`).

#### Query / Path 파라미터

| 파라미터 | 위치 | 타입 | 필수 | 기본값 | 설명 |
|---|---|---|---|---|---|
| `agent` | query | string | 아니오 | `main` | `effective` 를 계산할 에이전트 id(`^[a-z0-9][a-z0-9_-]{0,39}$`). 정책의 `agents.<id>` 가 없으면 에이전트 제한 없이 판정 |

#### Response Body

`GET /api/mcp/policy` 와 같다.

#### 응답 코드

| 코드 | 의미 | 본문 |
|---|---|---|
| `200` | 저장하고 적용함 | `GET` 과 같은 스키마 |
| `404` | `mcp_servers` 가 없어 정책 문이 없다 | `{"error": "..."}` |
| `422` | 모르는 `mode`, 범위 밖 `calls_per_hour`, 모르는 필드, 형식이 틀린 `agent` | FastAPI 검증 오류 |

#### 호출 예시

```bash
$ curl -s -X PUT http://localhost:7777/api/mcp/policy -H 'Content-Type: application/json' \
    -d '{"servers":{"google":{"tools":{"send_gmail_message":{"mode":"ask","lock":{"to":["me@example.com"]}}}}}}'
{"path":"/root/.ash/mcp_policy.yaml","agent":"main","policy":{"defaults":{"read":"allow","write":"ask","unknown":"ask"},"servers":{"google":{"tools":{"send_gmail_message":{"lock":{"to":["me@example.com"]},"mode":"ask"}}}},"agents":{}},"tools":[...],"enabled":true}
```

#### 특이사항

**재호출**: 같은 본문을 두 번 보내면 파일과 응답이 같다. 부분 갱신이 아니라 통째 교체라 빠뜨린 도구의 정책은 지워진다.

---

### GET /api/mcp/audit

MCP 호출 기록. 최신이 앞.

#### Endpoint

```
GET /api/mcp/audit
```

#### 호출 규약

| 항목 | 값 |
|---|---|
| Method | `GET` |
| 인증 | 설정 시 필요 |
| 요청 Content-Type | 없음 (본문 없음) |
| 응답 Content-Type | `application/json` |
| 필수 헤더 | 없음 |

#### Request Body

없음.

#### Query / Path 파라미터

| 파라미터 | 위치 | 타입 | 필수 | 기본값 | 설명 |
|---|---|---|---|---|---|
| `limit` | query | int | 아니오 | `50` | 1 에서 500 |

#### Response Body

| 필드 | 타입 | 널 허용 | 설명 |
|---|---|---|---|
| `entries` | object[] | 아니오 | 판정 줄 `{ts, type:"call", agent, server, tool, decision, reason, call}` 과 결과 줄 `{ts, type:"result", server, tool, ok, error}`. `call` 은 `서버.도구(인자=값, …)` 요약으로 비밀값 이름의 값은 `***`, 값은 60자에서 자른다 |

#### 응답 코드

| 코드 | 의미 | 본문 |
|---|---|---|
| `200` | 정상 | 위 스키마 |

#### 호출 예시

```bash
$ curl -s 'http://localhost:7777/api/mcp/audit?limit=2'
{"entries":[{"ts":1794741853895,"type":"result","server":"google","tool":"send_gmail_message","ok":true,"error":""},{"ts":1794741852895,"type":"call","agent":"main","server":"google","tool":"send_gmail_message","decision":"ask","reason":"write 도구 · 도구 정책 ask","call":"google.send_gmail_message(to=me@example.com)"}]}
```

#### 특이사항

**재호출**: 상태를 바꾸지 않는다. `mcp_servers` 가 없으면 빈 배열.

---

### GET /brand.js

에이전트 정체성(이름, 명언, 팔레트)을 `window.BRAND` 에 넣는 스크립트. 정적 셸은 에이전트와 무관하고 정체성은 이 라우트로만 들어간다.

#### Endpoint

```
GET /brand.js
```

#### 호출 규약

| 항목 | 값 |
|---|---|
| Method | `GET` |
| 인증 | 없음 |
| 요청 Content-Type | 없음 (본문 없음) |
| 응답 Content-Type | `application/javascript` |
| 필수 헤더 | 없음 |

#### Request Body

없음.

#### Query / Path 파라미터

| 파라미터 | 위치 | 타입 | 필수 | 기본값 | 설명 |
|---|---|---|---|---|---|
| 없음 | | | | | |

#### Response Body

JavaScript. `window.BRAND = {name, quote, palette: {primary, accent, background, nebula[]}}` 를 대입하고 CSS 변수(`--primary`, `--accent`, `--bg-0`, `--nebula-<i>`)를 설정한다. 값은 main 에이전트의 브랜드(`ASH_BRAND__*`)이고, 개성 문장(`persona`)은 모델에게 주는 지시라 싣지 않는다. 다른 에이전트 세션의 이름과 색은 화면이 `connected.agent` 로 바꾼다.

#### 응답 코드

| 코드 | 의미 | 본문 |
|---|---|---|
| `200` | 정상 | 스크립트 |

#### 호출 예시

```bash
$ curl -s http://localhost:7777/brand.js | head -c 200
window.BRAND = {"name": "A.S.H.", "quote": "System Online", "palette": {"primary": "#e6e8ea", "accent": "#f0642d", "background": "#14161a", "nebula": ["#ffb38a", "#f0642d", "#d9481a"]}};
```

#### 특이사항

**재호출**: 상태를 바꾸지 않는다. `Cache-Control: no-cache`.

---

### GET /manifest.json

PWA 매니페스트. 이름과 테마 색이 브랜드 설정에서 온다.

#### Endpoint

```
GET /manifest.json
```

#### 호출 규약

| 항목 | 값 |
|---|---|
| Method | `GET` |
| 인증 | 없음 |
| 요청 Content-Type | 없음 (본문 없음) |
| 응답 Content-Type | `application/json` |
| 필수 헤더 | 없음 |

#### Request Body

없음.

#### Query / Path 파라미터

| 파라미터 | 위치 | 타입 | 필수 | 기본값 | 설명 |
|---|---|---|---|---|---|
| 없음 | | | | | |

#### Response Body

Web App Manifest. `name`, `short_name`, `description`, `start_url`(`./`), `scope`, `display`(`standalone`), `orientation`, `background_color`, `theme_color`, `icons`(192, 512, maskable).

#### 응답 코드

| 코드 | 의미 | 본문 |
|---|---|---|
| `200` | 정상 | 매니페스트 |

#### 호출 예시

```bash
$ curl -s http://localhost:7777/manifest.json | head -c 200
{"name":"A.S.H. · HUD","short_name":"A.S.H.","description":"여러 AI 에이전트를 운영하는 Ash Industry 의 HUD","start_url":"./","scope":"./","display":"standalone","orientation":"any","ba
```

#### 특이사항

**재호출**: 상태를 바꾸지 않는다. 서버 미들웨어가 `Cache-Control: no-cache` 를 붙이고, nginx 도 같은 헤더를 붙인다. 정적 `manifest.json` 을 요청마다 읽어 `name`(`<이름> · HUD`), `short_name`, `background_color`, `theme_color` 만 main 에이전트 브랜드로 바꾼다.

---

### WS /ws

대화 채널. 연결 하나가 세션 하나에 붙고, 그 세션의 모든 에이전트 이벤트를 받는다. 같은 세션에 여러 연결이 붙으면 이벤트도 승인 요청도 전부에게 가고, 승인은 먼저 온 답 하나만 쓴다. 세션에 붙은 연결이 하나도 없을 때 도구가 승인을 요청하면 묻지 않고 바로 거부한다.

#### Endpoint

```
GET /ws?session_id=<id>&agent=<agent_id>&token=<key>   (Upgrade: websocket)
```

#### 호출 규약

| 항목 | 값 |
|---|---|
| Method | WebSocket |
| 인증 | 설정 시 `token` 쿼리 필수. 틀리면 accept 뒤 close `4401` |
| 에이전트 | 새 세션을 모르는 `agent` 로 열려 하거나 저장된 세션의 에이전트가 정의에 없으면 accept 뒤 close `4404`. 다시 붙어도 같은 답이다 |
| 메시지 포맷 | JSON 텍스트 프레임, 항상 `type` 필드. 바이너리 프레임은 웨이크워드용 오디오 하나뿐이다 |
| 필수 헤더 | 없음 |

#### Query / Path 파라미터

| 파라미터 | 위치 | 타입 | 필수 | 기본값 | 설명 |
|---|---|---|---|---|---|
| `session_id` | query | string | 아니오 | `default` | 열린 세션이 없으면 저장소에 만들고(이미 있으면 그대로) 조립한다 |
| `agent` | query | string | 아니오 | `main` | 새 세션을 맡을 에이전트. 이미 있는 세션(저장소 포함)은 저장된 에이전트로 열고 이 값은 무시한다 |
| `token` | query | string | 인증 시 예 | 없음 | API 키 |

#### 클라이언트 → 서버

| `type` | 필드 | 동작 |
|---|---|---|
| `user_message` | `text`, `id?`, `attachments?` | `attachments` 는 `POST /api/uploads` 의 `id` 목록(10개까지, 모르는 id 는 버린다). 있으면 `text` 가 비어도 보내고, 메시지 끝에 첨부마다 `[첨부] <이름> | 경로 <path>(문서 폴더 기준) | <kind> | <크기>바이트` 줄이 붙어 기록에도 남는다. png, jpeg, webp, gif 이고 5MB 이하인 이미지는 이번 턴 모델 호출에 그림으로도 붙는다(기록에는 글만. Ollama, vLLM 은 그림을 받지 않는다). 대기열이나 뒤에서 도는 작업으로 간 말에는 그림이 빠지고 안내 줄만 간다. 그 세션이 답하는 중이면 턴을 시작하지 않고 대기열에 담는다(`queue_changed`). 대기 중인 말은 그 턴의 도구 결과를 받은 직후 같은 턴의 사용자 메시지로 붙거나(`queue_delivered`), 턴이 끝나면 보낸 순서대로 빈 줄로 이어 다음 턴이 된다. `id`(영숫자와 `-`, 64자 이하, 아니면 서버가 만든다)가 같은 말은 한 번만 담긴다. 대화는 한가한데 그 세션에 뒤에서 도는 작업이 있으면 작은 모델이 그 작업에 대한 지시인지 가르고, 지시면 그 작업의 대기열로 보내며 `queue_delivered` 와 선응답 `proactive_message{kind:"filler"}`, `background_tasks`(그 작업의 `pending`)를 보낸다. 화면이 `id` 를 붙여 보냈는데 그 사이 턴이 끝나 바로 돌았으면 이 연결에 `queue_delivered` 를 보낸다. 슬래시 명령이면 디스패처가 처리하고 결과를 `agent_start`, `stream_delta`, `agent_end` 로 돌려준다. 남는 텍스트는 에이전트 프롬프트로. 비어 있으면 무시. `/focus` 로 시작하면 디스패처보다 먼저 Focus 가 받는다([Focus](#focus)) |
| `approval_response` | `id`, `approved`, `always` | `approval_request` 에 대한 답. 같은 `id` 에 먼저 온 답만 쓰고 나머지는 버린다. `always=true` 는 `approved=true` 일 때만 의미 있고 제안된 패턴을 세션 에이전트의 규칙 파일(`approvals/<agent_id>.yaml`)에 남긴다 |
| `proactive_feedback` | `id`, `accepted` | 🔔 에 대한 수락/무시. 임계치 학습기에 반영. 한 연결에서 같은 `id` 는 처음 한 번만 반영. Web HUD 는 더 보내지 않는다(서버가 다음 `user_message` 로 학습). 옛 화면을 위해 받는다. 이걸 받으면 다음 말로 다시 학습하지 않는다 |
| `reply_classify` | `kind`(`feedback`/`approval`), `id`, `text`, `context`, `has_always` | 키워드로 판정이 안 되는 짧은 답을 사고 모델로 분류. `feedback` 이면 `id` 는 🔔 의 `message_id`, `context` 는 🔔 본문. `approval` 이면 `id` 는 승인 요청 id, `context` 는 명령, `has_always` 는 항상 허용 패턴이 있는지. 결과는 `reply_classified`. 🔔 가 `accept`/`dismiss` 로 판정되면 서버가 바로 학습기에 반영한다(같은 `id` 는 한 번만). 승인은 판정만 돌려주고 승인 자체는 화면이 `approval_response` 로 보낸다 |
| `voice_tts_request` | `text`, `lang?`, `id?`, `source?`, `part?`, `full_text?`, `stream?` | 음성 합성. 서버가 마크다운 기호(제목, 강조, 목록, 표, 인라인 코드)를 지우고, 코드 블록과 URL 은 빼고, 링크는 글자만 남기고, 원, 만, 억 앞의 금액 숫자(`70,000,000원`)는 한글(`칠천만원`)로 바꾼 뒤 읽는다. 서버 TTS 가 없거나 읽을 글자가 없으면 `voice_tts_audio{data:"", text}` 로 되돌려 브라우저가 읽게 한다. `id` 는 결과에 그대로 돌아온다. `source`(reply, answer, filler, proactive, reminder, approval, approval_answer)는 무엇을 읽는지이고, 서버는 읽을 글을 외부 알림 채널(`spoken`)에도 보낸다. 서버가 이미 따로 보낸 `proactive`, `reminder`, `answer` 는 보내지 않는다. 같은 세션의 같은 글은 10초 안에 다시 와도(화면을 여럿 열었거나 재요청) 한 번만 보낸다. 화면이 글을 문장 조각으로 나눠 보내면 조각마다 `part`(0부터)와 따로 된 `id` 를 붙이고, `part` 0 에만 나누기 전 원문 `full_text` 를 붙인다. 서버는 조각마다 `voice_tts_audio` 를 하나씩 돌려주고, 외부 알림은 `part` 0 에서 `full_text` 로 한 번만 보낸다. `stream: true` 면 서버가 소리를 나오는 대로 조각으로 같은 `id` 의 `voice_tts_audio` 에 실어 보낸다(조각 길이는 TTS 프로바이더가 정한다). 영어 글은 문장마다 따로 합성한다. 조각으로 못 내는 TTS 는 문장마다 한 조각이다 |
| `voice_spoken` | `phrase` | 화면이 녹음 문구를 재생했다. 서버가 그 문구의 문장(`phrases.json` 의 `text`)을 외부 알림 채널에 보낸다. 같은 세션의 같은 문장은 10초 안에 한 번만. 모르는 이름이면 무시 |
| `voice_stt_submit` | `data`(base64), `mime`, `sample_rate`(기본 16000) | 서버 STT. `stt_provider` 가 browser 면 `stt_fallback` 으로 받아 적는다(처음 한 번 모델을 스레드에서 불러온다). `mime` 은 받기만 하고 쓰지 않는다. 서버 STT 가 없거나 `data` 가 비면 무시. 결과는 `voice_stt_result` |
| `abort` | 없음 | 진행 중인 에이전트 루프 중단. 한 데까지는 기록에 남고, 대기 중인 말이 있으면 바로 다음 턴이 된다. 도는 루프가 없으면 아무 일도 없다 |
| `send_now` | 없음 | 대기 중인 말을 지금 건넨다. 도구가 도는 중이면 그 턴을 선응답 `하던 작업은 뒤에서 이어 할게요. 끝나면 알려 드릴게요.` 로 떼어 뒤에서 잇게 하고(`background_tasks`), 글만 쓰는 중이면 그 단계를 멈춘다. 어느 쪽이든 대기 중인 말이 바로 다음 턴이 된다. 대기열이 비었으면 아무 일도 없다 |
| `background_stop` | `task_id`, `session_id?` | 그 세션(없으면 이 연결의 세션)의 뒤에서 도는 작업 하나를 멈춘다. 도는 도구 호출이 끝난 뒤 다음 확인 자리에서 멈추고 `background_tasks{done:{stopped:true}}`. 열린 세션이 아니거나 모르는 작업이면 아무 일도 없다 |
| `queue_take` | 없음 | 아직 건네지 않은 대기 말을 전부 되가져온다. 이 연결에 `queue_taken{items}`, 그 세션의 모든 연결에 빈 `queue_changed` |
| (바이너리 프레임) | 16kHz mono int16 LE PCM | 웨이크워드 감지. `connected.voice.wake` 가 true 일 때만 받고, 아니면 버린다. 프레임 경계는 자유롭다(서버가 80ms 단위로 이어 붙인다). 화면은 모드와 상관없이 기다리는 동안(듣기, 읽기, 응답, 승인 중이 아닐 때) 보낸다 |

#### 서버 → 클라이언트

| `type` | 필드 | 언제 |
|---|---|---|
| `connected` | `boot_id`, `session_id`, `agent`, `user`, `model`, `sessions[]`, `session_agents`, `active_agents[]`, `slash_commands[]`, `voice{stt_mode, stt_lang, server_stt, phrases[], wake}`, `reply_classifier`, `in_flight[]`, `approval_waiting[]`, `background_tasks[]`, `queued[]` | 접속 직후 한 번. `boot_id` 는 백엔드 프로세스의 기동 시각(epoch ms)이고 화면은 재접속 때 값이 바뀌었으면 새로 고친다(정적 파일을 새로 받는다). 그 뒤 쌓여 있던 `reminder` 를 `missed: true` 로 보내고, 진행 중인 Focus 작업이 있으면 `focus_state`, `focus_panel` 을 보낸다. `user` 는 인증이 켜져 있을 때 키의 사용자 이름, 아니면 null. `voice.stt_mode` 는 `browser`(Web Speech API) 또는 `server`(녹음을 `voice_stt_submit` 으로). `voice.server_stt` 는 브라우저 인식이 실패했을 때 녹음을 보내도 받아 적을 수 있는지(`stt_provider` 가 server 거나 `stt_fallback` 이 있을 때). `voice.phrases` 는 [읽기 문구](#get-apivoicephrasesname) 이름, `voice.wake` 는 웨이크워드 오디오를 받는지. `agent` 는 이 세션의 [Agent](#agent), `session_agents` 는 세션 id → 에이전트 id, `active_agents` 는 지금 루프가 도는 에이전트 id. `reply_classifier` 는 사고가 켜져 있어 `reply_classify` 를 쓸 수 있는지. `in_flight` 는 이 세션에서 지금 도는 턴의 이벤트(`agent_start` 부터, 연속된 `message_update` 는 하나로 합침, 최대 1000건)이고 턴이 없으면 빈 목록이다. 다른 에이전트로 옮겼다 돌아온 화면이 이력 뒤에 다시 그린다. `approval_waiting` 은 아래 `approval_waiting` 이벤트의 `waiting` 과 같다. `background_tasks` 는 아래 `background_tasks` 이벤트의 `tasks` 와 같다. `queued` 는 그 세션의 대기열(`queue_changed` 의 `items`) |
| `agent_start` | `session_id`, `prompt`, `agent_name`, `timestamp` | 루프 시작. `prompt` 는 늘 빈 문자열이다. `agent_name` 은 main 이 아닌 에이전트의 세션과 서브 에이전트에서 이름이 오고, main 세션의 루트 루프는 null. 슬래시 명령과 `/focus` 안내를 감싸는 `agent_start`, `agent_end` 는 `type` (과 `continues`)만 있다 |
| `turn_start` | `turn`, `timestamp` | 루프 안에서 LLM 호출 한 번이 시작될 때(0부터). 화면은 쓰지 않는다 |
| `message_update` | `text_delta`, `thinking_delta`, `timestamp` | 스트리밍 조각 |
| `stream_delta` | `text` | 슬래시 명령 결과 등 비스트림 텍스트 |
| `tool_execution_start` | `tool_call_id`, `tool_name`, `args`(object), `timestamp` | 도구 실행 시작 |
| `tool_execution_end` | `tool_call_id`, `tool_name`, `is_error`, `artifacts[]`, `timestamp` | 도구 실행 끝. `artifacts` 는 도구가 만든 결과물 `{kind: video\|audio\|image\|file\|document, path, title, store, pages[], source}`(`source` 는 문서가 그린 원본 경로, 다른 결과물은 빈 글). MCP 서버 `media` 의 결과 JSON(`output`, `video`, `audio`, `stems` 값)에서 모으고(`store: creative`), 서버 `docs` 의 `render_document` png, pdf 결과는 문서 하나(`kind: document`, `store: docs`, `title` 은 원본 파일 이름, `pages` 는 `.render/` 아래 쪽 그림이나 PDF, 60개까지)로 만든다. HUD 는 문서, 영상, 음악, 이미지 순으로 하나를 모달로 띄우고 파일은 `GET /api/creative/files/{path}` 나 `GET /api/docs/files/{path}` 로 받는다 |
| `agent_end` | `session_id`, `final_message`, `turns`, `agent_name`, `timestamp`, `continues?` | 루프 끝. `final_message` 는 마지막 assistant 메시지(`role`, `content[]`, `provider`, `model`, `usage{input, output, cache_read, cache_write}`, `stop_reason`, `error_message`, `timestamp`)이고 null 일 수 있다. 루트면 입력을 다시 받는다. `continues: true` 는 `/focus` 안내 뒤 메인 에이전트가 이어 돈다는 뜻이라, 화면은 입력 잠금과 음성 요청 표시를 그대로 둔다 |
| `agent_error` | `message`, `code`, `timestamp` | 모델 스트림이 오류를 냈다. `code` 는 지금 늘 null |
| `inner_thought` | `session_id`, `interpretation`, `decision`(기본 `silent`), `confidence`(0~1), `frame`(사고 프레임 전체), `timestamp` | 요청 시점과 성찰 시점의 사고 1회 |
| `thought_route` | `session_id`, `think`, `p_think` | router(`ASH_THOUGHT__ROUTER_MODEL`)가 켜져 있을 때 요청마다 한 번, 응답보다 먼저. `think: true` 면 사고가 응답과 함께 돌고 그 결과는 다음 턴 시스템 프롬프트에 한 번 들어간다. `p_think` 는 맥락 없는 판정과 직전 두 턴을 넣은 판정 중 큰 값이고, router 가 답하지 못하면 null 이며 `think: true` 로 둔다 |
| `thought_end` | `session_id`, `ok` | `think: true` 로 띄운 사고가 끝났다. 응답보다 늦게 올 수 있다. 실패해도 `ok: false` 로 보낸다 |
| `agenda_changed` | `session_id` | 요청마다 사고와 따로 도는 AGENDA 판단이 약속을 새로 열거나(기한 갱신 포함) 닫았다. 응답보다 늦게 올 수 있다. 화면은 `GET /api/agenda` 로 다시 읽는다 |
| `proactive_message` | `session_id`, `text`, `kind`(`filler`/`proactive`/`answer`), `speak`, `message_id` | 먼저 건네는 말. `proactive` 는 세션 대화 기록에도 assistant 메시지로 남아(히스토리에 보이고 다음 턴 모델이 안다) 사람이 건넨 말처럼 이어진다. 그 뒤 첫 `user_message` 를 서버가 이 말에 대한 반응(accept, dismiss, 딴 얘기는 약한 무시)으로 분류해 학습한다. 화면은 피드백을 묻지 않는다. `answer` 는 선응답으로 닫은 뒤 뒤에서 이어 돈 턴이 끝났을 때의 답이다. 대화 기록에도 남고(그 턴의 도구 호출과 결과 뒤), 화면은 에이전트의 답으로 그리며, 외부 알림 채널로도 간다. `message_id` 는 그 작업의 `task_id`. 지금 서버는 `filler` 를 보내지 않는다(선응답은 그 턴의 스트림과 `agent_end` 로 온다). Focus 작업 중이거나 그 세션이 답하는 중이면 `proactive` 를 보내지 않는다(`filler`, `answer` 는 보낸다). `speak` 는 지금 늘 false 다 |
| `approval_request` | `id`(uuid4), `command`(앞 500자), `reason`, `always_pattern`(없으면 빈 문자열) | 도구 실행 승인 요청. 같은 세션의 열린 연결 전부에 보내고, 기다리는 중에 새로 붙은 연결에도 보낸다. 요청 때 연결이 없어도 그 세션에 화면이 한 번이라도 붙었었다면 기다린다(다른 에이전트로 옮겨 간 경우). 화면이 붙은 적 없는 세션이면 바로 거부. 120초 안에 답이 없으면 거부로 처리 |
| `approval_resolved` | `id`, `timeout?` | 그 요청이 끝났다(어느 연결의 답, 또는 시간 초과). 아직 모달을 띄운 연결은 닫는다. 시간 초과면 `timeout: true` 이고, 에이전트 응답도 `승인 요청에 시간 안에 답이 없어 …` 로 거부(`승인이 거부되어 …`)와 구분된다 |
| `reminder` | `id`, `name`, `label`, `kind`, `agent`, `once`, `title`, `text`, `error`, `delayed_sec`, `fired_at`, `missed?` | 스케줄 실행 결과. 열린 연결 전부에 방송하고, 없으면 최근 20건을 쌓아 다음 접속 때 `missed: true` 로 보낸다. `label` 은 사람에게 보일 제목이다(사람이 붙인 이름, `/schedule` 이 붙인 이름이면 알림은 `알림`, 작업은 할 일 첫 줄). `kind: tool` 작업은 도구가 빈 글을 주면 보내지 않는다(새 공고가 없는 날 등). `kind: goal` 작업은 이미 알린 것만 있거나 알릴 것이 없으면 보내지 않고, `label` 은 `목표: <목표 문장 앞 60자>` 다. `deliver: conversation` 작업은 사용자가 그 에이전트와 최근 대화한 세션에 `proactive_message`(`kind: proactive`)로 건네고, 그런 세션이 없거나 건넬 수 없을 때만 이 이벤트로 보낸다 |
| `voice_tts_audio` | `data`(base64), `mime`, `text`, `id`, `more?` | 합성 결과. `text` 는 실제로 읽은 글이다. `data` 가 비면 브라우저 TTS 로(`text` 는 기호를 지운 문장). `ASH_VOICE__SPEAK_ENGLISH=true` 면 main 세션의 한국어 글은 `source` 와 상관없이 LLM 이 짧은 영어로 옮겨 영어 TTS 로 읽고(말투는 `voice.english_style`) `text` 에 그 영어를 준다. 옮기지 못하면(실패, 8초 초과) `voice.english_fallback`(기본 "I've put it on your screen.")을 읽는다. 다른 에이전트 세션은 원문 그대로다. 화면 글과 대화 기록은 한국어 그대로다. `id` 는 요청의 `id`(없었으면 null). 화면은 멈춘 읽기의 결과를 이 값으로 버린다. 요청이 `stream: true` 였으면 소리 조각마다 `more: true` 로 오고(`text` 는 그 조각이 속한 문장), 끝에 `data:""`, `text:""`, `more: false` 가 한 번 온다. 화면은 조각을 앞 조각이 끝나는 시각에 예약해 잇는다. 소리가 하나도 없었으면 끝 메시지의 `text` 에 읽을 글을 실어 브라우저가 읽게 한다. Qwen 서버가 첫 조각 전에 닿지 않으면 그 문장을 Piper 로 통째로 읽고, 조각을 보내다 끊기면 그 문장의 나머지는 읽지 않는다 |
| `voice_stt_result` | `text`, `error?`, `ambient?`, `silent?`, `unclear?`, `heard?` | 전사 결과. 말소리가 `voice.command_max_sec`(기본 12초)보다 길거나 글이 `voice.command_max_chars`(기본 120자)보다 길면 주변 대화로 보고 `text` 를 비우고 `ambient: true` 와 앞 80자 `heard` 를 준다. 되묻지 않는다(확신도 검사보다 먼저). 문장이 하나도 안 나오면(소음만 녹음) `text` 를 비우고 `silent: true` 만 준다. 되묻지 않는다. 확신도가 낮으면(말소리 없을 확률 > 0.6 또는 평균 로그 확률 < -1.0) `text` 를 비우고 `unclear: true` 와 받아 적은 글 `heard` 를 준다. 이때 서버가 이어서 되묻는 말을 `id` 없는 `voice_tts_audio` 로 보낸다(main 은 영어 `voice.english_unclear`, 기본 "I'm sorry, I didn't catch that.", 다른 에이전트는 한국어) |
| `voice_wake` | `score` | 바이너리 프레임의 오디오에서 웨이크워드를 들었다. 점수가 `ASH_VOICE__WAKE_THRESHOLD`(0.5) 이상인 첫 프레임에서 한 번 보내고, 그 뒤 1초(13프레임)는 다시 보내지 않는다 |
| `reply_classified` | `kind`, `id`, `verdict` | `reply_classify` 의 결과. `feedback` 은 `accept`/`dismiss`/`other`, `approval` 은 `allow`/`always`/`deny`/`unclear`. 사고 모델이 없거나 6초 안에 답하지 못하면 `other`, `unclear`. 항상 허용 패턴이 없는데 `always` 면 `allow` 로 낮춘다 |
| `approval_waiting` | `waiting[]{session_id, agent, count}` | 어느 세션이든 기다리는 승인 요청 수가 바뀔 때 열린 연결 전부에 목록 전체를 보낸다. 쌓아 두지 않는다. 화면은 지금 세션이 아닌 항목을 "승인 대기 · 이동" 띠로 보인다 |
| `queue_changed` | `session_id`, `items[]{id, text}` | 그 세션의 대기열 전체. 담거나 되가져올 때, 다음 턴으로 넘길 때. 화면은 받은 것으로 덮어쓴다 |
| `queue_delivered` | `session_id`, `items[]{id, text}`, `timestamp` | 대기 말이 모델에게 건네졌다(같은 턴의 도구 결과 뒤, 또는 다음 턴). 화면은 그 자리에 사용자 말로 붙인다. 진행 중인 턴의 재생(`in_flight`)에도 들어간다 |
| `artifacts` | `session_id`, `tool_name`, `artifacts[]{kind, path, title, store, pages}`, `timestamp` | 뒤로 넘긴 턴(선응답 뒤 이어 도는 턴)의 도구가 결과물을 만들었다. 그 턴의 `tool_execution_end` 는 화면에 오지 않아 결과물만 따로 낸다. 화면은 이것을 직접 띄우지 않고 아래 `artifacts_ready` 로 받는다 |
| `artifacts_ready` | `session_id`, `agent`, `artifacts[]{kind, path, title, store, pages}` | 열린 HUD 전부에 보낸다(SessionRelay). 어느 세션, 어느 에이전트의 도구가 만든 결과물이든(오류 없는 `tool_execution_end.artifacts`, `artifacts`) 사용자가 어느 화면에 있든 결과물 창(문서 창, 플레이어)을 띄운다. 맡긴 쪽과 맡은 쪽이 같은 결과물을 차례로 내므로 같은 `store:path` 는 20초 안에 한 번만 보낸다 |
| `session_message` | `session_id`, `agent`, `kind`(`proactive` \| `answer`), `text` | 열린 HUD 전부에 보낸다. 먼저 건넨 말과 뒤에서 끝난 답. 에이전트끼리의 대화 세션(`peer-`)과 대기 안내(`filler`)는 보내지 않는다. 화면은 지금 보는 세션 것은 `proactive_message` 로 이미 받았으니 버리고, 다른 세션 것은 활동 줄과 안 읽음 점으로 알린다 |
| `queue_taken` | `items[]{id, text}` | `queue_take` 의 답. 이 연결에만 |
| `background_tasks` | `tasks[]{task_id, session_id, agent, label, pending, applied}`, `done`(`{task_id, ok, stopped}` 또는 null) | 어느 세션이든 선응답으로 닫고 뒤에서 이어 도는 턴이 생기거나 끝날 때 열린 연결 전부에 목록 전체를 보낸다. 쌓아 두지 않는다. `done` 은 방금 끝난 작업. `label` 은 요청 앞 60자 |
| `background_task` | `session_id`, `task_id`, `label`, `state`(`started`/`updated`/`finished`), `ok`, `error`, `pending`(아직 읽지 않은 지시), `applied`(읽어 반영한 지시), `stopped` | 그 세션을 연 연결에만 오는 같은 사실. 화면은 `background_tasks` 를 쓰고 이것은 무시한다 |
| `agent_activity` | `active[]` | 어느 세션이든 루프가 시작하거나 끝나 일하는 에이전트 목록이 바뀔 때. 열린 연결 전부에 보내고 쌓아 두지 않는다. 먼저 시작한 순서, 같은 에이전트는 한 번 |
| `focus_state` | `session_id`, `state` | Focus 작업 상태 전체. `state.active=false` 면 Focus 종료(이때 `state` 는 `active`, `task_id` 뿐). 켜져 있으면 `task_id`, `task`, `steps[{title, done}]`, `progress`(0~1), `eta_sec`(완료 단계가 없으면 null), `elapsed_sec`. 접속 직후 진행 중인 작업이 있으면 한 번 보낸다 |
| `focus_panel` | `session_id`, `area`(`reference`/`log`/`analysis`), `markdown`, `busy` | 한 영역의 마크다운 전체. `busy=true` 는 sub-agent 가 갱신 중. 접속 직후 진행 중인 작업이 있으면 세 영역을 한 번씩 보낸다 |
| `workflow_changed` | `edge` | 위임이 열리거나 닫힐 때. `edge` 는 [Delegation](#delegation). 열린 연결 전부에 보내고 쌓아 두지 않는다 |
| `job_changed` | `job` | 백그라운드 작업이 시작하거나 끝날 때. `job` 은 [Job](#job) 에서 `enabled`, `next_run`, `agent` 가 빠진 모양 |
| `error` | `message` | 에이전트에 넘긴 요청이 실패했다(에이전트 사이 위임처럼 대기열을 쓰지 않는 호출에서 앞 요청이 3초 안에 끝나지 않아 거절한 `이전 요청을 아직 처리 중입니다. …` 포함. 화면의 `user_message` 는 거절되지 않고 대기열로 간다), `Focus 오류: …`, `TTS 오류: …` |

#### 호출 예시

```js
const ws = new WebSocket("ws://localhost:7777/ws?session_id=default");
ws.onmessage = (e) => console.log(JSON.parse(e.data).type);  // connected, agent_start, message_update, ...
ws.send(JSON.stringify({ type: "user_message", text: "안녕" }));
```

#### 특이사항

**재호출**: 같은 `session_id` 로 다시 붙으면 같은 세션이다. 재접속 자체는 멱등하다. 턴이 도는 중에 다시 붙으면 매번 그 시점까지의 `in_flight` 를 받고, 화면은 대화를 비운 뒤 다시 그리므로 몇 번 붙어도 같은 화면이 된다. `approval_waiting` 은 매번 목록 전체라 같은 것을 두 번 받아도 결과가 같다. `background_tasks` 도 목록 전체다. `user_message` 가 7.5초(`ASH_PROACTIVE__DETACH_AFTER_SEC`)를 넘기면 선응답으로 `agent_end` 가 먼저 오고 답은 뒤에 `proactive_message{kind:"answer"}` 로 온다. 같은 말을 다시 보내면 뒤에서 도는 작업이 하나 더 생긴다(같은 요청인지 가리지 않는다). `approval_request` 는 세션의 연결 전부가 받고 먼저 온 답이 채택되므로 탭을 여럿 열어도 같다. `user_message` 는 멱등하지 않다(보낼 때마다 한 턴). `reply_classify` 는 같은 답을 다시 보내면 모델을 다시 부르지만 🔔 학습은 연결당 `id` 하나에 한 번이다. 연결을 새로 열면 그 기록은 비므로 재접속 뒤 같은 `id` 를 다시 보내면 한 번 더 반영된다.

`reminder` 의 보류 큐는 기본(`ASH_SCHEDULER__NOTICE_BACKEND=in_memory`)이면 서버가 재시작되면 사라지고, `postgres` 면 `ash_pending_notices` 테이블에 있어 재시작 뒤 첫 접속 때 그대로 온다. 같은 알림은 `id` 로 하나만 남는다.

웨이크워드 감지기는 연결마다 하나이고 첫 오디오가 올 때 만든다. 앞 프레임을 기억하므로 재접속하면 처음부터 다시 듣는다.

#### Focus

`/focus <작업>` 은 이 세션의 Focus 작업을 시작하고, 안내(`agent_start`, `stream_delta`, `agent_end`)를 보낸 뒤 작업 문장을 에이전트 프롬프트로 이어 보낸다. 시작할 때 첫 분석과 단계 계획을 `ASH_FOCUS__READY_TIMEOUT_SEC`(30초)까지 기다린다. `/focus stop`(또는 `off`, `end`, `종료`, `끝`, `그만`. 대소문자 무시)은 끝내고, `/focus` 만 보내면 현황을 텍스트로 돌려준다.

| 명령 | 이미 작업이 있을 때 | 작업이 없을 때 |
|---|---|---|
| `/focus <작업>` | 거절하고 진행 중인 작업을 알려 준다 | 시작 |
| `/focus stop` | 종료, `focus_state{active:false}` | "진행 중인 작업이 없습니다" |
| `/focus` | 진행률과 단계 | 시작 방법 안내 |

Focus 동안 매 턴 앞에서 분석 sub-agent 가, 뒤에서 기록과 진행 sub-agent 가 돌고 결과를 `focus_panel`, `focus_state` 로 보낸다. 조사 sub-agent 는 시작할 때와 분석이 조사할 검색어를 낼 때 돈다. 메인 에이전트의 시스템 프롬프트에는 작업, 단계, 직전 분석, 조사 요약이 붙는다.

**재호출**: 세션당 작업은 하나다. `~/.ash/focus/active/<session_id>` 를 배타적으로 만들어 보증하므로 `/focus <작업>` 을 동시에 두 번 보내도 하나만 시작한다. `/focus stop` 은 두 번째부터 아무것도 하지 않는다. 서버가 재시작돼도 활성 표시와 `state.json` 으로 작업을 되살리고, 접속하면 화면을 Focus 로 돌려놓는다. 기록은 `~/.ash/focus/<task_id>/`(`log.md`, `references.md`, `analysis.jsonl`, `state.json`)에 남고 종료해도 지우지 않는다.

---

## 데이터 모델

### Agent

| 필드 | 타입 | 널 허용 | 설명 |
|---|---|---|---|
| `id` | string | 아니오 | 에이전트 id. main 은 `main`, 나머지는 정의 파일 이름 |
| `name` | string | 아니오 | 워드마크이자 표시 이름 |
| `description` | string | 아니오 | 맡은 일. main 은 빈 문자열 |
| `quote` | string | 아니오 | 명언 |
| `palette` | object | 아니오 | `primary`, `accent`, `background`, `nebula[]` 색(#rrggbb) |
| `main` | boolean | 아니오 | main 에이전트인지 |

### Schedule

| 필드 | 타입 | 널 허용 | 설명 |
|---|---|---|---|
| `name` | string | 아니오 | 작업 이름. `slash-`, `once-` 로 시작하면 `/schedule` 로, `goal-<목표 id>` 면 `/goal` 이나 `goal` 도구로 만든 것 |
| `description` | string | 아니오 | 설명. 자동 생성일 수 있다 |
| `prompt` | string | 아니오 | 실행 프롬프트 앞 160자 |
| `schedule` | string | 아니오 | cron 식 |
| `kind` | `"reminder" \| "task" \| "tool" \| "goal"` | 아니오 | 알림, 에이전트가 도는 작업, 도구를 바로 부르는 작업, 목표 한 차례(새로 알릴 것이 있을 때만 알린다) |
| `agent` | string | 아니오 | 작업을 실행하는 에이전트 id |
| `once` | boolean | 아니오 | 한 번만 도는 작업 |
| `enabled` | boolean | 아니오 | 켜짐 여부 |
| `next_run` | string | 예 | ISO 8601, 서버 시간대. 없으면 꺼졌거나 만료 |
| `run_until` | string | 예 | ISO 8601 만기 |

### OpenLoop

| 필드 | 타입 | 널 허용 | 설명 |
|---|---|---|---|
| `id` | string | 아니오 | 32자 hex |
| `description` | string | 아니오 | 약속이나 미완 작업 설명 |
| `due_ms` | integer | 예 | 기한(epoch ms). 사고가 "내일 10시" 같은 시각을 읽었을 때만 채워진다 |
| `created_at` | integer | 아니오 | epoch ms |
| `origin_session` | string | 예 | 감지된 세션 |
| `agent` | string | 아니오 | 약속을 감지한 세션의 에이전트 id. 에이전트 도입 전 약속은 `main` |

### Tool

| 필드 | 타입 | 널 허용 | 설명 |
|---|---|---|---|
| `name` | string | 아니오 | 도구 이름 |
| `description` | string | 아니오 | 첫 줄 160자 |
| `approval` | boolean | 아니오 | 실행 전 승인 필요 |

### Delegation

| 필드 | 타입 | 널 허용 | 설명 |
|---|---|---|---|
| `edge_id` | string | 아니오 | `<부른 세션 id>:<tool_call_id>`, Focus 는 `<세션 id>:focus-<영역>` |
| `kind` | `"ask" \| "subagent" \| "orchestrate" \| "focus" \| "background"` | 아니오 | `ask_agent`, `agent_<이름>`, `orchestrate` 도구, Focus sub-agent, 선응답으로 닫고 뒤에서 이어 도는 턴(받는 쪽 `background:<에이전트>`, `label` 은 요청 앞부분) |
| `source` | string | 아니오 | 맡긴 에이전트 id(부른 세션의 에이전트) |
| `target` | string | 아니오 | 받은 쪽. 최상위 에이전트 id, sub-agent 이름, `orchestrate:<패턴>`, `focus-<영역>` |
| `label` | string | 아니오 | 맡긴 일 앞 80자 |
| `started_ms` | integer | 아니오 | epoch ms |
| `ended_ms` | integer | 예 | 끝나지 않았으면 null |
| `ok` | boolean | 예 | 도구 결과가 오류가 아니었는지. 끝나지 않았으면 null |
| `session_id` | string | 아니오 | 부른 쪽 세션 id. 지도는 이 값으로 세션의 위임과 받는 쪽 세션(`peer-<부른 쪽>-<받는 쪽>`)의 위임을 잇는다. 이 필드가 생기기 전 간선은 빈 글 |
| `tokens` | integer | 예 | 받는 쪽이 이 일에 쓴 토큰(입력, 캐시 읽기, 출력 합). 받는 쪽 세션이 따로 있는 `ask` 만 세고, 그 세션의 턴이 끝날 때 더한다. 그 밖의 종류와 모르는 경우는 null |

### Job

| 필드 | 타입 | 널 허용 | 설명 |
|---|---|---|---|
| `job_id` | string | 아니오 | `schedule:<이름>`, `proactive:reflect`, `memory:consolidate`, `external:poll` |
| `kind` | `"schedule" \| "proactive" \| "consolidate" \| "external"` | 아니오 | 작업 종류 |
| `label` | string | 아니오 | 사람에게 보일 이름(스케줄은 설명, 외부 조회는 이번에 조회한 소스 이름) |
| `runs` | integer | 아니오 | 이 프로세스에서 시작한 횟수 |
| `running` | boolean | 아니오 | 지금 도는 중 |
| `last_started_ms`, `last_ended_ms` | integer | 예 | 마지막 시작과 끝(epoch ms) |
| `last_ok` | boolean | 예 | 마지막 실행이 성공했는지. 스케줄은 결과를 만들어 건넸는지 |
| `last_error` | string | 아니오 | 실패 이유 앞 200자 |
| `enabled`, `next_run`, `agent` | | | 스케줄만. [Schedule](#schedule) 의 같은 필드 |
