"""[core] 세션 이벤트(위임 도구 호출, Focus sub-agent 바쁨, 뒤로 넘긴 턴)에서 에이전트 사이 위임 간선을 모은다."""

from typing import Any
from dataclasses import replace
from collections import OrderedDict
from collections.abc import Callable

from ash_industry.core.workflow.workflow_types import DelegationEdge, DelegationKind
from ash_industry.agent_layer.session.session_protocol import PEER_SESSION_PREFIX

# 위임 도구 이름. core/multi_agent 의 agent_<이름> 도구와 orchestrate, app 의 ask_agent
ASK_TOOL = "ask_agent"
ORCHESTRATE_TOOL = "orchestrate"
SUBAGENT_PREFIX = "agent_"
FOCUS_PREFIX = "focus-"
# 선응답으로 닫고 뒤에서 이어 도는 턴의 받는 쪽. 에이전트마다 따로 두어 그래프에서 그 에이전트에 붙는다
BACKGROUND_PREFIX = "background:"
LABEL_CHARS = 80
# 메모리에 두는 최근 위임 수. 저장소가 있으면 기동 때 이만큼 읽어 온다
MAX_EDGES = 200


def delegation_of(tool_name: str, args: dict[str, Any]) -> tuple[DelegationKind, str, str] | None:
    """도구 호출이 위임이면 (종류, 받는 쪽, 맡긴 일). 위임이 아니면 None. 순수 함수."""
    if tool_name == ASK_TOOL:
        return "ask", str(args.get("agent", "")), str(args.get("message", ""))
    if tool_name == ORCHESTRATE_TOOL:
        return "orchestrate", f"{ORCHESTRATE_TOOL}:{args.get('pattern', '')}", str(args.get("task", ""))
    if tool_name.startswith(SUBAGENT_PREFIX) and len(tool_name) > len(SUBAGENT_PREFIX):
        return "subagent", tool_name[len(SUBAGENT_PREFIX):], str(args.get("task", ""))
    return None


def peer_session_of(edge: DelegationEdge) -> str:
    """ask 위임의 받는 쪽 세션 id. app 의 peer_session_id 와 같은 꼴이다."""
    return f"{PEER_SESSION_PREFIX}-{edge.source}-{edge.target}"


def tokens_of(usage: object) -> int:
    """턴 사용량을 토큰 하나로. 입력, 캐시 읽기, 출력의 합이라 모델이 실제로 읽고 쓴 양이다."""
    return int(getattr(usage, "input", 0) or 0) + int(getattr(usage, "cache_read", 0) or 0) + int(
        getattr(usage, "output", 0) or 0
    )


def _clip(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= LABEL_CHARS else text[: LABEL_CHARS - 1] + "…"


class WorkflowTracker:
    """간선 id 순서를 지키는 최근 위임 MAX_EDGES 개. 같은 이벤트를 두 번 받아도 간선은 하나다."""

    def __init__(self, clock: Callable[[], int]) -> None:
        self._clock = clock
        self._edges: OrderedDict[str, DelegationEdge] = OrderedDict()

    def edges(self) -> list[DelegationEdge]:
        return list(self._edges.values())

    def load(self, edges: list[DelegationEdge]) -> None:
        """저장소에서 읽은 간선을 오래된 순으로 채운다. 이미 있는 id 는 건드리지 않아 두 번 불러도 같다.
        끝나지 않은 간선은 이 프로세스가 끝을 볼 수 없어 지금 닫는다(결과는 모름)."""
        now = self._clock()
        for edge in edges:
            if edge.edge_id in self._edges:
                continue
            self._edges[edge.edge_id] = edge if edge.ended_ms is not None else replace(edge, ended_ms=now)
        while len(self._edges) > MAX_EDGES:
            self._edges.popitem(last=False)

    def observe(self, session_id: str, agent_id: str, event: object) -> DelegationEdge | None:
        """세션 이벤트 하나를 반영하고 바뀐 간선을 돌려준다. 바뀐 게 없으면 None."""
        kind = getattr(event, "type", "")
        if kind == "tool_execution_start":
            found = delegation_of(str(getattr(event, "tool_name", "")), dict(getattr(event, "args", {}) or {}))
            if found is None:
                return None
            edge_kind, target, label = found
            edge_id = f"{session_id}:{getattr(event, 'tool_call_id', '')}"
            return self._open(edge_id, edge_kind, agent_id, target, label, self._time_of(event), session_id)
        if kind == "agent_end":
            return self._spend(session_id, agent_id, tokens_of(getattr(event, "usage", None)))
        if kind == "tool_execution_end":
            edge_id = f"{session_id}:{getattr(event, 'tool_call_id', '')}"
            return self._close(edge_id, not bool(getattr(event, "is_error", False)), self._time_of(event))
        if kind == "background_task":
            edge_id = f"{session_id}:{BACKGROUND_PREFIX}{getattr(event, 'task_id', '')}"
            if getattr(event, "state", "") == "started":
                return self._open(
                    edge_id, "background", agent_id, f"{BACKGROUND_PREFIX}{agent_id}",
                    str(getattr(event, "label", "")), self._time_of(event), session_id,
                )
            if getattr(event, "state", "") == "finished":
                return self._close(edge_id, bool(getattr(event, "ok", True)), self._time_of(event))
            return None
        if kind == "focus_panel":
            area = str(getattr(event, "area", ""))
            edge_id = f"{session_id}:{FOCUS_PREFIX}{area}"
            if getattr(event, "busy", False):
                return self._open(
                    edge_id, "focus", agent_id, f"{FOCUS_PREFIX}{area}", area, self._clock(), session_id
                )
            return self._close(edge_id, True, self._clock())
        return None

    def _spend(self, session_id: str, agent_id: str, tokens: int) -> DelegationEdge | None:
        """받는 쪽 세션의 턴이 끝났다. 그 세션으로 열려 있는 ask 위임에 토큰을 더한다. 그런 위임이 없으면 None.

        받는 쪽의 agent_end 는 부른 쪽의 tool_execution_end 보다 먼저 오므로 그때 간선은 아직 열려 있다.
        """
        if tokens <= 0:
            return None
        open_asks = [
            e for e in self._edges.values()
            if e.ended_ms is None and e.kind == "ask" and e.target == agent_id and peer_session_of(e) == session_id
        ]
        if not open_asks:
            return None
        current = open_asks[-1]
        edge = replace(current, tokens=(current.tokens or 0) + tokens)
        self._edges[edge.edge_id] = edge
        return edge

    def _time_of(self, event: object) -> int:
        stamp = getattr(event, "timestamp", None)
        return int(stamp) if isinstance(stamp, int) else self._clock()

    def _open(
        self, edge_id: str, kind: DelegationKind, source: str, target: str, label: str, now: int, session_id: str
    ) -> DelegationEdge | None:
        current = self._edges.get(edge_id)
        if current is not None and current.ended_ms is None:
            return None
        # Focus 영역은 같은 id 로 다시 바빠진다. 끝난 간선을 지우고 맨 뒤에 새로 연다
        self._edges.pop(edge_id, None)
        edge = DelegationEdge(edge_id, kind, source, target, _clip(label), now, session_id=session_id)
        self._edges[edge_id] = edge
        while len(self._edges) > MAX_EDGES:
            self._edges.popitem(last=False)
        return edge

    def _close(self, edge_id: str, ok: bool, now: int) -> DelegationEdge | None:
        current = self._edges.get(edge_id)
        if current is None or current.ended_ms is not None:
            return None
        edge = replace(current, ended_ms=now, ok=ok)
        self._edges[edge_id] = edge
        return edge
