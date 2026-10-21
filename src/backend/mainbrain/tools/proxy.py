from __future__ import annotations

import ast
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

import psutil

from mainbrain.contracts.schemas import PolicyDecision, ToolRequest, ToolResult
from mainbrain.core.ids import utc_now
from mainbrain.security.policy import PolicyEngine
from mainbrain.security.redact import redact_secrets


class ToolProxy:
    """Visu rīku izpilde ar politiku pārbaudi pirms darbības."""

    def __init__(self, policy: PolicyEngine, workspace: Path | None = None) -> None:
        self.policy = policy
        self.workspace = workspace.resolve() if workspace else None
        self._input_lock_owner: str | None = None
        self._handlers: dict[str, Callable[[ToolRequest], Any]] = {
            "files.list": self._files_list,
            "files.read": self._files_read,
            "files.write": self._files_write,
            "files.patch": self._files_patch,
            "files.mkdir": self._files_mkdir,
            "files.move": self._files_move,
            "files.delete": self._files_delete,
            "process.start": self._process_start,
            "process.stop": self._process_stop,
            "process.status": self._process_status,
            "shell.run": self._shell_run,
            "python.run": self._python_run,
            "dotnet.build": self._dotnet_build,
            "git.status": self._git_status,
            "git.diff": self._git_diff,
            "git.commit": self._git_commit,
            "git.restore": self._git_restore,
            "tests.run": self._tests_run,
            "window.enumerate": self._window_stub,
            "window.inspect": self._window_stub,
            "window.focus": self._window_stub,
            "window.resize": self._window_stub,
            "window.capture": self._window_stub,
            "uia.query": self._window_stub,
            "uia.invoke": self._window_stub,
            "uia.set_value": self._window_stub,
            "input.click": self._input_stub,
            "input.type": self._input_stub,
            "input.shortcut": self._input_stub,
            "browser.navigate": self._browser_stub,
            "browser.inspect": self._browser_stub,
            "browser.click": self._browser_stub,
            "browser.fill": self._browser_stub,
            "browser.screenshot": self._browser_stub,
            "screen.capture": self._screen_stub,
            "logs.inspect": self._logs_inspect,
            "resources.inspect": self._resources_inspect,
        }
        self._processes: dict[int, subprocess.Popen[str]] = {}
        self.browser_session: dict[str, Any] = {"url": None, "history": []}

    def set_workspace(self, path: str | Path | None) -> None:
        self.workspace = Path(path).resolve() if path else None
        self.policy.set_workspace(self.workspace)

    def available_tools(self) -> list[str]:
        return sorted(self._handlers.keys())

    def execute(
        self,
        request: ToolRequest,
        *,
        agent_allowed_tools: list[str] | None = None,
        wait_for_approval: bool = False,
    ) -> ToolResult:
        started = time.perf_counter()
        decision = self.policy.decide(request, agent_allowed_tools=agent_allowed_tools)
        if not decision.allowed:
            return ToolResult(
                request_id=request.id,
                tool=request.tool,
                ok=False,
                error=decision.reason,
                duration_ms=int((time.perf_counter() - started) * 1000),
                policy=decision,
            )
        handler = self._handlers.get(request.tool)
        if handler is None:
            return ToolResult(
                request_id=request.id,
                tool=request.tool,
                ok=False,
                error=f"Nezināms rīks: {request.tool}",
                duration_ms=int((time.perf_counter() - started) * 1000),
                policy=decision,
            )
        try:
            output = handler(request)
            return ToolResult(
                request_id=request.id,
                tool=request.tool,
                ok=True,
                output=output,
                duration_ms=int((time.perf_counter() - started) * 1000),
                policy=decision,
            )
        except Exception as exc:  # noqa: BLE001 — robeža starp rīku un aģentu
            return ToolResult(
                request_id=request.id,
                tool=request.tool,
                ok=False,
                error=str(exc),
                duration_ms=int((time.perf_counter() - started) * 1000),
                policy=decision,
            )

    # --- failu rīki ---
    def _resolve(self, path_value: str | None, *, must_exist: bool = False) -> Path:
        if not path_value:
            if not self.workspace:
                raise ValueError("Nav norādīts ceļš un darba mape")
            return self.workspace
        path = Path(path_value)
        if not path.is_absolute():
            if not self.workspace:
                raise ValueError("Relatīvs ceļš bez darba mapes")
            path = self.workspace / path
        resolved = Path(os.path.realpath(path))
        if must_exist and not resolved.exists():
            raise FileNotFoundError(f"Fails nav atrasts: {resolved}")
        return resolved

    def _files_list(self, request: ToolRequest) -> dict[str, Any]:
        path = self._resolve(request.arguments.get("path"))
        if not path.exists():
            return {"path": str(path), "entries": []}
        entries = []
        for child in sorted(path.iterdir(), key=lambda p: p.name.lower()):
            entries.append(
                {
                    "name": child.name,
                    "path": str(child),
                    "is_dir": child.is_dir(),
                    "size": child.stat().st_size if child.is_file() else None,
                }
            )
        return {"path": str(path), "entries": entries}

    def _files_read(self, request: ToolRequest) -> dict[str, Any]:
        path = self._resolve(request.arguments.get("path"), must_exist=True)
        max_bytes = int(request.arguments.get("max_bytes", 1_000_000))
        data = path.read_bytes()[:max_bytes]
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            return {"path": str(path), "binary": True, "size": path.stat().st_size}
        return {"path": str(path), "content": text, "size": path.stat().st_size}

    def _files_write(self, request: ToolRequest) -> dict[str, Any]:
        path = self._resolve(request.arguments.get("path"))
        path.parent.mkdir(parents=True, exist_ok=True)
        content = request.arguments.get("content", "")
        path.write_text(str(content), encoding="utf-8")
        return {"path": str(path), "bytes": path.stat().st_size}

    def _files_patch(self, request: ToolRequest) -> dict[str, Any]:
        path = self._resolve(request.arguments.get("path"), must_exist=True)
        old = str(request.arguments.get("old", ""))
        new = str(request.arguments.get("new", ""))
        text = path.read_text(encoding="utf-8")
        if old not in text:
            raise ValueError("Patch fragments nav atrasts")
        path.write_text(text.replace(old, new, 1), encoding="utf-8")
        return {"path": str(path), "patched": True}

    def _files_mkdir(self, request: ToolRequest) -> dict[str, Any]:
        path = self._resolve(request.arguments.get("path"))
        path.mkdir(parents=True, exist_ok=True)
        return {"path": str(path), "created": True}

    def _files_move(self, request: ToolRequest) -> dict[str, Any]:
        src = self._resolve(request.arguments.get("path"), must_exist=True)
        dst = self._resolve(request.arguments.get("destination"))
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        return {"from": str(src), "to": str(dst)}

    def _files_delete(self, request: ToolRequest) -> dict[str, Any]:
        path = self._resolve(request.arguments.get("path"), must_exist=True)
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
        return {"path": str(path), "deleted": True}

    # --- procesi / čaula ---
    def _process_start(self, request: ToolRequest) -> dict[str, Any]:
        program = str(request.arguments.get("program") or request.arguments.get("executable"))
        args = request.arguments.get("args") or []
        cwd = self._resolve(request.arguments.get("cwd")) if request.arguments.get("cwd") else self.workspace
        proc = subprocess.Popen(  # noqa: S603
            [program, *map(str, args)],
            cwd=str(cwd) if cwd else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self._processes[proc.pid] = proc
        return {"pid": proc.pid, "program": program, "status": "running"}

    def _process_stop(self, request: ToolRequest) -> dict[str, Any]:
        pid = int(request.arguments["pid"])
        proc = self._processes.get(pid)
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
            return {"pid": pid, "status": "stopped"}
        if psutil.pid_exists(pid):
            p = psutil.Process(pid)
            p.terminate()
            return {"pid": pid, "status": "terminated"}
        return {"pid": pid, "status": "not_found"}

    def _process_status(self, request: ToolRequest) -> dict[str, Any]:
        pid = int(request.arguments.get("pid", 0))
        if not pid:
            return {
                "processes": [
                    {"pid": p.pid, "name": p.info["name"]}
                    for p in psutil.process_iter(["name"])
                ][:50]
            }
        if not psutil.pid_exists(pid):
            return {"pid": pid, "status": "not_found"}
        p = psutil.Process(pid)
        return {"pid": pid, "status": p.status(), "name": p.name()}

    def _run_cmd(
        self,
        command: list[str],
        *,
        cwd: Path | None,
        timeout: int,
        env: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        completed = subprocess.run(  # noqa: S603
            command,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            check=False,
        )
        return {
            "command": command,
            "exit_code": completed.returncode,
            "stdout": redact_secrets(completed.stdout),
            "stderr": redact_secrets(completed.stderr),
        }

    def _shell_run(self, request: ToolRequest) -> dict[str, Any]:
        command = request.arguments.get("command")
        if isinstance(command, str):
            # drošāk: shell=False ar shlex nav universāls Windows/Linux; šeit izmantojam sarakstu vai python -c nav
            cmd = command if sys.platform == "win32" else ["bash", "-lc", command]
            if sys.platform == "win32":
                cmd = ["powershell", "-NoProfile", "-Command", command]
        else:
            cmd = list(map(str, command))
        cwd = self._resolve(request.arguments.get("cwd")) if request.arguments.get("cwd") else self.workspace
        return self._run_cmd(cmd if isinstance(cmd, list) else [str(cmd)], cwd=cwd, timeout=request.timeout_sec)

    def _python_run(self, request: ToolRequest) -> dict[str, Any]:
        code = request.arguments.get("code")
        script = request.arguments.get("script")
        cwd = self._resolve(request.arguments.get("cwd")) if request.arguments.get("cwd") else self.workspace
        if script:
            path = self._resolve(script, must_exist=True)
            return self._run_cmd([sys.executable, str(path)], cwd=cwd, timeout=request.timeout_sec)
        if code:
            # drošības pārbaude: sintakse
            ast.parse(str(code))
            return self._run_cmd([sys.executable, "-c", str(code)], cwd=cwd, timeout=request.timeout_sec)
        raise ValueError("Nepieciešams code vai script")

    def _dotnet_build(self, request: ToolRequest) -> dict[str, Any]:
        project = self._resolve(request.arguments.get("project") or request.arguments.get("path"))
        if shutil.which("dotnet") is None:
            return {
                "status": "unavailable",
                "message": "dotnet nav pieejams šajā vidē",
                "project": str(project),
            }
        return self._run_cmd(
            ["dotnet", "build", str(project), "-c", str(request.arguments.get("configuration", "Release"))],
            cwd=project.parent if project.is_file() else project,
            timeout=request.timeout_sec,
        )

    def _git_status(self, request: ToolRequest) -> dict[str, Any]:
        cwd = self._resolve(request.arguments.get("cwd")) if request.arguments.get("cwd") else self.workspace
        return self._run_cmd(["git", "status", "--porcelain"], cwd=cwd, timeout=30)

    def _git_diff(self, request: ToolRequest) -> dict[str, Any]:
        cwd = self._resolve(request.arguments.get("cwd")) if request.arguments.get("cwd") else self.workspace
        return self._run_cmd(["git", "diff"], cwd=cwd, timeout=60)

    def _git_commit(self, request: ToolRequest) -> dict[str, Any]:
        cwd = self._resolve(request.arguments.get("cwd")) if request.arguments.get("cwd") else self.workspace
        message = str(request.arguments.get("message", "MainBrainOS kontrolpunkts"))
        add = self._run_cmd(["git", "add", "-A"], cwd=cwd, timeout=60)
        commit = self._run_cmd(["git", "commit", "-m", message, "--allow-empty"], cwd=cwd, timeout=60)
        return {"add": add, "commit": commit}

    def _git_restore(self, request: ToolRequest) -> dict[str, Any]:
        cwd = self._resolve(request.arguments.get("cwd")) if request.arguments.get("cwd") else self.workspace
        target = str(request.arguments.get("path", "."))
        return self._run_cmd(["git", "restore", target], cwd=cwd, timeout=60)

    def _tests_run(self, request: ToolRequest) -> dict[str, Any]:
        cwd = self._resolve(request.arguments.get("cwd")) if request.arguments.get("cwd") else self.workspace
        target = str(request.arguments.get("target", "tests"))
        if (cwd / "pytest.ini").exists() or (cwd / "pyproject.toml").exists() or target.endswith(".py"):
            cmd = [sys.executable, "-m", "pytest", "-q", target]
        else:
            cmd = [sys.executable, "-m", "unittest", "discover", "-s", target]
        return self._run_cmd(cmd, cwd=cwd, timeout=request.timeout_sec)

    # --- Windows / pārlūka stubi ar godīgu statusu ---
    def _platform_note(self) -> str:
        if sys.platform != "win32":
            return "Nav pieejams: Windows specifiska funkcija (pašreizējā OS nav Windows)"
        return "Windows komponents nav inicializēts šajā backend procesā"

    def _window_stub(self, request: ToolRequest) -> dict[str, Any]:
        return {
            "status": "unavailable",
            "tool": request.tool,
            "message": self._platform_note(),
            "capture_status": "unavailable",
        }

    def _input_stub(self, request: ToolRequest) -> dict[str, Any]:
        owner = request.agent_id or request.id
        if self._input_lock_owner and self._input_lock_owner != owner:
            return {
                "status": "blocked",
                "message": "Ievades fokusu pašlaik tur cits operators",
                "owner": self._input_lock_owner,
            }
        self._input_lock_owner = owner
        try:
            return {
                "status": "unavailable",
                "tool": request.tool,
                "message": self._platform_note(),
            }
        finally:
            self._input_lock_owner = None

    def _browser_stub(self, request: ToolRequest) -> dict[str, Any]:
        # Backend uztur sesijas modeli; īstā WebView2 ir desktop pusē.
        if request.tool == "browser.navigate":
            url = str(request.arguments.get("url", ""))
            self.browser_session["url"] = url
            self.browser_session["history"].append({"url": url, "at": utc_now().isoformat()})
            return {
                "status": "queued_for_webview2",
                "url": url,
                "message": "Navigācija nodota iegultajai WebView2 sesijai (desktop)",
            }
        return {
            "status": "session",
            "session": self.browser_session,
            "message": "Pārlūka darbība caur iegulto WebView2 kanālu",
        }

    def _screen_stub(self, request: ToolRequest) -> dict[str, Any]:
        return {"status": "unavailable", "message": self._platform_note()}

    def _logs_inspect(self, request: ToolRequest) -> dict[str, Any]:
        path = request.arguments.get("path")
        if path:
            resolved = self._resolve(str(path), must_exist=True)
            lines = resolved.read_text(encoding="utf-8", errors="replace").splitlines()[-200:]
            return {"path": str(resolved), "lines": [redact_secrets(line) for line in lines]}
        return {"lines": [], "message": "Nav norādīts žurnāla ceļš"}

    def _resources_inspect(self, request: ToolRequest) -> dict[str, Any]:
        vm = psutil.virtual_memory()
        return {
            "cpu_percent": psutil.cpu_percent(interval=0.1),
            "ram_total_mb": round(vm.total / (1024 * 1024), 1),
            "ram_used_mb": round(vm.used / (1024 * 1024), 1),
            "ram_percent": vm.percent,
            "disk_free_gb": round(shutil.disk_usage(str(self.workspace or Path.cwd())).free / (1024**3), 2),
            "platform": sys.platform,
            "python": sys.version.split()[0],
            "timestamp": utc_now().isoformat(),
        }
