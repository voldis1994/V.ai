from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx

from mainbrain.contracts.schemas import ModelHealth, ModelRole
from mainbrain.core.config import Settings
from mainbrain.core.ids import utc_now


class ModelRouter:
    """Lokālo llama.cpp / Ollama adapteru maršrutētājs."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._role_models: dict[ModelRole, dict[str, Any]] = {}
        self.scan_models()

    def scan_models(self) -> list[dict[str, Any]]:
        models_dir = self.settings.resolved_models_dir
        models_dir.mkdir(parents=True, exist_ok=True)
        found: list[dict[str, Any]] = []
        for path in models_dir.glob("**/*"):
            if path.suffix.lower() in {".gguf", ".bin"}:
                found.append(
                    {
                        "path": str(path),
                        "name": path.name,
                        "size_mb": round(path.stat().st_size / (1024 * 1024), 1),
                    }
                )
        # lomu noklusējumi pēc failu nosaukumiem
        for item in found:
            name = item["name"].lower()
            if "embed" in name:
                self._role_models[ModelRole.EMBEDDING] = {"provider": "llama.cpp", **item}
            elif "vision" in name or "vl" in name:
                self._role_models[ModelRole.VISION] = {"provider": "llama.cpp", **item}
            elif "code" in name or "coder" in name:
                self._role_models[ModelRole.CODING] = {"provider": "llama.cpp", **item}
            else:
                self._role_models.setdefault(ModelRole.REASONING, {"provider": "llama.cpp", **item})
        return found

    async def health(self) -> list[ModelHealth]:
        results: list[ModelHealth] = []
        llama_ok, llama_detail = await self._probe_openai_compatible(self.settings.llama_base_url)
        ollama_ok, ollama_detail = await self._probe_ollama(self.settings.ollama_base_url)
        for role in (ModelRole.REASONING, ModelRole.CODING, ModelRole.VISION, ModelRole.EMBEDDING):
            mapped = self._role_models.get(role)
            available = bool(mapped) and (llama_ok or ollama_ok)
            provider = None
            base = None
            details = "Modelis nav konfigurēts"
            if mapped and llama_ok:
                provider = "llama.cpp"
                base = self.settings.llama_base_url
                details = f"GGUF: {mapped['name']}; {llama_detail}"
            elif mapped and ollama_ok:
                provider = "ollama"
                base = self.settings.ollama_base_url
                details = f"Fails: {mapped['name']}; {ollama_detail}"
            elif not mapped:
                details = "Nav atrasts GGUF fails šai lomai"
            else:
                details = f"Modelis atrasts ({mapped['name']}), bet lokālā inference nav pieejama"
            results.append(
                ModelHealth(
                    role=role,
                    available=available,
                    provider=provider,
                    model_name=mapped["name"] if mapped else None,
                    base_url=base,
                    details=details,
                    checked_at=utc_now(),
                )
            )
        return results

    async def complete(
        self,
        *,
        role: ModelRole,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> dict[str, Any]:
        if role == ModelRole.NONE:
            return {"ok": True, "text": "", "provider": "none"}
        health = {h.role: h for h in await self.health()}
        status = health.get(role)
        if not status or not status.available:
            return {
                "ok": False,
                "text": "",
                "error": status.details if status else "Modeļa loma nav pieejama",
                "provider": None,
            }
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        if status.provider == "llama.cpp":
            return await self._chat_openai(self.settings.llama_base_url, messages, temperature, max_tokens)
        return await self._chat_ollama(self.settings.ollama_base_url, status.model_name or "local", messages)

    async def _probe_openai_compatible(self, base_url: str) -> tuple[bool, str]:
        url = base_url.rstrip("/") + "/models"
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.get(url)
                if resp.status_code < 500:
                    return True, f"llama-server atbild ({resp.status_code})"
                return False, f"llama-server kļūda {resp.status_code}"
        except Exception as exc:  # noqa: BLE001
            return False, f"llama-server nav sasniedzams: {exc}"

    async def _probe_ollama(self, base_url: str) -> tuple[bool, str]:
        url = base_url.rstrip("/") + "/api/tags"
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    return True, "Ollama pieejams"
                return False, f"Ollama statuss {resp.status_code}"
        except Exception as exc:  # noqa: BLE001
            return False, f"Ollama nav sasniedzams: {exc}"

    async def _chat_openai(
        self,
        base_url: str,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
    ) -> dict[str, Any]:
        url = base_url.rstrip("/") + "/chat/completions"
        payload = {
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            text = data["choices"][0]["message"]["content"]
            return {"ok": True, "text": text, "provider": "llama.cpp", "raw": data}

    async def _chat_ollama(
        self,
        base_url: str,
        model: str,
        messages: list[dict[str, str]],
    ) -> dict[str, Any]:
        url = base_url.rstrip("/") + "/api/chat"
        payload = {"model": model, "messages": messages, "stream": False}
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            text = data.get("message", {}).get("content", "")
            return {"ok": True, "text": text, "provider": "ollama", "raw": data}

    def assign_model(self, role: ModelRole, path: str) -> None:
        p = Path(path)
        self._role_models[role] = {
            "provider": "llama.cpp",
            "path": str(p),
            "name": p.name,
            "size_mb": round(p.stat().st_size / (1024 * 1024), 1) if p.exists() else 0,
        }

    def export_config(self) -> dict[str, Any]:
        return {
            role.value: info
            for role, info in self._role_models.items()
        }
