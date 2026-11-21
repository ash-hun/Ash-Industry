# Web HUD 수동 확인 시나리오

Docker 로 띄운 Web HUD 에서 proactive 성찰, 승인 기억, 절차 학습, Full-voice 알림 흐름을 눈으로 확인하는 절차다.
1~3 의 자동화 버전은 같은 디렉토리의 `hud_flow.py` 에 있다(스크립트 프로바이더, 실 LLM 없음). 눈으로 볼 때 1~3 은 10분쯤, 4 는 15분쯤 걸린다.

## 준비

`.env` 에서 아래 값을 확인한다. 메인 모델은 도구 호출이 되는 것이어야 한다(qwen3.5:0.8b 는 안 된다). 사고 모델은 `ASH_THOUGHT__MODEL=gemma4:e2b-it-qat` 로 분리한다(0.8b 급은 프레임 JSON 을 못 지킨다).

```bash
ASH_LLM__PROVIDER=ollama
ASH_LLM__BASE_URL=http://host.docker.internal:11434
ASH_LLM__MODEL=gemma4:e4b
ASH_THOUGHT__MODEL=gemma4:e2b-it-qat
ASH_PROACTIVE__DAEMON_ENABLED=true
ASH_PROACTIVE__DAEMON_INTERVAL_SEC=120     # 기본값과 같다
```

```bash
docker compose --profile web up -d        # .env 를 바꿨으면 restart 가 아니라 up -d
open http://localhost:7777
docker compose --profile web logs -f ash-backend | grep "\[Thought\]"   # 성찰 결과를 같이 본다
```

슬래시 명령을 입력할 때 자동완성 피커가 열리면 첫 Enter 는 항목 선택이다. Enter 를 한 번 더 누른다.

## 1. 성찰이 먼저 말을 거는가 (약 3분)

1. 입력: `내일 오전 10시에 팀에 배포 결과를 공유하기로 했어. 기억해줘`
2. 기대: 💭 줄(act · 100%) 뒤에 본 응답. 모델이 없는 도구(`calendar_tool` 등)를 부르면 CONVERSATION 에 `Error` 한 줄이 뜨고 텍스트로 회복한다. 모델의 환각이지 버그가 아니다.
3. 아무것도 하지 않고 기다린다. 주기 120초에 성찰 자체가 30~90초 걸리므로 3~4분 뒤 💭 줄이 한 번 더 뜨고(접혀 있다. 클릭하면 해석 전문), 바로 아래 🔔 proactive 발화가 에이전트의 한 턴처럼 보인다. 따로 묻지 않는다. 그 말에 대한 다음 말을 서버가 반응으로 읽는다.
4. 입력창에 `아니오` 를 보낸다. 백엔드 로그에 `[Proactive] reply to proactive: dismiss` 가 남고 세션 파일에 `proactive_ack` 항목이 생긴다. 다음 성찰은 💭 만 뜨고 🔔 는 뜨지 않는다. 같은 말의 되풀이 게이트와 쿨다운 300초가 막고, 무시로 임계치가 올라갔기 때문이다.
5. 오른쪽 AGENDA 의 OPEN LOOPS 에 "배포 결과 공유" 가 들어 있는지 본다.

## 2. 승인 기억 (약 1분)

1. 입력: `bash 로 echo hello 실행해줘`
2. 기대: 승인 모달에 `ALWAYS · echo hello`, `ALLOW`, `DENY` 세 버튼. **ALWAYS** 를 누른다.
3. 같은 입력을 한 번 더 보낸다. 모달 없이 바로 실행된다.
4. 입력: `bash 로 ls 실행해줘`. 다른 패턴이라 다시 묻는다. 이번엔 ALLOW.
5. 규칙 파일에는 `echo hello` 만 남아 있어야 한다.

```bash
docker compose --profile web exec ash-backend cat /root/.ash/approvals.yaml
```

## 3. 절차 학습 (약 3분)

1. 도구를 3번 이상 쓰게 하는 입력: `현재 디렉토리의 md 파일 목록을 보고, README.md 앞 20줄을 읽고, 마지막에 echo done 을 실행해서 요약해줘`
2. 응답이 끝나면 `/procedures learn`. 기대: `초안 저장: <name>`.
3. `/procedures learn` 을 한 번 더 보낸다. 기대: `새로 배울 구간이 없습니다`. 같은 구간은 두 번 배우지 않는다.
4. `/procedures approve <name>`. 오른쪽 SYSTEM 의 도구 목록에 `procedure_<name>` 이 추가된다.
5. `/<name>` 으로 호출하면 절차 본문이 프롬프트로 들어가 같은 작업을 다시 수행한다.

## 4. Full-voice: 중복 알림, 약속 되살리기 (약 15분)

준비: `.env` 에 `ASH_NOTIFY__DISCORD_WEBHOOK_URL` 이 있어야 디스코드 확인이 된다. 음성 모델(`./models`)이 없으면 브라우저 음성으로 읽는다. 메인 모델은 도구 호출이 되는 것이어야 한다. 디스코드 채널을 옆에 띄워 둔다.

### 4-1. 같은 세션을 연 두 화면이 같은 말을 읽어도 디스코드에는 한 번

1. 브라우저 탭 두 개로 `http://localhost:7777` 을 열고 둘 다 SESSIONS 에서 같은 세션(`default`)을 고른다.
2. 두 탭 모두 헤더에서 `FULL-VOICE` 를 누른다. 마이크 권한을 허용한다.
3. 한 탭의 구체를 누르고 말한다: "오늘 날짜 알려줘"
4. 기대: 두 탭이 같은 답을 각자 읽는다. 디스코드에는 `🔊 A.S.H.` 메시지가 **한 번만** 뜬다.
5. 10초 넘게 지난 뒤 같은 질문을 다시 한다. 디스코드에 한 번 더 뜬다(같은 글은 10초 안에서만 거른다).

### 4-2. 잘못 닫힌 약속을 되살린다

1. 말한다: "내일 오후 3시까지 팀장님께 보고서 보내야 해"
2. 기대: AGENDA 의 OPEN LOOPS 에 보고서 항목이 기한과 함께 들어온다(응답보다 늦게 올 수 있다).
3. 말한다: "보고서는 이미 보냈어"
4. 기대: 그 약속이 OPEN LOOPS 에서 빠지고 아래 `CLOSED 01` 줄이 생긴다. AGENDA 판단이 닫지 않았으면 ✓ 를 눌러 닫는다.
5. `CLOSED` 줄을 눌러 펼친다. 항목에 `완료 · HH:MM` 이 보인다.
6. ↺ 를 누른다. 기대: OPEN LOOPS 로 돌아오고 ACTIVITY 에 `↺ 되살림 · ...` 한 줄. 새로고침해도 열려 있다.
7. (선택) 기한이 6시간 넘게 지난 약속의 ↺ 는 ACTIVITY 에 빨간 `기한이 지나 되살리지 않음` 이 뜨고 CLOSED 에 남는다.

## 실패로 봐야 하는 것

| 증상 | 볼 곳 |
|---|---|
| 💭 가 2~3분 간격으로 안 뜬다 | 백엔드 로그. `frame invalid` 면 모델 출력 형식 문제, `call failed` 면 Ollama 연결 문제 |
| 💭 는 뜨는데 🔔 가 안 뜬다 | 백엔드 로그의 `proactive silent: <이유>`. `empty utterance` 면 모델이 utterance 를 안 채운 것, `cooldown` 이면 300초 대기 |
| 승인 모달에 ALWAYS 가 없다 | 백엔드가 옛 소스. `docker compose --profile web up -d` 로 재생성 |
| 응답이 1분 넘게 안 온다 | 성찰과 겹쳐 Ollama 가 직렬 처리 중. 기다리면 온다 |
| 디스코드에 🔊 가 화면 수만큼 뜬다 | 두 탭이 같은 세션인지 본다. 세션이 다르면 따로 보내는 것이 맞다 |
| Ollama 가 모든 요청에 500 | 호스트 Ollama 서버와 러너 버전 불일치. `brew services restart ollama` |

