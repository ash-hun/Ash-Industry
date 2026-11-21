"""settings 기능: 조회는 비밀값을 가리고, 편집은 허용 목록만 저장하며 바로 반영한다. 재시작은 키가 있어야 한다."""

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from tests.fixtures.web_hud_helpers import web_assembly, web_client  # noqa: E402
from ash_industry.ui.web.process_restart import ProcessRestart  # noqa: E402
from ash_industry.ui.web.server import create_app  # noqa: E402
from ash_industry.ash_config import AshSettings  # noqa: E402

KEY = "k-restart-1"


@pytest.fixture
def settings_file(monkeypatch, tmp_path):
    path = tmp_path / "settings.yaml"
    monkeypatch.setenv("ASH_SETTINGS_FILE", str(path))
    return path


@pytest.fixture
def client(monkeypatch, tmp_path, settings_file):
    with web_client(web_assembly(monkeypatch, tmp_path, LLM__API_KEY="sk-hidden-42")) as c:
        yield c


def test_health_and_settings_view_mask_secrets(client):
    health = client.get("/api/health").json()
    assert health["ok"] is True and health["version"].count(".") == 2
    body = client.get("/api/settings").json()

    assert "sk-hidden-42" not in str(body)
    assert body["effective"]["llm"]["api_key"] == "***"
    assert body["pending"] == {}


def test_put_settings_applies_now_and_next_boot_reads_the_same(client, settings_file):
    payload = {"voice": {"wake_threshold": 0.77}, "proactive": {"daemon_trigger": "idle"}}

    first = client.put("/api/settings", json=payload).json()
    again = client.put("/api/settings", json=payload).json()

    assert first["changed"] is True and again["changed"] is False
    assert sorted(first["applied"]) == ["proactive.daemon_trigger", "voice.wake_threshold"]
    assert first["restart_required"] is False and first["pending"] == {}
    assert first["editable"]["voice"]["wake_threshold"] == 0.77 and again["applied"] == []
    rebooted = AshSettings()
    assert (rebooted.voice.wake_threshold, rebooted.proactive.daemon_trigger) == (0.77, "idle")


def test_put_settings_reports_restart_required_for_thought_enabled(client, settings_file):
    body = client.put("/api/settings", json={"thought": {"enabled": False}}).json()

    assert body["restart_required"] is True and body["restart_keys"] == ["thought.enabled"]
    assert body["pending"] == {"thought": {"enabled": False}}
    assert client.get("/api/settings").json()["editable"]["thought"]["enabled"] is True


def test_put_settings_rejects_field_outside_allowlist(client, settings_file):
    response = client.put("/api/settings", json={"llm": {"api_key": "x"}})

    assert response.status_code == 422
    assert not settings_file.exists()


@pytest.fixture
def exits():
    return []


@pytest.fixture
def keyed_client(monkeypatch, tmp_path, settings_file, exits):
    keys = f'{{"{KEY}": {{"name": "jh", "roles": ["admin"]}}}}'
    assembly = web_assembly(monkeypatch, tmp_path, SECURITY__API_KEYS=keys)
    restart = ProcessRestart(supervised=lambda: True, exit_=lambda: exits.append("exit"), delay_sec=0)
    with TestClient(create_app(assembly, initial_session_id="default", restart=restart)) as c:
        yield c


def test_restart_and_settings_need_the_access_key(keyed_client, exits):
    no_key = keyed_client.post("/api/restart")
    no_key_put = keyed_client.put("/api/settings", json={"voice": {"wake_threshold": 0.5}})

    assert (no_key.status_code, no_key_put.status_code) == (401, 401)
    assert exits == []


def test_restart_with_key_warns_open_huds_then_calls_exit(keyed_client, exits):
    with keyed_client.websocket_connect(f"/ws?session_id=hud1&token={KEY}") as ws:
        ws.receive_json()
        res = keyed_client.post("/api/restart", headers={"Authorization": f"Bearer {KEY}"})
        notice = ws.receive_json()

    assert res.status_code == 202 and res.json() == {"ok": True, "result": "restarting"}
    assert notice == {"type": "restarting"}
    assert exits == ["exit"]


def test_restart_outside_a_supervisor_is_refused(monkeypatch, tmp_path, settings_file):
    restart = ProcessRestart(supervised=lambda: False, exit_=lambda: pytest.fail("must not exit"))
    with TestClient(create_app(web_assembly(monkeypatch, tmp_path), restart=restart)) as c:
        res = c.post("/api/restart")

    assert res.status_code == 409 and res.json() == {"ok": False, "result": "no supervisor"}
