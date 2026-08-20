from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from core.contracts import Priority, RiskLevel, TaskStatus


_ALLOWED_RESULT_STATES = frozenset(
    {
        TaskStatus.COMPLETED,
        TaskStatus.FAILED,
        TaskStatus.WAITING_APPROVAL,
    }
)


class AgentContractVersion(str, Enum):
    LEGACY_V1 = "legacy_v1"
    JARVIS_NATIVE_V1 = "jarvis_native_v1"


class AgentContractError(ValueError):
    pass


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


def _require_dict(value: object, field_name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError(f"{field_name} must be a dict")
    return value


@dataclass(frozen=True, slots=True)
class AgentTaskRequest:
    task_id: str
    goal_id: str
    title: str
    objective: str
    required_capabilities: tuple[str, ...]
    operation: str | None
    priority: Priority
    risk_level: RiskLevel
    requires_approval: bool
    input_data: dict[str, Any] = field(default_factory=dict)
    dependency_results: dict[str, dict[str, Any]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for field_name in ("task_id", "goal_id", "title", "objective"):
            _require_non_blank(getattr(self, field_name), field_name)
        _require_optional_non_blank(self.operation, "operation")
        _require_string_tuple(
            self.required_capabilities,
            "required_capabilities",
            allow_empty=False,
        )
        if not isinstance(self.priority, Priority):
            raise TypeError("priority must be a Priority")
        if not isinstance(self.risk_level, RiskLevel):
            raise TypeError("risk_level must be a RiskLevel")
        if not isinstance(self.requires_approval, bool):
            raise TypeError("requires_approval must be a bool")
        _require_dict(self.input_data, "input_data")
        dependencies = _require_dict(
            self.dependency_results,
            "dependency_results",
        )
        for task_id, result in dependencies.items():
            _require_non_blank(task_id, "dependency_results key")
            if not isinstance(result, dict):
                raise TypeError(
                    "dependency_results values must be dict instances"
                )


@dataclass(frozen=True, slots=True)
class AgentTaskResult:
    task_id: str
    status: TaskStatus
    output_data: dict[str, Any]
    summary: str
    error: str | None
    risk_level: RiskLevel
    requires_approval: bool

    def __post_init__(self) -> None:
        _require_non_blank(self.task_id, "task_id")
        _require_non_blank(self.summary, "summary")
        if not isinstance(self.status, TaskStatus):
            raise TypeError("status must be a TaskStatus")
        if self.status not in _ALLOWED_RESULT_STATES:
            raise ValueError(
                f"invalid native result status: {self.status.value}"
            )
        _require_dict(self.output_data, "output_data")
        if not isinstance(self.risk_level, RiskLevel):
            raise TypeError("risk_level must be a RiskLevel")
        if not isinstance(self.requires_approval, bool):
            raise TypeError("requires_approval must be a bool")

        if self.status == TaskStatus.FAILED:
            if self.error is None:
                raise ValueError("error cannot be blank")
            _require_non_blank(self.error, "error")
        elif self.error is not None:
            raise ValueError(
                f"{self.status.value} result cannot include an error"
            )
