"""workflow 의 tracker: 위임 도구 호출과 Focus 바쁨 신호를 간선으로 열고 닫는다."""

from ash_industry.agent_layer.agent_types import (
    AgentEndEvent,
    BackgroundTaskEvent,
    FocusPanelEvent,
    ToolExecutionEndEvent,
    ToolExecutionStartEvent,
)
from ash_industry.core.workflow.workflow_tracker import MAX_EDGES, WorkflowTracker, delegation_of, tokens_of
from ash_industry.core.workflow.workflow_types import DelegationEdge
from ash_industry.model_layer.model_types import Usage


def _start(call_id, tool, args, ts=100):
    return ToolExecutionStartEvent(tool_call_id=call_id, tool_name=tool, args=args, timestamp=ts)


def test_delegation_of_maps_delegation_tools_and_ignores_others():
    assert delegation_of("ask_agent", {"agent": "scribe", "message": "m"}) == ("ask", "scribe", "m")
    assert delegation_of("agent_researcher", {"task": "t"}) == ("subagent", "researcher", "t")
    orchestrate = delegation_of("orchestrate", {"pattern": "market", "task": "t"})
    assert orchestrate == ("orchestrate", "orchestrate:market", "t")
    assert delegation_of("agent_", {}) is None
    assert delegation_of("bash", {"command": "ls"}) is None


def test_tool_start_and_end_open_then_close_one_edge_idempotently():
    tracker = WorkflowTracker(clock=lambda: 0)
    start = _start("c1", "ask_agent", {"agent": "scribe", "message": "뉴스"})
    end = ToolExecutionEndEvent(tool_call_id="c1", tool_name="ask_agent", is_error=True, timestamp=250)

    opened = tracker.observe("s", "main", start)
    assert tracker.observe("s", "main", start) is None
    closed = tracker.observe("s", "main", end)
    assert tracker.observe("s", "main", end) is None

    assert opened is not None and (opened.source, opened.target, opened.started_ms) == ("main", "scribe", 100)
    assert opened.session_id == "s" and opened.tokens is None
    assert closed is not None and (closed.ended_ms, closed.ok) == (250, False)
    assert tracker.edges() == [closed]


def test_peer_turn_usage_lands_on_the_open_ask_edge_only():
    tracker = WorkflowTracker(clock=lambda: 0)
    tracker.observe("default", "main", _start("c1", "ask_agent", {"agent": "scribe", "message": "뉴스"}))
    usage = Usage(input=40, output=10, cache_read=20)

    stranger = tracker.observe("other", "scribe", AgentEndEvent(session_id="other", usage=usage))
    first = tracker.observe("peer-main-scribe", "scribe", AgentEndEvent(session_id="peer-main-scribe", usage=usage))
    second = tracker.observe("peer-main-scribe", "scribe", AgentEndEvent(session_id="peer-main-scribe", usage=usage))
    tracker.observe("default", "main", ToolExecutionEndEvent(tool_call_id="c1", tool_name="ask_agent", is_error=False))
    late = tracker.observe("peer-main-scribe", "scribe", AgentEndEvent(session_id="peer-main-scribe", usage=usage))

    assert stranger is None and late is None
    assert first is not None and first.tokens == 70 and second is not None and second.tokens == 140
    assert tracker.edges()[0].tokens == 140 and tokens_of(Usage()) == 0


def test_focus_busy_reopens_area_edge_at_the_end():
    clock = iter(range(10, 100, 10))
    tracker = WorkflowTracker(clock=lambda: next(clock))
    busy = FocusPanelEvent(session_id="s", area="analysis", markdown="", busy=True)
    idle = FocusPanelEvent(session_id="s", area="analysis", markdown="", busy=False)

    assert tracker.observe("s", "main", idle) is None
    tracker.observe("s", "main", busy)
    tracker.observe("s", "main", idle)
    tracker.observe("s", "main", _start("c1", "agent_x", {"task": "t"}))
    reopened = tracker.observe("s", "main", busy)

    assert [e.target for e in tracker.edges()] == ["x", "focus-analysis"]
    assert reopened is not None and reopened.ended_ms is None


def test_background_turn_opens_and_closes_one_edge_per_agent():
    tracker = WorkflowTracker(lambda: 0)
    start = BackgroundTaskEvent(session_id="s", task_id="t1", label="QKV 영상", state="started", timestamp=10)
    opened = tracker.observe("s", "studio", start)
    assert opened is not None
    assert (opened.kind, opened.source, opened.target) == ("background", "studio", "background:studio")
    assert opened.label == "QKV 영상"
    assert tracker.observe("s", "studio", start) is None
    update = BackgroundTaskEvent(session_id="s", task_id="t1", label="QKV 영상", state="updated", pending=1)
    assert tracker.observe("s", "studio", update) is None
    done = BackgroundTaskEvent(session_id="s", task_id="t1", label="QKV 영상", state="finished", ok=False, timestamp=20)
    closed = tracker.observe("s", "studio", done)
    assert closed is not None and (closed.ended_ms, closed.ok) == (20, False)
    assert tracker.observe("s", "studio", done) is None


def test_edges_keep_only_the_newest_max_edges():
    tracker = WorkflowTracker(clock=lambda: 0)
    for i in range(MAX_EDGES + 5):
        tracker.observe("s", "main", _start(f"c{i}", "agent_x", {"task": str(i)}))

    edges = tracker.edges()
    assert len(edges) == MAX_EDGES and edges[0].label == "5"


def test_load_restores_edges_closes_unfinished_and_is_idempotent():
    tracker = WorkflowTracker(clock=lambda: 999)
    done = DelegationEdge("s:c1", "ask", "main", "scribe", "뉴스", 100, 200, True)
    open_edge = DelegationEdge("s:c2", "subagent", "main", "x", "t", 300)

    tracker.load([done, open_edge])
    tracker.load([done, open_edge])

    edges = tracker.edges()
    assert [e.edge_id for e in edges] == ["s:c1", "s:c2"] and edges[0] == done
    assert (edges[1].ended_ms, edges[1].ok) == (999, None)
    assert tracker.observe("s", "main", _start("c2", "agent_x", {"task": "t"}, ts=400)) is not None


def test_load_keeps_live_edge_over_stored_one():
    tracker = WorkflowTracker(clock=lambda: 0)
    live = tracker.observe("s", "main", _start("c1", "ask_agent", {"agent": "scribe", "message": "m"}))

    tracker.load([DelegationEdge("s:c1", "ask", "main", "scribe", "옛 것", 1, 2, False)])

    assert tracker.edges() == [live]
