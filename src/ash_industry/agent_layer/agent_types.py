"""[agent_layer] 에이전트 루프가 내보내는 이벤트와 실행 컨텍스트, 루프 설정 모델을 정의한다."""

import time
from typing import Any, Literal
from pydantic import BaseModel, Field

from ash_industry.model_layer.model_types import (
    Artifact,
    AssistantMessage,
    Message,
    ModelConfig,
    StreamOptions,
    Tool,
    Usage,
)

# ── Agent events (Pi: AgentEvent 패턴) ────────────────────────────────────────

class AgentStartEvent(BaseModel):
    type: Literal["agent_start"] = "agent_start"
    session_id: str
    prompt: str
    agent_name: str | None = None
    timestamp: int = Field(default_factory=lambda: int(time.time() * 1000))


class TurnStartEvent(BaseModel):
    type: Literal["turn_start"] = "turn_start"
    turn: int
    timestamp: int = Field(default_factory=lambda: int(time.time() * 1000))


class MessageUpdateEvent(BaseModel):
    type: Literal["message_update"] = "message_update"
    text_delta: str = ""
    thinking_delta: str = ""
    timestamp: int = Field(default_factory=lambda: int(time.time() * 1000))


class ToolExecutionStartEvent(BaseModel):
    type: Literal["tool_execution_start"] = "tool_execution_start"
    tool_call_id: str
    tool_name: str
    args: dict[str, Any]
    timestamp: int = Field(default_factory=lambda: int(time.time() * 1000))


class ToolExecutionEndEvent(BaseModel):
    type: Literal["tool_execution_end"] = "tool_execution_end"
    tool_call_id: str
    tool_name: str
    is_error: bool
    # 도구가 만든 결과물(영상, 음악). 화면이 플레이어 모달로 띄운다
    artifacts: list[Artifact] = Field(default_factory=list)
    timestamp: int = Field(default_factory=lambda: int(time.time() * 1000))


class AgentEndEvent(BaseModel):
    type: Literal["agent_end"] = "agent_end"
    session_id: str
    final_message: AssistantMessage | None = None
    turns: int = 0
    agent_name: str | None = None
    overflows: int = 0  # max_turns 를 다 쓰고도 도구를 부르던 횟수. 1 이면 이어가서 끝냈고 2 면 정리문이 답이다
    # 이 턴의 LLM 호출 전부를 더한 사용량(final_message.usage 는 마지막 호출뿐이다)
    usage: Usage = Field(default_factory=Usage)
    timestamp: int = Field(default_factory=lambda: int(time.time() * 1000))


class AgentErrorEvent(BaseModel):
    type: Literal["agent_error"] = "agent_error"
    message: str
    code: str | None = None
    timestamp: int = Field(default_factory=lambda: int(time.time() * 1000))


class InnerThoughtEvent(BaseModel):
    """inner thought(메타인지) 산출물을 UI/로그로 노출. 메인 응답과 분리된 사고 스트림."""

    type: Literal["inner_thought"] = "inner_thought"
    session_id: str
    interpretation: str = ""
    decision: str = "silent"
    confidence: float = 0.0
    frame: dict[str, Any] = Field(default_factory=dict)  # ThoughtFrame.model_dump()
    timestamp: int = Field(default_factory=lambda: int(time.time() * 1000))


class ThoughtRouteEvent(BaseModel):
    """router 가 이번 요청에 inner thought 를 돌릴지 정했다. think 면 사고가 응답과 함께 돈다."""

    type: Literal["thought_route"] = "thought_route"
    session_id: str
    think: bool
    p_think: float | None = None  # None 이면 router 가 답하지 못해 think 로 둔 것
    timestamp: int = Field(default_factory=lambda: int(time.time() * 1000))


class ThoughtEndEvent(BaseModel):
    """think 로 띄운 사고가 끝났다. 실패해도 보낸다(화면이 사고 중 표시를 풀 수 있게)."""

    type: Literal["thought_end"] = "thought_end"
    session_id: str
    ok: bool
    timestamp: int = Field(default_factory=lambda: int(time.time() * 1000))


class AgendaChangedEvent(BaseModel):
    """AGENDA 판단이 약속을 새로 열거나 닫았다. 판단은 응답과 함께 돌아 응답보다 늦게 끝날 수 있다."""

    type: Literal["agenda_changed"] = "agenda_changed"
    session_id: str
    timestamp: int = Field(default_factory=lambda: int(time.time() * 1000))


class ProactiveMessageEvent(BaseModel):
    """시스템 → 사용자 비요청 발화 (Tier 1 Push 채널).

    kind:
    - filler    : Dual-Channel: "오래 걸림"을 알리는 즉답 (voice는 즉시 TTS)
    - proactive : daemon이 먼저 거는 말
    - answer    : 뒤로 넘긴 턴이 끝난 뒤의 답. 대화 기록에도 남는다
    """

    type: Literal["proactive_message"] = "proactive_message"
    session_id: str
    text: str
    kind: Literal["filler", "proactive", "answer"] = "proactive"
    speak: bool = False  # voice 모드에서 즉시 TTS 대상인지
    message_id: str = ""  # 피드백(수락/무시)이 참조할 식별자
    timestamp: int = Field(default_factory=lambda: int(time.time() * 1000))


class FocusStateEvent(BaseModel):
    """Focus 작업의 현재 상태 전체. 화면은 받은 것으로 덮어쓴다(active=False 면 Focus 종료)."""

    type: Literal["focus_state"] = "focus_state"
    session_id: str
    state: dict[str, Any]


class FocusPanelEvent(BaseModel):
    """Focus 영역(reference, log, analysis) 하나의 마크다운 전체."""

    type: Literal["focus_panel"] = "focus_panel"
    session_id: str
    area: str
    markdown: str
    busy: bool = False  # sub-agent 가 이 영역을 갱신하는 중인지


class BackgroundTaskEvent(BaseModel):
    """오래 걸려 뒤로 넘긴 턴 하나의 시작과 끝. 화면은 작업마다 별 하나를 띄우고, 끝나면 지운다."""

    type: Literal["background_task"] = "background_task"
    session_id: str
    task_id: str
    label: str
    # updated: 그 작업에 보낸 지시의 대기 수가 바뀌었다
    state: Literal["started", "updated", "finished"]
    ok: bool = True
    error: str = ""
    pending: int = 0  # 그 작업이 아직 읽지 않은 지시 수
    applied: int = 0  # 그 작업이 읽어 맥락에 붙인 지시 수
    stopped: bool = False  # 사용자가 멈췄다
    timestamp: int = Field(default_factory=lambda: int(time.time() * 1000))


class QueueChangedEvent(BaseModel):
    """일하는 동안 보낸 말의 대기열 전체. 화면은 받은 것으로 덮어쓴다."""

    type: Literal["queue_changed"] = "queue_changed"
    session_id: str
    items: list[dict[str, str]]


class QueueDeliveredEvent(BaseModel):
    """대기 중이던 말을 모델에게 건넸다(같은 턴의 도구 결과 뒤, 또는 다음 턴). 화면은 대화에 사용자 말로 붙인다."""

    type: Literal["queue_delivered"] = "queue_delivered"
    session_id: str
    items: list[dict[str, str]]
    timestamp: int = Field(default_factory=lambda: int(time.time() * 1000))


AgentEvent = (
    AgentStartEvent
    | TurnStartEvent
    | MessageUpdateEvent
    | ToolExecutionStartEvent
    | ToolExecutionEndEvent
    | AgentEndEvent
    | AgentErrorEvent
    | InnerThoughtEvent
    | ThoughtRouteEvent
    | ThoughtEndEvent
    | AgendaChangedEvent
    | ProactiveMessageEvent
    | FocusStateEvent
    | FocusPanelEvent
    | BackgroundTaskEvent
    | QueueChangedEvent
    | QueueDeliveredEvent
)


# ── Agent context & config ────────────────────────────────────────────────────

class AgentContext(BaseModel):
    session_id: str
    messages: list[Message] = Field(default_factory=list)
    tools: list[Tool] = Field(default_factory=list)
    model: ModelConfig
    system_prompt: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentLoopConfig(BaseModel):
    max_turns: int = 20
    stream_options: StreamOptions = Field(default_factory=StreamOptions)
    tool_execution_mode: Literal["parallel", "sequential"] = "parallel"
    abort_on_error: bool = False
    # max_turns 를 다 쓰고도 도구를 부르던 중이면 정리하고 절반만큼 이어간다. 끄면 예전처럼 그 자리에서 끊는다
    overflow_resume: bool = True
