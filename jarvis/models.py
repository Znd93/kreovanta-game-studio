from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from core.contracts import Priority, RiskLevel, TaskStatus
from jarvis.agent_contract import AgentContractVersion


def _new_id() -> str:
    return str(uuid4())


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _require_non_blank(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if not value.strip():
        raise ValueError(f"{field_name} cannot be blank")
    return value


def _require_optional_non_blank(value: object, field_name: str) -> None:
    if value is not None:
        _require_non_blank(value, field_name)


def _require_string_tuple(
    values: object,
    field_name: str,
    *,
    allow_empty: bool,
) -> tuple[str, ...]:
    if not isinstance(values, tuple):
        raise TypeError(f"{field_name} must be a tuple")
    if not allow_empty and not values:
        raise ValueError(f"{field_name} cannot be empty")
    for value in values:
        _require_non_blank(value, field_name)
    return values


class OrchestratorState(str, Enum):
    IDLE = "idle"
    PLANNING = "planning"
    EXECUTING = "executing"
    WAITING_APPROVAL = "waiting_approval"
    FAILED = "failed"
    COMPLETED = "completed"


class ApprovalDecision(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"
    CHANGE = "change"


class ApprovalDisposition(str, Enum):
    CONTINUE = "continue"
    CONTINUE_AUDIT = "continue_audit"
    WAIT = "wait"


@dataclass(slots=True)
class JarvisTask:
    plan_key: str
    goal_id: str
    title: str
    objective: str
    required_capabilities: tuple[str, ...]
    id: str = field(default_factory=_new_id)
    parent_id: str | None = None
    operation: str | None = None
    dependencies: tuple[str, ...] = ()
    assigned_agent: str | None = None
    status: TaskStatus = TaskStatus.PENDING
    priority: Priority = Priority.NORMAL
    risk_level: RiskLevel = RiskLevel.LOW
    requires_approval: bool = False
    input_data: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    created_at: datetime = field(default_factory=_utc_now)
    started_at: datetime | None = None
    completed_at: datetime | None = None

    def __post_init__(self) -> None:
        for field_name in ("id", "plan_key", "goal_id", "title", "objective"):
            _require_non_blank(getattr(self, field_name), field_name)
        _require_optional_non_blank(self.parent_id, "parent_id")
        _require_optional_non_blank(self.operation, "operation")
        _require_optional_non_blank(self.assigned_agent, "assigned_agent")
        _require_string_tuple(
            self.required_capabilities,
            "required_capabilities",
            allow_empty=False,
        )
        dependencies = _require_string_tuple(
            self.dependencies,
            "dependencies",
            allow_empty=True,
        )
        if self.id in dependencies:
            raise ValueError("dependencies cannot include task id")
        if not isinstance(self.status, TaskStatus):
            raise TypeError("status must be a TaskStatus")
        if not isinstance(self.priority, Priority):
            raise TypeError("priority must be a Priority")
        if not isinstance(self.risk_level, RiskLevel):
            raise TypeError("risk_level must be a RiskLevel")
        if not isinstance(self.requires_approval, bool):
            raise TypeError("requires_approval must be a bool")
        if not isinstance(self.input_data, dict):
            raise TypeError("input_data must be a dict")
        if not isinstance(self.result, dict):
            raise TypeError("result must be a dict")
        _require_optional_non_blank(self.error, "error")
        if not isinstance(self.created_at, datetime):
            raise TypeError("created_at must be a datetime")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        for field_name in ("started_at", "completed_at"):
            value = getattr(self, field_name)
            if value is not None and not isinstance(value, datetime):
                raise TypeError(f"{field_name} must be a datetime or None")


@dataclass(slots=True)
class ExecutionPlan:
    goal_id: str
    goal: str
    summary: str
    tasks: tuple[JarvisTask, ...]
    requires_founder_approval: bool = False

    def __post_init__(self) -> None:
        _require_non_blank(self.goal_id, "goal_id")
        _require_non_blank(self.goal, "goal")
        _require_non_blank(self.summary, "summary")
        if not isinstance(self.tasks, tuple):
            raise TypeError("tasks must be a tuple")
        if not self.tasks:
            raise ValueError("tasks cannot be empty")
        if not all(isinstance(task, JarvisTask) for task in self.tasks):
            raise TypeError("tasks must contain JarvisTask instances")
        if not isinstance(self.requires_founder_approval, bool):
            raise TypeError("requires_founder_approval must be a bool")

        seen_keys: set[str] = set()
        for task in self.tasks:
            if task.goal_id != self.goal_id:
                raise ValueError("task goal_id must match plan goal_id")
            if task.plan_key in seen_keys:
                raise ValueError(f"duplicate task plan_key: {task.plan_key}")
            seen_keys.add(task.plan_key)


@dataclass(frozen=True, slots=True)
class AgentRegistration:
    name: str
    agent_class: type
    capabilities: frozenset[str]
    allowed_risk_levels: frozenset[RiskLevel]
    contract_version: AgentContractVersion = AgentContractVersion.LEGACY_V1
    enabled: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_non_blank(self.name, "name")
        if not isinstance(self.agent_class, type):
            raise TypeError("agent_class must be a type")
        if not isinstance(self.capabilities, frozenset):
            raise TypeError("capabilities must be a frozenset")
        if not self.capabilities:
            raise ValueError("capabilities cannot be empty")
        for capability in self.capabilities:
            _require_non_blank(capability, "capabilities")
        if not isinstance(self.allowed_risk_levels, frozenset):
            raise TypeError("allowed_risk_levels must be a frozenset")
        if not self.allowed_risk_levels:
            raise ValueError("allowed_risk_levels cannot be empty")
        if not all(
            isinstance(risk_level, RiskLevel)
            for risk_level in self.allowed_risk_levels
        ):
            raise TypeError("allowed_risk_levels must contain RiskLevel values")
        if not isinstance(self.contract_version, AgentContractVersion):
            raise TypeError(
                "contract_version must be an AgentContractVersion"
            )
        if not isinstance(self.enabled, bool):
            raise TypeError("enabled must be a bool")
        if not isinstance(self.metadata, dict):
            raise TypeError("metadata must be a dict")


@dataclass(frozen=True, slots=True)
class ApprovalEvaluation:
    suggested_risk: RiskLevel
    policy_risk: RiskLevel
    effective_risk: RiskLevel
    disposition: ApprovalDisposition
    requires_explicit_confirmation: bool


@dataclass(slots=True)
class PendingApproval:
    task_id: str
    stage: str
    effective_risk: RiskLevel
    requires_explicit_confirmation: bool
    result_ready: bool = False

    def __post_init__(self) -> None:
        _require_non_blank(self.task_id, "task_id")
        _require_non_blank(self.stage, "stage")


@dataclass(frozen=True, slots=True)
class OrchestratorResult:
    state: OrchestratorState
    goal_id: str
    message: str
    pending_task_id: str | None = None
    error_code: str | None = None
    change_context: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_non_blank(self.goal_id, "goal_id")
        _require_non_blank(self.message, "message")
        _require_optional_non_blank(self.pending_task_id, "pending_task_id")
        _require_optional_non_blank(self.error_code, "error_code")
        if not isinstance(self.change_context, dict):
            raise TypeError("change_context must be a dict")
