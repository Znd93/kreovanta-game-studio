from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from core.contracts import AgentMessage, MessageKind, Priority, RiskLevel, TaskStatus


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

_REQUEST_PAYLOAD_KEYS = frozenset(
    {
        "contract_version",
        "task_id",
        "goal_id",
        "title",
        "required_capabilities",
        "operation",
        "input_data",
        "dependency_results",
    }
)

_RESULT_PAYLOAD_KEYS = frozenset(
    {
        "contract_version",
        "task_id",
        "summary",
        "output_data",
        "error",
    }
)

_RESULT_KIND_BY_STATUS = {
    TaskStatus.COMPLETED: MessageKind.RESULT,
    TaskStatus.FAILED: MessageKind.ERROR,
    TaskStatus.WAITING_APPROVAL: MessageKind.APPROVAL_REQUEST,
}


def _require_exact_payload_keys(
    payload: dict[str, Any],
    expected: frozenset[str],
    *,
    label: str,
) -> None:
    actual = frozenset(payload)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise AgentContractError(
            f"{label} payload keys invalid; missing={missing}, extra={extra}"
        )


def request_to_message(
    request: AgentTaskRequest,
    *,
    recipient: str,
) -> AgentMessage:
    if not isinstance(request, AgentTaskRequest):
        raise TypeError("request must be an AgentTaskRequest")
    _require_non_blank(recipient, "recipient")

    return AgentMessage(
        sender="jarvis",
        recipient=recipient,
        kind=MessageKind.TASK,
        objective=request.objective,
        payload={
            "contract_version": AgentContractVersion.JARVIS_NATIVE_V1.value,
            "task_id": request.task_id,
            "goal_id": request.goal_id,
            "title": request.title,
            "required_capabilities": list(request.required_capabilities),
            "operation": request.operation,
            "input_data": dict(request.input_data),
            "dependency_results": {
                task_id: dict(result)
                for task_id, result in request.dependency_results.items()
            },
        },
        priority=request.priority,
        risk_level=request.risk_level,
        requires_approval=request.requires_approval,
    )


def request_from_message(message: AgentMessage) -> AgentTaskRequest:
    if not isinstance(message, AgentMessage):
        raise TypeError("message must be an AgentMessage")
    if message.kind != MessageKind.TASK:
        raise AgentContractError("native request must use MessageKind.TASK")

    _require_exact_payload_keys(
        message.payload,
        _REQUEST_PAYLOAD_KEYS,
        label="request",
    )
    if (
        message.payload["contract_version"]
        != AgentContractVersion.JARVIS_NATIVE_V1.value
    ):
        raise AgentContractError("wrong native request contract version")

    capabilities = message.payload["required_capabilities"]
    if not isinstance(capabilities, list):
        raise AgentContractError("required_capabilities must be a list")

    try:
        return AgentTaskRequest(
            task_id=message.payload["task_id"],
            goal_id=message.payload["goal_id"],
            title=message.payload["title"],
            objective=message.objective,
            required_capabilities=tuple(capabilities),
            operation=message.payload["operation"],
            priority=message.priority,
            risk_level=message.risk_level,
            requires_approval=message.requires_approval,
            input_data=dict(message.payload["input_data"]),
            dependency_results={
                task_id: dict(result)
                for task_id, result in message.payload[
                    "dependency_results"
                ].items()
            },
        )
    except (TypeError, ValueError, AttributeError) as exc:
        raise AgentContractError(str(exc)) from exc


def result_to_message(
    result: AgentTaskResult,
    *,
    sender: str,
    parent_id: str,
) -> AgentMessage:
    if not isinstance(result, AgentTaskResult):
        raise TypeError("result must be an AgentTaskResult")
    _require_non_blank(sender, "sender")
    _require_non_blank(parent_id, "parent_id")

    return AgentMessage(
        parent_id=parent_id,
        sender=sender,
        recipient="jarvis",
        kind=_RESULT_KIND_BY_STATUS[result.status],
        objective=result.summary,
        payload={
            "contract_version": AgentContractVersion.JARVIS_NATIVE_V1.value,
            "task_id": result.task_id,
            "summary": result.summary,
            "output_data": dict(result.output_data),
            "error": result.error,
        },
        status=result.status,
        risk_level=result.risk_level,
        requires_approval=result.requires_approval,
    )


def result_from_message(
    message: AgentMessage,
    *,
    expected_task_id: str,
) -> AgentTaskResult:
    if not isinstance(message, AgentMessage):
        raise TypeError("message must be an AgentMessage")
    _require_non_blank(expected_task_id, "expected_task_id")
    if message.recipient != "jarvis":
        raise AgentContractError(
            "native result must be addressed to jarvis"
        )

    _require_exact_payload_keys(
        message.payload,
        _RESULT_PAYLOAD_KEYS,
        label="result",
    )
    if (
        message.payload["contract_version"]
        != AgentContractVersion.JARVIS_NATIVE_V1.value
    ):
        raise AgentContractError("wrong native result contract version")

    expected_kind = _RESULT_KIND_BY_STATUS.get(message.status)
    if expected_kind is None or message.kind != expected_kind:
        raise AgentContractError(
            "native result message kind/status combination is invalid"
        )

    task_id = message.payload["task_id"]
    if task_id != expected_task_id:
        raise AgentContractError(
            f"native result task_id mismatch: {task_id!r} != "
            f"{expected_task_id!r}"
        )

    try:
        return AgentTaskResult(
            task_id=task_id,
            status=message.status,
            output_data=dict(message.payload["output_data"]),
            summary=message.payload["summary"],
            error=message.payload["error"],
            risk_level=message.risk_level,
            requires_approval=message.requires_approval,
        )
    except (TypeError, ValueError, AttributeError) as exc:
        raise AgentContractError(str(exc)) from exc
