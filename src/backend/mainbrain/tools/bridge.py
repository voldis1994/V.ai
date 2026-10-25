from __future__ import annotations

import json
import os
import sys
import time
from typing import Any

from mainbrain.core.ids import new_id


class DesktopToolBridge:
    """Klients uz Windows Named Pipe Tool Bridge.

    Linux/macOS: IsAvailable=False, izsaukumi atgriež godīgu unavailable.
    """

    def __init__(
        self,
        token: str | None = None,
        pipe_name: str = "MainBrainToolBridge",
        timeout_sec: float = 30.0,
    ) -> None:
        self.token = token or os.environ.get("MAINBRAIN_BRIDGE_TOKEN") or os.environ.get(
            "MAINBRAIN_API_TOKEN", ""
        )
        self.pipe_name = pipe_name
        self.timeout_sec = timeout_sec

    @property
    def is_available(self) -> bool:
        return sys.platform == "win32" and bool(self.token)

    def call(
        self,
        tool: str,
        arguments: dict[str, Any] | None = None,
        *,
        agent_id: str | None = None,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        if not self.is_available:
            return {
                "ok": False,
                "tool": tool,
                "result": {
                    "status": "unavailable",
                    "performed": False,
                    "message": "Desktop Tool Bridge pieejams tikai Windows ar autentificētu tokenu",
                },
            }
        if not self.token:
            return {
                "ok": False,
                "tool": tool,
                "error": "Trūkst tilta autentifikācijas tokena",
                "result": {"status": "unauthorized", "performed": False},
            }

        payload = {
            "token": self.token,
            "tool": tool,
            "arguments": arguments or {},
            "agent_id": agent_id,
            "correlation_id": correlation_id or new_id("corr_"),
        }
        try:
            return self._exchange(payload)
        except Exception as exc:  # noqa: BLE001
            return {
                "ok": False,
                "tool": tool,
                "error": str(exc),
                "result": {"status": "error", "performed": False, "message": str(exc)},
            }

    def _exchange(self, payload: dict[str, Any]) -> dict[str, Any]:
        # Windows named pipe caur pywin32 nav obligāts — izmantojam file API \\.\pipe\name
        pipe_path = rf"\\.\pipe\{self.pipe_name}"
        deadline = time.time() + self.timeout_sec
        last_error: Exception | None = None
        while time.time() < deadline:
            try:
                with open(pipe_path, "r+b", buffering=0) as pipe:
                    data = (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")
                    pipe.write(data)
                    # lasa līdz newline
                    buf = bytearray()
                    while True:
                        chunk = pipe.read(1)
                        if not chunk:
                            break
                        if chunk == b"\n":
                            break
                        buf.extend(chunk)
                        if len(buf) > 8_000_000:
                            raise RuntimeError("Tilta atbilde pārāk liela")
                    return json.loads(buf.decode("utf-8"))
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                time.sleep(0.1)
        raise RuntimeError(f"Neizdevās savienoties ar Desktop Tool Bridge: {last_error}")
