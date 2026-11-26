"""auto_approve 기능: 에이전트별 auto mode 를 API 로 켜고 끄면 파일과 앱의 저장소에 바로 남는다."""

import pytest

pytest.importorskip("fastapi")

from tests.fixtures.web_hud_helpers import web_assembly, web_client  # noqa: E402


@pytest.fixture
def assembly(monkeypatch, tmp_path):
    return web_assembly(monkeypatch, tmp_path, SECURITY__AUTO_APPROVE_PATH=str(tmp_path / "auto.yaml"))


def test_toggle_is_saved_and_open_session_follows_it(assembly, tmp_path):
    with web_client(assembly) as client:
        with client.websocket_connect("/ws?session_id=auto") as ws:
            ws.receive_json()
            before = client.get("/api/auto-approve").json()["agents"]
            on = client.put("/api/auto-approve/main", json={"enabled": True}).json()["agents"]
            again = client.put("/api/auto-approve/main", json={"enabled": True}).json()["agents"]
            unknown = client.put("/api/auto-approve/nobody", json={"enabled": True})
            bad = client.put("/api/auto-approve/main", json={"enabled": "yes"})

    assert next(a for a in before if a["id"] == "main")["enabled"] is False
    assert on == again and next(a for a in on if a["id"] == "main")["enabled"] is True
    assert unknown.status_code == 404 and bad.status_code == 422
    assert "main: true" in (tmp_path / "auto.yaml").read_text()
    assert assembly.ctx.auto_approve.enabled("main")
