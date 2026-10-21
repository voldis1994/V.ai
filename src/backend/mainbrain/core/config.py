from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_data_dir() -> Path:
    local = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_DATA_HOME")
    if local:
        return Path(local) / "MainBrainOS"
    return Path.home() / ".local" / "share" / "MainBrainOS"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MAINBRAIN_", env_file=".env", extra="ignore")

    app_name: str = "Main Brain OS"
    api_host: str = "127.0.0.1"
    api_port: int = 8765
    api_token: str = Field(default_factory=lambda: os.environ.get("MAINBRAIN_API_TOKEN", ""))
    data_dir: Path = Field(default_factory=_default_data_dir)
    workspace_root: Path | None = None
    llama_base_url: str = "http://127.0.0.1:8080/v1"
    ollama_base_url: str = "http://127.0.0.1:11434"
    models_dir: Path | None = None
    max_parallel_agents: int = 4
    max_parallel_llm: int = 2
    max_browser_sessions: int = 2
    max_retries: int = 2
    task_timeout_sec: int = 600
    offline_mode: bool = False
    language: str = "lv"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "mainbrain.db"

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def projects_dir(self) -> Path:
        return self.data_dir / "projects"

    @property
    def checkpoints_dir(self) -> Path:
        return self.data_dir / "checkpoints"

    @property
    def resolved_models_dir(self) -> Path:
        if self.models_dir:
            return self.models_dir
        return self.data_dir / "models"

    def ensure_dirs(self) -> None:
        for path in (
            self.data_dir,
            self.logs_dir,
            self.projects_dir,
            self.checkpoints_dir,
            self.resolved_models_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings
