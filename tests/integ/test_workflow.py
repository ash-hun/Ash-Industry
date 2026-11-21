"""workflow 기능: 위임 도구 호출이 관계 간선으로 ws 와 /api/workflow 에 보이고, 스케줄 실행이 /api/jobs 에 남는다."""

import pytest

pytest.importorskip("fastapi")

from tests.fixtures.web_hud_helpers import (  # noqa: E402
    run_turn,
    web_client,
    scripted_env,
    use_provider,
    web_assembly,
    agenda_assembly,
)
from tests.fixtures.team_provider import TeamProvider  # noqa: E402

SCRIBE = (
    "name: S.C.R.I.B.E.\ndescription: 정보 수집\nsystem_prompt: 당신은 스크라이브입니다.\n"
    "tools: [read_file]\nproactive: false\n"
)


@pytest.fixture
def provider():
    yield from use_provider(TeamProvider())


@pytest.fixture
def team_assembly(monkeypatch, tmp_path, provider):
    (tmp_path / "team").mkdir()
    (tmp_path / "team" / "scribe.yaml").write_text(SCRIBE)
    return web_assembly(monkeypatch, tmp_path, **scripted_env("team", tmp_path, tmp_path / "team"))


def test_ask_agent_turn_becomes_delegation_edges(team_assembly):
    with web_client(team_assembly) as client:
        with client.websocket_connect("/ws?session_id=default") as ws:
            ws.receive_json()
            seen = run_turn(ws, "스크라이브에게 AI 뉴스 좀 물어봐")
        graph = client.get("/api/workflow?session=default").json()

    pushed = [m["edge"] for m in seen if m["type"] == "workflow_changed"]
    routes = {(e["source"], e["target"], e["kind"]) for e in pushed}
    assert routes >= {("main", "scribe", "ask"), ("scribe", "main", "ask")}
    # 지도의 뿌리와, 받는 쪽 세션이 쓴 토큰이 그 위임에 붙는다
    assert graph["root"]["agent"] == "main" and graph["root"]["name"] == "A.S.H."
    assert graph["root"]["model"] and graph["root"]["context_tokens"] >= 1
    first_ask = next(e for e in graph["edges"] if (e["source"], e["target"]) == ("main", "scribe"))
    assert first_ask["session_id"] == "default" and first_ask["tokens"] >= 1
    assert [a["id"] for a in graph["agents"]] == ["main", "scribe"]
    done = [(e["source"], e["target"], e["ok"]) for e in graph["edges"]]
    assert ("main", "scribe", True) in done and ("scribe", "main", True) in done
    assert all(e["ended_ms"] >= e["started_ms"] for e in graph["edges"])
    caps = graph["capabilities"]
    assert {"name", "description", "approval", "agents"} <= set(caps[0])
    assert all(set(c["agents"]) <= {"main", "scribe"} for c in caps)
    shared = next(c for c in caps if c["name"] == "ask_agent")
    assert shared["agents"] == ["main", "scribe"]
    assert [len(c["agents"]) > 1 for c in caps] == sorted(len(c["agents"]) > 1 for c in caps)


def test_jobs_list_schedules_before_and_after_a_run(monkeypatch, tmp_path):
    from ash_industry.core.scheduler.task import ScheduledTask

    assembly, scheduler = agenda_assembly(monkeypatch, tmp_path)
    ping = ScheduledTask(name="ping", schedule="0 22 * * *", prompt="물 마시기", kind="reminder")
    scheduler.ensure_task(ping)

    with web_client(assembly) as client:
        before = client.get("/api/jobs").json()
        client.portal.call(scheduler._run_and_deliver, ping)
        after = client.get("/api/jobs").json()

    first = {j["job_id"]: j for j in before["jobs"]}
    assert first["schedule:ping"]["runs"] == 0 and first["schedule:ping"]["next_run"]
    assert first["schedule:off"]["enabled"] is False and first["schedule:off"]["next_run"] is None
    ran = {j["job_id"]: j for j in after["jobs"]}["schedule:ping"]
    assert (ran["runs"], ran["running"], ran["last_ok"]) == (1, False, True)
    assert before["daemon"]["enabled"] is False


def test_job_runs_continue_across_a_restart(monkeypatch, tmp_path):
    from ash_industry.core.scheduler.task import ScheduledTask

    assembly, scheduler = agenda_assembly(monkeypatch, tmp_path)
    ping = ScheduledTask(name="ping", schedule="0 22 * * *", prompt="물 마시기", kind="reminder")
    scheduler.ensure_task(ping)
    with web_client(assembly) as client:
        client.portal.call(scheduler._run_and_deliver, ping)

    with web_client(assembly) as client:
        restored = {j["job_id"]: j for j in client.get("/api/jobs").json()["jobs"]}["schedule:ping"]
        client.portal.call(scheduler._run_and_deliver, ping)
        again = {j["job_id"]: j for j in client.get("/api/jobs").json()["jobs"]}["schedule:ping"]

    assert (restored["runs"], restored["running"], restored["last_ok"]) == (1, False, True)
    assert again["runs"] == 2


def test_layout_put_then_get_survives_restart_and_rejects_bad_body(monkeypatch, tmp_path):
    env = {"WORKFLOW__LAYOUT_PATH": str(tmp_path / "layout.json")}
    body = {"nodes": {"agent:main": {"x": 480.0, "y": 210.0}, "leaf:main:bash": {"x": 370.5, "y": 180.0}}}

    with web_client(web_assembly(monkeypatch, tmp_path, **env)) as client:
        empty = client.get("/api/workflow/layout").json()
        first = client.put("/api/workflow/layout", json=body)
        again = client.put("/api/workflow/layout", json=body)
        bad = client.put("/api/workflow/layout", json={"nodes": {"agent:main": {"x": 1e9, "y": 0}}})

    assert empty == {"nodes": {}}
    assert first.status_code == again.status_code == 200 and first.json() == again.json() == body
    assert bad.status_code == 422

    with web_client(web_assembly(monkeypatch, tmp_path, **env)) as client:
        restored = client.get("/api/workflow/layout").json()
        reset = client.put("/api/workflow/layout", json={"nodes": {}}).json()

    assert restored == body
    assert reset == {"nodes": {}}
