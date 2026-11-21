"""[repository] 편집 계획을 id 로 보관한다. id 는 원본 상태와 계획에서 나와 같은 입력이면 같다."""

import json
import hashlib
from typing import Any
from pathlib import Path
from dataclasses import field, dataclass

from docparse import EditPlan


def plan_id_for(rel_path: str, source: Path, plan: EditPlan) -> str:
    """원본의 크기와 수정 시각까지 섞어, 원본이 바뀌면 옛 계획 id 가 쓸모없어진다."""
    stat = source.stat()
    body = json.dumps(
        {"path": rel_path, "size": stat.st_size, "mtime_ns": stat.st_mtime_ns, "plan": plan.model_dump()},
        ensure_ascii=False, sort_keys=True,
    )
    return hashlib.sha256(body.encode()).hexdigest()[:12]


@dataclass
class StoredPlan:
    plan_id: str
    rel_path: str
    plan: EditPlan
    preview: dict[str, Any]
    result: dict[str, Any] | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class PlanStore:
    """프로세스 메모리. 서버가 다시 뜨면 비어 plan_edit 부터 다시 한다.

    # ponytail: 파일 보관은 승인이 재시작을 넘길 때
    """

    def __init__(self, keep: int = 200) -> None:
        self._plans: dict[str, StoredPlan] = {}
        self._keep = keep

    def put(self, stored: StoredPlan) -> StoredPlan:
        existing = self._plans.get(stored.plan_id)
        if existing is not None:
            return existing
        self._plans[stored.plan_id] = stored
        while len(self._plans) > self._keep:
            oldest = next(iter(self._plans))
            del self._plans[oldest]
        return stored

    def get(self, plan_id: str) -> StoredPlan | None:
        return self._plans.get(plan_id)
