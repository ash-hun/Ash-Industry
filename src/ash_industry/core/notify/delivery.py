"""[core] 알림마다 내용에서 결정적 키를 만들어 한 번만 보내고, 실패는 짧은 backoff 로 다시 보낸다."""

import json
import time
import asyncio
import hashlib
from typing import Any
from collections.abc import Awaitable, Callable, Mapping

from ash_industry.core.notify.sent_store import SentStore
from ash_industry.common.logger import get_logger

CHANNEL_SLACK = "slack webhook"
CHANNEL_DISCORD = "discord webhook"
CHANNEL_WEBPUSH = "web push"
# 키에 넣는 payload 칸. id 가 없는 알림(spoken)은 글과 시각 버킷으로 구분한다
KEY_FIELDS = ("type", "kind", "id", "agent", "text")
BUCKET_SEC = 600.0
# 첫 전송 뒤 다시 보내는 횟수와 그 사이 대기. 둘을 넘으면 포기한다
RETRIES = 2
BACKOFF_SEC = (0.5, 1.0)
# 네트워크 오류나 타임아웃으로 상태가 없을 때
NO_STATUS = 0

Clock = Callable[[], float]
Sleep = Callable[[float], Awaitable[None]]
Send = Callable[[], Awaitable[int]]

logger = get_logger(__name__)


def time_bucket(now: float, bucket_sec: float = BUCKET_SEC) -> int:
    """시각을 bucket_sec 단위로 내린 정수. 순수 함수."""
    return int(now // bucket_sec)


def delivery_key(channel: str, payload: Mapping[str, Any], bucket: int, scope: str = "") -> str:
    """채널(과 그 안의 scope, 예: 푸시 구독), 알림 내용, 시각 버킷에서 만든 결정적 키. 순수 함수."""
    parts = {field: str(payload.get(field) or "") for field in KEY_FIELDS}
    head = {"channel": channel, "scope": scope, "bucket": bucket}
    text = json.dumps({**head, **parts}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:24]


def is_success(status: int) -> bool:
    """2xx, 3xx 만 간 것으로 본다. 상태 없음(0)은 실패다."""
    return 200 <= status < 400


def is_retryable(status: int) -> bool:
    """상태 없음(네트워크 오류, 타임아웃)과 5xx 만 다시 보낸다. 4xx 는 다시 보내도 같다."""
    return status == NO_STATUS or status >= 500


def backoff_sec(attempt: int, backoff: tuple[float, ...] = BACKOFF_SEC) -> float:
    """attempt 번째(0 부터) 실패 뒤 기다리는 시간. 표보다 뒤는 마지막 값."""
    return backoff[min(attempt, len(backoff) - 1)] if backoff else 0.0


def default_delivery() -> "Delivery":
    """채널을 따로 조립하지 않을 때. 메모리에만 기억하고 실제 시계로 돈다."""
    return Delivery(SentStore(None), clock=time.time)


class Delivery:
    """채널 하나의 전송 하나를 감싼다. 같은 키는 한 번만, 실패는 retries 번 더. 시계와 sleep 은 경계에서 받는다."""

    def __init__(
        self,
        store: SentStore,
        clock: Clock,
        *,
        sleep: Sleep = asyncio.sleep,
        retries: int = RETRIES,
        backoff: tuple[float, ...] = BACKOFF_SEC,
    ) -> None:
        self._store = store
        self._clock = clock
        self._sleep = sleep
        self._retries = retries
        self._backoff = backoff
        self._inflight: set[str] = set()

    async def deliver(self, channel: str, payload: Mapping[str, Any], send: Send, *, scope: str = "") -> int | None:
        """보냈으면 마지막 HTTP 상태, 이미 보낸 키라 건너뛰었으면 None. 성공한 직후 키를 적는다.

        scope 는 키에만 들어가고 로그에는 남지 않는다(푸시 구독 endpoint 처럼 비밀에 가까운 값).
        """
        now = self._clock()
        key = delivery_key(channel, payload, time_bucket(now), scope)
        if key in self._inflight or await self._store.contains(key, now):
            logger.debug(f"[Notify] {channel} skipped, already sent ({key})")
            return None
        self._inflight.add(key)
        try:
            status = await self._attempt(channel, send)
            if is_success(status):
                await self._store.add(key, self._clock())
            return status
        finally:
            self._inflight.discard(key)

    async def _attempt(self, channel: str, send: Send) -> int:
        status, error, tries = NO_STATUS, "", 0
        for attempt in range(self._retries + 1):
            tries = attempt + 1
            try:
                status, error = await send(), ""
            except Exception as exc:  # 네트워크 오류, 타임아웃. 상태 없음으로 보고 다시 보낸다
                status, error = NO_STATUS, repr(exc)
            if is_success(status):
                return status
            if not is_retryable(status) or attempt == self._retries:
                break
            await self._sleep(backoff_sec(attempt, self._backoff))
        reason = error or f"returned {status}"
        logger.info(f"[Notify] {channel} {reason} after {tries} attempt{'s' if tries > 1 else ''}, giving up")
        return status
