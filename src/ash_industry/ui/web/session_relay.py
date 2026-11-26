"""[ui] SessionRelay: 사용자가 다른 에이전트나 세션 화면에 있어도 놓치면 안 되는 이벤트를 열린 HUD 전부에 보낸다.

세션 이벤트는 그 세션을 연 화면에만 간다. 화면을 옮기면 그 사이 결과물(문서 렌더, 영상)과 다른 세션의 답이 안 보였다.
"""

import time
from typing import TYPE_CHECKING
from collections.abc import Awaitable, Callable

from ash_industry.agent_layer.agent_types import ArtifactsEvent, ProactiveMessageEvent, ToolExecutionEndEvent

if TYPE_CHECKING:
    from ash_industry.model_layer.model_types import Artifact
    from ash_industry.core.session import AgentSession

ARTIFACTS_EVENT = "artifacts_ready"
MESSAGE_EVENT = "session_message"
# 맡긴 쪽과 맡은 쪽이 같은 결과물을 차례로 낸다(받는 쪽 도구 끝, 부른 쪽 ask_agent 끝). 이 안이면 한 번만 보낸다
REPEAT_SEC = 20.0
# 에이전트끼리의 대화 세션. 사용자가 보는 세션이 아니라 그 말은 알리지 않는다(결과물은 알린다)
PEER_PREFIX = "peer-"
# 다른 화면에 알릴 말. filler 는 그 세션에서 막 보낸 말의 대기 안내라 그 화면에만 의미가 있다
NOTIFY_KINDS = frozenset({"proactive", "answer"})

Broadcast = Callable[[dict[str, object]], Awaitable[None]]


def artifact_key(artifact: "Artifact") -> str:
    return f"{artifact.store}:{artifact.path}"


class SessionRelay:
    """세션마다 이벤트를 구독해 결과물과 먼저 건넨 말, 뒤에서 끝난 답을 방송한다.

    같은 결과물은 REPEAT_SEC 안에 한 번만 보낸다. 화면은 지금 보는 세션의 말은 이미 받았으니 버린다.
    프로세스 메모리라 재시작하면 잊는다.
    """

    def __init__(self, broadcast: Broadcast, clock: Callable[[], float] = time.monotonic) -> None:
        self._broadcast = broadcast
        self._clock = clock
        self._sent: dict[str, float] = {}

    def fresh(self, artifacts: "list[Artifact]") -> "list[Artifact]":
        """아직 보내지 않았거나 보낸 지 오래된 결과물만. 고른 것은 보낸 것으로 적는다."""
        now = self._clock()
        self._sent = {k: at for k, at in self._sent.items() if now - at < REPEAT_SEC}
        picked = [a for a in artifacts if artifact_key(a) not in self._sent]
        for artifact in picked:
            self._sent[artifact_key(artifact)] = now
        return picked

    def watch(self, session_id: str, agent_id: str, session: "AgentSession") -> None:
        """세션 이벤트를 구독한다. SessionRegistry 가 세션을 처음 열 때 한 번 부른다."""

        async def on_event(event: object) -> None:
            if isinstance(event, ProactiveMessageEvent):
                if event.kind in NOTIFY_KINDS and event.text.strip() and not session_id.startswith(PEER_PREFIX):
                    await self._broadcast({
                        "type": MESSAGE_EVENT, "session_id": session_id, "agent": agent_id,
                        "kind": event.kind, "text": event.text,
                    })
                return
            done = isinstance(event, ToolExecutionEndEvent) and not event.is_error
            if not (done or isinstance(event, ArtifactsEvent)):
                return
            picked = self.fresh(getattr(event, "artifacts", []))
            if picked:
                await self._broadcast({
                    "type": ARTIFACTS_EVENT, "session_id": session_id, "agent": agent_id,
                    "artifacts": [a.model_dump() for a in picked],
                })

        session.subscribe(on_event)
