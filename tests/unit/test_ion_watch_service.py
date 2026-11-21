"""ion 의 감시 루프: 무응답 3회에 사고 하나와 알림 하나, 회복하면 닫히고, 답은 처음 한 번만 행동한다."""


from tests.fixtures.ion_helpers import FakeBackend, FakeDocker, make_watch_service
from ash_industry.ion.watch_service import notification, to_observation
from ash_industry.ion.docker_client import ContainerState
from ash_industry.ion.incident_store import Incident

async def test_three_failures_open_one_incident_notify_once_and_recovery_closes_it(tmp_path):
    backend, docker = FakeBackend(), FakeDocker()
    svc, sent = make_watch_service(tmp_path, backend, docker)
    backend.ok = False

    for _ in range(4):
        await svc.tick()
    assert len(sent) == 1 and sent[0]["kind"] == "backend_down" and sent[0]["actions"] == ["restart", "ignore"]
    assert len(svc.store.open_incidents()) == 1 and svc.status()["backend_ok"] is False

    backend.ok = True
    await svc.tick()
    assert svc.store.open_incidents() == [] and len(sent) == 1

    # 같은 시간대에 다시 죽으면 새 사고로 다시 알린다. 닫힌 사고가 막지 않는다
    backend.ok = False
    for _ in range(3):
        await svc.tick()
    assert len(sent) == 2 and len(svc.store.open_incidents()) == 1


async def test_restart_backend_restarts_each_time_it_is_asked(tmp_path):
    backend, docker = FakeBackend(), FakeDocker()
    svc, _ = make_watch_service(tmp_path, backend, docker)

    assert await svc.restart_backend() is True and await svc.restart_backend() is True
    assert docker.restarts == 2


async def test_respond_acts_once_and_pause_disables_only_enabled_jobs_of_the_agent(tmp_path):
    backend, docker = FakeBackend(), FakeDocker()
    svc, _ = make_watch_service(tmp_path, backend, docker)
    svc.store.open(Incident("backend_down:backend:0", "backend_down", "backend", "x", 1))
    svc.store.open(Incident("agent_failing:scribe:0", "agent_failing", "scribe", "x", 1))

    first = await svc.respond("backend_down:backend:0", "restart")
    again = await svc.respond("backend_down:backend:0", "restart")
    assert first is not None and first.action_result == "재기동함" and again == first and docker.restarts == 1

    paused = await svc.respond("agent_failing:scribe:0", "pause")
    assert paused is not None and paused.action_result == "작업 1개 멈춤" and backend.toggled == [("goal-1", False)]
    assert await svc.respond("ghost", "restart") is None
    assert await svc.respond("agent_failing:scribe:0", "dance") is None


def test_observation_and_notification_are_built_from_what_was_fetched():
    metrics = {"loop_lag": {"max_ms": 7.5}, "agents": [
        {"agent": "scribe", "jobs": 2, "fail_streak": 1, "last_ok_ms": 9},
        {"agent": "main", "jobs": 0, "scheduled": True}, {"agent": "shared", "jobs": 1},
    ]}
    obs = to_observation(100, True, metrics, ContainerState("abc", "ash-backend", "running", 3, 10, 100))
    assert (obs.loop_lag_ms, obs.restart_count, obs.rss_bytes, obs.memory_limit_bytes) == (7.5, 3, 10, 100)
    assert list(obs.agents) == ["scribe", "main"] and obs.agents["scribe"].scheduled is True
    # 재기동 직후라 기록은 없어도 켜진 스케줄이 있으면 감시 대상이다
    assert obs.agents["main"].scheduled is True
    assert to_observation(1, None, None, None).health_ok is None
    due = to_observation(100, True, {"agents": [{"agent": "main", "scheduled": True, "last_due_ms": 7}]}, None)
    assert due.agents["main"].last_due_ms == 7 and obs.agents["scribe"].last_due_ms is None

    failing = Incident("agent_failing:scribe:0", "agent_failing", "scribe", "연속 실패 3회", 1)
    note = notification(failing, "/", {"scribe": "S.C.R.I.B.E."})
    assert note["title"] == "Ion: S.C.R.I.B.E. 의 작업이 계속 실패해요" and note["tag"] == "agent_failing:scribe:0"
    assert note["target"] == "scribe" and notification(failing, "/")["title"] == "Ion: scribe 의 작업이 계속 실패해요"
    assert note["severity"] == "warning"
    down = notification(Incident("backend_down:backend:0", "backend_down", "backend", "x", 1), "/")
    assert down["severity"] == "critical"
