"""web_hud: TurnReplay 가 진행 중인 루트 턴만 모으고, 글자 조각을 합치고, 턴이 끝나면 비우는지 검증한다."""

from ash_industry.agent_layer.agent_types import AgentStartEvent, MessageUpdateEvent
from ash_industry.ui.web.turn_replay import TurnReplay, merge_delta


def _ev(kind, **fields):
    return {"type": kind, **fields}


def test_records_root_turn_and_merges_deltas():
    replay = TurnReplay()
    replay.record("s", _ev("agent_start"))
    replay.record("s", _ev("message_update", text_delta="안녕", thinking_delta=""))
    replay.record("s", _ev("message_update", text_delta="하세요", thinking_delta=""))
    replay.record("s", _ev("tool_execution_start", tool_call_id="t1"))
    replay.record("s", _ev("inner_thought", text="무시"))
    assert [e["type"] for e in replay.snapshot("s")] == ["agent_start", "message_update", "tool_execution_start"]
    assert replay.snapshot("s")[1]["text_delta"] == "안녕하세요"


def test_nested_agent_keeps_turn_until_root_end():
    replay = TurnReplay()
    replay.record("s", _ev("agent_start"))
    replay.record("s", _ev("agent_start", agent_name="sub"))
    replay.record("s", _ev("agent_end", agent_name="sub"))
    assert [e["type"] for e in replay.snapshot("s")] == ["agent_start", "agent_start", "agent_end"]
    replay.record("s", _ev("agent_end"))
    assert replay.snapshot("s") == []


def test_events_outside_turn_are_ignored_and_sessions_are_separate():
    replay = TurnReplay()
    replay.record("s", _ev("message_update", text_delta="x"))
    replay.record("s", _ev("agent_end"))
    replay.record("other", _ev("agent_start"))
    assert replay.snapshot("s") == []
    assert len(replay.snapshot("other")) == 1


def test_new_root_start_drops_stale_turn():
    replay = TurnReplay()
    replay.record("s", _ev("agent_start"))
    replay.record("s", _ev("tool_execution_start", tool_call_id="old"))
    replay.forget("s")
    replay.record("s", _ev("agent_start"))
    assert [e["type"] for e in replay.snapshot("s")] == ["agent_start"]


def test_cap_stops_recording():
    replay = TurnReplay(max_events=2)
    replay.record("s", _ev("agent_start"))
    for i in range(5):
        replay.record("s", _ev("tool_execution_start", tool_call_id=str(i)))
    assert len(replay.snapshot("s")) == 2


def test_snapshot_is_a_copy():
    replay = TurnReplay()
    replay.record("s", _ev("agent_start"))
    replay.snapshot("s")[0]["type"] = "changed"
    assert replay.snapshot("s")[0]["type"] == "agent_start"


def test_merge_delta_only_joins_message_updates():
    events = [_ev("tool_execution_start")]
    assert merge_delta(events, _ev("message_update", text_delta="a")) is False
    assert merge_delta([], _ev("message_update", text_delta="a")) is False


async def test_watch_records_session_events():
    listeners = []

    class _Session:
        def subscribe(self, fn):
            listeners.append(fn)
            return lambda: None

    replay = TurnReplay()
    replay.watch("s", "studio", _Session())
    await listeners[0](AgentStartEvent(session_id="s", prompt="그려줘"))
    await listeners[0](MessageUpdateEvent(text_delta="그림"))
    assert [e["type"] for e in replay.snapshot("s")] == ["agent_start", "message_update"]
