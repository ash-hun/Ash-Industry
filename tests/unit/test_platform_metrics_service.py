"""platform 의 지표: 작업 기록을 에이전트별로 접고, 프로세스 자원을 읽어 한 장으로 낸다."""

from ash_industry.core.platform.metrics_service import PlatformMetricsService, agent_metrics, schedule_agent_of
from ash_industry.core.workflow.workflow_types import JobRecord


def _job(job_id: str, ok: bool | None, ended: int | None, streak: int = 0, running: bool = False) -> JobRecord:
    return JobRecord(job_id=job_id, kind="schedule", label=job_id, runs=1, running=running,
                     last_ended_ms=ended, last_ok=ok, last_error="" if ok else "boom", fail_streak=streak)


def test_agent_metrics_fold_jobs_by_agent_and_count_sessions():
    agent_of = schedule_agent_of({"goal-1": "scribe", "ping": "main"})
    records = [
        _job("schedule:goal-1", True, 100),
        _job("schedule:ping", False, 200, streak=2, running=True),
        _job("proactive:reflect", True, 300),
    ]

    out = {m.agent: m for m in agent_metrics(records, agent_of, ["main", "scribe"], {"s1": "main", "s2": "main"},
                                             scheduled={"scribe"})}

    assert (out["scribe"].jobs, out["scribe"].last_ok_ms, out["scribe"].open_sessions) == (1, 100, 0)
    assert out["scribe"].scheduled is True and out["main"].scheduled is False
    main = out["main"]
    assert (main.fail_streak, main.running, main.last_error, main.open_sessions) == (2, 1, "boom", 2)
    assert (out["shared"].jobs, out["shared"].last_ok_ms) == (1, 300)


def test_agent_without_jobs_still_appears_with_zeros():
    out = agent_metrics([], lambda _: None, ["clerk"], {}, scheduled={"clerk"}, due={"clerk": 5})
    assert [(m.agent, m.jobs, m.last_ok_ms, m.scheduled, m.last_due_ms) for m in out] == [
        ("clerk", 0, None, True, 5), ("shared", 0, None, False, None),
    ]


def test_snapshot_reads_this_process_and_lists_agents():
    svc = PlatformMetricsService(records=lambda: [], agent_of=lambda _: None, agents=lambda: ["main"],
                                 sessions=lambda: {}, now=lambda: 1000.0)

    snap = svc.snapshot()

    assert snap["at_ms"] == 1_000_000 and snap["process"]["rss_bytes"] > 0 and snap["process"]["threads"] >= 1
    assert snap["loop_lag"] == {"last_ms": 0.0, "max_ms": 0.0, "samples": 0}
    assert [a["agent"] for a in snap["agents"]] == ["main", "shared"]


def test_agent_metrics_carry_last_activity_and_display_name():
    out = {m.agent: m for m in agent_metrics([], lambda _: None, ["main", "scribe"], {}, active={"scribe": 5},
                                             names={"scribe": "S.C.R.I.B.E."})}
    assert (out["scribe"].last_active_ms, out["scribe"].name) == (5, "S.C.R.I.B.E.")
    # 이름을 모르면 id 그대로라 화면이 빈칸을 그리지 않는다
    assert (out["main"].last_active_ms, out["main"].name) == (None, "main")
