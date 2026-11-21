"""notify: slack 이 알림 payload 를 슬랙 본문으로 바꾸고, 같은 알림은 한 번만, 5xx 는 다시 보내는지 검증."""

import pytest

from ash_industry.core.notify.slack import format_slack, slack_notifier
from ash_industry.core.notify.sent_store import SentStore
from ash_industry.core.notify.delivery import Delivery


async def _no_sleep(_sec: float) -> None:
    return None


def _delivery() -> Delivery:
    return Delivery(SentStore(None), clock=lambda: 1000.0, sleep=_no_sleep)


@pytest.mark.parametrize(
    ("payload", "text"),
    [
        ({"type": "reminder", "name": "daily", "text": "날씨 맑음"}, "*⏰ daily*\n날씨 맑음"),
        (
            {"type": "proactive_message", "text": "배포 결과 공유 잊지 마세요"},
            "*💭 Ash*\n배포 결과 공유 잊지 마세요",
        ),
        ({"type": "weird"}, "*weird*\n{'type': 'weird'}"),
    ],
)
def test_format_slack_formats_by_payload_type(payload, text):
    assert format_slack(payload) == {"text": text}


def test_format_slack_marks_failed_reminder():
    failed = format_slack({"type": "reminder", "name": "x", "text": "실패", "error": True})

    assert failed["text"].startswith("*⏰ x (실패)*")


def test_format_slack_truncates_long_text():
    assert len(format_slack({"type": "proactive_message", "text": "x" * 5000})["text"]) <= 2800


async def test_slack_notifier_posts_formatted_body_once_and_retries_5xx(capsys):
    sent: list[tuple[str, dict]] = []

    async def fake_post(url, body):
        sent.append((url, body))
        return 500 if "fail" in body["text"] else 200

    notify = slack_notifier("https://hooks.example/abc", post=fake_post, delivery=_delivery())

    await notify({"type": "reminder", "id": "r1", "name": "n", "text": "ok"})
    await notify({"type": "reminder", "id": "r1", "name": "n", "text": "ok"})
    await notify({"type": "reminder", "id": "r2", "name": "n", "text": "fail"})

    assert sent[0] == ("https://hooks.example/abc", {"text": "*⏰ n*\nok"})
    assert [b["text"] for _, b in sent] == ["*⏰ n*\nok", "*⏰ n*\nfail", "*⏰ n*\nfail", "*⏰ n*\nfail"]
    assert "slack webhook returned 500 after 3 attempts" in capsys.readouterr().out
