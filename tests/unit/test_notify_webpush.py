"""notify: webpush 가 payload 를 {title, body, tag} 로 바꾸고 구독마다 한 번 보내며 죽은 구독은 지우는지 검증."""

import json
import pytest
import asyncio

from ash_industry.core.notify.webpush import BODY_MAX, Subscription, is_gone, push_body, sphere, validate_subscription
from ash_industry.core.notify.webpush import webpush_notifier
from ash_industry.core.notify.sent_store import SentStore
from ash_industry.core.notify.delivery import Delivery

ALIVE = Subscription("https://web.push.apple.com/alive", "p", "a")
DEAD = Subscription("https://web.push.apple.com/dead", "p", "a")


async def _no_sleep(_sec: float) -> None:
    return None


def _delivery() -> Delivery:
    return Delivery(SentStore(None), clock=lambda: 1000.0, sleep=_no_sleep)


class Store:
    def __init__(self, subs: list[Subscription]) -> None:
        self.subs = {s.endpoint: s for s in subs}

    async def all(self):
        return list(self.subs.values())

    async def delete(self, endpoint):
        self.subs.pop(endpoint, None)


def test_push_body_uses_the_headline_and_the_id_as_tag():
    body = push_body({"type": "reminder", "kind": "reminder", "label": "아침 날씨", "text": "맑음, 18도", "id": "r1"})
    assert body == {"title": "⏰ 아침 날씨", "body": "맑음, 18도", "tag": "r1"}
    long = {"type": "proactive_message", "agent_name": "S.C.R.I.B.E.", "text": "x" * 5000, "message_id": "m"}
    proactive = push_body(long)
    assert proactive is not None and len(proactive["body"]) == BODY_MAX and proactive["tag"] == "m"


def test_push_body_title_is_the_agent_sphere_and_name():
    scribe = {
        "type": "reminder", "kind": "tool", "label": "오늘의 LH 공고", "text": "공고 2건",
        "agent_name": "S.C.R.I.B.E.", "agent_color": "#97BC62", "agent_avatar": "https://cdn/scribe.png",
    }
    assert push_body(scribe) == {
        "title": "🟢 S.C.R.I.B.E.", "body": "⏱ 오늘의 LH 공고\n공고 2건", "tag": "", "icon": "https://cdn/scribe.png",
    }
    main = {
        "type": "proactive_message", "agent_name": "A.S.H.", "agent_color": "#5fc8e2",
        "text": "Okay, 회의 10분 전입니다.",
    }
    assert push_body(main)["title"] == "🔵 A.S.H."  # type: ignore[index]
    assert push_body(main)["body"] == "💭 Okay, 회의 10분 전입니다."  # type: ignore[index]
    # 이름을 모르면 예전 그대로
    assert push_body({**scribe, "agent_name": ""})["title"] == "⏱ 오늘의 LH 공고"  # type: ignore[index]


def test_sphere_picks_the_nearest_colour_and_falls_back_to_blue():
    assert sphere("#97BC62") == "🟢" and sphere("#5fc8e2") == "🔵" and sphere("#e04050") == "🔴"
    assert sphere("") == "🔵" and sphere("#zzz") == "🔵"


def test_is_gone_and_validate_subscription():
    assert is_gone(404) and is_gone(410) and not is_gone(201) and not is_gone(429)
    sub = validate_subscription({"endpoint": "https://e", "expirationTime": None, "keys": {"p256dh": "p", "auth": "a"}})
    assert sub == Subscription("https://e", "p", "a")
    for bad in ({"endpoint": "http://e", "keys": {"p256dh": "p", "auth": "a"}}, {"endpoint": "https://e", "keys": {}}):
        with pytest.raises(ValueError):
            validate_subscription(bad)


def test_webpush_notifier_sends_to_every_subscription_once_and_drops_the_dead_one():
    store = Store([ALIVE, DEAD])
    sent: list[tuple[str, dict]] = []

    async def send(sub, data):
        sent.append((sub.endpoint, json.loads(data)))
        return 410 if sub is DEAD else 201

    notify = webpush_notifier(store, send, _delivery())
    payload = {"type": "reminder", "label": "알림", "text": "회의 10분 전", "id": "r"}

    async def twice():
        await notify(payload)
        await notify(payload)

    asyncio.run(twice())
    assert [e for e, _ in sent] == [ALIVE.endpoint, DEAD.endpoint]  # 410 은 4xx 라 다시 보내지 않고 지운다
    assert sent[0][1]["body"] == "회의 10분 전"
    assert list(store.subs) == [ALIVE.endpoint]


def test_webpush_notifier_retries_a_subscription_that_fails_without_status_and_keeps_the_rest():
    store = Store([ALIVE, DEAD])
    sent: list[str] = []

    async def send(sub, data):
        sent.append(sub.endpoint)
        return 0 if sub is DEAD else 201

    notify = webpush_notifier(store, send, _delivery())

    asyncio.run(notify({"type": "reminder", "label": "알림", "text": "t", "id": "r"}))
    assert sent == [ALIVE.endpoint, DEAD.endpoint, DEAD.endpoint, DEAD.endpoint]
    assert list(store.subs) == [ALIVE.endpoint, DEAD.endpoint]  # 네트워크 오류는 구독을 지울 근거가 아니다
