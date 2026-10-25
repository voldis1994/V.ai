from pathlib import Path

from fastapi.testclient import TestClient

from mainbrain.api.app import create_app
from mainbrain.brain.chat import (
    _is_junk,
    looks_like_person_lookup,
    wants_execution,
)
from mainbrain.brain.chat import ChatService
from mainbrain.core.config import Settings


def test_wants_execution_heuristics():
    assert wants_execution("Sveiki!") is False
    assert wants_execution("Kas ir Python?") is False
    assert wants_execution("Izveido Python failu hello.py") is True
    assert wants_execution("Izpildi: atver notepad") is True
    assert wants_execution("labdien", force_execute=True) is True
    assert wants_execution("Izveido kodu", force_execute=False) is False


def test_looks_like_person_lookup_catches_screenshot_queries():
    # Exact queries from the user's broken chat screenshot
    assert looks_like_person_lookup(
        "vai vari atrast informāciju par edgars gaidulis ?"
    )
    assert looks_like_person_lookup("persona Edgars Gaidulis")
    assert looks_like_person_lookup("Edgars Gaidulis")
    assert looks_like_person_lookup("Edgars Gaidulis?")
    assert looks_like_person_lookup("Kas ir Edgars Gaidulis?")
    assert looks_like_person_lookup("pastāsti man par Edgaru Gaiduli")
    assert looks_like_person_lookup("who is Elon Musk")
    # Not person lookups — single-concept / non-person
    assert not looks_like_person_lookup("sveiks")
    assert not looks_like_person_lookup("cik ir 2+2")
    assert not looks_like_person_lookup("Izveido Python failu")
    assert not looks_like_person_lookup("Kas ir Python?")
    assert not looks_like_person_lookup("how you today?")


def test_is_junk_detects_gaidis_loop():
    junk = (
        "Ja gaidis, tad varu atrast informāciju par gaidiju. "
        "Tā ir jābūt jautājumu, kādā arī gaidis."
    )
    assert _is_junk(junk)
    assert _is_junk(junk + " " + junk)
    assert not _is_junk("Sveiki! Kā varu palīdzēt?")


def test_local_replies_without_llm():
    svc = ChatService(models=None, brain=None)  # type: ignore[arg-type]
    assert "Sveiki" in (svc._local_reply("sveiks") or "")
    person = svc._local_reply("vai vari atrast informāciju par edgars gaidulis ?")
    assert person and "nav drošu lokālo datu" in person.lower()
    lang = svc._local_reply("cik valodas tu zini ?")
    assert lang and "latvie" in lang.lower()
    assert svc._local_reply("cik ir 2+2") == "2 + 2 = 4"
    assert svc._local_reply("how you today?") is None  # goes to LLM


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
        # Greeting is answered locally without llama-server
        resp = client.post("/chat", json={"message": "Sveiki", "session_id": "t1"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["mode"] == "chat"
        assert "Sveiki" in body["reply"]
        assert body["session_id"] == "t1"

        # Person lookup must never hallucinate
        resp2 = client.post(
            "/chat",
            json={
                "message": "vai vari atrast informāciju par edgars gaidulis ?",
                "session_id": "t1",
            },
        )
        assert resp2.status_code == 200
        reply = resp2.json()["reply"].lower()
        assert "gaidis" not in reply
        assert "nav" in reply or "nezinu" in reply or "datu" in reply
