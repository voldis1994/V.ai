from pathlib import Path

from fastapi.testclient import TestClient

from mainbrain.api.app import create_app
from mainbrain.brain.chat import ChatService, _is_junk, wants_execution
from mainbrain.brain.intent import Intent, classify_intent
from mainbrain.core.config import Settings


def test_wants_execution_heuristics():
    assert wants_execution("Sveiki!") is False
    assert wants_execution("Kas ir Python?") is False
    assert wants_execution("Izveido Python failu hello.py") is True
    assert wants_execution("uztaisi programmu kalkulators") is True
    assert wants_execution("Izpildi: atver notepad") is True
    assert wants_execution("labdien", force_execute=True) is True
    assert wants_execution("Izveido kodu", force_execute=False) is False


def test_intent_search_learn_explain_build():
    assert classify_intent("sveiks") == Intent.GREET
    assert classify_intent("cik ir 2+2") == Intent.MATH

    # Lietotāja sūdzība: sameklē / iemācies / izskaidro
    assert classify_intent("izskaidro kas ir Python") == Intent.EXPLAIN
    assert classify_intent("Kas ir Python?") == Intent.EXPLAIN
    assert classify_intent("iemācies kā uztaisīt vienkāršu HTTP serveri") == Intent.LEARN
    # «sameklē kā strādā» = skaidrojuma intents (noderīgāks nekā tukša meklēšana)
    assert classify_intent("sameklē kā strādā regex") == Intent.EXPLAIN
    assert classify_intent("sameklē informāciju par Python list") == Intent.SEARCH
    assert classify_intent("sameklē dokumentāciju par FastAPI") == Intent.SEARCH

    # Personu meklēšana — bez halucinācijām
    assert classify_intent(
        "vai vari atrast informāciju par edgars gaidulis ?"
    ) == Intent.PERSON
    assert classify_intent("persona Edgars Gaidulis") == Intent.PERSON
    assert classify_intent("Edgars Gaidulis") == Intent.PERSON

    # Programmas — BUILD
    assert classify_intent("uztaisi Python failu hello.py") == Intent.BUILD
    assert classify_intent("sameklē un uztaisi kalkulatoru Python") == Intent.BUILD
    assert classify_intent("atver notepad") == Intent.OPEN
    assert classify_intent("atver pārlūku") == Intent.OPEN


def test_is_junk_detects_gaidis_loop():
    junk = (
        "Ja gaidis, tad varu atrast informāciju par gaidiju. "
        "Tā ir jābūt jautājumu, kādā arī gaidis."
    )
    assert _is_junk(junk)
    assert not _is_junk("Python ir programmēšanas valoda.")


def test_local_greet_without_llm():
    import asyncio

    from mainbrain.contracts.schemas import ChatRequest

    svc = ChatService(models=None, brain=None)  # type: ignore[arg-type]

    async def run():
        r1 = await svc.chat(ChatRequest(message="sveiks", session_id="x"))
        assert "Sveiki" in r1.reply
        assert "Ollama" in r1.reply or "llama" in r1.reply.lower()

    asyncio.run(run())


def test_meta_ollama_and_learning_without_llm():
    import asyncio

    from mainbrain.contracts.schemas import ChatRequest

    svc = ChatService(models=None, brain=None)  # type: ignore[arg-type]

    async def run():
        r1 = await svc.chat(ChatRequest(message="Vai tu pats mācies?", session_id="meta1"))
        assert "māc" in r1.reply.lower()
        assert "ollama" in r1.reply.lower() or "GGUF" in r1.reply or "zināšanu" in r1.reply.lower()

        r2 = await svc.chat(ChatRequest(message="Vai tiek kustināts Ollama?", session_id="meta2"))
        assert "ollama" in r2.reply.lower()
        low = r2.reply.lower()
        assert "nav" in low or "izslēgt" in low or "neizmanto" in low

    asyncio.run(run())


def test_auto_remember_indexes_knowledge(tmp_path: Path):
    from mainbrain.learning.engine import LearningEngine
    from mainbrain.memory.store import MemoryStore

    class _Brain:
        def __init__(self) -> None:
            self.store = MemoryStore(tmp_path / "mem.db")
            self.learning = LearningEngine(self.store)

    brain = _Brain()
    svc = ChatService(models=None, brain=brain)  # type: ignore[arg-type]
    ok = svc._remember(
        "Python",
        "Python ir programmēšanas valoda ar vienkāršu sintaksi.",
        kind="chat",
    )
    assert ok is True
    hits = brain.store.search_knowledge("Python")
    assert hits
    assert "programmēšanas" in hits[0]["content"]


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
        resp = client.post("/chat", json={"message": "Sveiki", "session_id": "t1"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["mode"] == "chat"
        assert "Sveiki" in body["reply"]

        resp2 = client.post(
            "/chat",
            json={
                "message": "persona Edgars Gaidulis",
                "session_id": "t1",
            },
        )
        assert resp2.status_code == 200
        reply = resp2.json()["reply"].lower()
        assert "gaidis" not in reply


def test_chat_create_hello_world_no_500(tmp_path: Path):
    """Ekrānšāviņa kļūda: VerificationReport.summary → nedrīkst mest 500."""
    project = tmp_path / "proj"
    project.mkdir()
    settings = Settings(
        data_dir=tmp_path / "data",
        api_token="test-token",
        workspace_root=tmp_path,
    )
    settings.ensure_dirs()
    app = create_app(settings)
    with TestClient(app) as client:
        client.headers.update({"Authorization": "Bearer test-token"})
        resp = client.post(
            "/chat",
            json={
                "message": "izveido python kodu hello world",
                "session_id": "hw",
                "workspace_path": str(project),
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["mode"] == "execute"
        assert "summary" not in (body.get("reply") or "").lower() or "VerificationReport" not in (
            body.get("reply") or ""
        )
        assert "VerificationReport" not in (body.get("reply") or "")
        assert "no attribute" not in (body.get("reply") or "")
        # Jābūt hello.py
        assert (project / "hello.py").exists()
        assert "Hello" in (project / "hello.py").read_text(encoding="utf-8")
