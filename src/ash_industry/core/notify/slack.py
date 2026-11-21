"""[core] 슬랙 incoming webhook 으로 알림 payload 를 보낸다."""

from typing import Any
from collections.abc import Awaitable, Callable

from ash_industry.core.notify.delivery import CHANNEL_SLACK, Delivery, default_delivery
from ash_industry.core.notify.webhook import Post, headline, post_json

MAX_TEXT = 2800  # 슬랙 메시지 한도(약 3000자) 아래로 자른다


def format_slack(payload: dict[str, Any]) -> dict[str, Any]:
    """알림 payload → 슬랙 메시지 본문. 순수 함수."""
    head, body = headline(payload)
    text = f"*{head}*\n{body}" if body else f"*{head}*"
    return {"text": text[:MAX_TEXT]}


def slack_notifier(
    webhook_url: str, *, post: Post | None = None, delivery: Delivery | None = None
) -> Callable[[dict[str, Any]], Awaitable[None]]:
    """알림마다 키를 만들어 한 번만 보내고, 네트워크 오류와 5xx 는 짧게 기다려 다시 보낸다. 4xx 는 로그만."""
    send = post or post_json
    deliver = delivery or default_delivery()

    async def notify(payload: dict[str, Any]) -> None:
        body = format_slack(payload)
        await deliver.deliver(CHANNEL_SLACK, payload, lambda: send(webhook_url, body))

    return notify
