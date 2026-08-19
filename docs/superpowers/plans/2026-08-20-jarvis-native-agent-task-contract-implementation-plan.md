# Jarvis-native Agent Task Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the Founder-approved Jarvis-native task protocol so all future specialists can receive typed task context, consume dependency results, and return validated results without role-specific workflow logic in `JarvisOrchestrator`.

**Architecture:** Keep `AgentMessage` as the transport contract and layer `AgentTaskRequest` / `AgentTaskResult` above it. Existing agents remain `LEGACY_V1`; new specialists use `JARVIS_NATIVE_V1`. The Orchestrator branches only by contract version, never by agent name, and TaskManager remains the sole authority for task state.

**Tech Stack:** Python 3.14.x, Python standard library only, `dataclasses`, `enum`, `unittest`, existing in-memory `MessageBus`.

**Spec:** `docs/superpowers/specs/2026-08-20-jarvis-native-agent-task-contract-design.md`

## Global Constraints

- GitHub repository: `Znd93/kreovanta-game-studio`.
- Active branch: `agent/agent-contract-v1`.
- Canonical starting commit: `10894ff0ff943b13a5deb812ec9582276d6e63e4`.
- Python standard library only; add no mandatory external dependency.
- `AgentMessage` remains the transport contract.
- `AgentTaskRequest` and `AgentTaskResult` are the Jarvis-native task contract.
- `AgentRegistration` explicitly declares contract version.
- Existing agents default to `LEGACY_V1`.
- New specialists use `JARVIS_NATIVE_V1`.
- `JarvisOrchestrator` owns orchestration; TaskManager owns task state; ApprovalService owns authorization; Router owns specialist selection.
- Agents never choose downstream agents or tasks and never modify dependency state.
- Agents may escalate risk but cannot reduce policy minimums.
- `input_data` and `dependency_results` remain separate.
- Top-level `AgentTaskRequest` is immutable.
- Control fields already owned by `AgentMessage` are not duplicated in payload.
- Contract-version branching is allowed; agent-name workflow branching is forbidden.
- Malformed native protocol traffic fails closed with `AGENT_PROTOCOL_ERROR`.
- No autonomous repair, retry, replanning, rerouting, parallel execution, Developer Agent, Tester Agent, Reviewer Agent, Git Worker, Agent Factory, Roblox publishing, or Rojo automation in this task.
- Existing 137 regression tests are the baseline and must remain green.

---

## File Map

### New files

- `jarvis/agent_contract.py`
  - Owns `AgentContractVersion`, `AgentContractError`, `AgentTaskRequest`, `AgentTaskResult`.
  - Owns strict request/result serialization and deserialization.
  - Contains no routing, MessageBus state, Planner logic, specialist logic, or Ollama calls.

- `agents/jarvis_native.py`
  - Owns `JarvisNativeAgent`.
  - Converts `AgentMessage -> AgentTaskRequest`, calls typed `_execute()`, and converts `AgentTaskResult -> AgentMessage`.
  - Contains no specialist behavior.

- `tests/test_agent_contract.py`
  - Unit tests for native contract models and serialization.

- `tests/test_jarvis_native_agent.py`
  - Unit tests for the generic native base-agent adapter.

### Modified files

- `jarvis/models.py`
  - Adds `contract_version` to `AgentRegistration`, defaulting to `LEGACY_V1`.

- `jarvis/registry.py`
  - Validates that `JARVIS_NATIVE_V1` registrations use `JarvisNativeAgent`.

- `jarvis/orchestrator.py`
  - Builds native requests from `JarvisTask`.
  - Collects completed dependency results.
  - Dispatches by `registration.contract_version`.
  - Parses native results and stores stable `{summary, output_data}` results.
  - Preserves the legacy path unchanged in behavior.

- `tests/test_jarvis_models.py`
  - Covers registration version default/type validation.

- `tests/test_registry.py`
  - Covers legacy compatibility and native-class enforcement.

- `tests/test_orchestrator.py`
  - Covers dependency propagation, A→B→C native chaining, result storage, risk escalation, approval behavior, and protocol failures.

- `JARVIS_STATUS.md`
  - Updated only after implementation and full verification are complete.

---

### Task 1.1: Add native contract models and invariants

**Files:**
- Create: `jarvis/agent_contract.py`
- Create: `tests/test_agent_contract.py`

**Interfaces:**
- Produces:
  - `class AgentContractVersion(str, Enum)`
  - `class AgentContractError(ValueError)`
  - `@dataclass(frozen=True, slots=True) class AgentTaskRequest`
  - `@dataclass(frozen=True, slots=True) class AgentTaskResult`
- Consumes:
  - `Priority`, `RiskLevel`, `TaskStatus` from `core.contracts`

- [ ] **Step 1: Write failing model-validation tests**

Create `tests/test_agent_contract.py` with these initial tests:

```python
import unittest

from core.contracts import Priority, RiskLevel, TaskStatus
from jarvis.agent_contract import (
    AgentContractVersion,
    AgentTaskRequest,
    AgentTaskResult,
)


class AgentTaskRequestTests(unittest.TestCase):
    def make_request(self, **overrides) -> AgentTaskRequest:
        values = {
            "task_id": "task-a",
            "goal_id": "goal-1",
            "title": "Implement feature",
            "objective": "Implement the requested feature",
            "required_capabilities": ("code_implementation",),
            "operation": "code_change",
            "priority": Priority.NORMAL,
            "risk_level": RiskLevel.LOW,
            "requires_approval": False,
            "input_data": {"repository": "example/repo"},
            "dependency_results": {},
        }
        values.update(overrides)
        return AgentTaskRequest(**values)

    def test_valid_request_is_accepted(self):
        request = self.make_request()

        self.assertEqual(request.task_id, "task-a")
        self.assertEqual(request.required_capabilities, ("code_implementation",))
        self.assertEqual(request.dependency_results, {})

    def test_request_rejects_blank_task_id(self):
        with self.assertRaises(ValueError):
            self.make_request(task_id="   ")

    def test_request_rejects_empty_capabilities(self):
        with self.assertRaises(ValueError):
            self.make_request(required_capabilities=())

    def test_request_rejects_invalid_dependency_results(self):
        with self.assertRaises(TypeError):
            self.make_request(dependency_results={"task-z": "not-a-dict"})


class AgentTaskResultTests(unittest.TestCase):
    def make_result(self, **overrides) -> AgentTaskResult:
        values = {
            "task_id": "task-a",
            "status": TaskStatus.COMPLETED,
            "output_data": {"artifact": "x"},
            "summary": "Completed work",
            "error": None,
            "risk_level": RiskLevel.LOW,
            "requires_approval": False,
        }
        values.update(overrides)
        return AgentTaskResult(**values)

    def test_valid_completed_result_is_accepted(self):
        result = self.make_result()

        self.assertEqual(result.status, TaskStatus.COMPLETED)
        self.assertEqual(result.output_data, {"artifact": "x"})

    def test_failed_result_requires_error(self):
        with self.assertRaises(ValueError):
            self.make_result(status=TaskStatus.FAILED, error=None)

    def test_completed_result_rejects_error(self):
        with self.assertRaises(ValueError):
            self.make_result(error="unexpected")

    def test_result_rejects_orchestration_owned_status(self):
        with self.assertRaises(ValueError):
            self.make_result(status=TaskStatus.RUNNING)


class AgentContractVersionTests(unittest.TestCase):
    def test_version_values_are_stable(self):
        self.assertEqual(AgentContractVersion.LEGACY_V1.value, "legacy_v1")
        self.assertEqual(
            AgentContractVersion.JARVIS_NATIVE_V1.value,
            "jarvis_native_v1",
        )


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the new tests and confirm the expected failure**

Run:

```powershell
python -m unittest tests.test_agent_contract -v
```

Expected: FAIL because `jarvis.agent_contract` does not exist.

- [ ] **Step 3: Implement the contract models with strict invariants**

Create `jarvis/agent_contract.py`:

```python
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
            _require_non_blank(self.error, "error")
        elif self.error is not None:
            raise ValueError(
                f"{self.status.value} result cannot include an error"
            )
```

- [ ] **Step 4: Run the model tests**

Run:

```powershell
python -m unittest tests.test_agent_contract -v
```

Expected: all tests in `tests.test_agent_contract` PASS.

- [ ] **Step 5: Verify no unrelated diff and commit only these files**

Run:

```powershell
git status --short
git diff --check
git diff -- jarvis/agent_contract.py tests/test_agent_contract.py
git add -- jarvis/agent_contract.py tests/test_agent_contract.py
git diff --cached --check
git commit -m "feat: add Jarvis-native task contract models"
```

Expected: commit contains only the new contract model and its tests.

---

### Task 1.2: Add deterministic request/result transport serialization

**Files:**
- Modify: `jarvis/agent_contract.py`
- Modify: `tests/test_agent_contract.py`

**Interfaces:**
- Consumes:
  - `AgentTaskRequest`
  - `AgentTaskResult`
  - `AgentMessage`, `MessageKind`
- Produces:
  - `request_to_message(request: AgentTaskRequest, *, recipient: str) -> AgentMessage`
  - `request_from_message(message: AgentMessage) -> AgentTaskRequest`
  - `result_to_message(result: AgentTaskResult, *, sender: str, parent_id: str) -> AgentMessage`
  - `result_from_message(message: AgentMessage, *, expected_task_id: str) -> AgentTaskResult`

- [ ] **Step 1: Add failing serialization tests**

Append tests that verify exact payload shape and strict failure behavior:

```python
from core.contracts import AgentMessage, MessageKind


class AgentContractSerializationTests(unittest.TestCase):
    def make_request(self) -> AgentTaskRequest:
        return AgentTaskRequest(
            task_id="task-a",
            goal_id="goal-1",
            title="Implement feature",
            objective="Implement the requested feature",
            required_capabilities=("code_implementation",),
            operation="code_change",
            priority=Priority.HIGH,
            risk_level=RiskLevel.MEDIUM,
            requires_approval=False,
            input_data={"repository": "example/repo"},
            dependency_results={
                "task-parent": {
                    "summary": "Prepared input",
                    "output_data": {"artifact": "x"},
                }
            },
        )

    def test_request_round_trip_preserves_contract(self):
        request = self.make_request()

        message = request_to_message(request, recipient="developer")
        parsed = request_from_message(message)

        self.assertEqual(message.sender, "jarvis")
        self.assertEqual(message.recipient, "developer")
        self.assertEqual(message.kind, MessageKind.TASK)
        self.assertEqual(
            message.payload["contract_version"],
            AgentContractVersion.JARVIS_NATIVE_V1.value,
        )
        self.assertEqual(parsed, request)

    def test_request_rejects_wrong_contract_version(self):
        request = self.make_request()
        message = request_to_message(request, recipient="developer")
        message.payload["contract_version"] = "legacy_v1"

        with self.assertRaises(AgentContractError):
            request_from_message(message)

    def test_request_rejects_wrong_message_kind(self):
        request = self.make_request()
        message = request_to_message(request, recipient="developer")
        message.kind = MessageKind.RESULT

        with self.assertRaises(AgentContractError):
            request_from_message(message)

    def test_completed_result_round_trip_maps_message_kind(self):
        result = AgentTaskResult(
            task_id="task-a",
            status=TaskStatus.COMPLETED,
            output_data={"files_changed": ["x.py"]},
            summary="Implemented change",
            error=None,
            risk_level=RiskLevel.LOW,
            requires_approval=False,
        )

        message = result_to_message(
            result,
            sender="developer",
            parent_id="message-1",
        )
        parsed = result_from_message(message, expected_task_id="task-a")

        self.assertEqual(message.kind, MessageKind.RESULT)
        self.assertEqual(message.recipient, "jarvis")
        self.assertEqual(parsed, result)

    def test_failed_result_maps_error_kind(self):
        result = AgentTaskResult(
            task_id="task-a",
            status=TaskStatus.FAILED,
            output_data={},
            summary="Implementation failed",
            error="compile error",
            risk_level=RiskLevel.LOW,
            requires_approval=False,
        )

        message = result_to_message(
            result,
            sender="developer",
            parent_id="message-1",
        )

        self.assertEqual(message.kind, MessageKind.ERROR)

    def test_waiting_result_maps_approval_kind(self):
        result = AgentTaskResult(
            task_id="task-a",
            status=TaskStatus.WAITING_APPROVAL,
            output_data={"candidate": "x"},
            summary="Founder review required",
            error=None,
            risk_level=RiskLevel.HIGH,
            requires_approval=True,
        )

        message = result_to_message(
            result,
            sender="reviewer",
            parent_id="message-1",
        )

        self.assertEqual(message.kind, MessageKind.APPROVAL_REQUEST)

    def test_result_rejects_task_id_mismatch(self):
        result = AgentTaskResult(
            task_id="task-a",
            status=TaskStatus.COMPLETED,
            output_data={},
            summary="Done",
            error=None,
            risk_level=RiskLevel.LOW,
            requires_approval=False,
        )
        message = result_to_message(
            result,
            sender="developer",
            parent_id="message-1",
        )

        with self.assertRaises(AgentContractError):
            result_from_message(message, expected_task_id="task-b")
```

Update the imports to include:

```python
from jarvis.agent_contract import (
    AgentContractError,
    AgentContractVersion,
    AgentTaskRequest,
    AgentTaskResult,
    request_from_message,
    request_to_message,
    result_from_message,
    result_to_message,
)
```

- [ ] **Step 2: Run only the serialization tests and verify failure**

Run:

```powershell
python -m unittest tests.test_agent_contract.AgentContractSerializationTests -v
```

Expected: FAIL because the serializer/deserializer functions do not exist.

- [ ] **Step 3: Implement exact native transport mapping**

Add to `jarvis/agent_contract.py`:

```python
from core.contracts import AgentMessage, MessageKind, Priority, RiskLevel, TaskStatus


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
```

- [ ] **Step 4: Run the full contract test module**

Run:

```powershell
python -m unittest tests.test_agent_contract -v
```

Expected: all model and serialization tests PASS.

- [ ] **Step 5: Commit only the serializer change**

Run:

```powershell
git status --short
git diff --check
git add -- jarvis/agent_contract.py tests/test_agent_contract.py
git diff --cached --check
git commit -m "feat: add Jarvis-native message serialization"
```

---

### Task 1.3: Version agent registrations without breaking legacy agents

**Files:**
- Modify: `jarvis/models.py` in `AgentRegistration`
- Modify: `jarvis/registry.py`
- Modify: `tests/test_jarvis_models.py`
- Modify: `tests/test_registry.py`

**Interfaces:**
- Consumes: `AgentContractVersion`
- Produces:
  - `AgentRegistration.contract_version: AgentContractVersion`
  - Legacy default: `AgentContractVersion.LEGACY_V1`
  - Registry invariant: native registrations must subclass `JarvisNativeAgent` once that class exists.

**Ordering note:** Add the model field and default in this task. Defer the `JarvisNativeAgent` subclass enforcement to Task 1.4 after the class exists; do not introduce a temporary circular import.

- [ ] **Step 1: Add failing model tests for contract version**

Add to `tests/test_jarvis_models.py`:

```python
from jarvis.agent_contract import AgentContractVersion


def test_agent_registration_defaults_to_legacy_contract(self):
    registration = AgentRegistration(
        name="legacy",
        agent_class=object,
        capabilities=frozenset({"cap"}),
        allowed_risk_levels=frozenset({RiskLevel.LOW}),
    )

    self.assertEqual(
        registration.contract_version,
        AgentContractVersion.LEGACY_V1,
    )


def test_agent_registration_rejects_invalid_contract_version(self):
    with self.assertRaises(TypeError):
        AgentRegistration(
            name="invalid",
            agent_class=object,
            capabilities=frozenset({"cap"}),
            allowed_risk_levels=frozenset({RiskLevel.LOW}),
            contract_version="jarvis_native_v1",
        )
```

Use the existing `unittest.TestCase` class structure in that file rather than creating free functions if the file is class-based.

- [ ] **Step 2: Run the focused model test**

Run:

```powershell
python -m unittest tests.test_jarvis_models -v
```

Expected: FAIL because `AgentRegistration` has no `contract_version`.

- [ ] **Step 3: Add the version field to `AgentRegistration`**

In `jarvis/models.py`, import:

```python
from jarvis.agent_contract import AgentContractVersion
```

Add to `AgentRegistration` after `allowed_risk_levels`:

```python
contract_version: AgentContractVersion = AgentContractVersion.LEGACY_V1
```

Add to `__post_init__`:

```python
if not isinstance(self.contract_version, AgentContractVersion):
    raise TypeError(
        "contract_version must be an AgentContractVersion"
    )
```

Keep `enabled` and `metadata` behavior unchanged.

- [ ] **Step 4: Prove current registry callers remain legacy by default**

Add to `tests/test_registry.py`:

```python
from jarvis.agent_contract import AgentContractVersion


def test_existing_registration_helper_defaults_to_legacy_v1(self):
    item = registration("researcher")

    self.assertEqual(
        item.contract_version,
        AgentContractVersion.LEGACY_V1,
    )
```

Run:

```powershell
python -m unittest tests.test_jarvis_models tests.test_registry -v
```

Expected: PASS.

- [ ] **Step 5: Commit the backward-compatible registration version**

Run:

```powershell
git diff --check
git add -- jarvis/models.py tests/test_jarvis_models.py tests/test_registry.py
git diff --cached --check
git commit -m "feat: version Jarvis agent registrations"
```

---

### Task 1.4: Add the generic `JarvisNativeAgent` adapter

**Files:**
- Create: `agents/jarvis_native.py`
- Create: `tests/test_jarvis_native_agent.py`
- Modify: `jarvis/registry.py`
- Modify: `tests/test_registry.py`

**Interfaces:**
- Consumes:
  - `BaseAgent`
  - `AgentMessage`
  - `AgentTaskRequest`
  - `AgentTaskResult`
  - `request_from_message`
  - `result_to_message`
- Produces:
  - `abstract class JarvisNativeAgent(BaseAgent)`
  - `_execute(self, request: AgentTaskRequest) -> AgentTaskResult`

- [ ] **Step 1: Write failing native-adapter tests**

Create `tests/test_jarvis_native_agent.py`:

```python
import unittest

from agents.jarvis_native import JarvisNativeAgent
from core.contracts import Priority, RiskLevel, TaskStatus
from jarvis.agent_contract import (
    AgentContractError,
    AgentTaskRequest,
    AgentTaskResult,
    request_to_message,
    result_from_message,
)


class EchoNativeAgent(JarvisNativeAgent):
    name = "echo_native"
    requests: list[AgentTaskRequest] = []

    def _execute(
        self,
        request: AgentTaskRequest,
    ) -> AgentTaskResult:
        type(self).requests.append(request)
        return AgentTaskResult(
            task_id=request.task_id,
            status=TaskStatus.COMPLETED,
            output_data={"received": request.input_data},
            summary="Echo complete",
            error=None,
            risk_level=request.risk_level,
            requires_approval=False,
        )


class WrongTaskNativeAgent(JarvisNativeAgent):
    name = "wrong_task"

    def _execute(
        self,
        request: AgentTaskRequest,
    ) -> AgentTaskResult:
        return AgentTaskResult(
            task_id="different-task",
            status=TaskStatus.COMPLETED,
            output_data={},
            summary="Wrong task",
            error=None,
            risk_level=RiskLevel.LOW,
            requires_approval=False,
        )


class JarvisNativeAgentTests(unittest.TestCase):
    def setUp(self):
        EchoNativeAgent.requests = []

    def make_request(self) -> AgentTaskRequest:
        return AgentTaskRequest(
            task_id="task-a",
            goal_id="goal-1",
            title="Echo",
            objective="Echo input",
            required_capabilities=("echo",),
            operation=None,
            priority=Priority.NORMAL,
            risk_level=RiskLevel.LOW,
            requires_approval=False,
            input_data={"value": 7},
            dependency_results={},
        )

    def test_handle_converts_transport_to_typed_request_and_back(self):
        request = self.make_request()
        message = request_to_message(
            request,
            recipient=EchoNativeAgent.name,
        )

        result_message = EchoNativeAgent().handle(message)
        result = result_from_message(
            result_message,
            expected_task_id=request.task_id,
        )

        self.assertEqual(EchoNativeAgent.requests, [request])
        self.assertEqual(
            result.output_data,
            {"received": {"value": 7}},
        )

    def test_wrong_result_task_id_fails_closed(self):
        request = self.make_request()
        message = request_to_message(
            request,
            recipient=WrongTaskNativeAgent.name,
        )

        with self.assertRaises(AgentContractError):
            WrongTaskNativeAgent().handle(message)
```

- [ ] **Step 2: Run the native-adapter tests**

Run:

```powershell
python -m unittest tests.test_jarvis_native_agent -v
```

Expected: FAIL because `agents.jarvis_native` does not exist.

- [ ] **Step 3: Implement `JarvisNativeAgent`**

Create `agents/jarvis_native.py`:

```python
from __future__ import annotations

from abc import abstractmethod

from agents.base_agent import BaseAgent
from core.contracts import AgentMessage
from jarvis.agent_contract import (
    AgentContractError,
    AgentTaskRequest,
    AgentTaskResult,
    request_from_message,
    result_to_message,
)


class JarvisNativeAgent(BaseAgent):
    def _handle(self, message: AgentMessage) -> AgentMessage:
        request = request_from_message(message)
        result = self._execute(request)

        if not isinstance(result, AgentTaskResult):
            raise AgentContractError(
                "_execute() must return an AgentTaskResult"
            )
        if result.task_id != request.task_id:
            raise AgentContractError(
                "native agent result task_id must match request task_id"
            )

        return result_to_message(
            result,
            sender=self.name,
            parent_id=message.id,
        )

    @abstractmethod
    def _execute(
        self,
        request: AgentTaskRequest,
    ) -> AgentTaskResult:
        raise NotImplementedError
```

- [ ] **Step 4: Add registry enforcement for native registrations**

In `tests/test_registry.py`, add:

```python
from agents.jarvis_native import JarvisNativeAgent
from core.contracts import TaskStatus
from jarvis.agent_contract import (
    AgentContractVersion,
    AgentTaskRequest,
    AgentTaskResult,
)


class NativeAgent(JarvisNativeAgent):
    name = "native"

    def _execute(
        self,
        request: AgentTaskRequest,
    ) -> AgentTaskResult:
        return AgentTaskResult(
            task_id=request.task_id,
            status=TaskStatus.COMPLETED,
            output_data={},
            summary="Done",
            error=None,
            risk_level=request.risk_level,
            requires_approval=False,
        )


def test_native_registration_requires_native_agent_subclass(self):
    registry = AgentRegistry()
    item = AgentRegistration(
        name="researcher",
        agent_class=ResearcherAgent,
        capabilities=frozenset({"market_research"}),
        allowed_risk_levels=frozenset({RiskLevel.LOW}),
        contract_version=AgentContractVersion.JARVIS_NATIVE_V1,
    )

    with self.assertRaises(TypeError):
        registry.register(item)


def test_native_registration_accepts_native_agent_subclass(self):
    registry = AgentRegistry()
    item = AgentRegistration(
        name="native",
        agent_class=NativeAgent,
        capabilities=frozenset({"native_cap"}),
        allowed_risk_levels=frozenset({RiskLevel.LOW}),
        contract_version=AgentContractVersion.JARVIS_NATIVE_V1,
    )

    registry.register(item)

    self.assertIs(registry.get("native"), item)
```

Implement in `jarvis/registry.py`:

```python
from agents.jarvis_native import JarvisNativeAgent
from jarvis.agent_contract import AgentContractVersion
```

Inside `register()` after the existing `BaseAgent` subclass check:

```python
if (
    registration.contract_version
    == AgentContractVersion.JARVIS_NATIVE_V1
    and not issubclass(
        registration.agent_class,
        JarvisNativeAgent,
    )
):
    raise TypeError(
        "JARVIS_NATIVE_V1 agent_class must be a "
        "JarvisNativeAgent subclass"
    )
```

- [ ] **Step 5: Run the focused adapter/registry suite**

Run:

```powershell
python -m unittest tests.test_jarvis_native_agent tests.test_registry -v
```

Expected: PASS.

- [ ] **Step 6: Run current legacy agent tests as a compatibility checkpoint**

Run:

```powershell
python -m unittest tests.test_agents tests.test_base_agent tests.test_main -v
```

Expected: PASS with no legacy-agent migration.

- [ ] **Step 7: Commit the generic adapter**

Run:

```powershell
git diff --check
git add -- agents/jarvis_native.py tests/test_jarvis_native_agent.py jarvis/registry.py tests/test_registry.py
git diff --cached --check
git commit -m "feat: add Jarvis-native base agent"
```

---

### Task 1.5: Build native requests and propagate dependency results generically

**Files:**
- Modify: `jarvis/orchestrator.py`
- Modify: `tests/test_orchestrator.py`

**Interfaces:**
- Consumes:
  - `AgentContractVersion`
  - `AgentTaskRequest`
  - `request_to_message`
  - `TaskManager.get(task_id)`
- Produces:
  - `_collect_dependency_results(task: JarvisTask) -> dict[str, dict[str, Any]]`
  - `_build_native_request(task: JarvisTask, effective_risk: RiskLevel) -> AgentTaskRequest`

- [ ] **Step 1: Add a fake native agent that records requests**

At the top of `tests/test_orchestrator.py`, import:

```python
from agents.jarvis_native import JarvisNativeAgent
from jarvis.agent_contract import (
    AgentContractVersion,
    AgentTaskRequest,
    AgentTaskResult,
)
```

Add:

```python
class RecordingNativeAgent(JarvisNativeAgent):
    name = "recording_native"
    requests: list[AgentTaskRequest] = []

    def _execute(
        self,
        request: AgentTaskRequest,
    ) -> AgentTaskResult:
        type(self).requests.append(request)
        return AgentTaskResult(
            task_id=request.task_id,
            status=TaskStatus.COMPLETED,
            output_data={"task": request.task_id},
            summary=f"Completed {request.task_id}",
            error=None,
            risk_level=request.risk_level,
            requires_approval=False,
        )
```

Reset its request list in `setUp()`.

Extend the existing registration helper with:

```python
contract_version: AgentContractVersion = AgentContractVersion.LEGACY_V1,
```

and pass it to `AgentRegistration`.

- [ ] **Step 2: Write the failing dependency propagation test**

Add:

```python
def test_native_task_receives_completed_dependency_results(self):
    first = self.make_task("first", "native_cap")
    second = self.make_task(
        "second",
        "native_cap",
        dependencies=(first.id,),
    )
    registry = self.make_registry(
        self.registration(
            "recording_native",
            RecordingNativeAgent,
            "native_cap",
            contract_version=AgentContractVersion.JARVIS_NATIVE_V1,
        )
    )
    orchestrator, _, _, _, _ = self.make_orchestrator(
        self.make_plan(first, second),
        registry,
    )

    result = orchestrator.start("Execute native chain")

    self.assertEqual(result.state, OrchestratorState.COMPLETED)
    self.assertEqual(len(RecordingNativeAgent.requests), 2)
    downstream = RecordingNativeAgent.requests[1]
    self.assertEqual(
        downstream.dependency_results,
        {
            first.id: {
                "summary": f"Completed {first.id}",
                "output_data": {"task": first.id},
            }
        },
    )
```

- [ ] **Step 3: Run that exact test and verify failure**

Run:

```powershell
python -m unittest tests.test_orchestrator.JarvisOrchestratorTests.test_native_task_receives_completed_dependency_results -v
```

Expected: FAIL because the Orchestrator still sends only legacy `task_id` + `input_data`.

- [ ] **Step 4: Add native request construction helpers**

In `jarvis/orchestrator.py`, import:

```python
from jarvis.agent_contract import (
    AgentContractError,
    AgentContractVersion,
    AgentTaskRequest,
    request_to_message,
    result_from_message,
)
```

Add helper:

```python
def _collect_dependency_results(
    self,
    task: JarvisTask,
) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    for dependency_id in task.dependencies:
        dependency = self._task_manager.get(dependency_id)
        if dependency.status != TaskStatus.COMPLETED:
            raise AgentContractError(
                f"dependency {dependency_id} is not completed"
            )
        if not isinstance(dependency.result, dict):
            raise AgentContractError(
                f"dependency {dependency_id} result must be a dict"
            )
        results[dependency_id] = dict(dependency.result)

    if frozenset(results) != frozenset(task.dependencies):
        raise AgentContractError(
            "dependency result keys do not match task dependencies"
        )
    return results


def _build_native_request(
    self,
    task: JarvisTask,
    effective_risk: RiskLevel,
) -> AgentTaskRequest:
    return AgentTaskRequest(
        task_id=task.id,
        goal_id=task.goal_id,
        title=task.title,
        objective=task.objective,
        required_capabilities=task.required_capabilities,
        operation=task.operation,
        priority=task.priority,
        risk_level=effective_risk,
        requires_approval=task.requires_approval,
        input_data=dict(task.input_data),
        dependency_results=self._collect_dependency_results(task),
    )
```

- [ ] **Step 5: Branch task-message creation by contract version only**

Replace the single legacy `task_message = AgentMessage(...)` construction with:

```python
if (
    registration.contract_version
    == AgentContractVersion.JARVIS_NATIVE_V1
):
    try:
        request = self._build_native_request(
            task,
            evaluation.effective_risk,
        )
        task_message = request_to_message(
            request,
            recipient=agent.name,
        )
    except (AgentContractError, TypeError, ValueError) as exc:
        return self._fail_running_task(
            task,
            str(exc) or "native request protocol error",
            error_code="AGENT_PROTOCOL_ERROR",
        )
else:
    task_message = AgentMessage(
        sender="jarvis",
        recipient=agent.name,
        kind=MessageKind.TASK,
        objective=task.objective,
        payload={
            "task_id": task.id,
            "input_data": dict(task.input_data),
        },
        priority=task.priority,
        risk_level=evaluation.effective_risk,
        requires_approval=task.requires_approval,
    )
```

Do not add any agent-name checks.

- [ ] **Step 6: Run focused native dependency test plus legacy routing tests**

Run:

```powershell
python -m unittest tests.test_orchestrator.JarvisOrchestratorTests.test_native_task_receives_completed_dependency_results -v
python -m unittest tests.test_orchestrator.JarvisOrchestratorTests.test_two_sequential_tasks_route_by_capability_not_fixed_agent_names -v
python -m unittest tests.test_orchestrator.JarvisOrchestratorTests.test_agent_receives_task_message_with_task_id_and_input_data -v
```

Expected: all PASS. The last test proves legacy payload behavior remains intact.

- [ ] **Step 7: Commit native request propagation**

Run:

```powershell
git diff --check
git add -- jarvis/orchestrator.py tests/test_orchestrator.py
git diff --cached --check
git commit -m "feat: propagate native task dependency context"
```

---

### Task 1.6: Parse native results, store stable outputs, and fail closed

**Files:**
- Modify: `jarvis/orchestrator.py`
- Modify: `tests/test_orchestrator.py`

**Interfaces:**
- Consumes:
  - `result_from_message(message, expected_task_id=...)`
  - `AgentTaskResult`
- Produces:
  - Native stable TaskManager result:
    - `{"summary": str, "output_data": dict}`
  - Native protocol errors map to `AGENT_PROTOCOL_ERROR`.
  - Native result risk/approval values participate in existing post-result approval logic.

- [ ] **Step 1: Add tests for stable native result storage**

Add:

```python
def test_native_completed_result_stores_summary_and_output_data(self):
    task = self.make_task("native", "native_cap")
    registry = self.make_registry(
        self.registration(
            "recording_native",
            RecordingNativeAgent,
            "native_cap",
            contract_version=AgentContractVersion.JARVIS_NATIVE_V1,
        )
    )
    orchestrator, _, _, _, _ = self.make_orchestrator(
        self.make_plan(task),
        registry,
    )

    result = orchestrator.start("Execute native task")

    self.assertEqual(result.state, OrchestratorState.COMPLETED)
    self.assertEqual(
        task.result,
        {
            "summary": f"Completed {task.id}",
            "output_data": {"task": task.id},
        },
    )
```

- [ ] **Step 2: Add a native agent that deliberately returns a malformed transport result**

Because `JarvisNativeAgent` itself prevents malformed typed results, use a `BaseAgent` test double registered as legacy only for existing protocol tests, and separately test native adapter failures through `AgentContractError`. For the Orchestrator's native fail-closed path, create a `JarvisNativeAgent` whose `_execute` raises `AgentContractError`:

```python
class BrokenNativeAgent(JarvisNativeAgent):
    name = "broken_native"

    def _execute(
        self,
        request: AgentTaskRequest,
    ) -> AgentTaskResult:
        raise AgentContractError("malformed native result")
```

Add:

```python
def test_native_contract_error_fails_with_agent_protocol_error(self):
    task = self.make_task("native", "broken_cap")
    registry = self.make_registry(
        self.registration(
            "broken_native",
            BrokenNativeAgent,
            "broken_cap",
            contract_version=AgentContractVersion.JARVIS_NATIVE_V1,
        )
    )
    orchestrator, _, _, _, _ = self.make_orchestrator(
        self.make_plan(task),
        registry,
    )

    result = orchestrator.start("Execute broken native task")

    self.assertEqual(result.state, OrchestratorState.FAILED)
    self.assertEqual(result.error_code, "AGENT_PROTOCOL_ERROR")
    self.assertEqual(task.status, TaskStatus.FAILED)
```

- [ ] **Step 3: Add native risk-escalation/approval test**

Create:

```python
class EscalatingNativeAgent(JarvisNativeAgent):
    name = "escalating_native"

    def _execute(
        self,
        request: AgentTaskRequest,
    ) -> AgentTaskResult:
        return AgentTaskResult(
            task_id=request.task_id,
            status=TaskStatus.WAITING_APPROVAL,
            output_data={"candidate": "change"},
            summary="Critical risk discovered",
            error=None,
            risk_level=RiskLevel.CRITICAL,
            requires_approval=True,
        )
```

Test:

```python
def test_native_result_can_escalate_risk_and_require_approval(self):
    task = self.make_task("native", "escalate_cap")
    registry = self.make_registry(
        self.registration(
            "escalating_native",
            EscalatingNativeAgent,
            "escalate_cap",
            contract_version=AgentContractVersion.JARVIS_NATIVE_V1,
            allowed_risk_levels=frozenset(RiskLevel),
        )
    )
    orchestrator, _, _, approvals, _ = self.make_orchestrator(
        self.make_plan(task),
        registry,
    )

    result = orchestrator.start("Execute native task")

    self.assertEqual(
        result.state,
        OrchestratorState.WAITING_APPROVAL,
    )
    self.assertEqual(task.status, TaskStatus.WAITING_APPROVAL)
    self.assertIsNotNone(approvals.pending)
    self.assertEqual(
        approvals.pending.effective_risk,
        RiskLevel.CRITICAL,
    )
    self.assertEqual(
        task.result,
        {
            "summary": "Critical risk discovered",
            "output_data": {"candidate": "change"},
        },
    )
```

- [ ] **Step 4: Run the new native result tests and confirm they fail before implementation**

Run:

```powershell
python -m unittest tests.test_orchestrator -v
```

Expected: new native result tests FAIL while existing legacy tests remain mostly green.

- [ ] **Step 5: Catch native contract errors distinctly from agent failures**

Around `agent.handle(incoming)` in `jarvis/orchestrator.py`, use:

```python
try:
    agent_result = agent.handle(incoming)
except AgentContractError as exc:
    return self._fail_running_task(
        task,
        str(exc) or "native agent protocol error",
        error_code="AGENT_PROTOCOL_ERROR",
    )
except Exception as exc:
    return self._fail_running_task(
        task,
        f"agent execution failed: {exc}",
        error_code="AGENT_FAILED",
    )
```

- [ ] **Step 6: Parse native results before generic state handling**

After collecting the result from MessageBus, branch by contract version:

```python
if (
    registration.contract_version
    == AgentContractVersion.JARVIS_NATIVE_V1
):
    try:
        native_result = result_from_message(
            agent_result,
            expected_task_id=task.id,
        )
    except (AgentContractError, TypeError, ValueError) as exc:
        return self._fail_running_task(
            task,
            str(exc) or "native result protocol error",
            error_code="AGENT_PROTOCOL_ERROR",
        )

    result_status = native_result.status
    result_risk = native_result.risk_level
    result_requires_approval = native_result.requires_approval
    result_payload = {
        "summary": native_result.summary,
        "output_data": dict(native_result.output_data),
    }
    failure_detail = native_result.error
else:
    result_status = agent_result.status
    result_risk = agent_result.risk_level
    result_requires_approval = agent_result.requires_approval
    result_payload = dict(agent_result.payload)
    failure_detail = agent_result.payload.get(
        "error",
        "agent reported failure",
    )
```

Then drive the existing status/approval logic from the normalized local variables, not from specialist-specific output keys.

For failed results:

```python
if result_status == TaskStatus.FAILED:
    detail = failure_detail
    if not isinstance(detail, str) or not detail.strip():
        detail = "agent reported failure"
    return self._fail_running_task(
        task,
        detail,
        error_code="AGENT_FAILED",
    )
```

For status validity:

```python
if result_status not in {
    TaskStatus.COMPLETED,
    TaskStatus.WAITING_APPROVAL,
}:
    return self._fail_running_task(
        task,
        f"invalid agent result state: {result_status.value}",
        error_code="AGENT_PROTOCOL_ERROR",
    )
```

For post-result approval:

```python
if task.requires_approval or result_requires_approval:
    suggested_risk = max(
        task.risk_level,
        result_risk,
        key=_RISK_RANK.__getitem__,
    )
    post_evaluation = self._approvals.evaluate(
        task.operation,
        suggested_risk,
    )
    self._task_manager.wait_for_approval(
        task.id,
        result_payload,
    )
    self._approvals.begin(
        task.id,
        "post_result",
        post_evaluation,
        result_ready=True,
    )
    self._state = OrchestratorState.WAITING_APPROVAL
    return self._result(
        message=(
            f"Founder approval required for result "
            f"of task {task.id}"
        ),
        pending_task_id=task.id,
    )

self._task_manager.complete(task.id, result_payload)
```

Preserve the existing policy call so `ApprovalService` continues enforcing operation minimums.

- [ ] **Step 7: Add A→B→C native integration test with no agent-name workflow logic**

Add these test-only native agents near the other fake agents in `tests/test_orchestrator.py`:

```python
class NativeAAgent(JarvisNativeAgent):
    name = "native_a"
    requests: list[AgentTaskRequest] = []

    def _execute(
        self,
        request: AgentTaskRequest,
    ) -> AgentTaskResult:
        type(self).requests.append(request)
        return AgentTaskResult(
            task_id=request.task_id,
            status=TaskStatus.COMPLETED,
            output_data={"artifact": "a"},
            summary="A complete",
            error=None,
            risk_level=request.risk_level,
            requires_approval=False,
        )


class NativeBAgent(JarvisNativeAgent):
    name = "native_b"
    requests: list[AgentTaskRequest] = []

    def _execute(
        self,
        request: AgentTaskRequest,
    ) -> AgentTaskResult:
        type(self).requests.append(request)
        return AgentTaskResult(
            task_id=request.task_id,
            status=TaskStatus.COMPLETED,
            output_data={"artifact": "b"},
            summary="B complete",
            error=None,
            risk_level=request.risk_level,
            requires_approval=False,
        )


class NativeCAgent(JarvisNativeAgent):
    name = "native_c"
    requests: list[AgentTaskRequest] = []

    def _execute(
        self,
        request: AgentTaskRequest,
    ) -> AgentTaskResult:
        type(self).requests.append(request)
        return AgentTaskResult(
            task_id=request.task_id,
            status=TaskStatus.COMPLETED,
            output_data={"artifact": "c"},
            summary="C complete",
            error=None,
            risk_level=request.risk_level,
            requires_approval=False,
        )
```

Reset all three `.requests` lists in `setUp()`.

Then add the integration test:

```python
def test_three_task_native_chain_uses_dependencies_not_agent_names(self):
    first = self.make_task("a", "cap_a")
    second = self.make_task(
        "b",
        "cap_b",
        dependencies=(first.id,),
    )
    third = self.make_task(
        "c",
        "cap_c",
        dependencies=(first.id, second.id),
    )

    registry = self.make_registry(
        self.registration(
            "native_a",
            NativeAAgent,
            "cap_a",
            contract_version=AgentContractVersion.JARVIS_NATIVE_V1,
        ),
        self.registration(
            "native_b",
            NativeBAgent,
            "cap_b",
            contract_version=AgentContractVersion.JARVIS_NATIVE_V1,
        ),
        self.registration(
            "native_c",
            NativeCAgent,
            "cap_c",
            contract_version=AgentContractVersion.JARVIS_NATIVE_V1,
        ),
    )

    orchestrator, _, manager, _, _ = self.make_orchestrator(
        self.make_plan(first, second, third),
        registry,
    )

    result = orchestrator.start("Execute native graph")

    self.assertEqual(result.state, OrchestratorState.COMPLETED)
    self.assertTrue(manager.is_complete())
    self.assertEqual(
        frozenset(NativeCAgent.requests[0].dependency_results),
        frozenset({first.id, second.id}),
    )
```

The production Orchestrator must contain no `native_a`, `native_b`, `native_c`, `developer`, `tester`, or `reviewer` branches.

- [ ] **Step 8: Run the complete Orchestrator suite**

Run:

```powershell
python -m unittest tests.test_orchestrator -v
```

Expected: all Orchestrator tests PASS, including old legacy behavior and new native behavior.

- [ ] **Step 9: Commit native result integration**

Run:

```powershell
git diff --check
git add -- jarvis/orchestrator.py tests/test_orchestrator.py
git diff --cached --check
git commit -m "feat: integrate Jarvis-native result protocol"
```

---

### Task 1.7: Full regression, static verification, and source-of-truth status

**Files:**
- Modify only after all code verification passes: `JARVIS_STATUS.md`
- No production code changes unless verification exposes a defect.

**Interfaces:**
- Produces:
  - Fully verified Task 1 implementation.
  - Updated source-of-truth status pointing to the actual implementation commits.
  - Exact next engineering step: `Task 2 — Developer Agent`.

- [ ] **Step 1: Run the entire regression suite**

Run:

```powershell
python -m unittest discover -s tests -v
```

Expected:
- All pre-existing 137 tests PASS.
- All new Task 1 tests PASS.
- Final total is greater than 137.
- Record the exact final count; do not estimate it.

- [ ] **Step 2: Run compile verification**

Run:

```powershell
python -m compileall -q .
```

Expected: exit code `0` and no syntax errors.

- [ ] **Step 3: Run whitespace/diff verification**

Run:

```powershell
git diff --check
git status --short
```

Expected:
- `git diff --check` produces no output.
- Working tree is clean before the status documentation update.

- [ ] **Step 4: Audit for forbidden agent-name branching**

Run:

```powershell
git grep -n -E 'if .*developer|if .*tester|if .*reviewer|elif .*developer|elif .*tester|elif .*reviewer' -- jarvis agents
```

Expected: no new Orchestrator workflow branching by specialist name.

Also inspect the native branch explicitly:

```powershell
git grep -n "contract_version" -- jarvis agents
```

Expected: branching is based on `AgentContractVersion`, not specialist identity.

- [ ] **Step 5: Verify legacy registrations remain `LEGACY_V1` by default**

Run the focused suites:

```powershell
python -m unittest tests.test_registry tests.test_main tests.test_agents -v
```

Expected: PASS without modifying Producer, Researcher, or Game Director payload contracts.

- [ ] **Step 6: Update `JARVIS_STATUS.md` only after the exact verification numbers are known**

Update the status document to include:
- Task 1 — Jarvis-native Agent Task Contract: COMPLETE.
- `AgentTaskRequest`, `AgentTaskResult`, `AgentContractVersion`, `JarvisNativeAgent`.
- Native dependency-result propagation.
- Native fail-closed protocol semantics.
- Legacy `LEGACY_V1` compatibility.
- Exact full test count from Step 1.
- `compileall PASS`.
- `git diff --check PASS`.
- Next task: `Task 2 — Developer Agent`.
- The exact implementation commit SHAs created in Tasks 1.1–1.6.

Do not claim Developer/Tester/Reviewer exist.

- [ ] **Step 7: Commit only the status update**

Run:

```powershell
git diff -- JARVIS_STATUS.md
git add -- JARVIS_STATUS.md
git diff --cached --check
git commit -m "docs: finalize Jarvis-native agent contract status"
```

- [ ] **Step 8: Push only after explicit Founder authorization**

Before pushing, show:

```powershell
git log --oneline --decorate -8
git status --short
```

Then, only with explicit Founder authorization:

```powershell
git push origin agent/agent-contract-v1
```

- [ ] **Step 9: Verify GitHub canonical state after push**

Run locally:

```powershell
git rev-parse HEAD
git status --short
```

Then verify the returned SHA against GitHub and confirm:
- branch `agent/agent-contract-v1` points at that SHA,
- working tree is clean,
- all implementation/status commits are present,
- only Task 1 scope changed.

---

## Final Acceptance Checklist

Task 1 is complete only when every item below is verified:

- [ ] `AgentTaskRequest` exists and validates all approved fields.
- [ ] `AgentTaskResult` exists and permits only `COMPLETED`, `FAILED`, `WAITING_APPROVAL`.
- [ ] `AgentContractVersion` contains `LEGACY_V1` and `JARVIS_NATIVE_V1`.
- [ ] Existing registrations default to `LEGACY_V1`.
- [ ] Native registrations require `JarvisNativeAgent`.
- [ ] `JarvisNativeAgent` converts transport messages to typed requests/results.
- [ ] Native request payload contains no duplicated `priority`, `risk_level`, `requires_approval`, or `objective`.
- [ ] Dependency results are keyed exactly by declared dependency task IDs.
- [ ] `input_data` and `dependency_results` are not merged.
- [ ] Native completed results store `summary` + `output_data`.
- [ ] Result task-ID correlation is enforced.
- [ ] Wrong contract version, kind, malformed payload, task mismatch, and native protocol exceptions fail closed.
- [ ] Native result risk can escalate Founder approval requirements.
- [ ] Agents cannot reduce policy minimum risk.
- [ ] No agent-name workflow branching exists.
- [ ] Producer, Researcher, and Game Director remain legacy-compatible.
- [ ] No Developer/Tester/Reviewer/Git Worker implementation is included.
- [ ] All old 137 tests remain green.
- [ ] All new Task 1 tests pass.
- [ ] Exact total test count is recorded.
- [ ] `python -m compileall -q .` passes.
- [ ] `git diff --check` passes.
- [ ] `JARVIS_STATUS.md` reflects the verified implementation.
- [ ] GitHub branch state is verified after the authorized push.

## Next Engineering Step

After this plan is fully executed and Task 1 is verified, start a separate design/implementation cycle for:

`Bootstrap Engineering Team — Task 2: Developer Agent`

The Developer Agent must consume only `AgentTaskRequest` and return only `AgentTaskResult`; it must not require new role-specific branching in `JarvisOrchestrator`.
