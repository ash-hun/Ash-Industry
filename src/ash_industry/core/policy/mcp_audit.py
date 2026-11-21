"""[core] MCP 도구 호출의 판정과 결과를 jsonl 로 남기고 최근 것을 메모리에 들어 시간당 호출 수를 센다."""

import json
from typing import Any
from pathlib import Path
from collections import deque
from collections.abc import Callable

DEFAULT_PATH = "~/.ash/mcp_audit.jsonl"
KEEP = 500  # 메모리와 화면에 두는 최근 줄 수. 파일은 그 두 배가 되면 최근 KEEP 줄로 다시 쓴다
HOUR_MS = 3_600_000


class McpAudit:
    def __init__(
        self, path: str | None = DEFAULT_PATH, keep: int = KEEP, clock: Callable[[], float] | None = None
    ) -> None:
        self._path = Path(path).expanduser() if path else None
        self._keep = keep
        self._clock = clock
        self._recent: deque[dict[str, Any]] = deque(maxlen=keep)
        self._lines = 0
        self._load_tail()

    def _load_tail(self) -> None:
        if self._path is None or not self._path.exists():
            return
        with open(self._path, encoding="utf-8") as f:
            lines = f.readlines()
        self._lines = len(lines)
        for line in lines[-self._keep:]:
            try:
                self._recent.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    def record(self, entry: dict[str, Any]) -> dict[str, Any]:
        """한 줄 남긴다. ts 가 없으면 지금 시각(ms)."""
        if "ts" not in entry:
            import time
            now = self._clock() if self._clock else time.time()
            entry = {"ts": int(now * 1000), **entry}
        self._recent.append(entry)
        if self._path is not None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            self._lines += 1
            if self._lines >= self._keep * 2:
                self._compact()
        return entry

    def _compact(self) -> None:
        assert self._path is not None
        tmp = self._path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            for e in self._recent:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
        tmp.replace(self._path)
        self._lines = len(self._recent)

    def recent(self, limit: int = 50) -> list[dict[str, Any]]:
        """최신이 앞."""
        return list(self._recent)[-limit:][::-1]

    def calls_last_hour(self, server: str, tool: str, now_ms: int) -> int:
        """지난 한 시간에 허용되어 나간 호출 수(판정 줄 가운데 allow, ask 승인)."""
        since = now_ms - HOUR_MS
        return sum(
            1 for e in self._recent
            if e.get("type") == "call" and e.get("server") == server and e.get("tool") == tool
            and e.get("decision") in ("allow", "ask") and int(e.get("ts", 0)) >= since
        )
