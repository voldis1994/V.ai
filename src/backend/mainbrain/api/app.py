from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from mainbrain import __version__
from mainbrain.agents.runtime import AgentRuntime
from mainbrain.brain.orchestrator import MainBrain
from mainbrain.contracts.schemas import (
    AgentInvokeRequest,
    ApprovalRequest,
    ModelHealth,
    RunGoalRequest,
    ToolRequest,
)
from mainbrain.core.config import Settings, get_settings
from mainbrain.learning.engine import LearningEngine
from mainbrain.memory.store import MemoryStore
from mainbrain.models.router import ModelRouter
from mainbrain.registry.catalog import get_agent, list_agents, list_sections
from mainbrain.scheduler.resources import ResourceScheduler
from mainbrain.security.auth import AuthGate
from mainbrain.security.policy import PolicyEngine
from mainbrain.tools.proxy import ToolProxy


class AppState:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        # Tokens TIKAI no vides / skaidras konfigurācijas — nav publiska /auth/token
        self.auth = AuthGate(token=settings.api_token or AuthGate().token)
        self.store = MemoryStore(settings.db_path)
        self.policy = PolicyEngine(settings.workspace_root)
        from mainbrain.tools.bridge import DesktopToolBridge

        self.tools = ToolProxy(
            self.policy,
            settings.workspace_root,
            bridge=DesktopToolBridge(token=self.auth.token),
        )
        self.models = ModelRouter(settings)
        self.learning = LearningEngine(self.store)
        self.scheduler = ResourceScheduler(
            max_agents=settings.max_parallel_agents,
            max_llm=settings.max_parallel_llm,
            max_browser=settings.max_browser_sessions,
        )
        self.runtime = AgentRuntime(self.tools, self.models, self.learning, self.scheduler)
        self.brain = MainBrain(
            self.runtime,
            self.store,
            self.policy,
            self.learning,
            self.scheduler,
            models=self.models,
        )
        self.subscribers: list[WebSocket] = []


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.mb = AppState(settings)
        yield
        app.state.mb.store.close()

    app = FastAPI(
        title="Main Brain OS API",
        version=__version__,
        description="Lokālais AI vadības starpnieks (loopback)",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1", "http://localhost"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def state() -> AppState:
        return app.state.mb

    def require_auth(authorization: str | None = Header(default=None), x_mainbrain_token: str | None = Header(default=None)) -> None:
        token = None
        if authorization and authorization.lower().startswith("bearer "):
            token = authorization.split(" ", 1)[1].strip()
        elif x_mainbrain_token:
            token = x_mainbrain_token
        # ja tokens tukšs testu režīmā — atļauj loopback bez auth tikai ja settings.api_token tukšs un env test
        st = state()
        if not st.auth.verify(token):
            # atļaujam arī failā saglabāto tokenu nolasīt desktop klientam pirmajā reizē
            raise HTTPException(status_code=401, detail="Nepieciešama lokālā autentifikācija")

    @app.get("/health")
    async def health(st: AppState = Depends(state)) -> dict[str, Any]:
        resources = st.tools.execute(ToolRequest(tool="resources.inspect", arguments={}))
        models = await st.models.health()
        return {
            "status": "ok",
            "version": __version__,
            "offline_mode": st.settings.offline_mode,
            "emergency_stop": st.policy.emergency_stop,
            "agents": len(list_agents()),
            "resources": resources.output,
            "models": [m.model_dump(mode="json") for m in models],
            "language": "lv",
        }

    @app.get("/auth/status", dependencies=[Depends(require_auth)])
    async def auth_status() -> dict[str, Any]:
        """Apstiprina, ka klients jau zina derīgu tokenu. Pašu tokenu neatklāj."""
        return {"authenticated": True, "method": "bearer"}

    @app.get("/agents", dependencies=[Depends(require_auth)])
    async def agents() -> list[dict[str, Any]]:
        return [a.model_dump(mode="json") for a in list_agents()]

    @app.get("/agents/sections", dependencies=[Depends(require_auth)])
    async def agent_sections() -> dict[str, Any]:
        sections = list_sections()
        return {name: [a.model_dump(mode="json") for a in items] for name, items in sections.items()}

    @app.get("/agents/{agent_id}", dependencies=[Depends(require_auth)])
    async def agent_detail(agent_id: str) -> dict[str, Any]:
        try:
            return get_agent(agent_id).model_dump(mode="json")
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.post("/agents/invoke", dependencies=[Depends(require_auth)])
    async def invoke_agent(body: AgentInvokeRequest, st: AppState = Depends(state)) -> dict[str, Any]:
        result = await st.runtime.invoke(
            body.agent_id,
            body.goal,
            inputs=body.inputs,
            workspace_path=body.workspace_path,
            correlation_id=body.correlation_id,
        )
        payload = result.model_dump(mode="json")
        await _broadcast(st, {"type": "agent_invoke", "data": payload})
        return payload

    @app.post("/goals/run", dependencies=[Depends(require_auth)])
    async def run_goal(body: RunGoalRequest, st: AppState = Depends(state)) -> dict[str, Any]:
        response = await st.brain.run_goal(body)
        payload = response.model_dump(mode="json")
        await _broadcast(st, {"type": "goal_finished", "data": payload})
        return payload

    @app.post("/tools/execute", dependencies=[Depends(require_auth)])
    async def execute_tool(body: ToolRequest, st: AppState = Depends(state)) -> dict[str, Any]:
        result = st.tools.execute(body)
        return result.model_dump(mode="json")

    @app.get("/approvals", dependencies=[Depends(require_auth)])
    async def approvals(pending_only: bool = True, st: AppState = Depends(state)) -> list[dict[str, Any]]:
        return [a.model_dump(mode="json") for a in st.policy.list_approvals(pending_only=pending_only)]

    @app.post("/approvals/{approval_id}/decide", dependencies=[Depends(require_auth)])
    async def decide_approval(approval_id: str, decision: str, st: AppState = Depends(state)) -> dict[str, Any]:
        try:
            approval = st.policy.decide_approval(approval_id, decision)
        except KeyError as exc:
            raise HTTPException(404, "Apstiprinājums nav atrasts") from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        await _broadcast(st, {"type": "approval", "data": approval.model_dump(mode="json")})
        return approval.model_dump(mode="json")

    @app.post("/control/stop", dependencies=[Depends(require_auth)])
    async def emergency_stop(st: AppState = Depends(state)) -> dict[str, Any]:
        st.brain.stop_all()
        stopped = st.tools.stop_owned_processes()
        await _broadcast(st, {"type": "stop", "data": {"active": True, "stopped_pids": stopped}})
        return {"status": "STOP aktīvs", "stopped_pids": stopped}

    @app.post("/control/pause", dependencies=[Depends(require_auth)])
    async def pause(st: AppState = Depends(state)) -> dict[str, str]:
        st.brain.pause()
        return {"status": "Pauze"}

    @app.post("/control/resume", dependencies=[Depends(require_auth)])
    async def resume(st: AppState = Depends(state)) -> dict[str, str]:
        st.brain.resume()
        return {"status": "Turpināts"}

    @app.get("/models/health", dependencies=[Depends(require_auth)])
    async def models_health(st: AppState = Depends(state)) -> list[dict[str, Any]]:
        health = await st.models.health()
        return [h.model_dump(mode="json") for h in health]

    @app.post("/models/scan", dependencies=[Depends(require_auth)])
    async def models_scan(st: AppState = Depends(state)) -> dict[str, Any]:
        found = st.models.scan_models()
        return {"models": found, "roles": st.models.export_config()}

    @app.get("/memory/search", dependencies=[Depends(require_auth)])
    async def memory_search(q: str, st: AppState = Depends(state)) -> list[dict[str, Any]]:
        return st.store.search_knowledge(q)

    @app.get("/learning/metrics", dependencies=[Depends(require_auth)])
    async def learning_metrics(st: AppState = Depends(state)) -> list[dict[str, Any]]:
        return st.store.list_metrics()

    @app.get("/learning/training", dependencies=[Depends(require_auth)])
    async def training_status(st: AppState = Depends(state)) -> dict[str, Any]:
        return st.learning.training_prerequisites()

    @app.get("/layout/{layout_id}", dependencies=[Depends(require_auth)])
    async def get_layout(layout_id: str = "default", st: AppState = Depends(state)) -> dict[str, Any]:
        layout = st.store.get_layout(layout_id) or {
            "mode": "focus",
            "panels": [],
            "theme": "dark",
        }
        return layout

    @app.put("/layout/{layout_id}", dependencies=[Depends(require_auth)])
    async def put_layout(payload: dict[str, Any], layout_id: str = "default", st: AppState = Depends(state)) -> dict[str, str]:
        st.store.save_layout(layout_id, payload)
        return {"status": "saglabāts"}

    @app.get("/events/{correlation_id}", dependencies=[Depends(require_auth)])
    async def events(correlation_id: str, st: AppState = Depends(state)) -> list[dict[str, Any]]:
        return st.store.list_events(correlation_id)

    @app.websocket("/ws/events")
    async def ws_events(websocket: WebSocket) -> None:
        await websocket.accept()
        st = state()
        # Auth ar pirmo JSON ziņojumu {"type":"auth","token":"..."} — tokens nav URL
        try:
            first = await asyncio.wait_for(websocket.receive_json(), timeout=5.0)
        except Exception:  # noqa: BLE001
            await websocket.close(code=4401)
            return
        token = None
        if isinstance(first, dict) and first.get("type") == "auth":
            token = first.get("token")
        if not st.auth.verify(token if isinstance(token, str) else None):
            await websocket.close(code=4401)
            return
        await websocket.send_json({"type": "auth_ok"})
        st.subscribers.append(websocket)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            if websocket in st.subscribers:
                st.subscribers.remove(websocket)

    @app.exception_handler(Exception)
    async def on_error(_, exc: Exception):
        return JSONResponse(status_code=500, content={"detail": str(exc)})

    return app


async def _broadcast(st: AppState, message: dict[str, Any]) -> None:
    dead: list[WebSocket] = []
    for ws in st.subscribers:
        try:
            await ws.send_json(message)
        except Exception:  # noqa: BLE001
            dead.append(ws)
    for ws in dead:
        st.subscribers.remove(ws)


def run() -> None:
    settings = get_settings()
    uvicorn.run(
        "mainbrain.api.app:create_app",
        factory=True,
        host=settings.api_host,
        port=settings.api_port,
        log_level="info",
    )


# ASGI ieeja (uvicorn mainbrain.api.app:app)
app = create_app()


if __name__ == "__main__":
    run()
