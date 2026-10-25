from pathlib import Path

from fastapi.testclient import TestClient

from mainbrain.api.app import create_app
from mainbrain.brain.chat import wants_execution
from mainbrain.core.config import Settings


def test_wants_execution_heuristics():
    assert wants_execution("Sveiki!") is False
    assert wants_execution("Kas ir Python?") is False
    assert wants_execution("Izveido Python failu hello.py") is True
    assert wants_execution("Izpildi: atver notepad") is True
    assert wants_execution("labdien", force_execute=True) is True
    assert wants_execution("Izveido kodu", force_execute=False) is False


def test_chat_endpoint(tmp_path: Path):
    settings = Settings(
        data_dir=tmp_path / "data",
        api_token="test-token",
        workspace_root=tmp_path,
    )
    settings.ensure_dirs()
    app = create_app(settings)
    with TestClient(app) as client:
        client.headers.update({"Authorization": "Bearer test-token"})
        resp = client.post("/chat", json={"message": "Sveiki, kas tu esi?", "session_id": "t1"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["mode"] == "chat"
        assert body["reply"]
        assert body["session_id"] == "t1"
