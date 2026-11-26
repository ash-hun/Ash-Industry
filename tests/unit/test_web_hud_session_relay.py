"""web_hud: SessionRelay 가 결과물과 다른 세션의 말을 열린 HUD 전부에 보내고 같은 결과물은 한 번만 보내는지 검증한다."""

from ash_industry.agent_layer.agent_types import ArtifactsEvent, ProactiveMessageEvent, ToolExecutionEndEvent
from ash_industry.ui.web.session_relay import ARTIFACTS_EVENT, MESSAGE_EVENT, REPEAT_SEC, SessionRelay
from ash_industry.model_layer.model_types import Artifact

PAGE = ".render/a/a-1.png"


class _Session:
    def __init__(self):
        self.listeners = []

    def subscribe(self, fn):
        self.listeners.append(fn)
        return lambda: None

    async def emit(self, event):
        for fn in self.listeners:
            await fn(event)


def _relay():
    sent = []
    now = [0.0]

    async def broadcast(payload):
        sent.append(payload)

    return SessionRelay(broadcast, clock=lambda: now[0]), sent, now


def _doc() -> Artifact:
    return Artifact(kind="document", path=PAGE, store="docs", pages=[PAGE])


async def test_artifacts_from_any_session_are_broadcast_once_within_window():
    relay, sent, now = _relay()
    evi, main = _Session(), _Session()
    relay.watch("peer-main-evi", "evi", evi)
    relay.watch("default", "main", main)
    await evi.emit(ToolExecutionEndEvent(tool_call_id="r", tool_name="render_document", is_error=False,
                                         artifacts=[_doc()]))
    await main.emit(ToolExecutionEndEvent(tool_call_id="a", tool_name="ask_agent", is_error=False,
                                          artifacts=[_doc()]))
    await main.emit(ArtifactsEvent(session_id="default", tool_name="ask_agent", artifacts=[_doc()]))
    assert [(p["type"], p["session_id"], p["agent"]) for p in sent] == [(ARTIFACTS_EVENT, "peer-main-evi", "evi")]
    assert sent[0]["artifacts"][0]["pages"] == [PAGE]
    now[0] = REPEAT_SEC + 1
    await main.emit(ArtifactsEvent(session_id="default", tool_name="render_document", artifacts=[_doc()]))
    assert len(sent) == 2 and sent[1]["session_id"] == "default"


async def test_error_and_empty_tool_ends_are_not_broadcast():
    relay, sent, _ = _relay()
    session = _Session()
    relay.watch("default", "main", session)
    await session.emit(ToolExecutionEndEvent(tool_call_id="a", tool_name="x", is_error=True, artifacts=[_doc()]))
    await session.emit(ToolExecutionEndEvent(tool_call_id="b", tool_name="bash", is_error=False))
    assert sent == []


async def test_proactive_and_answer_are_broadcast_but_not_filler_or_peer():
    relay, sent, _ = _relay()
    main, peer = _Session(), _Session()
    relay.watch("default", "main", main)
    relay.watch("peer-main-evi", "evi", peer)
    await main.emit(ProactiveMessageEvent(session_id="default", text="발표 자료를 만들었어요", kind="answer"))
    await main.emit(ProactiveMessageEvent(session_id="default", text="잠시만요", kind="filler"))
    await main.emit(ProactiveMessageEvent(session_id="default", text="  ", kind="proactive"))
    await peer.emit(ProactiveMessageEvent(session_id="peer-main-evi", text="렌더했어요", kind="answer"))
    assert sent == [{
        "type": MESSAGE_EVENT, "session_id": "default", "agent": "main", "kind": "answer",
        "text": "발표 자료를 만들었어요",
    }]
