"""[core] Workflow 그래프에서 사용자가 옮긴 노드 자리를 설치 하나에 JSON 파일 하나로 남기는 저장소."""

import os
import json
import threading
from pathlib import Path
from pydantic import Field, BaseModel, ConfigDict, field_validator

DEFAULT_PATH = "~/.ash/workflow_layout.json"
MAX_NODES = 2000
KEY_MAX = 200
# 그림은 잎이 많으면 자라지만 몇천 px 안이다. 이 밖의 값은 깨진 클라이언트가 보낸 것으로 본다
COORD_LIMIT = 100_000.0


class NodePosition(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)

    x: float = Field(ge=-COORD_LIMIT, le=COORD_LIMIT)
    y: float = Field(ge=-COORD_LIMIT, le=COORD_LIMIT)


class WorkflowLayout(BaseModel):
    """노드 키(agent:<id>, leaf:<에이전트>:<이름>, shared:<이름>)마다 자리. 비우면 기본 배치로 돌아간다."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    nodes: dict[str, NodePosition] = Field(default_factory=dict, max_length=MAX_NODES)

    @field_validator("nodes")
    @classmethod
    def _keys(cls, nodes: dict[str, NodePosition]) -> dict[str, NodePosition]:
        for key in nodes:
            if not 1 <= len(key) <= KEY_MAX or not key.isprintable():
                raise ValueError(f"노드 키는 제어 문자 없이 1~{KEY_MAX}자: {key[:40]!r}")
        return nodes


class WorkflowLayoutStore:
    """키를 정렬해 쓰므로 같은 배치를 두 번 저장해도 파일이 같다. 쓰기는 임시 파일 뒤 교체."""

    def __init__(self, path: str = DEFAULT_PATH) -> None:
        self._path = Path(path).expanduser()
        self._lock = threading.Lock()

    def load(self) -> WorkflowLayout:
        """파일이 없거나 깨졌으면 빈 배치. 화면은 기본 배치로 그리면 되므로 기동을 막지 않는다."""
        try:
            with open(self._path, encoding="utf-8") as f:
                return WorkflowLayout.model_validate(json.load(f))
        except (OSError, ValueError):
            return WorkflowLayout()

    def save(self, layout: WorkflowLayout) -> WorkflowLayout:
        body = json.dumps(layout.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, indent=1)
        with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(".tmp")
            tmp.write_text(body + "\n", encoding="utf-8")
            os.replace(tmp, self._path)
        return layout
