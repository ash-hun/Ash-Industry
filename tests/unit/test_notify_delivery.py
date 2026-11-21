"""notify: delivery 가 내용에서 결정적 키를 만들고, 같은 키는 한 번만 보내며, 실패를 backoff 로 다시 보내는지 검증."""

import pytest

from ash_industry.core.notify.delivery import Delivery, backoff_sec, delivery_key, is_retryable, is_success, time_bucket
from ash_industry.core.notify.sent_store import SentStore

PAYLOAD = {"type": "reminder", "id": "r1", "kind": "task", "agent": "main", "text": "공고 3건", "fired_at": "x"}


def test_delivery_key_is_deterministic_and_ignores_fields_outside_the_key():
    key = delivery_key("slack webhook", PAYLOAD, 7)

    assert key == delivery_key("slack webhook", {**PAYLOAD, "fired_at": "y", "delayed_sec": 3}, 7)
    assert len(key) == 24


@pytest.mark.parametrize(
    "other",
    [
        delivery_key("discord webhook", PAYLOAD, 7),
        delivery_key("slack webhook", PAYLOAD, 8),
        delivery_key("slack webhook", {**PAYLOAD, "text": "공고 4건"}, 7),
        delivery_key("slack webhook", PAYLOAD, 7, scope="https://push/one"),
    ],
    ids=["channel", "bucket", "text", "scope"],
)
def test_delivery_key_changes_with_channel_bucket_text_or_scope(other):
    assert other != delivery_key("slack webhook", PAYLOAD, 7)


def test_time_bucket_backoff_and_status_classes():
    assert time_bucket(0.0) == 0 and time_bucket(599.9) == 0 and time_bucket(600.0) == 1
    assert [backoff_sec(i) for i in range(4)] == [0.5, 1.0, 1.0, 1.0] and backoff_sec(0, ()) == 0.0
    assert is_success(200) and is_success(204) and not is_success(0) and not is_success(404)
    assert is_retryable(0) and is_retryable(500) and is_retryable(503)
    assert not is_retryable(400) and not is_retryable(404) and not is_retryable(429)


async def test_deliver_sends_once_per_key_and_records_only_after_success():
    store = SentStore(None)
    calls: list[int] = []

    async def send() -> int:
        calls.append(1)
        return 200

    delivery = Delivery(store, clock=lambda: 1000.0)

    first = await delivery.deliver("slack webhook", PAYLOAD, send)
    second = await delivery.deliver("slack webhook", PAYLOAD, send)
    other = await delivery.deliver("discord webhook", PAYLOAD, send)

    assert (first, second, other) == (200, None, 200)
    assert len(calls) == 2 and len(store) == 2


async def test_deliver_retries_with_backoff_then_gives_up_without_recording(capsys):
    slept: list[float] = []
    statuses = [503, 0, 500]

    async def sleep(sec: float) -> None:
        slept.append(sec)

    async def send() -> int:
        return statuses.pop(0) if statuses else 500

    store = SentStore(None)
    delivery = Delivery(store, clock=lambda: 1000.0, sleep=sleep)

    status = await delivery.deliver("slack webhook", PAYLOAD, send)
    again = await delivery.deliver("slack webhook", PAYLOAD, send)

    assert status == 500 and slept == [0.5, 1.0, 0.5, 1.0]
    assert again == 500 and len(store) == 0  # 못 보낸 키는 적히지 않아 다음 호출이 다시 보낸다
    assert "slack webhook returned 500 after 3 attempts, giving up" in capsys.readouterr().out


async def test_deliver_treats_an_exception_as_retryable_and_a_4xx_as_final():
    attempts: list[str] = []

    async def raising() -> int:
        attempts.append("raise")
        raise TimeoutError("slow")

    async def forbidden() -> int:
        attempts.append("403")
        return 403

    async def no_sleep(_sec: float) -> None:
        return None

    delivery = Delivery(SentStore(None), clock=lambda: 1000.0, sleep=no_sleep, retries=1)

    assert await delivery.deliver("slack webhook", PAYLOAD, raising) == 0
    assert await delivery.deliver("slack webhook", {**PAYLOAD, "id": "r2"}, forbidden) == 403
    assert attempts == ["raise", "raise", "403"]
