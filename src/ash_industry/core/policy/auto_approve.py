"""[core] 에이전트별 auto mode(승인 자동 허용) 켜짐 여부를 YAML 파일 하나에 두고 읽는 저장소."""

import os
import yaml
import threading
from pathlib import Path

from ash_industry.common.logger import get_logger

logger = get_logger(__name__)


class AutoApproveStore:
    """{agents: {<id>: true}} 꼴. 읽기는 메모리에서 하고 바꿀 때만 파일에 쓴다. 같은 값을 다시 써도 결과가 같다."""

    def __init__(self, path: str) -> None:
        self._path = Path(path).expanduser()
        self._lock = threading.Lock()
        self._agents = self._load()

    def _load(self) -> dict[str, bool]:
        if not self._path.exists():
            return {}
        try:
            data = yaml.safe_load(self._path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError) as exc:
            # 깨진 파일 때문에 승인이 풀리면 안 된다. 모두 꺼진 것으로 시작한다
            logger.warning(f"[AutoApprove] cannot read {self._path}: {exc}, all agents start with auto mode off")
            return {}
        agents = data.get("agents") if isinstance(data, dict) else None
        return {str(k): v for k, v in (agents or {}).items() if v is True}

    def enabled(self, agent_id: str) -> bool:
        return self._agents.get(agent_id, False)

    def all(self) -> dict[str, bool]:
        return dict(self._agents)

    def set(self, agent_id: str, on: bool) -> None:
        with self._lock:
            agents = {**self._agents, agent_id: True} if on else {
                k: v for k, v in self._agents.items() if k != agent_id
            }
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(".tmp")
            tmp.write_text(yaml.safe_dump({"agents": agents}, allow_unicode=True, sort_keys=True), encoding="utf-8")
            os.replace(tmp, self._path)
            self._agents = agents
        logger.info(f"[AutoApprove] {agent_id} auto mode {'on' if on else 'off'}")
