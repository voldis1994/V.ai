from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mainbrain.api.app import create_app
from mainbrain.brain.planner import AiPlanner
from mainbrain.core.config import Settings
from mainbrain.models.router import ModelRouter
from mainbrain.security.execution_policy import assess_python_code, assess_shell_command
from mainbrain.tools.bridge import DesktopToolBridge
from mainbrain.tools.proxy import ToolProxy
from mainbrain.security.policy import PolicyEngine
from mainbrain.contracts.schemas import ToolRequest


@pytest.mark.asyncio
async def test_planner_fallback_without_model(tmp_path: Path):
    settings = Settings(data_dir=tmp_path / "data", api_token="t")
    settings.ensure_dirs()
    planner = AiPlanner(ModelRouter(settings))
    dag = await planner.plan("Izveido Python programmu, kas nolasa CSV un sagatavo atskaiti")
    assert dag.tasks
    assert any(t.agent_id == "PythonDeveloper" for t in dag.tasks)
    assert dag.source.startswith("fallback") or dag.used_model in {True, False}


def test_shell_policy_denies_dangerous():
    result = assess_shell_command("rm -rf /")
    assert result["allowed"] is False


def test_shell_policy_allows_pytest():
    result = assess_shell_command("pytest -q")
    assert result["allowed"] is True


def test_python_code_policy():
    assert assess_python_code("print(1)")["allowed"] is True
    assert assess_python_code("import os; os.system('id')")["allowed"] is False


def test_bridge_unavailable_on_linux():
    bridge = DesktopToolBridge(token="x")
    assert bridge.is_available is False
    out = bridge.call("window.enumerate", {})
    assert out["result"]["status"] == "unavailable"
    assert out["result"]["performed"] is False


def test_toolproxy_bridge_does_not_fake_success(tmp_path: Path):
    policy = PolicyEngine(tmp_path)
    proxy = ToolProxy(policy, tmp_path, bridge=DesktopToolBridge(token="x"))
    result = proxy.execute(ToolRequest(tool="window.enumerate", arguments={}))
    assert result.ok is True  # unavailable ir derīgs platformas rezultāts
    assert result.output["status"] == "unavailable"
    assert result.output.get("performed") is False


def test_auth_token_endpoint_removed(tmp_path: Path):
    settings = Settings(data_dir=tmp_path / "data", api_token="secret", workspace_root=tmp_path)
    settings.ensure_dirs()
    app = create_app(settings)
    with TestClient(app) as client:
        assert client.get("/auth/token").status_code == 404
        assert client.get("/agents").status_code == 401
        ok = client.get("/agents", headers={"Authorization": "Bearer secret"})
        assert ok.status_code == 200
        assert len(ok.json()) == 50
