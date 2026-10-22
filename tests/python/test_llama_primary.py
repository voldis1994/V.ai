import asyncio
from pathlib import Path

from mainbrain.contracts.schemas import ModelRole
from mainbrain.core.config import Settings
from mainbrain.models.router import ModelRouter


def test_ollama_disabled_by_default(tmp_path: Path):
    settings = Settings(data_dir=tmp_path / "data", api_token="t")
    assert settings.ollama_enabled is False
    assert settings.primary_provider == "llama.cpp"


def test_error_message_points_to_llama_server(tmp_path: Path):
    settings = Settings(data_dir=tmp_path / "data", api_token="t", ollama_enabled=False)
    settings.ensure_dirs()
    router = ModelRouter(settings)
    result = asyncio.run(router.complete(role=ModelRole.REASONING, prompt="tests"))
    assert result["ok"] is False
    assert "llama-server" in result["error"]
    assert "llama.cpp" in result["error"]
