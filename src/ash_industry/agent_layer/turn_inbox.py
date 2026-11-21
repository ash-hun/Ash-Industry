"""[agent_layer] TurnInbox: 에이전트가 일하는 동안 사용자가 보낸 말을 순서대로 담아 두는 세션별 대기열."""

from dataclasses import dataclass

QUEUE_TEXT_CHARS = 4000


@dataclass(frozen=True)
class QueuedMessage:
    """대기 중인 말 하나. id 는 화면이 만들어 보내고, 같은 id 는 한 번만 담긴다."""

    id: str
    text: str

    def to_dict(self) -> dict[str, str]:
        return {"id": self.id, "text": self.text}


def join_queued(items: list[QueuedMessage]) -> str:
    """여러 말을 한 번에 건넬 때의 글. 보낸 순서대로 빈 줄로 잇는다. 순수 함수."""
    return "\n\n".join(item.text for item in items)


class TurnInbox:
    """넣은 순서를 지킨다. 꺼내면 비운다. 같은 상태에서 같은 호출은 같은 결과다."""

    def __init__(self) -> None:
        self._items: list[QueuedMessage] = []

    def put(self, item: QueuedMessage) -> bool:
        """담았으면 True. 같은 id 가 이미 있거나 글이 비었으면 False 이고 아무것도 바꾸지 않는다."""
        text = item.text.strip()[:QUEUE_TEXT_CHARS]
        if not text or any(existing.id == item.id for existing in self._items):
            return False
        self._items.append(QueuedMessage(item.id, text))
        return True

    def take_all(self) -> list[QueuedMessage]:
        """담긴 말을 전부 꺼내고 비운다. 비었으면 빈 목록."""
        items, self._items = self._items, []
        return items

    def items(self) -> list[QueuedMessage]:
        return list(self._items)

    def __len__(self) -> int:
        return len(self._items)
