from __future__ import annotations

import asyncio
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from mainbrain.agents.runtime import AgentRuntime
from mainbrain.contracts.schemas import (
    Artifact,
    Plan,
    ProgressEvent,
    RunGoalRequest,
    RunGoalResponse,
    TaskNode,
    TaskStatus,
    UserGoal,
    VerificationReport,
)
from mainbrain.core.ids import new_id, utc_now
from mainbrain.learning.engine import LearningEngine
from mainbrain.memory.store import MemoryStore
from mainbrain.scheduler.resources import ResourceScheduler
from mainbrain.security.policy import PolicyEngine


class BrainState(TypedDict, total=False):
    goal: dict[str, Any]
    plan: dict[str, Any]
    events: list[dict[str, Any]]
    artifacts: list[dict[str, Any]]
    verification: dict[str, Any] | None
    status: str
    error: str | None


class MainBrain:
    """Orķestrēta izpildes sistēma ar DAG un LangGraph kontrolpunktiem."""

    def __init__(
        self,
        runtime: AgentRuntime,
        store: MemoryStore,
        policy: PolicyEngine,
        learning: LearningEngine,
        scheduler: ResourceScheduler,
    ) -> None:
        self.runtime = runtime
        self.store = store
        self.policy = policy
        self.learning = learning
        self.scheduler = scheduler
        self._paused = False
        self._cancelled: set[str] = set()
        self._graph = self._build_graph()

    def _build_graph(self):
        # Mezglu nosaukumi nedrīkst sakrist ar BrainState atslēgām (LangGraph ierobežojums).
        graph = StateGraph(BrainState)
        graph.add_node("node_analyze", self._node_analyze)
        graph.add_node("node_plan", self._node_plan)
        graph.add_node("node_execute", self._node_execute)
        graph.add_node("node_verify", self._node_verify)
        graph.add_node("node_memory", self._node_memory)
        graph.set_entry_point("node_analyze")
        graph.add_edge("node_analyze", "node_plan")
        graph.add_edge("node_plan", "node_execute")
        graph.add_edge("node_execute", "node_verify")
        graph.add_edge("node_verify", "node_memory")
        graph.add_edge("node_memory", END)
        return graph.compile()

    async def run_goal(self, request: RunGoalRequest) -> RunGoalResponse:
        if self.policy.emergency_stop:
            raise RuntimeError("Ārkārtas STOP ir aktīvs")
        if request.workspace_path:
            self.runtime.tools.set_workspace(request.workspace_path)
            self.policy.set_workspace(request.workspace_path)

        goal = UserGoal(
            text=request.text,
            project_id=request.project_id,
            workspace_path=request.workspace_path,
            constraints=request.constraints,
            success_criteria=request.success_criteria,
        )
        self.store.save_json("goals", goal.id, goal.model_dump(mode="json"), created_at=goal.created_at.isoformat())
        initial: BrainState = {
            "goal": goal.model_dump(mode="json"),
            "events": [],
            "artifacts": [],
            "status": TaskStatus.RUNNING.value,
            "verification": None,
            "error": None,
        }
        final = await self._graph.ainvoke(initial)
        plan = Plan.model_validate(final["plan"])
        events = [ProgressEvent.model_validate(e) for e in final.get("events", [])]
        artifacts = [Artifact.model_validate(a) for a in final.get("artifacts", [])]
        verification = (
            VerificationReport.model_validate(final["verification"])
            if final.get("verification")
            else None
        )
        status = TaskStatus(final.get("status", TaskStatus.FAILED.value))
        return RunGoalResponse(
            goal=goal,
            plan=plan,
            status=status,
            events=events,
            artifacts=artifacts,
            verification=verification,
        )

    def pause(self) -> None:
        self._paused = True

    def resume(self) -> None:
        self._paused = False
        self.policy.resume()

    def cancel(self, correlation_id: str) -> None:
        self._cancelled.add(correlation_id)

    def stop_all(self) -> None:
        self.policy.stop()

    async def _wait_if_paused(self) -> None:
        while self._paused and not self.policy.emergency_stop:
            await asyncio.sleep(0.05)

    async def _node_analyze(self, state: BrainState) -> BrainState:
        goal = UserGoal.model_validate(state["goal"])
        await self._wait_if_paused()
        result = await self.runtime.invoke(
            "Strategist",
            goal.text,
            inputs={"success_criteria": goal.success_criteria},
            workspace_path=goal.workspace_path,
            correlation_id=goal.correlation_id,
        )
        event = ProgressEvent(
            correlation_id=goal.correlation_id,
            event_type="analyze",
            message="Prasību analīze pabeigta",
            agent_id="Strategist",
            data=result.outputs,
        )
        self.store.add_event(event)
        events = list(state.get("events", []))
        events.append(event.model_dump(mode="json"))
        return {**state, "events": events}

    async def _node_plan(self, state: BrainState) -> BrainState:
        goal = UserGoal.model_validate(state["goal"])
        await self._wait_if_paused()
        req = await self.runtime.invoke(
            "RequirementsPlanner",
            goal.text,
            workspace_path=goal.workspace_path,
            correlation_id=goal.correlation_id,
        )
        dag = req.outputs.get("dag") or []
        tasks: list[TaskNode] = []
        for node in dag:
            tasks.append(
                TaskNode(
                    id=str(node.get("id") or new_id("task_")),
                    title=str(node.get("title") or "Uzdevums"),
                    description=str(node.get("title") or ""),
                    agent_id=node.get("agent"),
                    depends_on=list(node.get("depends_on") or []),
                    status=TaskStatus.PENDING,
                )
            )
        # ja DAG tukšs — minimālais ceļš
        if not tasks:
            tasks = [
                TaskNode(id="t1", title="Implementācija", description=goal.text, agent_id="PythonDeveloper"),
                TaskNode(
                    id="t2",
                    title="Testi",
                    description="Palaist testus",
                    agent_id="UnitTestEngineer",
                    depends_on=["t1"],
                ),
                TaskNode(
                    id="t3",
                    title="Pārbaude",
                    description="Pārbaudīt rezultātu",
                    agent_id="ResultReviewer",
                    depends_on=["t2"],
                ),
            ]
        # optimizē aģentu izvēli
        ranking = dict(self.learning.rank_agents([t.agent_id for t in tasks if t.agent_id]))
        for task in tasks:
            if task.agent_id and task.agent_id in ranking:
                task.inputs["selection_score"] = ranking[task.agent_id]
        plan = Plan(goal_id=goal.id, summary=req.outputs.get("functional", [goal.text])[0], tasks=tasks)
        self.store.save_json(
            "plans",
            plan.id,
            plan.model_dump(mode="json"),
            goal_id=goal.id,
            created_at=plan.created_at.isoformat(),
        )
        event = ProgressEvent(
            correlation_id=goal.correlation_id,
            event_type="plan",
            message=f"Plāns ar {len(tasks)} uzdevumiem",
            agent_id="RequirementsPlanner",
            data={"plan_id": plan.id},
        )
        self.store.add_event(event)
        events = list(state.get("events", []))
        events.append(event.model_dump(mode="json"))
        return {**state, "plan": plan.model_dump(mode="json"), "events": events}

    async def _node_execute(self, state: BrainState) -> BrainState:
        goal = UserGoal.model_validate(state["goal"])
        plan = Plan.model_validate(state["plan"])
        events = list(state.get("events", []))
        artifacts: list[dict[str, Any]] = list(state.get("artifacts", []))
        outputs_by_task: dict[str, dict[str, Any]] = {}

        pending = {t.id: t for t in plan.tasks}
        while pending:
            if self.policy.emergency_stop or goal.correlation_id in self._cancelled:
                for task in pending.values():
                    task.status = TaskStatus.CANCELLED
                break
            await self._wait_if_paused()

            ready = [
                t
                for t in pending.values()
                if all(dep not in pending and outputs_by_task.get(dep, {}).get("ok", True) for dep in t.depends_on)
            ]
            # atkarīgie, kuru dep failed — fail
            blocked = []
            for t in list(pending.values()):
                failed_dep = any(outputs_by_task.get(dep, {}).get("ok") is False for dep in t.depends_on)
                if failed_dep:
                    t.status = TaskStatus.FAILED
                    t.error = "Atkarīgais uzdevums neizdevās"
                    blocked.append(t.id)
            for bid in blocked:
                pending.pop(bid, None)

            if not ready:
                if pending:
                    # deadlock aizsardzība
                    for t in pending.values():
                        t.status = TaskStatus.FAILED
                        t.error = "Neizdevās atrisināt atkarības"
                    pending.clear()
                break

            async def _run_one(task: TaskNode) -> tuple[TaskNode, Any]:
                task.status = TaskStatus.RUNNING
                task.started_at = utc_now()
                agent_id = task.agent_id or "PythonDeveloper"
                # failu bloķēšana vienkāršam konfliktu gadījumam
                lock_path = str((goal.workspace_path or "") + ":" + task.title)
                if not self.scheduler.acquire_file(lock_path, task.id):
                    await asyncio.sleep(0.05)
                try:
                    result = await self.runtime.invoke(
                        agent_id,
                        f"{goal.text}\nUzdevums: {task.title}",
                        inputs={
                            "task_id": task.id,
                            "prior": outputs_by_task,
                            **task.inputs,
                        },
                        workspace_path=goal.workspace_path,
                        correlation_id=goal.correlation_id,
                    )
                finally:
                    self.scheduler.release_file(lock_path, task.id)
                return task, result

            results = await asyncio.gather(*[_run_one(t) for t in ready])
            for task, result in results:
                task.finished_at = utc_now()
                task.outputs = result.outputs
                task.status = TaskStatus.SUCCEEDED if result.ok else TaskStatus.FAILED
                if not result.ok:
                    task.error = result.error
                    if task.retries < task.max_retries:
                        task.retries += 1
                        task.status = TaskStatus.PENDING
                        task.error = None
                        continue
                outputs_by_task[task.id] = {"ok": result.ok, "outputs": result.outputs, "agent_id": result.agent_id}
                for art in result.artifacts:
                    artifacts.append(art.model_dump(mode="json"))
                event = ProgressEvent(
                    correlation_id=goal.correlation_id,
                    event_type="task",
                    message=f"{task.title}: {'OK' if result.ok else 'KĻŪDA'}",
                    task_id=task.id,
                    agent_id=result.agent_id,
                    data={"summary": result.summary},
                )
                self.store.add_event(event)
                events.append(event.model_dump(mode="json"))
                self.store.save_json(
                    "tasks",
                    task.id,
                    task.model_dump(mode="json"),
                    plan_id=plan.id,
                    status=task.status.value,
                    updated_at=utc_now().isoformat(),
                )
                if task.status != TaskStatus.PENDING:
                    pending.pop(task.id, None)

        plan.tasks = list(plan.tasks)
        status = TaskStatus.SUCCEEDED
        if any(t.status == TaskStatus.FAILED for t in plan.tasks):
            status = TaskStatus.FAILED
        if any(t.status == TaskStatus.CANCELLED for t in plan.tasks):
            status = TaskStatus.CANCELLED
        return {
            **state,
            "plan": plan.model_dump(mode="json"),
            "events": events,
            "artifacts": artifacts,
            "status": status.value,
            "outputs_by_task": outputs_by_task,  # type: ignore[typeddict-item]
        }

    async def _node_verify(self, state: BrainState) -> BrainState:
        goal = UserGoal.model_validate(state["goal"])
        await self._wait_if_paused()
        tests_ok = False
        for art in state.get("artifacts", []):
            if art.get("kind") == "report" or str(art.get("path", "")).endswith("report.md"):
                tests_ok = True
        # palaist ResultReviewer
        review = await self.runtime.invoke(
            "ResultReviewer",
            goal.text,
            inputs={
                "artifacts": state.get("artifacts", []),
                "criteria": goal.success_criteria
                or ["Ir rezultāta fails", "Uzdevumi pabeigti bez kritiskām kļūdām"],
                "tests_ok": tests_ok or state.get("status") == TaskStatus.SUCCEEDED.value,
                "task_id": goal.id,
            },
            workspace_path=goal.workspace_path,
            correlation_id=goal.correlation_id,
        )
        verification = review.verification.model_dump(mode="json") if review.verification else {
            "passed": review.ok,
            "task_id": goal.id,
            "criteria": [],
            "evidence": [],
            "notes": review.summary,
            "reviewer_agent_id": "ResultReviewer",
            "created_at": utc_now().isoformat(),
            "id": new_id("ver_"),
        }
        event = ProgressEvent(
            correlation_id=goal.correlation_id,
            event_type="verify",
            message="Neatkarīga pārbaude pabeigta",
            agent_id="ResultReviewer",
            data=verification,
        )
        self.store.add_event(event)
        events = list(state.get("events", []))
        events.append(event.model_dump(mode="json"))
        status = state.get("status", TaskStatus.FAILED.value)
        if not verification.get("passed") and status == TaskStatus.SUCCEEDED.value:
            status = TaskStatus.FAILED.value
        return {**state, "verification": verification, "events": events, "status": status}

    async def _node_memory(self, state: BrainState) -> BrainState:
        goal = UserGoal.model_validate(state["goal"])
        await self.runtime.invoke(
            "KnowledgeCurator",
            goal.text,
            inputs={
                "content": f"Mērķis: {goal.text}; statuss: {state.get('status')}",
                "source": goal.id,
                "verified": state.get("status") == TaskStatus.SUCCEEDED.value,
            },
            workspace_path=goal.workspace_path,
            correlation_id=goal.correlation_id,
        )
        event = ProgressEvent(
            correlation_id=goal.correlation_id,
            event_type="memory",
            message="Rezultāts saglabāts atmiņā",
            agent_id="KnowledgeCurator",
        )
        self.store.add_event(event)
        events = list(state.get("events", []))
        events.append(event.model_dump(mode="json"))
        return {**state, "events": events}
