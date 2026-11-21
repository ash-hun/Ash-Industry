"""ion 기능: /ion 이 상태, 사고, 로그를 내고 답과 재기동을 받아 행동한다."""

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from tests.fixtures.ion_helpers import FakeBackend, FakeDocker, make_watch_service  # noqa: E402
from ash_industry.ion.ion_app import EventHub, build_ion_app  # noqa: E402
from ash_industry.ion.watch_service import sse_line  # noqa: E402


def _app(tmp_path, key: str | None):  # type: ignore[no-untyped-def]
    backend, docker = FakeBackend(), FakeDocker()
    backend.ok = False
    # 배경 루프는 한 시간에 한 번만 돌게 해 두고 tick 은 테스트가 직접 부른다
    svc, _ = make_watch_service(tmp_path, backend, docker, poll_sec=3600)
    return build_ion_app(svc, EventHub(), key), svc, docker


def test_backend_outage_shows_as_incident_and_restart_response_acts_once(tmp_path):
    app, svc, docker = _app(tmp_path, None)
    with TestClient(app) as client:
        for _ in range(3):
            client.portal.call(svc.tick)
        status = client.get("/ion/status").json()
        (incident,) = status["incidents"]
        assert status["backend_ok"] is False and incident["kind"] == "backend_down"

        first = client.post(f"/ion/incidents/{incident['id']}/respond", json={"action": "restart"})
        again = client.post(f"/ion/incidents/{incident['id']}/respond", json={"action": "restart"})
        assert first.status_code == 200 and first.json()["incident"]["action_result"] == "재기동함"
        assert again.json() == first.json() and docker.restarts == 1
        assert client.post("/ion/incidents/ghost/respond", json={"action": "restart"}).status_code == 404
        assert client.post(f"/ion/incidents/{incident['id']}/respond", json={"action": "nap"}).status_code == 400


def test_access_key_guards_every_route(tmp_path):
    app, _, _ = _app(tmp_path, "secret")
    with TestClient(app) as client:
        assert client.get("/ion/status").status_code == 401
        assert client.get("/ion/status", headers={"Authorization": "Bearer secret"}).status_code == 200
        assert client.get("/ion/status", params={"token": "secret"}).status_code == 200


async def test_event_hub_streams_hello_then_published_events():
    hub = EventHub()
    stream = hub.stream()
    assert await anext(stream) == sse_line({"type": "hello"})
    await hub.publish({"type": "incident", "id": "x"})
    assert await anext(stream) == sse_line({"type": "incident", "id": "x"})
    await stream.aclose()


async def test_incident_titles_use_the_agent_display_name_from_metrics(tmp_path):
    backend, docker = FakeBackend(), FakeDocker()
    backend.rows = [{"agent": "scribe", "name": "S.C.R.I.B.E.", "fail_streak": 3, "jobs": 1}]
    svc, _ = make_watch_service(tmp_path, backend, docker, poll_sec=3600)
    app = build_ion_app(svc, EventHub(), None)
    await svc.tick()
    with TestClient(app) as client:
        rows = client.get("/ion/incidents").json()["incidents"]
    assert [(r["target"], r["title"]) for r in rows] == [("scribe", "Ion: S.C.R.I.B.E. 의 작업이 계속 실패해요")]
