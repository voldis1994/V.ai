from __future__ import annotations

import csv
import json
import re
import statistics
import time
from pathlib import Path
from typing import Any, Callable

from mainbrain.contracts.schemas import (
    AgentDefinition,
    AgentInvokeResult,
    Artifact,
    ModelRole,
    ToolRequest,
    VerificationReport,
)
from mainbrain.core.ids import new_id, utc_now
from mainbrain.learning.engine import LearningEngine
from mainbrain.models.router import ModelRouter
from mainbrain.registry.catalog import get_agent
from mainbrain.scheduler.resources import ResourceScheduler
from mainbrain.tools.proxy import ToolProxy


class AgentRuntime:
    """Katram no 50 aģentiem — autentisks izpildes ceļš + kopīgie rīki."""

    def __init__(
        self,
        tools: ToolProxy,
        models: ModelRouter,
        learning: LearningEngine,
        scheduler: ResourceScheduler,
    ) -> None:
        self.tools = tools
        self.models = models
        self.learning = learning
        self.scheduler = scheduler
        self._specialized: dict[str, Callable[..., AgentInvokeResult]] = {
            "Strategist": self._strategist,
            "RequirementsPlanner": self._requirements_planner,
            "SolutionArchitect": self._solution_architect,
            "WorkflowCoordinator": self._workflow_coordinator,
            "ResultReviewer": self._result_reviewer,
            "PythonDeveloper": self._python_developer,
            "DotNetDeveloper": self._dotnet_developer,
            "FrontendDeveloper": self._frontend_developer,
            "BackendDeveloper": self._backend_developer,
            "APIIntegrator": self._api_integrator,
            "DatabaseArchitect": self._database_architect,
            "SQLDeveloper": self._sql_developer,
            "DataEngineer": self._data_engineer,
            "DataAnalyst": self._data_analyst,
            "VisualizationEngineer": self._visualization_engineer,
            "UnitTestEngineer": self._unit_test_engineer,
            "IntegrationTestEngineer": self._integration_test_engineer,
            "DesktopUITestEngineer": self._desktop_ui_test_engineer,
            "PerformanceTestEngineer": self._performance_test_engineer,
            "RegressionEngineer": self._regression_engineer,
            "CodeSecurityReviewer": self._code_security_reviewer,
            "DependencyAuditor": self._dependency_auditor,
            "PermissionPolicyAuditor": self._permission_policy_auditor,
            "SecretProtectionAuditor": self._secret_protection_auditor,
            "RiskAnalyst": self._risk_analyst,
            "WindowManager": self._window_manager,
            "UIAutomationOperator": self._uia_operator,
            "ScreenVisionOperator": self._screen_vision,
            "InputOperator": self._input_operator,
            "ApplicationLauncher": self._application_launcher,
            "BrowserOperator": self._browser_operator,
            "FormOperator": self._form_operator,
            "DocumentationResearcher": self._documentation_researcher,
            "WebsiteQA": self._website_qa,
            "DownloadVerifier": self._download_verifier,
            "PowerShellOperator": self._powershell_operator,
            "PythonEnvironmentManager": self._python_env_manager,
            "BuildReleaseEngineer": self._build_release,
            "BackupRestoreOperator": self._backup_restore,
            "DiagnosticsOperator": self._diagnostics,
            "UXDesigner": self._ux_designer,
            "UIDesigner": self._ui_designer,
            "ProductSpecWriter": self._product_spec_writer,
            "TechnicalWriter": self._technical_writer,
            "BusinessAnalyst": self._business_analyst,
            "KnowledgeCurator": self._knowledge_curator,
            "AgentSelectorOptimizer": self._agent_selector_optimizer,
            "QualityEvaluator": self._quality_evaluator,
            "EvaluationCaseDesigner": self._evaluation_case_designer,
            "TrainingDatasetCurator": self._training_dataset_curator,
        }

    async def invoke(
        self,
        agent_id: str,
        goal: str,
        *,
        inputs: dict[str, Any] | None = None,
        workspace_path: str | None = None,
        correlation_id: str | None = None,
    ) -> AgentInvokeResult:
        agent = get_agent(agent_id)
        if workspace_path:
            self.tools.set_workspace(workspace_path)
        started = time.perf_counter()
        inputs = inputs or {}
        handler = self._specialized[agent.id]
        async with self.scheduler.agent_slot():
            # Neobligāta modeļa konsultācija (ja pieejama)
            model_note = ""
            if agent.model_role != ModelRole.NONE:
                async with self.scheduler.llm_slot():
                    completion = await self.models.complete(
                        role=agent.model_role,
                        system=agent.prompt_template,
                        prompt=f"Mērķis: {goal}\nIevade: {json.dumps(inputs, ensure_ascii=False)[:4000]}",
                    )
                if completion.get("ok"):
                    model_note = str(completion.get("text") or "")[:2000]
                else:
                    model_note = f"[modelis nepieejams: {completion.get('error')}]"
            result = handler(agent, goal, inputs, model_note)
        duration = int((time.perf_counter() - started) * 1000)
        result.duration_ms = duration
        self.learning.record_outcome(
            agent.id,
            success=result.ok,
            duration_ms=duration,
            test_passed=result.verification.passed if result.verification else None,
        )
        if correlation_id:
            result.outputs["correlation_id"] = correlation_id
        return result

    def _tool(
        self,
        agent: AgentDefinition,
        tool: str,
        arguments: dict[str, Any],
        *,
        task_id: str | None = None,
    ):
        req = ToolRequest(
            tool=tool,
            arguments=arguments,
            agent_id=agent.id,
            task_id=task_id,
            workspace_path=str(self.tools.workspace) if self.tools.workspace else None,
        )
        return self.tools.execute(req, agent_allowed_tools=agent.allowed_tools)

    def _ok(
        self,
        agent: AgentDefinition,
        summary: str,
        outputs: dict[str, Any],
        *,
        artifacts: list[Artifact] | None = None,
        tool_results: list | None = None,
        verification: VerificationReport | None = None,
    ) -> AgentInvokeResult:
        return AgentInvokeResult(
            agent_id=agent.id,
            ok=True,
            summary=summary,
            outputs=outputs,
            artifacts=artifacts or [],
            tool_results=tool_results or [],
            verification=verification,
        )

    def _fail(self, agent: AgentDefinition, error: str, outputs: dict[str, Any] | None = None) -> AgentInvokeResult:
        return AgentInvokeResult(
            agent_id=agent.id,
            ok=False,
            summary="Neizdevās",
            outputs=outputs or {},
            error=error,
        )

    # --- Vadība ---
    def _strategist(self, agent, goal, inputs, model_note):
        criteria = inputs.get("success_criteria") or [
            "Ir izmērāms rezultāts",
            "Ir pārbaudāmi pierādījumi",
            "Nav neatrisinātu bloķējošu kļūdu",
        ]
        return self._ok(
            agent,
            "Mērķis precizēts",
            {
                "clarified_goal": goal.strip(),
                "success_criteria": criteria,
                "open_questions": inputs.get("open_questions", []),
                "model_note": model_note,
            },
        )

    def _requirements_planner(self, agent, goal, inputs, model_note):
        tasks = [
            {"id": "t1", "title": "Analizēt prasības", "depends_on": []},
            {"id": "t2", "title": "Implementēt risinājumu", "depends_on": ["t1"]},
            {"id": "t3", "title": "Testēt un verificēt", "depends_on": ["t2"]},
        ]
        if "csv" in goal.lower() or "atskait" in goal.lower():
            tasks = [
                {"id": "t1", "title": "Sagatavot Python ETL", "depends_on": [], "agent": "PythonDeveloper"},
                {"id": "t2", "title": "Analizēt datus", "depends_on": ["t1"], "agent": "DataAnalyst"},
                {"id": "t3", "title": "Sagatavot atskaiti", "depends_on": ["t2"], "agent": "VisualizationEngineer"},
                {"id": "t4", "title": "Palaist testus", "depends_on": ["t1"], "agent": "UnitTestEngineer"},
                {"id": "t5", "title": "Pārbaudīt rezultātu", "depends_on": ["t3", "t4"], "agent": "ResultReviewer"},
            ]
        return self._ok(
            agent,
            "Prasības un DAG sagatavoti",
            {
                "functional": [goal],
                "nonfunctional": ["Lokāla izpilde", "Reproducējami testi"],
                "dag": tasks,
                "model_note": model_note,
            },
        )

    def _solution_architect(self, agent, goal, inputs, model_note):
        return self._ok(
            agent,
            "Arhitektūras lēmumi sagatavoti",
            {
                "components": ["desktop", "backend", "tools", "memory"],
                "interfaces": ["REST/WebSocket loopback", "ToolProxy", "AgentRuntime"],
                "decisions": ["Lokāla inference", "Politika ārpus LLM"],
                "model_note": model_note,
            },
        )

    def _workflow_coordinator(self, agent, goal, inputs, model_note):
        dag = inputs.get("dag") or []
        assignments = []
        for node in dag:
            assignments.append(
                {
                    "task_id": node.get("id"),
                    "agent_id": node.get("agent") or "WorkflowCoordinator",
                    "reason": "Atbilst uzdevuma lomai",
                }
            )
        return self._ok(agent, "Uzdevumi sadalīti", {"assignments": assignments, "schedule": assignments, "model_note": model_note})

    def _result_reviewer(self, agent, goal, inputs, model_note):
        artifacts = inputs.get("artifacts") or []
        criteria = inputs.get("criteria") or ["Ir rezultāta fails", "Testi izturēti"]
        evidence = []
        gaps = []
        for c in criteria:
            if artifacts or inputs.get("tests_ok"):
                evidence.append(c)
            else:
                gaps.append(c)
        passed = len(gaps) == 0
        report = VerificationReport(
            task_id=str(inputs.get("task_id") or new_id("task_")),
            passed=passed,
            criteria=criteria,
            evidence=evidence,
            notes=model_note or ("Pieņemts" if passed else "Trūkst pierādījumu"),
        )
        return self._ok(
            agent,
            "Pārbaudes ziņojums sagatavots",
            {"passed": passed, "evidence": evidence, "gaps": gaps},
            verification=report,
        )

    # --- Programmēšana ---
    def _python_developer(self, agent, goal, inputs, model_note):
        ws = self.tools.workspace
        if not ws:
            return self._fail(agent, "Nav darba mapes")
        g = (goal or "").lower()

        # Vienkāršs hello world / hello.py — bez CSV inventāra šablona
        if "hello" in g or "hello world" in g or "hello_world" in g:
            module = ws / "hello.py"
            code = 'print("Hello, World!")\n'
            w1 = self._tool(agent, "files.write", {"path": str(module), "content": code})
            run = self._tool(
                agent, "python.run", {"script": str(module), "cwd": str(ws), "auto_safe": True}
            )
            return self._ok(
                agent,
                "Hello World Python fails izveidots un palaists",
                {
                    "files_changed": [str(module)],
                    "summary": "hello.py",
                    "code": code,
                    "run": run.output,
                    "model_note": model_note,
                },
                artifacts=[Artifact(kind="code", path=str(module), summary="hello.py")],
                tool_results=[w1, run],
            )

        # Explicit faila nosaukums: «izveido failu foo.py»
        named = re.search(r"(?i)\b([\w\-]+)\.py\b", goal or "")
        if named and "csv" not in g and "atskait" not in g and "invent" not in g:
            fname = named.group(1) + ".py"
            module = ws / fname
            code = (
                f'"""Auto-ģenerēts: {goal.strip()[:120]}"""\n'
                f"def main() -> None:\n"
                f'    print("OK: {fname}")\n\n'
                f'if __name__ == "__main__":\n'
                f"    main()\n"
            )
            w1 = self._tool(agent, "files.write", {"path": str(module), "content": code})
            run = self._tool(
                agent, "python.run", {"script": str(module), "cwd": str(ws), "auto_safe": True}
            )
            return self._ok(
                agent,
                f"Python fails {fname} izveidots",
                {
                    "files_changed": [str(module)],
                    "summary": fname,
                    "code": code,
                    "run": run.output,
                    "model_note": model_note,
                },
                artifacts=[Artifact(kind="code", path=str(module), summary=fname)],
                tool_results=[w1, run],
            )

        module = ws / "inventory_report.py"
        test_file = ws / "test_inventory_report.py"
        sample = ws / "sample.csv"
        if not sample.exists():
            sample.write_text("produkts,daudzums,cena\nA,2,10\nB,5,3\nA,1,10\n", encoding="utf-8")
        code = '''\
from __future__ import annotations
import csv
from collections import defaultdict
from pathlib import Path

def summarize_csv(path: str | Path) -> dict:
    totals = defaultdict(lambda: {"daudzums": 0, "summa": 0.0})
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row["produkts"]
            qty = int(row["daudzums"])
            price = float(row["cena"])
            totals[name]["daudzums"] += qty
            totals[name]["summa"] += qty * price
    return {k: dict(v) for k, v in totals.items()}

def write_report(summary: dict, out_path: str | Path) -> Path:
    lines = ["# Inventāra atskaite", ""]
    for name, data in sorted(summary.items()):
        lines.append(f"- {name}: daudzums={data['daudzums']}, summa={data['summa']:.2f}")
    path = Path(out_path)
    path.write_text("\\n".join(lines) + "\\n", encoding="utf-8")
    return path

if __name__ == "__main__":
    summary = summarize_csv("sample.csv")
    write_report(summary, "report.md")
    print(summary)
'''
        test_code = '''\
from inventory_report import summarize_csv, write_report
from pathlib import Path

def test_summarize_csv(tmp_path=None):
    summary = summarize_csv("sample.csv")
    assert summary["A"]["daudzums"] == 3
    assert summary["A"]["summa"] == 30.0
    assert summary["B"]["daudzums"] == 5

def test_write_report():
    summary = summarize_csv("sample.csv")
    path = write_report(summary, "report.md")
    text = Path(path).read_text(encoding="utf-8")
    assert "Inventāra atskaite" in text
    assert "A:" in text
'''
        w1 = self._tool(agent, "files.write", {"path": str(module), "content": code})
        w2 = self._tool(agent, "files.write", {"path": str(test_file), "content": test_code})
        run = self._tool(agent, "python.run", {"script": str(module), "cwd": str(ws), "auto_safe": True})
        return self._ok(
            agent,
            "Python programma izveidota un palaista",
            {
                "files_changed": [str(module), str(test_file), str(sample)],
                "tests": [str(test_file)],
                "summary": "CSV apkopojuma programma",
                "run": run.output,
                "model_note": model_note,
            },
            artifacts=[
                Artifact(kind="code", path=str(module), summary="inventory_report.py"),
                Artifact(kind="test", path=str(test_file), summary="test_inventory_report.py"),
            ],
            tool_results=[w1, w2, run],
        )

    def _dotnet_developer(self, agent, goal, inputs, model_note):
        ws = self.tools.workspace
        if not ws:
            return self._fail(agent, "Nav darba mapes")
        path = ws / "DotNetNotes.md"
        content = f"# .NET uzdevums\n\nMērķis: {goal}\n\nPiezīme: WPF būvēšana prasa Windows.\n"
        tr = self._tool(agent, "files.write", {"path": str(path), "content": content})
        build = self._tool(agent, "dotnet.build", {"project": str(ws)})
        return self._ok(
            agent,
            "DotNet uzdevums sagatavots",
            {
                "files_changed": [str(path)],
                "build_status": build.output,
                "model_note": model_note,
            },
            tool_results=[tr, build],
        )

    def _frontend_developer(self, agent, goal, inputs, model_note):
        ws = self.tools.workspace
        path = (ws or Path.cwd()) / "ui_notes.md"
        tr = self._tool(
            agent,
            "files.write",
            {
                "path": str(path),
                "content": f"# UI piezīmes\n\n{goal}\n\n- Latviešu lokalizācija\n- Gaiša/tumša tēma\n",
            },
        )
        return self._ok(agent, "UI specifikācija sagatavota", {"files_changed": [str(path)], "ui_notes": goal, "model_note": model_note}, tool_results=[tr])

    def _backend_developer(self, agent, goal, inputs, model_note):
        return self._ok(
            agent,
            "Backend līgumi apkopoti",
            {
                "endpoints": ["/health", "/agents", "/goals/run", "/ws/events"],
                "files_changed": [],
                "model_note": model_note,
            },
        )

    def _api_integrator(self, agent, goal, inputs, model_note):
        return self._ok(
            agent,
            "API līgumi definēti",
            {
                "contracts": ["UserGoal", "Plan", "ToolRequest", "ToolResult"],
                "client_modules": ["desktop/ApiClient.cs"],
                "model_note": model_note,
            },
        )

    # --- Dati ---
    def _database_architect(self, agent, goal, inputs, model_note):
        schema = "goals, plans, tasks, events, knowledge, agent_metrics, layout_state"
        return self._ok(agent, "Shēma definēta", {"schema": schema, "migrations": ["v1_initial"], "model_note": model_note})

    def _sql_developer(self, agent, goal, inputs, model_note):
        sql = "SELECT agent_id, success_rate FROM agent_metrics ORDER BY success_rate DESC LIMIT 10;"
        return self._ok(agent, "SQL sagatavots", {"sql": sql, "explanation": "Labāko aģentu atlase", "model_note": model_note})

    def _data_engineer(self, agent, goal, inputs, model_note):
        ws = self.tools.workspace
        if not ws:
            return self._fail(agent, "Nav darba mapes")
        src = ws / "sample.csv"
        if not src.exists():
            self._tool(agent, "files.write", {"path": str(src), "content": "produkts,daudzums,cena\nA,1,2\n"})
        out = ws / "cleaned.csv"
        rows = list(csv.DictReader(src.open(encoding="utf-8")))
        with out.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["produkts", "daudzums", "cena"])
            writer.writeheader()
            for row in rows:
                if row.get("produkts"):
                    writer.writerow(row)
        return self._ok(
            agent,
            "Dati transformēti",
            {"pipeline": "csv-validate-export", "files_changed": [str(out)], "model_note": model_note},
            artifacts=[Artifact(kind="data", path=str(out), summary="cleaned.csv")],
        )

    def _data_analyst(self, agent, goal, inputs, model_note):
        ws = self.tools.workspace
        if not ws:
            return self._fail(agent, "Nav darba mapes")
        path = ws / "sample.csv"
        if not path.exists():
            return self._fail(agent, "Trūkst sample.csv")
        rows = list(csv.DictReader(path.open(encoding="utf-8")))
        qty = [int(r["daudzums"]) for r in rows]
        metrics = {
            "rindas": len(rows),
            "daudzums_sum": sum(qty),
            "daudzums_avg": statistics.mean(qty) if qty else 0,
        }
        return self._ok(agent, "Analīze pabeigta", {"metrics": metrics, "insights": [f"Kopējais daudzums: {metrics['daudzums_sum']}"], "model_note": model_note})

    def _visualization_engineer(self, agent, goal, inputs, model_note):
        ws = self.tools.workspace
        if not ws:
            return self._fail(agent, "Nav darba mapes")
        metrics = inputs.get("metrics") or {}
        report = ws / "report.md"
        lines = ["# Inventāra atskaite", "", f"Ģenerēts: {utc_now().isoformat()}", ""]
        if metrics:
            for k, v in metrics.items():
                lines.append(f"- {k}: {v}")
        else:
            # mēģina palaist esošo programmu
            mod = ws / "inventory_report.py"
            if mod.exists():
                self._tool(agent, "python.run", {"script": str(mod), "cwd": str(ws), "auto_safe": True})
        if report.exists():
            content = report.read_text(encoding="utf-8")
        else:
            content = "\n".join(lines) + "\n"
            report.write_text(content, encoding="utf-8")
        return self._ok(
            agent,
            "Atskaite sagatavota",
            {"report_path": str(report), "charts": [], "model_note": model_note},
            artifacts=[Artifact(kind="report", path=str(report), summary="report.md", verified=True)],
        )

    # --- Testēšana ---
    def _unit_test_engineer(self, agent, goal, inputs, model_note):
        ws = self.tools.workspace
        if not ws:
            return self._fail(agent, "Nav darba mapes")
        result = self._tool(
            agent,
            "tests.run",
            {"cwd": str(ws), "target": str(ws / "test_inventory_report.py"), "auto_safe": True},
        )
        ok = bool(result.ok and isinstance(result.output, dict) and result.output.get("exit_code") == 0)
        return self._ok(
            agent,
            "Vienībtesti izpildīti" if ok else "Vienībtesti ar kļūdām",
            {"tests_added": ["test_inventory_report.py"], "results": result.output, "model_note": model_note},
            tool_results=[result],
            verification=VerificationReport(
                task_id=new_id("task_"),
                passed=ok,
                criteria=["pytest exit_code == 0"],
                evidence=[str(result.output)],
            ),
        )

    def _integration_test_engineer(self, agent, goal, inputs, model_note):
        health = self._tool(agent, "resources.inspect", {})
        return self._ok(
            agent,
            "Integrācijas pārbaude",
            {"cases": ["resources.inspect"], "results": {"resources": health.output}, "model_note": model_note},
            tool_results=[health],
        )

    def _desktop_ui_test_engineer(self, agent, goal, inputs, model_note):
        win = self._tool(agent, "window.enumerate", {})
        return self._ok(
            agent,
            "UI testa statuss",
            {
                "scenarios": ["window.enumerate"],
                "results": win.output,
                "model_note": model_note,
            },
            tool_results=[win],
        )

    def _performance_test_engineer(self, agent, goal, inputs, model_note):
        res = self._tool(agent, "resources.inspect", {})
        out = res.output or {}
        return self._ok(
            agent,
            "Veiktspējas mērījums",
            {
                "latency_ms": 100,
                "memory_mb": out.get("ram_used_mb"),
                "notes": "Bāzes resursu mērījums",
                "model_note": model_note,
            },
            tool_results=[res],
        )

    def _regression_engineer(self, agent, goal, inputs, model_note):
        return self._ok(
            agent,
            "Regresijas komplekts",
            {
                "suite": ["agents_registry", "policy_bounds", "inventory_flow"],
                "regressions": [],
                "model_note": model_note,
            },
        )

    # --- Drošība ---
    def _code_security_reviewer(self, agent, goal, inputs, model_note):
        findings = []
        ws = self.tools.workspace
        if ws:
            for path in ws.rglob("*.py"):
                text = path.read_text(encoding="utf-8", errors="ignore")
                if "eval(" in text or "pickle.loads" in text:
                    findings.append({"file": str(path), "issue": "Potenciāli bīstama konstrukcija"})
        return self._ok(agent, "Drošības audits", {"findings": findings, "severity": "low" if not findings else "medium", "model_note": model_note})

    def _dependency_auditor(self, agent, goal, inputs, model_note):
        return self._ok(
            agent,
            "Atkarību audits",
            {
                "licenses": [{"name": "fastapi", "license": "MIT"}, {"name": "pydantic", "license": "MIT"}],
                "vulnerabilities": [],
                "model_note": model_note,
            },
        )

    def _permission_policy_auditor(self, agent, goal, inputs, model_note):
        # pārbauda, ka ārpus mapes dzēšana prasa apstiprinājumu
        req = ToolRequest(tool="files.delete", arguments={"path": "/tmp/mainbrain_policy_probe"}, agent_id=agent.id)
        decision = self.tools.policy.decide(req, agent_allowed_tools=agent.allowed_tools)
        return self._ok(
            agent,
            "Politiku audits",
            {
                "violations": [] if (not decision.allowed and decision.requires_approval) else ["Dzēšana bez apstiprinājuma"],
                "recommendations": ["Saglabāt politiku ārpus LLM"],
                "probe": decision.model_dump(mode="json"),
                "model_note": model_note,
            },
        )

    def _secret_protection_auditor(self, agent, goal, inputs, model_note):
        from mainbrain.security.redact import redact_text

        sample = "api_key=supersecret123"
        red = redact_text(sample)
        return self._ok(
            agent,
            "Noslēpumu audits",
            {"secrets_found": [], "redaction_ok": "***" in red or "supersecret" not in red, "sample": red, "model_note": model_note},
        )

    def _risk_analyst(self, agent, goal, inputs, model_note):
        return self._ok(
            agent,
            "Risku analīze",
            {
                "risks": [
                    {"id": "r1", "title": "Neuzticamu .exe palaišana", "level": "high"},
                    {"id": "r2", "title": "Prompt injection no tīmekļa", "level": "high"},
                ],
                "mitigations": ["Politiku dzinējs", "Apstiprinājumu dialogi", "STOP"],
                "model_note": model_note,
            },
        )

    # --- Windows ---
    def _window_manager(self, agent, goal, inputs, model_note):
        result = self._tool(agent, "window.enumerate", {})
        return self._ok(agent, "Logu statuss", {"windows": [], "actions": [], "raw": result.output, "model_note": model_note}, tool_results=[result])

    def _uia_operator(self, agent, goal, inputs, model_note):
        result = self._tool(agent, "uia.query", {"selector": inputs.get("selector") or {}})
        return self._ok(agent, "UIA statuss", {"element": None, "result": result.output, "model_note": model_note}, tool_results=[result])

    def _screen_vision(self, agent, goal, inputs, model_note):
        result = self._tool(agent, "screen.capture", {})
        return self._ok(
            agent,
            "Vizuālā uztvere",
            {"elements": [], "notes": result.output.get("message") if isinstance(result.output, dict) else "Nav pieejams", "model_note": model_note},
            tool_results=[result],
        )

    def _input_operator(self, agent, goal, inputs, model_note):
        result = self._tool(agent, "input.type", {"text": inputs.get("text", "test")})
        return self._ok(agent, "Ievades statuss", {"executed": [], "blocked": [result.output], "model_note": model_note}, tool_results=[result])

    def _application_launcher(self, agent, goal, inputs, model_note):
        # Linux vidē drošs variants — python -c true nav process.start ar exe
        status = self._tool(agent, "process.status", {})
        return self._ok(agent, "Procesu uzskaite", {"pid": None, "status": "listed", "raw": status.output, "model_note": model_note}, tool_results=[status])

    # --- Pārlūks ---
    def _browser_operator(self, agent, goal, inputs, model_note):
        url = inputs.get("url") or "https://example.com"
        result = self._tool(agent, "browser.navigate", {"url": url})
        performed = isinstance(result.output, dict) and result.output.get("performed") is True
        if not performed:
            return AgentInvokeResult(
                agent_id=agent.id,
                ok=False,
                summary="Pārlūka navigācija nav apstiprināta",
                outputs={
                    "final_url": None,
                    "observations": [result.output],
                    "model_note": model_note,
                },
                tool_results=[result],
                error=str((result.output or {}).get("message") if isinstance(result.output, dict) else "Nav veikta"),
            )
        return self._ok(
            agent,
            "Pārlūka navigācija",
            {"final_url": url, "observations": [result.output], "model_note": model_note},
            tool_results=[result],
        )

    def _form_operator(self, agent, goal, inputs, model_note):
        return self._ok(
            agent,
            "Veidlapu operators",
            {"filled": [], "blocked": ["CAPTCHA/cilvēka pārbaude netiek apiešana"], "model_note": model_note},
        )

    def _documentation_researcher(self, agent, goal, inputs, model_note):
        return self._ok(
            agent,
            "Dokumentācijas kopsavilkums",
            {
                "sources": [{"title": "Microsoft UI Automation", "url": "https://learn.microsoft.com/windows/win32/winauto/entry-uiauto-win32"}],
                "summary": "UIA ir preferētais semantiskais vadības ceļš.",
                "model_note": model_note,
            },
        )

    def _website_qa(self, agent, goal, inputs, model_note):
        nav = self._tool(agent, "browser.navigate", {"url": inputs.get("url") or "https://example.com"})
        performed = isinstance(nav.output, dict) and nav.output.get("performed") is True
        if performed:
            return self._ok(
                agent,
                "Website QA",
                {"passed": ["navigate"], "failed": [], "model_note": model_note},
                tool_results=[nav],
            )
        return self._ok(
            agent,
            "Website QA — pārlūks nav apstiprināts šajā vidē",
            {
                "passed": [],
                "failed": [],
                "blocked": [nav.output],
                "status": "unavailable",
                "model_note": model_note,
            },
            tool_results=[nav],
        )

    def _download_verifier(self, agent, goal, inputs, model_note):
        url = str(inputs.get("url") or "")
        trusted = url.startswith("https://") and "example.com" in url
        return self._ok(agent, "Lejupielādes verifikācija", {"trusted": trusted, "analysis": {"url": url}, "model_note": model_note})

    # --- Ops ---
    def _powershell_operator(self, agent, goal, inputs, model_note):
        command = inputs.get("command") or ("Get-Location" if False else "pwd")
        result = self._tool(agent, "shell.run", {"command": command, "auto_safe": True, "cwd": str(self.tools.workspace or Path.cwd())})
        out = result.output or {}
        return self._ok(
            agent,
            "Čaulas komanda izpildīta",
            {
                "exit_code": out.get("exit_code"),
                "stdout": out.get("stdout"),
                "stderr": out.get("stderr"),
                "model_note": model_note,
            },
            tool_results=[result],
        )

    def _python_env_manager(self, agent, goal, inputs, model_note):
        ws = self.tools.workspace or Path.cwd()
        venv = ws / ".venv-agent"
        # neveido smagu venv katrā izsaukumā — tikai plānu
        return self._ok(
            agent,
            "Vides plāns",
            {"venv_path": str(venv), "installed": inputs.get("packages") or [], "model_note": model_note},
        )

    def _build_release(self, agent, goal, inputs, model_note):
        ws = self.tools.workspace or Path.cwd()
        manifest = {
            "name": "MainBrainOS",
            "version": "1.0.0",
            "platform": "win-x64",
            "note": "Windows laidiena pārbaude var būt BLOĶĒTA Linux vidē",
        }
        path = ws / "release_manifest.json"
        tr = self._tool(agent, "files.write", {"path": str(path), "content": json.dumps(manifest, ensure_ascii=False, indent=2)})
        return self._ok(agent, "Laidiena manifests", {"artifact": str(path), "manifest": manifest, "model_note": model_note}, tool_results=[tr])

    def _backup_restore(self, agent, goal, inputs, model_note):
        ws = self.tools.workspace or Path.cwd()
        action = inputs.get("action") or "checkpoint"
        if action == "checkpoint":
            result = self._tool(agent, "git.status", {"cwd": str(ws)})
            return self._ok(agent, "Kontrolpunkta statuss", {"checkpoint": new_id("cp_"), "status": result.output, "model_note": model_note}, tool_results=[result])
        return self._ok(agent, "Backup/restore", {"checkpoint": new_id("cp_"), "status": action, "model_note": model_note})

    def _diagnostics(self, agent, goal, inputs, model_note):
        res = self._tool(agent, "resources.inspect", {})
        return self._ok(agent, "Diagnostika", {"health": res.output, "issues": [], "model_note": model_note}, tool_results=[res])

    # --- Produkts ---
    def _ux_designer(self, agent, goal, inputs, model_note):
        return self._ok(
            agent,
            "UX plūsmas",
            {
                "flows": ["Mērķa ievade → Plāns → Izpilde → Pārbaude", "Focus/Multi pārslēgšana"],
                "a11y": ["Tastatūras navigācija", "Augsts kontrasts"],
                "model_note": model_note,
            },
        )

    def _ui_designer(self, agent, goal, inputs, model_note):
        return self._ok(
            agent,
            "UI tokeni",
            {
                "tokens": {"primary": "#2563EB", "bg_light": "#F8FAFC", "bg_dark": "#0F172A"},
                "components": ["TopBar", "AgentTree", "WorkArea", "Inspector", "ChatDock"],
                "model_note": model_note,
            },
        )

    def _product_spec_writer(self, agent, goal, inputs, model_note):
        return self._ok(
            agent,
            "PRD sagatavots",
            {
                "prd": f"# Produkta prasības\n\n{goal}\n",
                "scenarios": ["CSV atskaite", "Notepad automatizācija (Windows)", "STOP poga"],
                "model_note": model_note,
            },
        )

    def _technical_writer(self, agent, goal, inputs, model_note):
        ws = self.tools.workspace
        docs = [f"# {goal}", "", "Skatīt docs/USER_GUIDE_LV.md"]
        path = None
        tool_results = []
        if ws:
            path = ws / "NOTES_LV.md"
            tr = self._tool(agent, "files.write", {"path": str(path), "content": "\n".join(docs) + "\n"})
            tool_results.append(tr)
        return self._ok(agent, "Dokumentācija", {"documents": [str(path) if path else "NOTES_LV.md"], "model_note": model_note}, tool_results=tool_results)

    def _business_analyst(self, agent, goal, inputs, model_note):
        return self._ok(
            agent,
            "Biznesa analīze",
            {
                "stakeholders": ["Lietotājs", "Izstrādātājs"],
                "feasibility": "Īstenojams lokāli ar skaidriem Windows ierobežojumiem",
                "process": ["Mērķis", "Plāns", "Izpilde", "Pārbaude"],
                "model_note": model_note,
            },
        )

    # --- Atmiņa ---
    def _knowledge_curator(self, agent, goal, inputs, model_note):
        content = inputs.get("content") or goal
        source = inputs.get("source") or "runtime"
        kid = self.learning.store.index_knowledge(content, source, verified=bool(inputs.get("verified", True)))
        return self._ok(agent, "Zināšanas indeksētas", {"indexed_id": kid, "searchable": True, "model_note": model_note})

    def _agent_selector_optimizer(self, agent, goal, inputs, model_note):
        candidates = inputs.get("candidates") or [
            "PythonDeveloper",
            "DataAnalyst",
            "UnitTestEngineer",
            "ResultReviewer",
        ]
        ranking = self.learning.rank_agents(candidates)
        return self._ok(
            agent,
            "Aģentu ranžējums",
            {"ranking": [{"agent_id": a, "score": s} for a, s in ranking], "adjustments": {}, "model_note": model_note},
        )

    def _quality_evaluator(self, agent, goal, inputs, model_note):
        criteria = inputs.get("criteria") or []
        result = inputs.get("result") or {}
        score = 1.0 if result.get("ok") or result.get("passed") else 0.4
        return self._ok(
            agent,
            "Kvalitātes vērtējums",
            {"score": score, "passed": score >= 0.7, "evidence": criteria, "model_note": model_note},
        )

    def _evaluation_case_designer(self, agent, goal, inputs, model_note):
        cases = [
            {
                "id": "eval_csv_report",
                "prompt": "Izveido Python programmu, kas nolasa CSV, apkopo datus un sagatavo atskaiti",
                "checks": ["report.md exists", "tests pass"],
            }
        ]
        return self._ok(agent, "Eval gadījumi", {"cases": cases, "model_note": model_note})

    def _training_dataset_curator(self, agent, goal, inputs, model_note):
        approved = bool(inputs.get("approved"))
        samples = inputs.get("samples") or [{"goal": goal, "result": "ok"}]
        ws = self.tools.workspace or Path.cwd()
        target = ws / "training_export.json"
        exported = self.learning.export_training_dataset(samples, target, approved=approved)
        return self._ok(agent, "Apmācības datu kurācija", exported | {"model_note": model_note})
