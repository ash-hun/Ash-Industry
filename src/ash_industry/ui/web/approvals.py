"""[ui] SessionApprovals: 세션 하나의 승인 요청을 붙어 있는 모든 연결에 보내고 먼저 온 답을 쓴다."""

import uuid
import asyncio
from collections.abc import Awaitable, Callable

from ash_industry.core.policy.sandbox import TIMEOUT

APPROVAL_TIMEOUT_SEC = 120.0

# 기다리는 요청 수가 바뀔 때 부른다. 다른 세션을 보고 있는 화면에 "승인 대기" 를 띄우는 데 쓴다
OnWaiting = Callable[[int], Awaitable[None]]


class Connection:
    """승인 요청을 받는 연결 하나의 부모. 기본 send 는 아무것도 보내지 않는다."""

    async def send(self, payload: dict[str, object]) -> None:
        return None


class SessionApprovals:
    """연결은 오가도 세션당 하나. 샌드박스 콜백은 이 객체의 request 로 고정된다."""

    def __init__(
        self,
        timeout_sec: float = APPROVAL_TIMEOUT_SEC,
        new_id: Callable[[], str] = lambda: str(uuid.uuid4()),
        on_waiting: OnWaiting | None = None,
    ) -> None:
        self._timeout_sec = timeout_sec
        self._new_id = new_id
        self._on_waiting = on_waiting
        self._connections: set[Connection] = set()
        # 화면이 한 번이라도 붙었던 세션. 사용자가 다른 에이전트로 옮겨 가도 돌아와 답할 수 있다
        self._seen_connection = False
        self._pending: dict[str, tuple[asyncio.Future[bool | str], dict[str, object]]] = {}

    async def attach(self, conn: Connection) -> None:
        """기다리는 요청이 있으면 새 연결에도 바로 보여준다."""
        self._connections.add(conn)
        self._seen_connection = True
        for _, payload in list(self._pending.values()):
            await conn.send(payload)

    def detach(self, conn: Connection) -> None:
        self._connections.discard(conn)

    @property
    def connection_count(self) -> int:
        return len(self._connections)

    @property
    def pending_ids(self) -> list[str]:
        return list(self._pending)

    async def request(self, command: str, reason: str, always_pattern: str = "") -> bool | str:
        # 화면이 붙은 적 없는 세션(스케줄, 헤드리스)은 답할 사람이 없다. 붙었던 세션은 잠시 떠났어도 기다린다
        if not self._connections and not self._seen_connection:
            return False
        approval_id = self._new_id()
        future: asyncio.Future[bool | str] = asyncio.get_running_loop().create_future()
        payload: dict[str, object] = {
            "type": "approval_request",
            "id": approval_id,
            "command": command[:500],
            "reason": reason,
            "always_pattern": always_pattern,
        }
        self._pending[approval_id] = (future, payload)
        resolved: dict[str, object] = {"type": "approval_resolved", "id": approval_id}
        try:
            await self._notify_waiting()
            await self._broadcast(payload)
            return await asyncio.wait_for(future, timeout=self._timeout_sec)
        except TimeoutError:
            resolved["timeout"] = True
            return TIMEOUT
        finally:
            self._pending.pop(approval_id, None)
            await self._broadcast(resolved)
            await self._notify_waiting()

    def resolve(self, approval_id: str, approved: bool, always: bool = False) -> bool:
        """먼저 온 답만 쓴다. always 는 approved 일 때만 의미가 있다. 늦은 답과 모르는 id 는 False."""
        entry = self._pending.get(approval_id)
        if entry is None or entry[0].done():
            return False
        entry[0].set_result("always" if approved and always else approved)
        return True

    async def _notify_waiting(self) -> None:
        if self._on_waiting is not None:
            await self._on_waiting(len(self._pending))

    async def _broadcast(self, payload: dict[str, object]) -> None:
        for conn in list(self._connections):
            await conn.send(payload)
