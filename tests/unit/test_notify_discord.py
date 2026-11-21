"""notify: discord 가 payload 를 디스코드 본문으로 바꾸고(머리, 길이, 멘션 막기) 4xx 는 다시 보내지 않는지 검증."""

import pytest

from ash_industry.core.notify.discord import discord_notifier, format_discord
from ash_industry.core.scheduler.task import ScheduledTask, task_label
from ash_industry.core.notify.sent_store import SentStore
from ash_industry.core.notify.delivery import Delivery


async def _no_sleep(_sec: float) -> None:
    return None


def test_format_discord_bolds_head_truncates_and_blocks_mentions():
    body = format_discord({"type": "reminder", "name": "daily", "text": "@everyone @here <@123> 메일 a@b.com"})

    assert body["content"] == "**⏰ daily**\n@​everyone @​here <@​123> 메일 a@b.com"
    assert body["allowed_mentions"] == {"parse": []}
    assert len(format_discord({"type": "proactive_message", "text": "x" * 5000})["content"]) == 2000


@pytest.mark.parametrize(
    ("payload", "head"),
    [
        ({"type": "reminder", "kind": "tool", "label": "새 LH 공고", "text": "새 LH 공고 1건"}, "**⏱ 새 LH 공고**"),
        # 작업 결과는 HUD 와 같은 아이콘을 쓴다
        ({"type": "reminder", "kind": "task", "label": "공고 정리", "text": "세 건"}, "**⏱ 공고 정리**"),
        ({"type": "reminder", "kind": "reminder", "label": "알림", "text": "회의"}, "**⏰ 알림**"),
        # 뒤로 넘긴 작업의 답은 먼저 건넨 말과 다르게 보인다
        (
            {"type": "proactive_message", "kind": "answer", "agent_name": "S.C.R.I.B.E.", "text": "끝"},
            "**💬 S.C.R.I.B.E.**",
        ),
        (
            {"type": "proactive_message", "kind": "proactive", "agent_name": "S.C.R.I.B.E.", "text": "?"},
            "**💭 S.C.R.I.B.E.**",
        ),
    ],
    ids=["tool_task", "task", "reminder", "deferred_answer", "proactive"],
)
def test_format_discord_heads_by_kind(payload, head):
    assert format_discord(payload)["content"].startswith(head)


def test_reminder_title_hides_names_the_schedule_command_made_up():
    once = ScheduledTask(name="once-ba15fed1", prompt="회의 자료 챙기기", kind="reminder")
    task = ScheduledTask(name="slash-1a2b3c4d", prompt="공고 새로 나온 것 정리해줘\n지역은 경기", kind="task")
    named = ScheduledTask(name="daily-news", prompt="뉴스 요약", kind="task")

    head = format_discord({"type": "reminder", "name": "once-ba15fed1", "label": "알림", "text": "회의 자료 챙기기"})

    assert [task_label(t) for t in (once, task, named)] == ["알림", "공고 새로 나온 것 정리해줘", "daily-news"]
    assert head["content"] == "**⏰ 알림**\n회의 자료 챙기기"


async def test_discord_notifier_posts_once_and_does_not_retry_4xx(capsys):
    sent: list[tuple[str, dict]] = []

    async def fake_post(url, body):
        sent.append((url, body))
        return 429 if "fail" in body["content"] else 204

    delivery = Delivery(SentStore(None), clock=lambda: 1000.0, sleep=_no_sleep)
    notify = discord_notifier("https://discord.com/api/webhooks/1/t", post=fake_post, delivery=delivery)

    await notify({"type": "proactive_message", "id": "m1", "text": "ok"})
    await notify({"type": "proactive_message", "id": "m2", "text": "fail"})

    # 429 는 4xx, 다시 보내지 않는다
    assert [b["content"] for _, b in sent] == ["**💭 Ash**\nok", "**💭 Ash**\nfail"]
    assert "discord webhook returned 429 after 1 attempt" in capsys.readouterr().out


async def test_discord_notifier_retries_network_error_then_succeeds(capsys):
    calls: list[int] = []

    async def flaky_post(url, body):
        calls.append(1)
        if len(calls) == 1:
            raise ConnectionError("reset")
        return 204

    delivery = Delivery(SentStore(None), clock=lambda: 1000.0, sleep=_no_sleep)
    notify = discord_notifier("https://discord.com/api/webhooks/1/t", post=flaky_post, delivery=delivery)

    await notify({"type": "proactive_message", "id": "m1", "text": "hi"})
    await notify({"type": "proactive_message", "id": "m1", "text": "hi"})  # 보낸 뒤라 다시 가지 않는다

    assert len(calls) == 2
    assert "giving up" not in capsys.readouterr().out
