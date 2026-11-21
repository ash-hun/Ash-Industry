"""[ui] TurnReplay: 세션마다 진행 중인 루트 턴의 이벤트를 모아 두었다가 다시 붙은 화면에 돌려준다."""

from typing import TYPE_CHECKING

from ash_industry.ui.web.adapter import event_payload

if TYPE_CHECKING:
    from ash_industry.agent_layer.agent_types import AgentEvent
    from ash_industry.core.session import AgentSession

# 화면이 턴을 그리는 데 쓰는 이벤트만 모은다. 사고, AGENDA, Focus 는 따로 다시 받는다
REPLAYED = frozenset({
    "agent_start", "message_update", "tool_execution_start", "tool_execution_end", "agent_end", "agent_error",
    "queue_delivered",
})
MAX_EVENTS = 1000
DELTA_FIELDS = ("text_delta", "thinking_delta")


def merge_delta(events: list[dict[str, object]], payload: dict[str, object]) -> bool:
    """연속된 message_update 를 앞 것에 이어 붙인다. 붙였으면 True. 글자 조각마다 한 건씩 쌓이지 않게 한다."""
    if payload["type"] != "message_update" or not events or events[-1]["type"] != "message_update":
        return False
    last = events[-1]
    for field in DELTA_FIELDS:
        last[field] = f"{last.get(field) or ''}{payload.get(field) or ''}"
    return True


class TurnReplay:
    """세션 id 별로 루트 agent_start 부터 그 짝 agent_end 까지를 들고 있다. 턴이 끝나면 비운다.

    턴이 끝나야 답이 저장소에 남으므로, 그 사이에 다시 붙은 화면은 이력 대신 이것으로 진행 상황을 되살린다.
    """

    def __init__(self, max_events: int = MAX_EVENTS) -> None:
        self._max_events = max_events
        self._events: dict[str, list[dict[str, object]]] = {}
        self._depth: dict[str, int] = {}

    def record(self, session_id: str, payload: dict[str, object]) -> None:
        kind = payload.get("type")
        if kind not in REPLAYED:
            return
        depth = self._depth.get(session_id, 0)
        if kind == "agent_start":
            if depth == 0:
                # 끝 이벤트 없이 죽은 앞 턴이 남아 있어도 새 턴에서 지운다
                self._events[session_id] = []
            self._depth[session_id] = depth + 1
        elif depth == 0:
            return
        events = self._events[session_id]
        if kind == "agent_end":
            self._depth[session_id] = depth - 1
            if depth == 1:
                self.forget(session_id)
                return
        if merge_delta(events, payload):
            return
        # ponytail: 상한을 넘은 뒤 이벤트는 버려 재생이 중간에서 멈춘다, 한 턴 도구가 수백 개면 옛 흔적을 접는다
        if len(events) < self._max_events:
            events.append(dict(payload))

    def snapshot(self, session_id: str) -> list[dict[str, object]]:
        """진행 중인 턴의 이벤트 사본. 턴이 없으면 빈 목록."""
        return [dict(e) for e in self._events.get(session_id, [])]

    def forget(self, session_id: str) -> None:
        self._events.pop(session_id, None)
        self._depth.pop(session_id, None)

    def watch(self, session_id: str, agent_id: str, session: "AgentSession") -> None:
        """세션 이벤트를 구독한다. SessionRegistry 가 세션을 처음 열 때 한 번 부른다."""

        async def on_event(event: "AgentEvent") -> None:
            self.record(session_id, event_payload(event))

        session.subscribe(on_event)
