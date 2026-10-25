from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx

from mainbrain.contracts.schemas import ModelHealth, ModelRole
from mainbrain.core.config import Settings
from mainbrain.core.ids import utc_now


class ModelRouter:
    """Lokālās inference maršrutētājs.

    Primāri: llama.cpp `llama-server` (OpenAI saderīgs localhost).
    Ollama: tikai ja MAINBRAIN_OLLAMA_ENABLED=true — rezerves adapters.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._role_models: dict[ModelRole, dict[str, Any]] = {}
        self._health_cache: list[ModelHealth] | None = None
        self._health_cache_at: float = 0.0
        self._llama_ok_cache: bool | None = None
        self._llama_ok_at: float = 0.0
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
        # Lomu noklusējumi — preferē LIELĀKO GGUF lomā (7B > 3B > 1.5B)
        found_sorted = sorted(found, key=lambda x: x.get("size_mb") or 0, reverse=True)
        for item in found_sorted:
            name = item["name"].lower()
            mapped = {"provider": "llama.cpp", **item}
            if "embed" in name:
                self._role_models.setdefault(ModelRole.EMBEDDING, mapped)
            elif "vision" in name or "vl" in name or "moondream" in name:
                self._role_models.setdefault(ModelRole.VISION, mapped)
            elif "code" in name or "coder" in name:
                self._role_models.setdefault(ModelRole.CODING, mapped)
            else:
                self._role_models.setdefault(ModelRole.REASONING, mapped)
        return found

    async def health(self, *, force: bool = False) -> list[ModelHealth]:
        import time

        if not force and self._health_cache and (time.time() - self._health_cache_at) < 60:
            return self._health_cache
        results: list[ModelHealth] = []
        llama_ok, llama_detail = await self._probe_openai_compatible(self.settings.llama_base_url)
        # Ollama VIENMĒR OFF — netiek probe'ota / saukta / gaidīta
        llama_infer = (llama_ok, "server OK (bez inference probe)")
        if llama_ok and force:
            llama_infer = await self._probe_inference_openai(self.settings.llama_base_url)
        for role in (ModelRole.REASONING, ModelRole.CODING, ModelRole.VISION, ModelRole.EMBEDDING):
            mapped = self._role_models.get(role)
            provider = None
            base = None
            details = "Modelis nav konfigurēts"
            available = False
            # Tikai llama.cpp — Ollama nav rezerve
            if mapped and llama_ok:
                provider = "llama.cpp"
                base = self.settings.llama_base_url
                available = llama_infer[0]
                details = f"GGUF: {mapped['name']}; {llama_detail}; inference={llama_infer[1]}"
            elif llama_ok and not mapped and role == ModelRole.REASONING:
                provider = "llama.cpp"
                base = self.settings.llama_base_url
                available = llama_infer[0]
                details = f"llama-server aktīvs; inference={llama_infer[1]}"
            elif not mapped:
                details = (
                    "Nav GGUF šai lomai. Ievietojiet modeli models mapē un palaidiet llama-server. "
                    f"({llama_detail})"
                )
            else:
                details = (
                    f"GGUF atrasts ({mapped['name']}), bet llama-server nav sasniedzams uz "
                    f"{self.settings.llama_base_url}. {llama_detail}"
                )
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
        self._health_cache = results
        self._health_cache_at = time.time()
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
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return await self.complete_messages(
            role=role,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    async def complete_messages(
        self,
        *,
        role: ModelRole,
        messages: list[dict[str, str]],
        temperature: float = 0.2,
        max_tokens: int = 1024,
        frequency_penalty: float = 0.0,
        presence_penalty: float = 0.0,
        repeat_penalty: float = 1.0,
        stop: list[str] | None = None,
        timeout_sec: float = 75.0,
    ) -> dict[str, Any]:
        """OpenAI-style multi-turn chat — TIKAI llama.cpp. Ollama NETIEK gaidīta."""
        if role == ModelRole.NONE:
            return {"ok": True, "text": "", "provider": "none"}
        # Bez katras reizes probe — taisni uz llama-server (Ollama = OFF)
        import time

        now = time.time()
        if self._llama_ok_cache is True and (now - self._llama_ok_at) < 45:
            llama_ok, llama_detail = True, "cache"
        else:
            llama_ok, llama_detail = await self._probe_openai_compatible(self.settings.llama_base_url)
            self._llama_ok_cache = llama_ok
            self._llama_ok_at = now

        if llama_ok:
            return await self._chat_openai(
                self.settings.llama_base_url,
                messages,
                temperature,
                max_tokens,
                frequency_penalty=frequency_penalty,
                presence_penalty=presence_penalty,
                repeat_penalty=repeat_penalty,
                stop=stop,
                timeout_sec=timeout_sec,
            )
        # Ollama NEVIS rezerve pēc noklusējuma — lietotājs negrib gaidīt Ollama
        return {
            "ok": False,
            "text": "",
            "error": (
                "llama.cpp llama-server nav pieejams (Ollama netiek izmantota un netiek gaidīta). "
                "Pārstartē MainBrain / FIX_BACKEND.bat. "
                f"Detaļas: {llama_detail}"
            ),
            "provider": None,
        }

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

    async def _probe_inference_openai(self, base_url: str) -> tuple[bool, str]:
        try:
            result = await self._chat_openai(
                base_url,
                [{"role": "user", "content": "OK"}],
                temperature=0.0,
                max_tokens=4,
                timeout_sec=15.0,
            )
            if result.get("ok") and str(result.get("text") or "").strip():
                return True, "īsa inference OK"
            return False, str(result.get("error") or "tukša atbilde")
        except Exception as exc:  # noqa: BLE001
            return False, f"inference kļūda: {exc}"

    async def _probe_inference_ollama(self, base_url: str, model: str) -> tuple[bool, str]:
        try:
            result = await self._chat_ollama(
                base_url,
                model,
                [{"role": "user", "content": "OK"}],
                timeout_sec=15.0,
            )
            if result.get("ok") and str(result.get("text") or "").strip():
                return True, "īsa inference OK"
            return False, str(result.get("error") or "tukša atbilde")
        except Exception as exc:  # noqa: BLE001
            return False, f"inference kļūda: {exc}"

    async def _chat_openai(
        self,
        base_url: str,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
        *,
        frequency_penalty: float = 0.0,
        presence_penalty: float = 0.0,
        repeat_penalty: float = 1.0,
        stop: list[str] | None = None,
        timeout_sec: float = 75.0,
    ) -> dict[str, Any]:
        url = base_url.rstrip("/") + "/chat/completions"
        payload: dict[str, Any] = {
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if frequency_penalty:
            payload["frequency_penalty"] = frequency_penalty
        if presence_penalty:
            payload["presence_penalty"] = presence_penalty
        if repeat_penalty and repeat_penalty != 1.0:
            payload["repeat_penalty"] = repeat_penalty
        if stop:
            payload["stop"] = stop
        try:
            async with httpx.AsyncClient(timeout=timeout_sec) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()
                text = data["choices"][0]["message"]["content"]
                return {"ok": True, "text": text, "provider": "llama.cpp", "raw": data}
        except httpx.TimeoutException:
            return {
                "ok": False,
                "text": "",
                "error": (
                    f"Modelis neatbildēja {int(timeout_sec)}s laikā (CPU inference pārāk lēna). "
                    "Aizver citas programmas vai UPGRADE_MODEL.bat uz ātrāku Q4 profilu."
                ),
                "provider": "llama.cpp",
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "ok": False,
                "text": "",
                "error": f"llama-server kļūda: {exc}",
                "provider": "llama.cpp",
            }

    async def _chat_ollama(
        self,
        base_url: str,
        model: str,
        messages: list[dict[str, str]],
        *,
        timeout_sec: float = 75.0,
    ) -> dict[str, Any]:
        url = base_url.rstrip("/") + "/api/chat"
        payload = {"model": model, "messages": messages, "stream": False}
        try:
            async with httpx.AsyncClient(timeout=timeout_sec) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()
                text = data.get("message", {}).get("content", "")
                return {"ok": True, "text": text, "provider": "ollama", "raw": data}
        except httpx.TimeoutException:
            return {
                "ok": False,
                "text": "",
                "error": f"Ollama timeout {int(timeout_sec)}s",
                "provider": "ollama",
            }
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "text": "", "error": str(exc), "provider": "ollama"}

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
