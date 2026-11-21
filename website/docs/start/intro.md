---
sidebar_position: 1
slug: /intro
title: Ash Industry 소개
---

# Ash Industry 소개

Ash Industry 는 여러 AI 에이전트를 한 곳에서 띄우고 운영하는 플랫폼이다. 기본 에이전트 main 과 정의 파일로 늘리는 팀 에이전트가 같은 Web HUD, 기억, 스케줄러, MCP 도구를 함께 쓴다. 에이전트는 묻는 말에 답하는 데서 그치지 않고, 대화 뒤에서 한 번 더 생각하고 필요하면 먼저 말을 건다. 이 페이지는 Ash Industry 가 어떤 문제에서 출발했고 누구에게 맞는지, 어떤 화면으로 쓰는지를 소개한다.

소스는 공개하지만 OSI 오픈소스는 아니다. PolyForm Noncommercial 1.0.0 에 기계학습 학습 데이터 사용 금지 조항을 더한 라이선스이고, 전문은 저장소의 `LICENSE` 에 있다.

![Web HUD 화면. Inner Thought, 마크다운 응답, Proactive Dialogue, 승인 기억이 차례로 보인다](/img/hud-motion.gif)

## 서비스 개요

기존의 Chatbot Assistant 는 사용자가 먼저 말을 걸어야만 움직이고, 대화가 끝나면 다음 요청이 올 때까지 아무것도 하지 않는다. Ash Industry 의 에이전트는 이 지점에서 출발했다. 요청마다 메인 응답과 별도로 한 번 더 생각하고([Inner Thought](../concepts/conversation/inner-thought.md)), 그 판단으로 다음 네 가지를 정한다.

- 지금 바로 답할지, "잠깐만요, 확인할게요" 를 먼저 말하고 뒤에서 처리할지
- 대화에서 흘린 약속과 끝내지 못한 일을 기억해 둘지
- 요청이 없는 시간에 스스로 성찰해서 먼저 말을 걸지, 침묵할지
- 먼저 건넨 말이 도움이 됐는지 배우고 다음 발화 기준을 조정할지

에이전트는 쓸수록 사용자에게 맞춰진다. 한 번 허용한 명령 패턴은 다시 묻지 않고(승인 기억), 같은 종류로 세 번 성공한 작업은 다시 쓸 수 있는 절차로 남기며(절차 학습), 대화에서 사용자 성향을 뽑아 사용자 모델과 저널로 쌓는다.

## 이런 분께 추천한다

- 로컬 모델(Ollama, vLLM)과 클라우드 모델(Anthropic, OpenAI, Gemini)을 바꿔 가며 쓰고 싶은 개인
- 파일, 셸, 웹 검색을 도구로 쓰는 에이전트가 필요하지만, 위험한 명령은 사람이 승인하길 바라는 개발자
- DOCX, XLSX, HWPX 행정문서를 서식 그대로 고치거나 자주 쓰는 양식을 값만 말해 채우고 싶은 사람([Document Tools](../concepts/conversation/documents.md))
- 스케줄 알림, 약속 추적, 맡겨 두면 알아서 챙기는 목표, 먼저 말을 거는 비서가 필요한 사람
- 역할이 다른 에이전트 여럿을 정의 파일과 확장 패키지로 늘려 한 화면에서 운영하려는 팀

## 인터페이스

에이전트는 Web HUD 로 쓴다. 브라우저 탭으로 열어도 되고, 데스크톱 앱 창으로 열어도 된다.

| 화면 | 실행 | 특징 |
|---|---|---|
| Web HUD | `ash-industry` 또는 `docker compose --profile web up` | http://localhost:7777. 리액터 구체를 가운데 두고 AGENDA, ACTIVITY, SESSIONS, CONVERSATION 카드를 둘렀다. SYSTEM 과 설정은 SET 화면에 있다. 구체를 누르면 말로 대화를 시작하고, 답을 읽은 뒤 다시 듣는다. `/focus` 로 Focus 레이아웃 |
| 데스크톱 앱 | `cd desktop && npm install && npm start` | HUD 를 창 하나로 연다. 트레이에 남아 OS 알림을 띄우고, 전역 단축키(macOS `Command+Control+Shift+Enter`, 그 밖 OS `Control+Alt+Shift+Enter`)로 창을 불러 바로 듣는다. 백엔드가 없으면 `web` 프로파일을 띄운다 |

두 화면은 같은 백엔드에 붙어 같은 세션 저장소를 읽는다. 화면을 하나도 열지 않아도 스케줄 결과와 먼저 건네는 말을 Slack, Discord, 모바일 앱 Web Push 로 받을 수 있다.

## 어디서부터 읽을까

| 하려는 일 | 읽을 문서 |
|---|---|
| 에이전트를 더 두기 | [팀 에이전트 추가하기](../agents/new-agent.md) |
| 바로 설치해서 대화해 보기 | [Quick Start](./install.md) 다음 [Conversation](../concepts/conversation/index.md) |
| 어떻게 동작하는지 알아보기 | [Notice](../concepts/notice.md) |
| 설정 키나 명령 찾기 | [환경설정](/reference) |
| 낯선 말 찾아보기 | [전체 용어집](../reference/glossary.md) |
| 화면을 말로만 쓰거나 작업 하나에 집중하기 | [Mode](../concepts/mode/index.md) |
