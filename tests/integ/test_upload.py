"""upload 기능: 채팅 첨부를 uploads/ 에 한 번만 저장하고, 보낸 메시지에 경로 안내와 그림이 실려 모델에 간다."""

import pytest

pytest.importorskip("fastapi")

from tests.fixtures.web_hud_helpers import scripted_env, use_provider, web_assembly, web_client  # noqa: E402
from ash_industry.model_layer.model_types import ImageContent, UserMessage  # noqa: E402
from tests.fixtures.agent_loop_helpers import ScriptedProvider, text_turn  # noqa: E402

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


@pytest.fixture
def provider():
    yield from use_provider(ScriptedProvider([text_turn("받았어요")]))


@pytest.fixture
def client(monkeypatch, tmp_path, provider):
    env = {**scripted_env(provider.provider_name, tmp_path), "DOCS__DIR": str(tmp_path / "docs")}
    with web_client(web_assembly(monkeypatch, tmp_path, **env)) as c:
        yield c


def test_upload_saves_once_and_message_carries_path_and_image(client, provider, tmp_path):
    first = client.post("/api/uploads", files={"file": ("../스크린 샷.png", PNG, "image/png")}).json()
    again = client.post("/api/uploads", files={"file": ("../스크린 샷.png", PNG, "image/png")}).json()
    sheet = client.post("/api/uploads", files={"file": ("명단.xlsx", b"PK\x03\x04", "")}).json()

    assert first == again and first["path"] == f"uploads/{first['id']}-스크린_샷.png" and first["kind"] == "image"
    assert len(list((tmp_path / "docs" / "uploads").iterdir())) == 2 and sheet["kind"] == "document"

    with client.websocket_connect("/ws?session_id=up") as ws:
        ws.receive_json()
        ws.send_json({"type": "user_message", "text": "", "attachments": [first["id"], sheet["id"], "ffffffffffff"]})
        while ws.receive_json()["type"] != "agent_end":
            pass
        history = client.get("/api/sessions/up/messages").json()["messages"]

    sent = [m for m in provider.calls[0].messages if isinstance(m, UserMessage)][-1]
    assert isinstance(sent.content, list) and any(isinstance(p, ImageContent) for p in sent.content)
    user_text = history[0]["text"]
    assert f"[첨부] 스크린_샷.png | 경로 {first['path']}" in user_text and "명단.xlsx" in user_text
    assert "ffffffffffff" not in user_text


def test_upload_rejects_oversized_file(client, monkeypatch):
    monkeypatch.setattr("ash_industry.ui.web.router.upload_router.MAX_BYTES", 10)

    res = client.post("/api/uploads", files={"file": ("big.bin", b"x" * 11, "application/octet-stream")})

    assert res.status_code == 413
