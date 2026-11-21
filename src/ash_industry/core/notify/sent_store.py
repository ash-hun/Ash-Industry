"""[core] 보낸 알림 키를 jsonl 로 기억해 같은 알림을 두 번 보내지 않는다."""

import os
import json
import asyncio
import aiofiles
from pathlib import Path

# 키를 jsonl 한 줄씩 덧붙이고, 줄 수가 상한의 두 배에 닿으면 최신 상한만 남겨 다시 쓴다
DEFAULT_PATH = "~/.ash/notify_sent.jsonl"
MAX_KEYS = 5_000
TTL_SEC = 604_800.0


class SentStore:
    """path 가 None 이면 메모리에만 둔다(테스트, 일회성 운용). 시계는 경계에서 받는다."""

    def __init__(self, path: str | None = DEFAULT_PATH, *, max_keys: int = MAX_KEYS, ttl_sec: float = TTL_SEC) -> None:
        self._path = Path(path).expanduser() if path else None
        self._max_keys = max_keys
        self._ttl = ttl_sec
        self._seen: dict[str, float] = {}
        self._lines = 0
        self._loaded = self._path is None
        self._lock = asyncio.Lock()

    async def contains(self, key: str, now: float) -> bool:
        await self._ensure_loaded(now)
        self._prune(now)
        return key in self._seen

    async def add(self, key: str, now: float) -> None:
        """키를 적는다. 파일이 있으면 바로 덧붙여, 바로 뒤에 프로세스가 죽어도 남는다."""
        await self._ensure_loaded(now)
        self._seen[key] = now
        if self._path is None:
            self._prune(now)
            return
        async with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            async with aiofiles.open(self._path, "a", encoding="utf-8") as f:
                await f.write(json.dumps({"key": key, "ts": now}) + "\n")
            self._lines += 1
            if self._lines >= 2 * self._max_keys:
                self._prune(now)
                await self._rewrite()

    async def _ensure_loaded(self, now: float) -> None:
        if self._loaded or self._path is None:
            return
        async with self._lock:
            if self._loaded:
                return
            if self._path.exists():
                async with aiofiles.open(self._path, encoding="utf-8") as f:
                    async for line in f:
                        self._lines += 1
                        try:
                            record = json.loads(line)
                            self._seen[str(record["key"])] = float(record.get("ts", 0.0))
                        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                            continue
            self._loaded = True
            self._prune(now)
            if self._lines >= 2 * self._max_keys:
                await self._rewrite()

    async def _rewrite(self) -> None:
        """남은 키만 임시 파일에 쓰고 바꿔 끼운다. 중간에 죽어도 원본은 온전하다."""
        assert self._path is not None
        tmp = self._path.with_suffix(".jsonl.tmp")
        async with aiofiles.open(tmp, "w", encoding="utf-8") as f:
            await f.write("".join(json.dumps({"key": k, "ts": t}) + "\n" for k, t in self._seen.items()))
        os.replace(tmp, self._path)
        self._lines = len(self._seen)

    def _prune(self, now: float) -> None:
        if self._ttl > 0:
            for key in [k for k, t in self._seen.items() if now - t > self._ttl]:
                del self._seen[key]
        overflow = len(self._seen) - self._max_keys
        if overflow > 0:
            for key, _ in sorted(self._seen.items(), key=lambda kv: kv[1])[:overflow]:
                del self._seen[key]

    def __len__(self) -> int:
        return len(self._seen)
