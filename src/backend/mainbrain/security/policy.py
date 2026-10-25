from __future__ import annotations

import os
from pathlib import Path

from mainbrain.contracts.schemas import (
    ApprovalRequest,
    PolicyDecision,
    RiskCategory,
    ToolRequest,
)
from mainbrain.core.ids import new_id, utc_now
from mainbrain.security.execution_policy import assess_python_code, assess_shell_command
from mainbrain.security.redact import redact_secrets


SAFE_TOOLS = {
    "files.list",
    "files.read",
    "files.mkdir",
    "logs.inspect",
    "resources.inspect",
    "process.status",
    "git.status",
    "git.diff",
    "window.enumerate",
    "window.inspect",
    "browser.inspect",
    "browser.screenshot",
    "screen.capture",
    "tests.run",
    "dotnet.build",
    "web.search",
    "http.fetch",
    "camera.capture",
    "face.detect",
    "vision.analyze",
    "audio.speak",
}

APPROVAL_TOOLS = {
    "files.delete",
    "files.move",
    "process.start",
    "shell.run",
    "input.click",
    "input.type",
    "input.shortcut",
    "uia.invoke",
    "uia.set_value",
    "browser.navigate",
    "browser.click",
    "browser.fill",
    "git.commit",
    "git.restore",
}

# Pat full_access — šīs prasa apstiprinājumu (sistēmas kodols)
ALWAYS_APPROVAL_TOOLS = {
    "admin.elevate",
    "registry.write",
    "service.install",
}


class PolicyEngine:
    def __init__(
        self,
        workspace_root: Path | None = None,
        *,
        full_access: bool = True,
    ) -> None:
        self.workspace_root = workspace_root.resolve() if workspace_root else None
        # Lietotājs atļāvis: viss dators + internets
        self.full_access = full_access
        self._approvals: dict[str, ApprovalRequest] = {}
        self._task_grants: dict[str, set[str]] = {}
        self.emergency_stop = False

    def set_workspace(self, path: str | Path | None) -> None:
        self.workspace_root = Path(path).resolve() if path else None

    def set_full_access(self, enabled: bool) -> None:
        self.full_access = enabled

    def stop(self) -> None:
        self.emergency_stop = True

    def resume(self) -> None:
        self.emergency_stop = False

    def decide(self, request: ToolRequest, agent_allowed_tools: list[str] | None = None) -> PolicyDecision:
        if self.emergency_stop:
            return PolicyDecision(
                allowed=False,
                reason="Ārkārtas STOP ir aktīvs",
                risk_category=RiskCategory.CRITICAL,
                redacted_args=redact_secrets(request.arguments),
            )

        if request.tool in ALWAYS_APPROVAL_TOOLS:
            return self._require_approval(
                request,
                reason="Darbība prasa administratora/apstiprinājuma kontroli",
                risk=RiskCategory.CRITICAL,
                impact="Var mainīt sistēmas konfigurāciju vai privilēģijas",
            )

        if agent_allowed_tools is not None and request.tool not in agent_allowed_tools:
            # full_access: aģentu allowlist ir ieteikums, ne cietais bloķējums
            if not self.full_access:
                return PolicyDecision(
                    allowed=False,
                    reason=f"Aģentam nav atļauts rīks {request.tool}",
                    risk_category=RiskCategory.HIGH,
                    redacted_args=redact_secrets(request.arguments),
                )

        path = self._extract_path(request)
        if path is not None and not self.full_access:
            try:
                resolved = self._canonicalize(path)
            except OSError as exc:
                return PolicyDecision(
                    allowed=False,
                    reason=f"Ceļa kanonizācija neizdevās: {exc}",
                    risk_category=RiskCategory.HIGH,
                    redacted_args=redact_secrets(request.arguments),
                )
            if self.workspace_root and not self._is_inside_workspace(resolved):
                if request.tool.startswith("files.") or request.tool in {"shell.run", "python.run"}:
                    return self._require_approval(
                        request,
                        reason="Ceļš ir ārpus projekta darba mapes",
                        risk=RiskCategory.HIGH,
                        impact="Rakstīšana/dzēšana ārpus darba mapes",
                        paths=[str(resolved)],
                    )

            if request.tool == "files.delete" and self.workspace_root and self._is_inside_workspace(resolved):
                if resolved.name in {".git", "pyproject.toml", "MainBrainOS.sln"} or resolved.suffix == ".exe":
                    return self._require_approval(
                        request,
                        reason="Kritiska faila dzēšana",
                        risk=RiskCategory.HIGH,
                        impact="Iespējams zaudēt projekta struktūru",
                        paths=[str(resolved)],
                    )

        if request.tool == "process.start" and not self.full_access:
            exe = str(request.arguments.get("program") or request.arguments.get("executable") or "")
            if exe.lower().endswith(".exe") and "download" in exe.lower():
                return self._require_approval(
                    request,
                    reason="Neuzticama izpildfaila palaišana",
                    risk=RiskCategory.CRITICAL,
                    impact="Var palaist neuzticamu kodu",
                    command=exe,
                )

        if request.tool == "shell.run":
            assessment = assess_shell_command(
                request.arguments.get("command", ""),
                full_access=self.full_access,
            )
            if not assessment["allowed"]:
                return self._require_approval(
                    request,
                    reason=assessment["reason"],
                    risk=RiskCategory.CRITICAL if assessment["risk"] == "critical" else RiskCategory.HIGH,
                    impact="Čaulas komanda ar paaugstinātu risku",
                    command=str(request.arguments.get("command") or ""),
                )
            if not self.full_access and not self._path_safe(request):
                return self._require_approval(
                    request,
                    reason="Čaulas izpilde ārpus drošās darba mapes",
                    risk=RiskCategory.HIGH,
                    impact="Procesu izpilde ārpus projekta",
                    command=str(request.arguments.get("command") or ""),
                )

        if request.tool == "python.run" and request.arguments.get("code"):
            assessment = assess_python_code(
                str(request.arguments.get("code")),
                full_access=self.full_access,
            )
            if not assessment["allowed"]:
                return self._require_approval(
                    request,
                    reason=assessment["reason"],
                    risk=RiskCategory.HIGH,
                    impact="Python kods ar riskantām konstrukcijām",
                )

        # Internets / kamera / audio / sejas — atļauti (lokāli)
        if request.tool in {
            "web.search",
            "http.fetch",
            "camera.capture",
            "face.detect",
            "vision.analyze",
            "audio.speak",
        }:
            return PolicyDecision(
                allowed=True,
                reason="Sense/interneta rīks atļauts",
                risk_category=RiskCategory.MEDIUM,
                redacted_args=redact_secrets(request.arguments),
            )

        if self.full_access:
            # Lietotājs atļāvis: viss dators — auto-approve APPROVAL_TOOLS
            return PolicyDecision(
                allowed=True,
                reason="full_access: lietotājs atļāvis pilnu datoru + internetu",
                risk_category=RiskCategory.MEDIUM,
                redacted_args=redact_secrets(request.arguments),
            )

        if request.tool in APPROVAL_TOOLS and not self._has_grant(request):
            if request.tool in {"tests.run", "dotnet.build"} and self._path_safe(request):
                return PolicyDecision(
                    allowed=True,
                    reason="Atļauta izolēta projekta testa/būvēšanas izpilde",
                    risk_category=RiskCategory.MEDIUM,
                    redacted_args=redact_secrets(request.arguments),
                )
            if request.tool == "python.run" and self._path_safe(request) and request.arguments.get("script"):
                return PolicyDecision(
                    allowed=True,
                    reason="Atļauta projekta Python skripta izpilde",
                    risk_category=RiskCategory.MEDIUM,
                    redacted_args=redact_secrets(request.arguments),
                )
            if request.tool == "shell.run" and self._path_safe(request):
                return PolicyDecision(
                    allowed=True,
                    reason="Atļauta čaulas komanda no atļauto prefiksu saraksta projekta mapē",
                    risk_category=RiskCategory.MEDIUM,
                    redacted_args=redact_secrets(request.arguments),
                )
            return self._require_approval(
                request,
                reason=f"Rīks {request.tool} prasa lietotāja apstiprinājumu",
                risk=RiskCategory.MEDIUM,
                impact="Var mainīt failus, procesus vai UI stāvokli",
            )

        if request.tool in SAFE_TOOLS or request.tool.startswith("files.") or request.tool.startswith("git."):
            return PolicyDecision(
                allowed=True,
                reason="Atbilst noklusētajai drošajai politikai",
                risk_category=RiskCategory.LOW,
                redacted_args=redact_secrets(request.arguments),
            )

        return self._require_approval(
            request,
            reason="Nezināms rīks — nepieciešams apstiprinājums",
            risk=RiskCategory.HIGH,
            impact="Nezināma darbība",
        )

    def create_approval(
        self,
        *,
        action: str,
        reason: str,
        impact: str,
        source: str,
        paths: list[str] | None = None,
        command: str | None = None,
        task_id: str | None = None,
    ) -> ApprovalRequest:
        approval = ApprovalRequest(
            id=new_id("appr_"),
            action=action,
            paths=paths or [],
            command=command,
            source=source,
            reason=reason,
            impact=impact,
            task_id=task_id,
        )
        self._approvals[approval.id] = approval
        return approval

    def decide_approval(self, approval_id: str, decision: str) -> ApprovalRequest:
        approval = self._approvals[approval_id]
        if decision not in {"allowed_once", "allowed_task", "rejected"}:
            raise ValueError("Nederīgs apstiprinājuma lēmums")
        approval.status = decision  # type: ignore[assignment]
        approval.decided_at = utc_now()
        if decision == "allowed_task" and approval.task_id:
            self._task_grants.setdefault(approval.task_id, set()).add(approval.action)
        return approval

    def list_approvals(self, pending_only: bool = False) -> list[ApprovalRequest]:
        values = list(self._approvals.values())
        if pending_only:
            return [a for a in values if a.status == "pending"]
        return values

    def _require_approval(
        self,
        request: ToolRequest,
        *,
        reason: str,
        risk: RiskCategory,
        impact: str,
        paths: list[str] | None = None,
        command: str | None = None,
    ) -> PolicyDecision:
        if self._has_grant(request):
            return PolicyDecision(
                allowed=True,
                reason="Ir derīga uzdevuma atļauja",
                risk_category=risk,
                redacted_args=redact_secrets(request.arguments),
            )
        approval = self.create_approval(
            action=request.tool,
            reason=reason,
            impact=impact,
            source=request.agent_id or "system",
            paths=paths or ([str(self._extract_path(request))] if self._extract_path(request) else []),
            command=command or str(request.arguments.get("command") or ""),
            task_id=request.task_id,
        )
        return PolicyDecision(
            allowed=False,
            requires_approval=True,
            reason=reason,
            risk_category=risk,
            redacted_args=redact_secrets(request.arguments),
            approval_id=approval.id,
        )

    def _has_grant(self, request: ToolRequest) -> bool:
        if not request.task_id:
            return False
        return request.tool in self._task_grants.get(request.task_id, set())

    def _extract_path(self, request: ToolRequest) -> Path | None:
        for key in ("path", "target", "destination", "cwd", "workspace_path"):
            if key in request.arguments and request.arguments[key]:
                return Path(str(request.arguments[key]))
        if request.workspace_path:
            return Path(request.workspace_path)
        return None

    def _canonicalize(self, path: Path) -> Path:
        return Path(os.path.realpath(path))

    def _is_inside_workspace(self, path: Path) -> bool:
        if not self.workspace_root:
            return False
        try:
            path.relative_to(self.workspace_root)
            return True
        except ValueError:
            return False

    def _path_safe(self, request: ToolRequest) -> bool:
        path = self._extract_path(request)
        if path is None:
            return bool(self.workspace_root)
        try:
            resolved = self._canonicalize(path)
        except OSError:
            return False
        return self._is_inside_workspace(resolved)
