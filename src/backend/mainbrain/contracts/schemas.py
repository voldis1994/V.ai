from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from mainbrain.core.ids import new_id, utc_now


class RiskCategory(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TaskStatus(str, Enum):
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    VERIFYING = "verifying"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"


class ModelRole(str, Enum):
    REASONING = "reasoning"
    CODING = "coding"
    VISION = "vision"
    EMBEDDING = "embedding"
    NONE = "none"


class UserGoal(BaseModel):
    id: str = Field(default_factory=lambda: new_id("goal_"))
    text: str
    language: str = "lv"
    project_id: str | None = None
    workspace_path: str | None = None
    constraints: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    correlation_id: str = Field(default_factory=lambda: new_id("corr_"))


class TaskNode(BaseModel):
    id: str = Field(default_factory=lambda: new_id("task_"))
    title: str
    description: str
    agent_id: str | None = None
    depends_on: list[str] = Field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING
    inputs: dict[str, Any] = Field(default_factory=dict)
    outputs: dict[str, Any] = Field(default_factory=dict)
    artifacts: list[str] = Field(default_factory=list)
    retries: int = 0
    max_retries: int = 2
    idempotency_key: str = Field(default_factory=lambda: new_id("idem_"))
    deadline_at: datetime | None = None
    error: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class Plan(BaseModel):
    id: str = Field(default_factory=lambda: new_id("plan_"))
    goal_id: str
    summary: str
    tasks: list[TaskNode] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    version: int = 1


class AgentIOContract(BaseModel):
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    acceptance_criteria: list[str] = Field(default_factory=list)


class AgentDefinition(BaseModel):
    id: str
    number: int
    name: str
    section: str
    description: str
    responsibilities: list[str]
    model_role: ModelRole = ModelRole.REASONING
    allowed_tools: list[str] = Field(default_factory=list)
    risk_category: RiskCategory = RiskCategory.LOW
    prompt_template: str
    contract: AgentIOContract
    constraints: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        if not value or " " in value:
            raise ValueError("aģenta ID jābūt nestukšam bez atstarpēm")
        return value


class AgentAssignment(BaseModel):
    id: str = Field(default_factory=lambda: new_id("assign_"))
    task_id: str
    agent_id: str
    reason: str
    score: float = 0.0
    model_role: ModelRole = ModelRole.REASONING
    created_at: datetime = Field(default_factory=utc_now)


class ToolRequest(BaseModel):
    id: str = Field(default_factory=lambda: new_id("tool_"))
    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    agent_id: str | None = None
    task_id: str | None = None
    correlation_id: str = Field(default_factory=lambda: new_id("corr_"))
    idempotency_key: str = Field(default_factory=lambda: new_id("idem_"))
    workspace_path: str | None = None
    timeout_sec: int = 120


class PolicyDecision(BaseModel):
    allowed: bool
    requires_approval: bool = False
    reason: str
    risk_category: RiskCategory = RiskCategory.LOW
    redacted_args: dict[str, Any] = Field(default_factory=dict)
    approval_id: str | None = None


class ToolResult(BaseModel):
    request_id: str
    tool: str
    ok: bool
    output: Any = None
    error: str | None = None
    duration_ms: int = 0
    artifacts: list[str] = Field(default_factory=list)
    policy: PolicyDecision | None = None
    created_at: datetime = Field(default_factory=utc_now)


class Artifact(BaseModel):
    id: str = Field(default_factory=lambda: new_id("art_"))
    kind: str
    path: str | None = None
    content_type: str | None = None
    summary: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    verified: bool = False
    created_at: datetime = Field(default_factory=utc_now)


class ProgressEvent(BaseModel):
    id: str = Field(default_factory=lambda: new_id("evt_"))
    correlation_id: str
    event_type: str
    message: str
    task_id: str | None = None
    agent_id: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=utc_now)


class CaptureSession(BaseModel):
    id: str = Field(default_factory=lambda: new_id("cap_"))
    hwnd: int | None = None
    process_name: str | None = None
    status: Literal[
        "live_image",
        "embedded_browser",
        "editor",
        "terminal",
        "log",
        "unavailable",
    ] = "unavailable"
    frame_path: str | None = None
    error: str | None = None
    updated_at: datetime = Field(default_factory=utc_now)


class ApprovalRequest(BaseModel):
    id: str = Field(default_factory=lambda: new_id("appr_"))
    action: str
    paths: list[str] = Field(default_factory=list)
    command: str | None = None
    source: str
    reason: str
    impact: str
    status: Literal["pending", "allowed_once", "allowed_task", "rejected"] = "pending"
    task_id: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    decided_at: datetime | None = None


class VerificationReport(BaseModel):
    id: str = Field(default_factory=lambda: new_id("ver_"))
    task_id: str
    passed: bool
    criteria: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    notes: str = ""
    reviewer_agent_id: str = "ResultReviewer"
    created_at: datetime = Field(default_factory=utc_now)


class ModelHealth(BaseModel):
    role: ModelRole
    available: bool
    provider: str | None = None
    model_name: str | None = None
    base_url: str | None = None
    details: str = ""
    checked_at: datetime = Field(default_factory=utc_now)


class LearningMetric(BaseModel):
    agent_id: str
    success_rate: float = 0.0
    avg_duration_ms: float = 0.0
    retry_count: int = 0
    test_pass_rate: float = 0.0
    resource_usage: dict[str, float] = Field(default_factory=dict)
    manual_approvals: int = 0
    samples: int = 0
    updated_at: datetime = Field(default_factory=utc_now)


class AgentInvokeRequest(BaseModel):
    agent_id: str
    goal: str
    inputs: dict[str, Any] = Field(default_factory=dict)
    workspace_path: str | None = None
    correlation_id: str | None = None


class AgentInvokeResult(BaseModel):
    agent_id: str
    ok: bool
    summary: str
    outputs: dict[str, Any] = Field(default_factory=dict)
    artifacts: list[Artifact] = Field(default_factory=list)
    tool_results: list[ToolResult] = Field(default_factory=list)
    verification: VerificationReport | None = None
    error: str | None = None
    duration_ms: int = 0


class RunGoalRequest(BaseModel):
    text: str
    workspace_path: str | None = None
    project_id: str | None = None
    constraints: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)
    auto_approve_safe: bool = True


class RunGoalResponse(BaseModel):
    goal: UserGoal
    plan: Plan
    status: TaskStatus
    events: list[ProgressEvent] = Field(default_factory=list)
    artifacts: list[Artifact] = Field(default_factory=list)
    verification: VerificationReport | None = None


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"
    workspace_path: str | None = None
    force_execute: bool | None = None


class ChatResponse(BaseModel):
    reply: str
    mode: str = "chat"  # chat | execute | act
    session_id: str = "default"
    goal_status: str | None = None
    messages: list[ChatMessage] = Field(default_factory=list)
    # Fiziskā UI darbība Desktop klientam
    ui_action: str | None = None  # open_browser | open_editor | open_path | open_app | none
    open_url: str | None = None
    open_path: str | None = None
    focus: str | None = None  # home | browser | editor | terminal | live
    speak_text: str | None = None  # ja aizpildīts — Desktop/backends runā skaļi
    image_path: str | None = None  # kameras/sejas kadrs Dzīvajam skatam
