"""[core] 열린 화면이 없을 때 쌓아 두는 스케줄 알림 보류 큐의 기본 클래스(메모리 저장 동작)."""

from typing import Any
from collections import OrderedDict

Notice = dict[str, Any]
# 보류하는 알림 수. 넘치면 오래된 것부터 버린다
PENDING_NOTICE_MAX = 20


def notice_key(payload: Notice) -> str:
    """같은 알림을 두 번 넣어도 하나이게 하는 자연 키. 스케줄러가 붙인 id, 없으면 작업 이름과 발화 시각."""
    return str(payload.get("id") or f"{payload.get('name', '')}@{payload.get('fired_at', '')}")


class PendingNoticeStore:
    """그대로 쓰면 프로세스 메모리 큐라 재시작하면 빈다. Postgres 는 상속해서 저장 매체에 맞게 재정의한다."""

    def __init__(self, limit: int = PENDING_NOTICE_MAX) -> None:
        self._limit = limit
        self._items: OrderedDict[str, Notice] = OrderedDict()

    async def push(self, payload: Notice) -> None:
        """알림을 보류한다. 같은 키는 내용만 덮어 하나로 남는다."""
        self._items[notice_key(payload)] = dict(payload)
        while len(self._items) > self._limit:
            self._items.popitem(last=False)

    async def drain(self) -> list[Notice]:
        """쌓인 알림을 오래된 순으로 꺼내고 비운다. 두 번째 호출은 빈 목록이다."""
        items = list(self._items.values())
        self._items.clear()
        return items
