from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

from mainbrain.contracts.schemas import ToolRequest


def duckduckgo_url(query: str) -> str:
    return f"https://duckduckgo.com/?q={quote_plus(query.strip())}"


def google_url(query: str) -> str:
    return f"https://www.google.com/search?q={quote_plus(query.strip())}"


def resolve_app(name: str) -> tuple[str, list[str]] | None:
    """Atgriež (program, args) Windows/Linux tipiskām programmām."""
    n = (name or "").lower().strip()
    mapping = {
        "notepad": ("notepad.exe", []),
        "calc": ("calc.exe", []),
        "calculator": ("calc.exe", []),
        "explorer": ("explorer.exe", []),
        "cmd": ("cmd.exe", []),
        "powershell": ("powershell.exe", []),
        "code": ("code", []),
        "vscode": ("code", []),
        "chrome": ("chrome.exe", []),
        "edge": ("msedge.exe", []),
        "firefox": ("firefox.exe", []),
        "paint": ("mspaint.exe", []),
        "wordpad": ("wordpad.exe", []),
    }
    if n in mapping:
        return mapping[n]
    if n.endswith(".exe"):
        return (n, [])
    return None


class PhysicalActor:
    """Fiziskas darbības: atver pārlūku, programmas, failus — nevis tikai runā."""

    def __init__(self, tools: Any) -> None:
        self.tools = tools

    def _exec(self, tool: str, arguments: dict[str, Any]) -> Any:
        return self.tools.execute(ToolRequest(tool=tool, arguments=arguments, agent_id="PhysicalActor"))

    def open_url(self, url: str) -> dict[str, Any]:
        """Atver URL iegultajā WebView2 UN sistēmas pārlūkā (Chrome/Edge/start)."""
        results: dict[str, Any] = {"url": url, "webview": None, "system_browser": None}
        # 1) Iegultais pārlūks (ja Desktop tilts dzīvs)
        try:
            nav = self._exec("browser.navigate", {"url": url})
            results["webview"] = {
                "ok": nav.ok,
                "output": nav.output,
                "error": nav.error,
            }
        except Exception as exc:  # noqa: BLE001
            results["webview"] = {"ok": False, "error": str(exc)}

        # 2) Sistēmas pārlūks — vairāki mēģinājumi, lai lietotājs NOTEIKTI REDZ logu
        launched = False
        last_err = ""
        if sys.platform.startswith("win"):
            for cmd in (
                ["cmd", "/c", "start", "", url],
                ["cmd", "/c", "start", "msedge", url],
                ["cmd", "/c", "start", "chrome", url],
            ):
                try:
                    subprocess.Popen(cmd, shell=False)  # noqa: S603
                    launched = True
                    results["system_browser"] = {"ok": True, "performed": True, "via": cmd[0:3]}
                    break
                except Exception as exc:  # noqa: BLE001
                    last_err = str(exc)
            if not launched:
                try:
                    os.startfile(url)  # type: ignore[attr-defined]
                    launched = True
                    results["system_browser"] = {"ok": True, "performed": True, "via": "startfile"}
                except Exception as exc:  # noqa: BLE001
                    last_err = str(exc)
        else:
            try:
                opener = "open" if sys.platform == "darwin" else "xdg-open"
                subprocess.Popen([opener, url])  # noqa: S603
                launched = True
                results["system_browser"] = {"ok": True, "performed": True, "via": opener}
            except Exception as exc:  # noqa: BLE001
                last_err = str(exc)

        if not launched:
            shell = self._exec(
                "shell.run",
                {
                    "command": f'start "" "{url}"' if sys.platform.startswith("win") else f'xdg-open "{url}"',
                    "auto_safe": True,
                },
            )
            results["system_browser"] = {
                "ok": shell.ok,
                "output": shell.output,
                "error": last_err or shell.error,
            }
        return results

    def open_path(self, path: str) -> dict[str, Any]:
        p = Path(path)
        results: dict[str, Any] = {"path": str(p)}
        try:
            if sys.platform.startswith("win"):
                os.startfile(str(p))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(p)])  # noqa: S603
            else:
                subprocess.Popen(["xdg-open", str(p)])  # noqa: S603
            results["ok"] = True
            results["performed"] = True
        except Exception as exc:  # noqa: BLE001
            shell = self._exec(
                "shell.run",
                {
                    "command": f'explorer /select,"{p}"' if sys.platform.startswith("win") else f'xdg-open "{p}"',
                },
            )
            results["ok"] = shell.ok
            results["error"] = str(exc)
            results["shell"] = shell.output
        return results

    def launch_app(self, app: str, args: list[str] | None = None) -> dict[str, Any]:
        resolved = resolve_app(app)
        if resolved:
            program, base_args = resolved
            all_args = list(base_args) + list(args or [])
        else:
            program, all_args = app, list(args or [])

        # Windows: start via shell is more reliable for PATH apps
        if sys.platform.startswith("win"):
            arg_str = " ".join(f'"{a}"' if " " in a else a for a in all_args)
            cmd = f'start "" "{program}" {arg_str}'.strip()
            shell = self._exec("shell.run", {"command": cmd})
            return {
                "ok": shell.ok,
                "program": program,
                "args": all_args,
                "output": shell.output,
                "error": shell.error,
                "performed": shell.ok,
            }

        started = self._exec("process.start", {"program": program, "args": all_args})
        return {
            "ok": started.ok,
            "program": program,
            "args": all_args,
            "output": started.output,
            "error": started.error,
            "performed": started.ok,
        }

    def search_and_open(self, query: str) -> dict[str, Any]:
        url = duckduckgo_url(query)
        opened = self.open_url(url)
        return {"query": query, "url": url, **opened}

    def create_and_open_text(self, path: Path, content: str, *, open_with: str | None = "notepad") -> dict[str, Any]:
        path.parent.mkdir(parents=True, exist_ok=True)
        write = self._exec("files.write", {"path": str(path), "content": content})
        opened = None
        if open_with:
            if open_with.lower() in {"notepad", "notepad.exe"} and sys.platform.startswith("win"):
                opened = self.launch_app("notepad", [str(path)])
            else:
                opened = self.open_path(str(path))
        return {
            "write_ok": write.ok,
            "path": str(path),
            "opened": opened,
            "write": write.output,
            "error": write.error,
        }

    def detect_open_app(self, message: str) -> str | None:
        m = re.search(
            r"(?i)\b(?:atver|atvērt|open|palaid|palaist|start)\s+(notepad|calc|calculator|explorer|chrome|edge|firefox|code|vscode|powershell|cmd|paint)\b",
            message,
        )
        return m.group(1) if m else None
