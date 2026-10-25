from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from mainbrain.contracts.schemas import ModelRole, TaskNode, TaskStatus
from mainbrain.core.ids import new_id
from mainbrain.models.router import ModelRouter
from mainbrain.registry.catalog import get_agent, list_agents


class PlannedTask(BaseModel):
    id: str
    title: str
    description: str = ""
    agent_id: str
    depends_on: list[str] = Field(default_factory=list)


class PlannedDag(BaseModel):
    summary: str
    tasks: list[PlannedTask]
    assumptions: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    used_model: bool = False
    source: str = "fallback"


ALLOWED_AGENTS = {a.id for a in list_agents()}

FALLBACK_CSV = PlannedDag(
    summary="CSV apkopojums un atskaite",
    source="fallback_csv",
    tasks=[
        PlannedTask(
            id="t1",
            title="Sagatavot Python ETL",
            description="Izveidot CSV lasītāju un apkopojumu",
            agent_id="PythonDeveloper",
        ),
        PlannedTask(
            id="t2",
            title="Analizēt datus",
            description="Aprēķināt metriku",
            agent_id="DataAnalyst",
            depends_on=["t1"],
        ),
        PlannedTask(
            id="t3",
            title="Sagatavot atskaiti",
            description="Rakstīt report.md",
            agent_id="VisualizationEngineer",
            depends_on=["t2"],
        ),
        PlannedTask(
            id="t4",
            title="Palaist testus",
            description="Vienībtesti",
            agent_id="UnitTestEngineer",
            depends_on=["t1"],
        ),
        PlannedTask(
            id="t5",
            title="Pārbaudīt rezultātu",
            description="Neatkarīga pārbaude",
            agent_id="ResultReviewer",
            depends_on=["t3", "t4"],
        ),
    ],
)

FALLBACK_GENERIC = PlannedDag(
    summary="Vispārīga izstrādes plūsma",
    source="fallback_generic",
    tasks=[
        PlannedTask(id="t1", title="Implementācija", description="", agent_id="PythonDeveloper"),
        PlannedTask(
            id="t2",
            title="Testi",
            description="Palaist testus",
            agent_id="UnitTestEngineer",
            depends_on=["t1"],
        ),
        PlannedTask(
            id="t3",
            title="Pārbaude",
            description="Pārbaudīt rezultātu",
            agent_id="ResultReviewer",
            depends_on=["t2"],
        ),
    ],
)


class AiPlanner:
    """LLM plānošana ar tipizētu validāciju + drošām rezerves darbplūsmām."""

    def __init__(self, models: ModelRouter) -> None:
        self.models = models

    async def plan(self, goal_text: str, *, memory_hints: list[str] | None = None) -> PlannedDag:
        fallback = self._fallback_for(goal_text)
        completion = await self.models.complete(
            role=ModelRole.REASONING,
            system=(
                "Tu esi Main Brain uzdevumu plānotājs. Vispirms SAPROTI mērķi, tad plāno. "
                "Atbildi TIKAI ar JSON objektu latviešu valodā. "
                "Shēma: {\"summary\": str, \"tasks\":[{\"id\":str,\"title\":str,\"description\":str,"
                "\"agent_id\":str,\"depends_on\":[str]}], \"assumptions\":[str], \"risks\":[str]}. "
                f"Atļautie agent_id: {sorted(ALLOWED_AGENTS)}. "
                "Katram task.description jābūt konkrētam (ko darīt). "
                "Nedrīkst iekļaut čaulas komandas — tikai uzdevumu grafu. "
                "Ja mērķis neskaidrs — assumptions ieraksti ko pieņēmi."
            ),
            prompt=(
                f"Mērķis: {goal_text}\n"
                f"Atmiņas norādes: {memory_hints or []}\n"
                "1) Īsi interpretē ko lietotājs grib. 2) Izveido minimālu izpildāmu DAG."
            ),
            temperature=0.1,
            max_tokens=1200,
        )
        if not completion.get("ok"):
            fallback.assumptions.append(
                f"Lokālais modelis nav pieejams: {completion.get('error')}; izmantota rezerves plūsma"
            )
            return fallback

        parsed = self._extract_json(str(completion.get("text") or ""))
        if parsed is None:
            fallback.assumptions.append("Modeļa atbilde nebija derīgs JSON; izmantota rezerves plūsma")
            return fallback

        try:
            dag = PlannedDag.model_validate({**parsed, "used_model": True, "source": "llm"})
        except ValidationError as exc:
            fallback.assumptions.append(f"Plāna shēmas validācija neizdevās: {exc}; rezerves plūsma")
            return fallback

        return self._sanitize(dag, fallback)

    def to_task_nodes(self, dag: PlannedDag) -> list[TaskNode]:
        nodes: list[TaskNode] = []
        for t in dag.tasks:
            nodes.append(
                TaskNode(
                    id=t.id or new_id("task_"),
                    title=t.title,
                    description=t.description or t.title,
                    agent_id=t.agent_id,
                    depends_on=list(t.depends_on),
                    status=TaskStatus.PENDING,
                )
            )
        return nodes

    def _sanitize(self, dag: PlannedDag, fallback: PlannedDag) -> PlannedDag:
        cleaned: list[PlannedTask] = []
        ids: set[str] = set()
        for task in dag.tasks:
            if task.agent_id not in ALLOWED_AGENTS:
                # mēģina atrast pēc case-insensitive
                try:
                    task.agent_id = get_agent(task.agent_id).id
                except KeyError:
                    continue
            if not task.id:
                task.id = new_id("t")
            if task.id in ids:
                task.id = new_id("t")
            ids.add(task.id)
            task.depends_on = [d for d in task.depends_on if d != task.id]
            cleaned.append(task)
        if not cleaned:
            return fallback
        # noņem atkarības uz neeksistējošiem ID
        valid = {t.id for t in cleaned}
        for t in cleaned:
            t.depends_on = [d for d in t.depends_on if d in valid]
        # ciklu pārbaude
        if self._has_cycle(cleaned):
            fallback.assumptions.append("LLM DAG saturēja ciklus; izmantota rezerves plūsma")
            return fallback
        dag.tasks = cleaned
        return dag

    def _has_cycle(self, tasks: list[PlannedTask]) -> bool:
        graph = {t.id: list(t.depends_on) for t in tasks}
        state: dict[str, int] = {}

        def dfs(node: str) -> bool:
            state[node] = 1
            for dep in graph.get(node, []):
                if state.get(dep, 0) == 1:
                    return True
                if state.get(dep, 0) == 0 and dfs(dep):
                    return True
            state[node] = 2
            return False

        return any(dfs(n) for n in graph if state.get(n, 0) == 0)

    def _fallback_for(self, goal_text: str) -> PlannedDag:
        text = goal_text.lower()
        if "csv" in text or "atskait" in text or "pārskat" in text:
            return FALLBACK_CSV.model_copy(deep=True)
        if "notepad" in text or "windows" in text and "tekst" in text:
            return PlannedDag(
                summary="Windows Notepad automatizācija",
                source="fallback_notepad",
                tasks=[
                    PlannedTask(
                        id="t1",
                        title="Palaist Notepad",
                        agent_id="ApplicationLauncher",
                        description="Palaist notepad.exe",
                    ),
                    PlannedTask(
                        id="t2",
                        title="Ievadīt tekstu",
                        agent_id="UIAutomationOperator",
                        depends_on=["t1"],
                    ),
                    PlannedTask(
                        id="t3",
                        title="Saglabāt failu",
                        agent_id="UIAutomationOperator",
                        depends_on=["t2"],
                    ),
                    PlannedTask(
                        id="t4",
                        title="Pārbaudīt failu",
                        agent_id="ResultReviewer",
                        depends_on=["t3"],
                    ),
                ],
            )
        return FALLBACK_GENERIC.model_copy(deep=True)

    def _extract_json(self, text: str) -> dict[str, Any] | None:
        text = text.strip()
        if not text:
            return None
        try:
            data = json.loads(text)
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            pass
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return None
        try:
            data = json.loads(match.group(0))
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            return None
