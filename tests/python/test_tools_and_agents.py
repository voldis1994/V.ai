from pathlib import Path

import pytest

from mainbrain.agents.runtime import AgentRuntime
from mainbrain.contracts.schemas import ToolRequest
from mainbrain.core.config import Settings
from mainbrain.learning.engine import LearningEngine
from mainbrain.memory.store import MemoryStore
from mainbrain.models.router import ModelRouter
from mainbrain.registry import list_agents
from mainbrain.scheduler.resources import ResourceScheduler
from mainbrain.security.policy import PolicyEngine
from mainbrain.tools.proxy import ToolProxy


@pytest.fixture
def runtime(tmp_path: Path):
    settings = Settings(data_dir=tmp_path / "data", api_token="test")
    settings.ensure_dirs()
    store = MemoryStore(settings.db_path)
    policy = PolicyEngine(tmp_path)
    tools = ToolProxy(policy, tmp_path)
    models = ModelRouter(settings)
    learning = LearningEngine(store)
    scheduler = ResourceScheduler(max_agents=4, max_llm=1, max_browser=1)
    return AgentRuntime(tools, models, learning, scheduler), tmp_path, store


def test_files_roundtrip(runtime):
    rt, ws, _ = runtime
    write = rt.tools.execute(
        ToolRequest(tool="files.write", arguments={"path": str(ws / "a.txt"), "content": "sveiki"})
    )
    assert write.ok
    read = rt.tools.execute(ToolRequest(tool="files.read", arguments={"path": str(ws / "a.txt")}))
    assert read.ok
    assert read.output["content"] == "sveiki"


def test_path_traversal_blocked_by_policy(runtime):
    rt, ws, _ = runtime
    outside = ws.parent / "secret.txt"
    outside.write_text("nope", encoding="utf-8")
    decision = rt.tools.policy.decide(
        ToolRequest(tool="files.delete", arguments={"path": str(outside)})
    )
    assert decision.requires_approval is True


@pytest.mark.asyncio
async def test_all_50_agents_invoke(runtime):
    rt, ws, _ = runtime
    failures = []
    for agent in list_agents():
        result = await rt.invoke(
            agent.id,
            f"Testa uzdevums aģentam {agent.id}",
            inputs={"approved": True, "url": "https://example.com", "content": "zināšana"},
            workspace_path=str(ws),
        )
        if not result.ok:
            # daži aģenti var atgriezt ok=False ja trūkst failu — Python/data ceļš OK
            # bet izsaukumam jābūt bez izņēmuma
            failures.append((agent.id, result.error))
    # Platformas/datu atkarīgie aģenti drīkst atgriezt ok=False bez tilta/failiem
    allowed_fail = {
        "DataAnalyst",
        "BrowserOperator",
        "FormOperator",
        "WindowManager",
        "UIAutomationOperator",
        "ScreenVisionOperator",
        "InputOperator",
        "ApplicationLauncher",
    }
    hard_fail = [f for f in failures if f[0] not in allowed_fail]
    assert hard_fail == [], hard_fail


@pytest.mark.asyncio
async def test_python_inventory_flow(runtime):
    rt, ws, _ = runtime
    created = await rt.invoke("PythonDeveloper", "CSV atskaite", workspace_path=str(ws))
    assert created.ok
    tests = await rt.invoke("UnitTestEngineer", "Palaist testus", workspace_path=str(ws))
    assert tests.ok
    assert tests.verification and tests.verification.passed
    report = await rt.invoke("VisualizationEngineer", "Atskaite", workspace_path=str(ws))
    assert report.ok
    assert (ws / "report.md").exists()


def test_parallel_file_lock(runtime):
    rt, ws, store = runtime
    sched = rt.scheduler
    assert sched.acquire_file(str(ws / "f.txt"), "a")
    assert sched.acquire_file(str(ws / "f.txt"), "b") is False
    sched.release_file(str(ws / "f.txt"), "a")
    assert sched.acquire_file(str(ws / "f.txt"), "b")
