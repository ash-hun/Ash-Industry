"""send_now: TurnInbox 가 보낸 순서를 지키고 같은 id 와 빈 글을 한 번만 담으며, 꺼내면 비우는지 검증한다."""

from ash_industry.agent_layer.turn_inbox import QUEUE_TEXT_CHARS, QueuedMessage, TurnInbox, join_queued


def test_put_keeps_order_and_ignores_duplicates_and_blanks():
    inbox = TurnInbox()
    assert inbox.put(QueuedMessage("a", "자막은 빼줘")) is True
    assert inbox.put(QueuedMessage("a", "자막은 빼줘")) is False
    assert inbox.put(QueuedMessage("b", "   ")) is False
    assert inbox.put(QueuedMessage("c", " 길이는 1분 ")) is True
    expected = [{"id": "a", "text": "자막은 빼줘"}, {"id": "c", "text": "길이는 1분"}]
    assert [i.to_dict() for i in inbox.items()] == expected


def test_take_all_empties_and_long_text_is_clipped():
    inbox = TurnInbox()
    inbox.put(QueuedMessage("a", "가" * (QUEUE_TEXT_CHARS + 10)))
    taken = inbox.take_all()
    assert len(taken[0].text) == QUEUE_TEXT_CHARS
    assert inbox.take_all() == [] and len(inbox) == 0


def test_join_queued_uses_blank_line_between_messages():
    assert join_queued([QueuedMessage("a", "하나"), QueuedMessage("b", "둘")]) == "하나\n\n둘"
    assert join_queued([]) == ""
