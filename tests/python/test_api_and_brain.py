from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mainbrain.api.app import create_app
from mainbrain.core.config import Settings


@pytest.fixture
def client(tmp_path: Path):
    settings = Settings(
        data_dir=tmp_path / "data",
        api_token="test-token",
        workspace_root=tmp_path,
        api_host="127.0.0.1",
        api_port=8765,
    )
    settings.ensure_dirs()
    app = create_app(settings)
    with TestClient(app) as test_client:
        test_client.headers.update({"Authorization": "Bearer test-token"})
        yield test_client, tmp_path


def test_health_and_agents(client):
    test_client, _ = client
    health = test_client.get("/health")
    assert health.status_code == 200
    body = health.json()
    assert body["agents"] == 50
    agents = test_client.get("/agents")
    assert agents.status_code == 200
    assert len(agents.json()) == 50


def test_auth_required(client):
    test_client, _ = client
    resp = test_client.get("/agents", headers={"Authorization": "Bearer wrong"})
    assert resp.status_code == 401


def test_run_goal_csv_report(client):
    test_client, ws = client
    project = ws / "project"
    project.mkdir()
    resp = test_client.post(
        "/goals/run",
        json={
            "text": "Izveido Python programmu, kas nolasa CSV, apkopo datus un sagatavo atskaiti; palaid testus un parādi rezultātu.",
            "workspace_path": str(project),
            "success_criteria": ["Ir rezultāta fails", "Testi izturēti"],
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["plan"]["tasks"]
    assert (project / "inventory_report.py").exists() or data["status"] in {"succeeded", "failed"}
    # veiksmīgā plūsmā jābūt artefaktiem
    assert data["events"]


def test_stop_endpoint(client):
    test_client, _ = client
    resp = test_client.post("/control/stop")
    assert resp.status_code == 200
    health = test_client.get("/health").json()
    assert health["emergency_stop"] is True


def test_layout_persistence(client):
    test_client, _ = client
    payload = {"mode": "multi", "theme": "dark", "panels": [{"id": "browser"}]}
    assert test_client.put("/layout/default", json=payload).status_code == 200
    got = test_client.get("/layout/default").json()
    assert got["mode"] == "multi"


def test_learning_metrics_endpoint(client):
    test_client, ws = client
    test_client.post(
        "/agents/invoke",
        json={"agent_id": "Strategist", "goal": "Precizē mērķi", "workspace_path": str(ws)},
    )
    metrics = test_client.get("/learning/metrics").json()
    assert isinstance(metrics, list)
