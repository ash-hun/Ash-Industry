"""[core] 위임 간선과 작업 실행 기록 저장소의 기본 클래스(메모리 저장 동작). Postgres 는 상속해서 재정의한다."""

from collections import OrderedDict

from ash_industry.core.workflow.workflow_types import DelegationEdge, JobRecord

# 남겨 두는 간선 수. 화면이 기동 때 읽는 최근 개수보다 넉넉하고, 넘치면 오래된 것부터 지운다
EDGE_KEEP = 1000


class WorkflowStore:
    """간선은 edge_id, 작업은 job_id 로 upsert 한다. 같은 것을 두 번 저장해도 하나다."""

    def __init__(self, keep: int = EDGE_KEEP) -> None:
        self._keep = keep
        self._edges: OrderedDict[str, DelegationEdge] = OrderedDict()
        self._jobs: dict[str, JobRecord] = {}

    async def save_edge(self, edge: DelegationEdge) -> None:
        self._edges[edge.edge_id] = edge
        while len(self._edges) > self._keep:
            self._edges.popitem(last=False)

    async def recent_edges(self, limit: int) -> list[DelegationEdge]:
        """시작 시각이 늦은 limit 개를 오래된 순으로."""
        items = sorted(self._edges.values(), key=lambda e: e.started_ms)
        return items[-limit:] if limit > 0 else []

    async def save_job(self, record: JobRecord) -> None:
        self._jobs[record.job_id] = record

    async def jobs(self) -> list[JobRecord]:
        """job_id 순."""
        return [self._jobs[k] for k in sorted(self._jobs)]
