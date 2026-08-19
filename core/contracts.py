from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4


class MessageKind(str, Enum):
    TASK = "task"
    RESULT = "result"
    APPROVAL_REQUEST = "approval_request"
    DECISION = "decision"
    ERROR = "error"


class TaskStatus(str, Enum):
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    WAITING_APPROVAL = "waiting_approval"
    REJECTED = "rejected"


class Priority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


def _new_message_id() -> str:
    return str(uuid4())


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class AgentMessage:
    sender: str
    recipient: str
    kind: MessageKind
    objective: str
    id: str = field(default_factory=_new_message_id)
    parent_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    status: TaskStatus = TaskStatus.PENDING
    priority: Priority = Priority.NORMAL
    risk_level: RiskLevel = RiskLevel.LOW
    requires_approval: bool = False
    created_at: datetime = field(default_factory=_utc_now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for field_name in ("id", "sender", "recipient", "objective"):
            value = getattr(self, field_name)
            if not isinstance(value, str):
                raise TypeError(f"{field_name} must be a string")
            if not value.strip():
                raise ValueError(f"{field_name} cannot be blank")

        if self.parent_id is not None and not isinstance(self.parent_id, str):
            raise TypeError("parent_id must be a string or None")

        if not isinstance(self.kind, MessageKind):
            raise TypeError("kind must be a MessageKind")
        if not isinstance(self.status, TaskStatus):
            raise TypeError("status must be a TaskStatus")
        if not isinstance(self.priority, Priority):
            raise TypeError("priority must be a Priority")
        if not isinstance(self.risk_level, RiskLevel):
            raise TypeError("risk_level must be a RiskLevel")
        if not isinstance(self.requires_approval, bool):
            raise TypeError("requires_approval must be a bool")
        if not isinstance(self.payload, dict):
            raise TypeError("payload must be a dict")
        if not isinstance(self.metadata, dict):
            raise TypeError("metadata must be a dict")
        if not isinstance(self.created_at, datetime):
            raise TypeError("created_at must be a datetime")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
