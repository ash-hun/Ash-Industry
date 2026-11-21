"""[ui] Workflow 화면 REST: 에이전트 관계 그래프(에이전트, sub-agent, 최근 위임), 노드 배치, 백그라운드 작업 현황."""

import asyncio
from typing import Any
from datetime import datetime
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from ash_industry.core.workflow.workflow_layout_store import WorkflowLayout, WorkflowLayoutStore
from ash_industry.core.workflow.workflow_tracker import SUBAGENT_PREFIX
from ash_industry.ui.web.router.tool_router import short_description
from ash_industry.core.workflow.workflow_types import JobRecord
from ash_industry.app.agent_profile import MAIN_AGENT_ID
from ash_industry.ui.web.web_state import WebState

WORKFLOW_EXAMPLE = {
    "root": {"session_id": "default", "agent": "main", "name": "A.S.H.", "model": "claude-sonnet-5-5",
             "context_tokens": 598400},
    "agents": [{"id": "main", "name": "A.S.H.", "description": "", "primary": "#e6e8ea", "main": True}],
    "subagents": ["minutes", "researcher"],
    "subagent_owners": {"minutes": "scribe"},
    "capabilities": [
        {"name": "bash", "description": "셸 명령 실행", "approval": True, "agents": ["main"]},
        {"name": "web_search", "description": "웹 검색", "approval": False, "agents": ["main", "scribe"]},
    ],
    "edges": [{"edge_id": "default:call_1", "kind": "ask", "source": "main", "target": "scribe",
               "label": "오늘 일정 정리", "started_ms": 1791613276663, "ended_ms": 1791613279001, "ok": True,
               "session_id": "default", "tokens": 59012}],
}
LAYOUT_EXAMPLE = {"nodes": {"agent:main": {"x": 480.0, "y": 210.0}, "leaf:main:bash": {"x": 370.0, "y": 180.0}}}
JOBS_EXAMPLE = {
    "jobs": [{"job_id": "schedule:morning", "kind": "schedule", "label": "아침 브리핑", "runs": 3, "running": False,
              "last_started_ms": 1791613276663, "last_ended_ms": 1791613281000, "last_ok": True, "last_error": "",
              "enabled": True, "next_run": "2026-11-04T09:00:00+09:00", "agent": "main"}],
    "daemon": {"enabled": True, "trigger": "interval", "interval_sec": 120, "idle_sec": 180},
}


def merge_jobs(records: list[JobRecord], schedules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """스케줄 목록(아직 돈 적 없는 것 포함)에 실행 기록을 얹고, 스케줄이 아닌 작업 기록을 뒤에 붙인다. 순수 함수."""
    by_id = {r.job_id: r for r in records}
    jobs: list[dict[str, Any]] = []
    for sched in schedules:
        job_id = f"schedule:{sched['name']}"
        record = by_id.pop(job_id, None) or JobRecord(
            job_id=job_id, kind="schedule", label=str(sched.get("label") or sched["name"]), runs=0, running=False
        )
        jobs.append({**record.to_dict(), **{k: sched[k] for k in ("enabled", "next_run", "agent")}})
    jobs.extend(r.to_dict() for r in sorted(by_id.values(), key=lambda r: r.job_id))
    return jobs


def capability_map(tools_by_agent: dict[str, list[str]]) -> list[dict[str, Any]]:
    """도구 이름마다 그 도구를 쓰는 에이전트 목록. 한 에이전트만 가진 것이 먼저, 그다음 이름순. 순수 함수.

    에이전트 순서는 tools_by_agent 의 순서를 따른다. sub-agent 위임 도구(agent_<이름>)는 그래프가 따로 그려 뺀다.
    """
    owners: dict[str, list[str]] = {}
    for agent_id, names in tools_by_agent.items():
        for name in names:
            if name.startswith(SUBAGENT_PREFIX):
                continue
            ids = owners.setdefault(name, [])
            if agent_id not in ids:
                ids.append(agent_id)
    return [{"name": n, "agents": ids} for n, ids in sorted(owners.items(), key=lambda kv: (len(kv[1]) > 1, kv[0]))]


def context_tokens(messages: list[Any]) -> int:
    """마지막 assistant 메시지가 읽은 양(입력과 캐시 읽기). 다음 턴이 이만큼을 다시 읽는다. 순수 함수."""
    for message in reversed(messages):
        if getattr(message, "role", None) != "assistant":
            continue
        usage = getattr(message, "usage", None)
        return int(getattr(usage, "input", 0) or 0) + int(getattr(usage, "cache_read", 0) or 0)
    return 0


def build_workflow_router(state: WebState) -> APIRouter:
    router = APIRouter(tags=["workflow"])
    ctx = state.ctx
    agents = state.assembly.agents

    needs_approval = set(state.settings.security.require_approval_for)
    layouts = WorkflowLayoutStore(state.settings.workflow.layout_path)

    def capabilities() -> list[dict[str, Any]]:
        # 에이전트마다 세션이 실제로 쓰는 도구(정의의 tools, never 를 거른 것). 세션을 열지 않고 레지스트리만 만든다
        registries = {p.agent_id: agents.tool_registry(p.agent_id) for p in agents.profiles()}
        tools = {aid: [t.name for t in reg.list_all()] for aid, reg in registries.items() if reg is not None}
        described = {t.name: t for reg in registries.values() if reg is not None for t in reg.list_all()}
        return [
            {
                **cap,
                "description": short_description(described[cap["name"]].description),
                "approval": cap["name"] in needs_approval,
            }
            for cap in capability_map(tools)
        ]

    @router.get(
        "/api/workflow",
        summary="에이전트 관계 그래프",
        description=(
            "agents 는 최상위 에이전트, subagents 는 위임 도구(agent_<이름>)로 실린 sub-agent 이름순,"
            " subagent_owners 는 최상위 에이전트의 기능 담당(parent)인 sub-agent 마다 그 주인 id,"
            " capabilities 는 도구마다 그 도구를 쓰는 에이전트(한 에이전트만 가진 것이 먼저),"
            " edges 는 이 프로세스가 본 최근 위임 200개(오래된 것부터). 끝나지 않은 위임은 ended_ms 와 ok 가 null."
            " session 을 주면 root(그 세션의 에이전트, 모델, 마지막 턴이 읽은 토큰)를 함께 준다. 지도의 뿌리 카드다."
        ),
        responses={200: {"content": {"application/json": {"example": WORKFLOW_EXAMPLE}}}},
    )
    async def get_workflow(session: str = Query("", max_length=200)) -> JSONResponse:
        top = [
            {
                "id": p.agent_id, "name": p.name, "description": short_description(p.description),
                "primary": p.brand.palette.primary, "main": p.is_main,
            }
            for p in agents.profiles()
        ]
        # 기능 담당(parent 가 있는 정의)은 팀 전용 풀에 있다. 주인을 함께 알려 그래프가 그 허브 아래 둔다
        pools = [ctx.tool_registry] + ([ctx.agent_tools] if ctx.agent_tools is not None else [])
        delegates = {
            t.name[len(SUBAGENT_PREFIX):]: t
            for pool in pools for t in pool.list_all() if t.name.startswith(SUBAGENT_PREFIX)
        }
        owners = {
            name: parent
            for name, tool in delegates.items()
            if (parent := getattr(getattr(getattr(tool, "node", None), "definition", None), "parent", None))
        }
        edges = [e.to_dict() for e in state.workflow.edges()]
        body: dict[str, Any] = {
            "agents": top, "subagents": sorted(delegates), "subagent_owners": owners,
            "capabilities": capabilities(), "edges": edges,
        }
        if session:
            body["root"] = await root_of(session)
        return JSONResponse(body)

    async def root_of(session_id: str) -> dict[str, Any]:
        """지도의 뿌리. 열린 세션이면 그 에이전트, 아니면 저장소의 메타, 둘 다 없으면 main."""
        agent_id = state.registry.session_agents().get(session_id)
        if agent_id is None:
            metas = await ctx.session_repo.list()
            agent_id = next((m.agent_id for m in metas if m.session_id == session_id), MAIN_AGENT_ID)
        profile = agents.get(agent_id) or agents.main
        messages = await ctx.session_repo.get_messages(session_id)
        return {
            "session_id": session_id, "agent": profile.agent_id, "name": profile.name, "model": profile.model.model,
            "context_tokens": context_tokens(messages),
        }

    @router.get(
        "/api/workflow/layout",
        summary="그래프 노드 배치",
        description=(
            "사용자가 옮기거나 정렬이 정한 노드 자리. 키는 agent:<id>, leaf:<에이전트>:<이름>, shared:<이름>."
            " 설치 하나에 하나라 어느 기기에서 열어도 같다. 저장한 적 없으면 nodes 가 비어 있고 기본 배치로 그린다."
        ),
        responses={200: {"content": {"application/json": {"example": LAYOUT_EXAMPLE}}}},
    )
    async def get_layout() -> JSONResponse:
        layout = await asyncio.to_thread(layouts.load)
        return JSONResponse(layout.model_dump(mode="json"))

    @router.put(
        "/api/workflow/layout",
        summary="그래프 노드 배치 저장",
        description=(
            "nodes 전체를 바꾼다(합치지 않는다). 빈 nodes 는 기본 배치로 되돌린다. 노드 2000개, 키 200자,"
            " 좌표 ±100000 을 넘거나 수가 아니면 422. 같은 본문을 다시 보내면 같은 파일이 남는다."
        ),
        responses={200: {"content": {"application/json": {"example": LAYOUT_EXAMPLE}}}},
    )
    async def put_layout(body: WorkflowLayout) -> JSONResponse:
        saved = await asyncio.to_thread(layouts.save, body)
        return JSONResponse(saved.model_dump(mode="json"))

    @router.get(
        "/api/jobs",
        summary="백그라운드 작업 현황",
        description=(
            "스케줄(돈 적 없는 것도), 성찰 daemon, 기억 정리, 외부 조회의 마지막 실행. 실행 기록은 프로세스 메모리라"
            " 재시작하면 runs 가 0 부터 다시 센다. daemon 은 성찰 주기 설정."
        ),
        responses={200: {"content": {"application/json": {"example": JOBS_EXAMPLE}}}},
    )
    async def get_jobs() -> JSONResponse:
        schedules: list[dict[str, Any]] = []
        if ctx.scheduler is not None:
            from ash_industry.core.scheduler.scheduler_service import SchedulerService

            now = datetime.now()
            for task in ctx.scheduler.list_tasks():
                nxt = SchedulerService.next_run(task, now)
                schedules.append({
                    "name": task.name,
                    "label": task.description or task.name,
                    "enabled": task.enabled,
                    "next_run": nxt.astimezone().isoformat() if nxt else None,
                    "agent": task.agent,
                })
            schedules.sort(key=lambda s: str(s["name"]))
        pcfg = state.settings.proactive
        daemon = {
            "enabled": pcfg.daemon_enabled,
            "trigger": pcfg.daemon_trigger,
            "interval_sec": pcfg.daemon_interval_sec,
            "idle_sec": pcfg.daemon_idle_sec,
        }
        return JSONResponse({"jobs": merge_jobs(state.jobs.records(), schedules), "daemon": daemon})

    return router
