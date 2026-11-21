"""ion 감시 서비스 테스트용 가짜 백엔드, 가짜 Docker, 시각을 고정한 WatchService. 개인 확장 테스트도 쓴다."""

from typing import Any
from datetime import datetime

from ash_industry.ion.docker_client import ContainerState
from ash_industry.ion.incident_store import IncidentStore
from ash_industry.ion.watch_service import WatchService
from ash_industry.ion.ion_config import IonConfig

NOON = datetime(2026, 11, 12, 12, 0)


class FakeBackend:
    """백엔드 health, metrics, jobs 를 흉내 낸다. agent 는 지표와 작업이 속한 에이전트 id."""

    def __init__(self, agent: str = "scribe") -> None:
        self.ok = True
        self.agent = agent
        self.toggled: list[tuple[str, bool]] = []
        self.rows: list[dict[str, Any]] = [{"agent": agent, "jobs": 1, "fail_streak": 0, "last_ok_ms": 5}]

    async def health(self) -> bool:
        return self.ok

    async def metrics(self) -> dict[str, Any] | None:
        return {"loop_lag": {"max_ms": 1.0}, "agents": list(self.rows)}

    async def jobs(self) -> list[dict[str, Any]]:
        return [{"name": "goal-1", "agent": self.agent, "enabled": True},
                {"name": "off", "agent": self.agent, "enabled": False}]

    async def set_task_enabled(self, name: str, enabled: bool) -> bool:
        self.toggled.append((name, enabled))
        return True


class FakeDocker:
    def __init__(self) -> None:
        self.restarts = 0
        self.log_calls: list[tuple[int | None, int | None, int]] = []

    async def find(self, service: str) -> ContainerState | None:
        return ContainerState("abc", service, "running", 0)

    async def with_stats(self, state: ContainerState) -> ContainerState:
        return state

    async def restart(self, service: str) -> bool:
        self.restarts += 1
        return True

    async def stop(self, service: str) -> bool:
        return True

    async def logs(self, service: str, since_s: int | None, until_s: int | None, tail: int) -> str:
        self.log_calls.append((since_s, until_s, tail))
        return "[Loop] boom\nTraceback"


def make_watch_service(tmp_path, backend: FakeBackend, docker: FakeDocker, poll_sec: float = 0):  # type: ignore[no-untyped-def]
    sent: list[dict[str, Any]] = []
    clock = iter(range(1, 1000))

    async def notify(payload: dict[str, Any]) -> None:
        sent.append(payload)

    cfg = IonConfig(poll_sec=poll_sec, metrics_every=1, data_dir=str(tmp_path))
    store = IncidentStore(tmp_path / "incidents.json")
    svc = WatchService(cfg, backend, docker, store, notify,  # type: ignore[arg-type]
                       now_ms=lambda: next(clock) * 1000, clock=lambda: NOON)
    return svc, sent
