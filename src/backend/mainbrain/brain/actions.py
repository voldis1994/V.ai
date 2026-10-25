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
        "word": ("winword.exe", []),
        "excel": ("excel.exe", []),
        "powerpoint": ("powerpnt.exe", []),
        "spotify": ("spotify.exe", []),
        "discord": ("discord.exe", []),
        "telegram": ("telegram.exe", []),
        "steam": ("steam.exe", []),
        "vlc": ("vlc.exe", []),
        "notepad++": ("notepad++.exe", []),
        "npp": ("notepad++.exe", []),
        "python": ("python.exe", []),
        "terminal": ("wt.exe", []),
        "windows terminal": ("wt.exe", []),
    }
    if n in mapping:
        return mapping[n]
    if n.endswith(".exe"):
        return (n, [])
    # where.exe / PATH — atrast instalēto programmu pēc vārda
    found = _which_program(n if n.endswith(".exe") else n)
    if found:
        return (found, [])
    return None


def _which_program(name: str) -> str | None:
    """Mēģina atrast instalētu exe (where / shutil.which)."""
    import shutil

    candidates = [name, f"{name}.exe"] if not name.endswith(".exe") else [name]
    for c in candidates:
        hit = shutil.which(c)
        if hit:
            return hit
    if sys.platform.startswith("win"):
        for c in candidates:
            try:
                out = subprocess.run(
                    ["where", c],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )
                line = (out.stdout or "").strip().splitlines()
                if line:
                    return line[0].strip()
            except Exception:  # noqa: BLE001
                continue
    return None


class PhysicalActor:
    """Fiziskas darbības: atver pārlūku, programmas, failus — nevis tikai runā."""

    def __init__(self, tools: Any) -> None:
        self.tools = tools

    def _exec(self, tool: str, arguments: dict[str, Any]) -> Any:
        return self.tools.execute(ToolRequest(tool=tool, arguments=arguments, agent_id="PhysicalActor"))

    def open_url(self, url: str, *, via_bridge: bool = False) -> dict[str, Any]:
        """Atver URL. Noklusējumā BEZ bridge (izvairās no deadlock ar Desktop /chat)."""
        results: dict[str, Any] = {"url": url, "webview": None, "system_browser": None}
        # Bridge browser.navigate — TIKAI ja īpaši lūgts (var bloķēt pipe līdz 30s+)
        if via_bridge:
            try:
                nav = self._exec("browser.navigate", {"url": url})
                results["webview"] = {
                    "ok": nav.ok,
                    "output": nav.output,
                    "error": nav.error,
                }
            except Exception as exc:  # noqa: BLE001
                results["webview"] = {"ok": False, "error": str(exc)}

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
            results["system_browser"] = {"ok": False, "error": last_err or "neizdevās atvērt"}
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

    def search_and_open(self, query: str, *, via_bridge: bool = False) -> dict[str, Any]:
        url = duckduckgo_url(query)
        # via_bridge=False: Desktop PiP jau rāda URL; netraucējam ar pipe
        opened = self.open_url(url, via_bridge=via_bridge)
        return {"query": query, "url": url, **opened}

    def write_text_file(self, path: Path, content: str) -> dict[str, Any]:
        """Tikai ieraksta failu — bez Notepad/bridge (ātri, bez deadlock)."""
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            return {"write_ok": True, "path": str(path), "opened": None}
        except OSError as exc:
            return {"write_ok": False, "path": str(path), "error": str(exc)}

    def create_and_open_text(self, path: Path, content: str, *, open_with: str | None = "notepad") -> dict[str, Any]:
        path.parent.mkdir(parents=True, exist_ok=True)
        # Vispirms tieša rakstīšana — ātri un droši
        try:
            path.write_text(content, encoding="utf-8")
            write_ok = True
            write_out: Any = {"path": str(path), "bytes": len(content.encode("utf-8"))}
            write_err = None
        except OSError as exc:
            write = self._exec("files.write", {"path": str(path), "content": content})
            write_ok = bool(write.ok)
            write_out = write.output
            write_err = write.error or str(exc)
            if not write_ok:
                return {"write_ok": False, "path": str(path), "error": write_err}

        opened = None
        used = open_with
        if open_with and open_with.lower() not in {"none", "no", "false"}:
            if open_with.lower() in {"auto", "best", "editor"}:
                used = self.open_in_best_editor(str(path))
                opened = {"ok": True, "via": used}
            elif open_with.lower() in {"notepad", "notepad.exe"} and sys.platform.startswith("win"):
                opened = self.launch_app("notepad", [str(path)])
                used = "notepad"
            else:
                opened = self.open_path(str(path))
                used = open_with
        return {
            "write_ok": write_ok,
            "path": str(path),
            "opened": opened,
            "open_with": used,
            "write": write_out,
            "error": write_err,
        }

    def open_in_best_editor(self, path: str) -> str:
        """Atver failu ar VS Code / Notepad++ / Notepad — kas pieejams datorā."""
        p = str(path)
        for app in ("code", "notepad++", "notepad"):
            resolved = resolve_app(app)
            if resolved is None and app != "notepad":
                continue
            try:
                if app == "code":
                    # code.cmd var būt PATH; start "" "code" file
                    result = self.launch_app("code", [p])
                    if result.get("ok") or result.get("performed"):
                        return "VS Code"
                elif app == "notepad++":
                    result = self.launch_app("notepad++", [p])
                    if result.get("ok") or result.get("performed"):
                        return "Notepad++"
                else:
                    self.launch_app("notepad", [p])
                    return "Notepad"
            except Exception:  # noqa: BLE001
                continue
        self.open_path(p)
        return "noklusējuma programma"

    def detect_open_app(self, message: str) -> str | None:
        m = re.search(
            r"(?i)\b(?:atver|atvērt|open|palaid|palaist|start)\s+"
            r"(notepad\+{0,2}|npp|calc|calculator|explorer|chrome|edge|firefox|"
            r"code|vscode|powershell|cmd|paint|word|excel|spotify|discord|"
            r"telegram|steam|vlc|python|terminal)\b",
            message,
        )
        return m.group(1) if m else None
