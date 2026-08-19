# Jarvis Orchestrator v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the fixed Producer → Researcher → Game Director execution path with a tested, synchronous, capability-routed Jarvis Orchestrator that validates plans, tracks dependencies, enforces approval policy, and fails closed.

**Architecture:** Keep `core/` as generic messaging/LLM infrastructure and add a focused `jarvis/` package for orchestration. The local LLM-backed Planner proposes structured work; deterministic Registry, Router, Task Manager, Approval Service, and Orchestrator decide what may execute and when.

**Tech Stack:** Python 3.14+, standard library only (`dataclasses`, `enum`, `json`, `uuid`, `datetime`, `unittest`), existing Ollama client, existing `AgentMessage` and `MessageBus`.

**Spec:** `docs/superpowers/specs/2026-08-19-jarvis-orchestrator-v1-design.md`

## Global Constraints

- Python standard library first; no Pydantic or mandatory third-party core dependency.
- Execution remains synchronous in v1.
- MessageBus remains in-memory in v1 and its public interface remains compatible with existing agents.
- Existing 29 Agent Contract v1 tests must remain green throughout implementation.
- Planner/agent suggested risk may never reduce approval policy minimum risk.
- Router may select only enabled, registered agents that satisfy all required capabilities and allowed risk constraints.
- Task Manager is the only source of truth for task state and plan completion.
- HIGH operations require Founder approval; CRITICAL operations require Founder approval plus explicit confirmation.
- Invalid plans, unknown capabilities, missing routes, execution failures, and dependency failures fail closed.
- `core/workflow.py` stays available during migration; remove it only in a later cleanup.
- No autonomous code-writing agents, parallel execution, SQLite persistence, Git automation, Roblox publishing, Game Factory, automatic replanning, or partial-agent team splitting in this version.

## File Map

**Create**
- `jarvis/__init__.py` — package marker and public exports only.
- `jarvis/models.py` — `JarvisTask`, `ExecutionPlan`, `AgentRegistration`, `OrchestratorState`, approval/result data types.
- `jarvis/registry.py` — explicit specialist catalog and capability/risk lookup.
- `jarvis/router.py` — deterministic capability router and `NoRouteError`.
- `jarvis/task_manager.py` — task lifecycle, dependency resolution, blocking, plan completion.
- `jarvis/approvals.py` — policy minimums, effective risk, pending approval context, audit records.
- `jarvis/planner.py` — Ollama-backed JSON planner parser/validator.
- `jarvis/orchestrator.py` — deterministic orchestration loop and Founder decision handling.
- `tests/test_jarvis_models.py`
- `tests/test_registry.py`
- `tests/test_router.py`
- `tests/test_task_manager.py`
- `tests/test_approvals.py`
- `tests/test_planner.py`
- `tests/test_orchestrator.py`

**Modify**
- `core/contracts.py` — add `READY` and `BLOCKED` to `TaskStatus`.
- `main.py` — switch the active CLI entry point to `JarvisOrchestrator` after its tests are green.
- `JARVIS_STATUS.md` — record real pushed branch state and Orchestrator v1 completion state.

---

### Task 1: Domain Models and Shared Task States

**Files:**
- Modify: `core/contracts.py`
- Create: `jarvis/__init__.py`
- Create: `jarvis/models.py`
- Create: `tests/test_jarvis_models.py`

**Interfaces:**
- Consumes: `Priority`, `RiskLevel`, `TaskStatus` from `core.contracts`.
- Produces:
  - `JarvisTask`
  - `ExecutionPlan`
  - `AgentRegistration`
  - `OrchestratorState`
  - `ApprovalDecision`
  - `ApprovalDisposition`
  - `ApprovalEvaluation`
  - `PendingApproval`
  - `OrchestratorResult`

- [ ] **Step 1: Write failing model/state tests**

Create `tests/test_jarvis_models.py` with concrete coverage:

```python
import unittest

from core.contracts import Priority, RiskLevel, TaskStatus
from jarvis.models import (
    AgentRegistration,
    ApprovalDecision,
    OrchestratorState,
    ExecutionPlan,
    JarvisTask,
)


class JarvisModelTests(unittest.TestCase):
    def test_task_status_includes_ready_and_blocked(self):
        self.assertEqual(TaskStatus.READY.value, "ready")
        self.assertEqual(TaskStatus.BLOCKED.value, "blocked")

    def test_jarvis_task_has_safe_defaults(self):
        task = JarvisTask(
            plan_key="market_research",
            goal_id="goal-1",
            title="Market research",
            objective="Find opportunities",
            required_capabilities=("market_research",),
        )
        self.assertTrue(task.id)
        self.assertEqual(task.status, TaskStatus.PENDING)
        self.assertEqual(task.priority, Priority.NORMAL)
        self.assertEqual(task.risk_level, RiskLevel.LOW)
        self.assertEqual(task.dependencies, ())
        self.assertIsNone(task.assigned_agent)

    def test_execution_plan_rejects_duplicate_task_keys(self):
        first = JarvisTask(
            plan_key="same",
            goal_id="goal-1",
            title="A",
            objective="A",
            required_capabilities=("market_research",),
        )
        second = JarvisTask(
            plan_key="same",
            goal_id="goal-1",
            title="B",
            objective="B",
            required_capabilities=("concept_analysis",),
        )
        with self.assertRaisesRegex(ValueError, "duplicate task plan_key"):
            ExecutionPlan(
                goal_id="goal-1",
                goal="Find a game",
                summary="Research",
                tasks=(first, second),
            )

    def test_agent_registration_normalizes_capability_sets(self):
        registration = AgentRegistration(
            name="researcher",
            agent_class=object,
            capabilities=frozenset({"market_research"}),
            allowed_risk_levels=frozenset({RiskLevel.LOW, RiskLevel.MEDIUM}),
        )
        self.assertIn("market_research", registration.capabilities)
        self.assertTrue(registration.enabled)

    def test_orchestrator_and_approval_enums_are_stable(self):
        self.assertEqual(OrchestratorState.WAITING_APPROVAL.value, "waiting_approval")
        self.assertEqual(ApprovalDecision.APPROVE.value, "approve")
```

- [ ] **Step 2: Run the model tests and confirm failure**

Run:

```powershell
python -m unittest tests.test_jarvis_models -v
```

Expected: import/attribute failures because `jarvis.models`, `READY`, and `BLOCKED` do not exist yet.

- [ ] **Step 3: Add shared status values**

Modify `TaskStatus` in `core/contracts.py` to include exactly:

```python
class TaskStatus(str, Enum):
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    WAITING_APPROVAL = "waiting_approval"
    REJECTED = "rejected"
```

Do not rename or remove any existing values.

- [ ] **Step 4: Implement the v1 domain models**

Create `jarvis/models.py` using `@dataclass(slots=True)` and these exact public signatures:

```python
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
    id: str = field(default_factory=lambda: str(uuid4()))
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
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = None
    completed_at: datetime | None = None


@dataclass(slots=True)
class ExecutionPlan:
    goal_id: str
    goal: str
    summary: str
    tasks: tuple[JarvisTask, ...]
    requires_founder_approval: bool = False


@dataclass(frozen=True, slots=True)
class AgentRegistration:
    name: str
    agent_class: type
    capabilities: frozenset[str]
    allowed_risk_levels: frozenset[RiskLevel]
    enabled: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


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


@dataclass(frozen=True, slots=True)
class OrchestratorResult:
    state: OrchestratorState
    goal_id: str
    message: str
    pending_task_id: str | None = None
    error_code: str | None = None
    change_context: dict[str, Any] = field(default_factory=dict)
```

Validation requirements inside `__post_init__`:
- all IDs/keys/titles/objectives/names are non-blank strings;
- `required_capabilities` contains only non-blank strings and is non-empty for executable tasks;
- dependencies contain non-blank strings and cannot include the task's own `id`;
- `ExecutionPlan.tasks` is non-empty and `plan_key` values are unique;
- all tasks in an `ExecutionPlan` have the same `goal_id` as the plan;
- `AgentRegistration.capabilities` is non-empty;
- `AgentRegistration.allowed_risk_levels` is non-empty.

Create `jarvis/__init__.py` with no side effects; export only model names that are stable enough for imports.

- [ ] **Step 5: Run model tests and the full existing suite**

Run:

```powershell
python -m unittest tests.test_jarvis_models -v
python -m unittest discover -s tests -v
```

Expected: new tests pass; all pre-existing Agent Contract tests remain green.

- [ ] **Step 6: Commit Task 1**

```powershell
git add core/contracts.py jarvis/__init__.py jarvis/models.py tests/test_jarvis_models.py
git commit -m "feat: add Jarvis orchestration domain models"
```

---

### Task 2: Explicit Agent Registry

**Files:**
- Create: `jarvis/registry.py`
- Create: `tests/test_registry.py`

**Interfaces:**
- Consumes: `BaseAgent`, `AgentRegistration`, `RiskLevel`.
- Produces:
  - `AgentRegistry.register(registration: AgentRegistration) -> None`
  - `AgentRegistry.get(name: str) -> AgentRegistration`
  - `AgentRegistry.create(name: str) -> BaseAgent`
  - `AgentRegistry.enabled_capabilities() -> frozenset[str]`
  - `AgentRegistry.candidates(required_capabilities: frozenset[str], risk_level: RiskLevel) -> tuple[AgentRegistration, ...]`

- [ ] **Step 1: Write failing registry tests**

Create `tests/test_registry.py` with small fake `BaseAgent` subclasses and tests for:
- registration and lookup;
- duplicate name rejection;
- disabled registrations excluded from `candidates()` and `enabled_capabilities()`;
- candidates must contain all required capabilities;
- risk level must be listed in `allowed_risk_levels`;
- `create()` instantiates the registered class and verifies it is a `BaseAgent`.

Use a concrete assertion such as:

```python
self.assertEqual(
    [item.name for item in registry.candidates(frozenset({"market_research"}), RiskLevel.LOW)],
    ["researcher"],
)
```

- [ ] **Step 2: Run and confirm failure**

```powershell
python -m unittest tests.test_registry -v
```

Expected: failure because `jarvis.registry` does not exist.

- [ ] **Step 3: Implement `AgentRegistry`**

Create `jarvis/registry.py` with deterministic insertion-independent output. `candidates()` must return registrations sorted by `registration.name`, even if registration order differs.

Required error behavior:
- duplicate name → `ValueError("agent already registered: <name>")`;
- unknown `get()`/`create()` name → `KeyError(name)`;
- registered class not subclassing `BaseAgent` → `TypeError` during registration;
- created instance name must equal registration name or `ValueError` is raised.

- [ ] **Step 4: Run registry tests plus full suite**

```powershell
python -m unittest tests.test_registry -v
python -m unittest discover -s tests -v
```

Expected: all pass.

- [ ] **Step 5: Commit Task 2**

```powershell
git add jarvis/registry.py tests/test_registry.py
git commit -m "feat: add explicit Jarvis agent registry"
```

---

### Task 3: Deterministic Capability Router

**Files:**
- Create: `jarvis/router.py`
- Create: `tests/test_router.py`

**Interfaces:**
- Consumes: `JarvisTask`, `AgentRegistry`, `RiskLevel`.
- Produces:
  - `NoRouteError(RuntimeError)` with `.task_id` and `.required_capabilities`.
  - `JarvisRouter.route(task: JarvisTask, effective_risk: RiskLevel) -> AgentRegistration`

- [ ] **Step 1: Write failing router tests**

Create `tests/test_router.py` covering these exact ordering rules:
1. exact capability-set match beats a larger superset;
2. otherwise smallest superset wins;
3. equal-size supersets break ties alphabetically by registration name;
4. disabled agents are never selected;
5. risk-disallowed agents are never selected;
6. no full match raises `NoRouteError` and never returns a partial match.

Representative test:

```python
selected = router.route(task, RiskLevel.LOW)
self.assertEqual(selected.name, "researcher")
```

- [ ] **Step 2: Run and confirm failure**

```powershell
python -m unittest tests.test_router -v
```

- [ ] **Step 3: Implement the router**

Implementation algorithm must be exactly:

```python
candidates = registry.candidates(frozenset(task.required_capabilities), effective_risk)
if not candidates:
    raise NoRouteError(task.id, task.required_capabilities)

required = frozenset(task.required_capabilities)
return min(
    candidates,
    key=lambda item: (
        0 if item.capabilities == required else 1,
        len(item.capabilities - required),
        item.name,
    ),
)
```

Do not consult the LLM in the Router.

- [ ] **Step 4: Run router and full tests**

```powershell
python -m unittest tests.test_router -v
python -m unittest discover -s tests -v
```

- [ ] **Step 5: Commit Task 3**

```powershell
git add jarvis/router.py tests/test_router.py
git commit -m "feat: route Jarvis tasks by capability"
```

---

### Task 4: Task Manager and Dependency State Machine

**Files:**
- Create: `jarvis/task_manager.py`
- Create: `tests/test_task_manager.py`

**Interfaces:**
- Consumes: `ExecutionPlan`, `JarvisTask`, `TaskStatus`.
- Produces:
  - `TaskManager.load_plan(plan: ExecutionPlan) -> None`
  - `TaskManager.get(task_id: str) -> JarvisTask`
  - `TaskManager.ready_tasks() -> tuple[JarvisTask, ...]`
  - `TaskManager.start(task_id: str, agent_name: str) -> JarvisTask`
  - `TaskManager.complete(task_id: str, result: dict[str, Any]) -> JarvisTask`
  - `TaskManager.fail(task_id: str, error: str) -> JarvisTask`
  - `TaskManager.wait_for_approval(task_id: str, result: dict[str, Any] | None = None) -> JarvisTask`
  - `TaskManager.approve(task_id: str) -> JarvisTask`
  - `TaskManager.reject(task_id: str, reason: str) -> JarvisTask`
  - `TaskManager.is_complete() -> bool`
  - `TaskManager.has_failed() -> bool`

- [ ] **Step 1: Write failing dependency/state tests**

Create `tests/test_task_manager.py` covering:
- root task becomes `READY` after `load_plan()`;
- dependent task starts `BLOCKED` until every dependency is `COMPLETED`;
- completing a prerequisite unlocks the dependent to `READY`;
- `start()` only accepts `READY` and records `assigned_agent`/`started_at`;
- `complete()` only accepts `RUNNING` or approved `WAITING_APPROVAL` result flow;
- `fail()` marks task `FAILED` and recursively keeps downstream tasks `BLOCKED`;
- `reject()` marks task `REJECTED` and downstream tasks `BLOCKED`;
- `wait_for_approval()` preserves result without unlocking dependents;
- `approve()` converts a post-result `WAITING_APPROVAL` task to `COMPLETED` and unlocks dependents;
- plan completion is true only when every task is `COMPLETED`;
- missing dependency ID at load time raises `ValueError`.

- [ ] **Step 2: Run and confirm failure**

```powershell
python -m unittest tests.test_task_manager -v
```

- [ ] **Step 3: Implement dependency initialization**

On `load_plan()`:
- copy task objects into an internal `dict[str, JarvisTask]` keyed by task ID;
- verify every dependency is an existing task ID;
- tasks with no dependencies become `READY`;
- tasks with dependencies become `BLOCKED`;
- reject loading a second active plan into the same manager instance.

- [ ] **Step 4: Implement state transitions and downstream refresh**

Use one private method `_refresh_blocked_tasks()` after completion/approval/rejection/failure. A blocked task becomes `READY` only if every dependency is `COMPLETED`. If any dependency is `FAILED` or `REJECTED`, it stays `BLOCKED` permanently in v1.

Timestamps must be timezone-aware UTC.

- [ ] **Step 5: Run Task Manager and full tests**

```powershell
python -m unittest tests.test_task_manager -v
python -m unittest discover -s tests -v
```

- [ ] **Step 6: Commit Task 4**

```powershell
git add jarvis/task_manager.py tests/test_task_manager.py
git commit -m "feat: add Jarvis task dependency manager"
```

---

### Task 5: Approval Policy and Founder Gates

**Files:**
- Create: `jarvis/approvals.py`
- Create: `tests/test_approvals.py`

**Interfaces:**
- Consumes: `RiskLevel`, `ApprovalDecision`, `ApprovalDisposition`, `ApprovalEvaluation`, `PendingApproval`.
- Produces:
  - `ApprovalService.evaluate(operation: str | None, suggested_risk: RiskLevel) -> ApprovalEvaluation`
  - `ApprovalService.begin(task_id: str, stage: str, evaluation: ApprovalEvaluation, result_ready: bool = False) -> PendingApproval`
  - `ApprovalService.decide(decision: ApprovalDecision, *, explicit_confirmation: bool = False, change_context: dict[str, Any] | None = None) -> PendingApproval | None`
  - `ApprovalService.pending -> PendingApproval | None`
  - `ApprovalService.audit_log() -> tuple[dict[str, Any], ...]`

- [ ] **Step 1: Write failing approval tests**

Create `tests/test_approvals.py` with tests for:
- LOW → `CONTINUE`;
- MEDIUM → `CONTINUE_AUDIT` and append audit entry;
- HIGH → `WAIT`;
- CRITICAL → `WAIT` with `requires_explicit_confirmation=True`;
- operation policy raises LOW `publish` to HIGH;
- operation policy raises LOW `credentials` to CRITICAL;
- higher suggested risk is never lowered by policy;
- beginning a second pending gate while one exists raises `RuntimeError`;
- CRITICAL `APPROVE` without explicit confirmation raises `PermissionError` and keeps gate pending;
- CRITICAL `APPROVE` with confirmation releases gate;
- `REJECT` releases the approval object only through orchestrator-controlled task state handling;
- `CHANGE` retains caller-provided change context in the service audit record.

- [ ] **Step 2: Run and confirm failure**

```powershell
python -m unittest tests.test_approvals -v
```

- [ ] **Step 3: Implement policy minimums and risk ordering**

Use exactly:

```python
_POLICY_MINIMUMS = {
    "publish": RiskLevel.HIGH,
    "delete_important_data": RiskLevel.HIGH,
    "credentials": RiskLevel.CRITICAL,
    "security_policy_change": RiskLevel.CRITICAL,
    "locked_core_change": RiskLevel.CRITICAL,
    "paid_action": RiskLevel.CRITICAL,
}

_RISK_RANK = {
    RiskLevel.LOW: 0,
    RiskLevel.MEDIUM: 1,
    RiskLevel.HIGH: 2,
    RiskLevel.CRITICAL: 3,
}
```

Compute effective risk using `max(..., key=_RISK_RANK.__getitem__)`.

- [ ] **Step 4: Implement pending/audit behavior**

Audit entries are plain immutable snapshots (`dict.copy()` when exposed through `audit_log()`), containing at minimum:
- task ID when applicable;
- stage;
- suggested risk;
- policy risk;
- effective risk;
- action/disposition/decision;
- UTC timestamp.

No disk persistence in v1.

- [ ] **Step 5: Run approval and full tests**

```powershell
python -m unittest tests.test_approvals -v
python -m unittest discover -s tests -v
```

- [ ] **Step 6: Commit Task 5**

```powershell
git add jarvis/approvals.py tests/test_approvals.py
git commit -m "feat: enforce Jarvis founder approval policy"
```

---

### Task 6: Structured Ollama Planner and Plan Validation

**Files:**
- Create: `jarvis/planner.py`
- Create: `tests/test_planner.py`

**Interfaces:**
- Consumes: `core.ollama_client.chat`, `AgentRegistry.enabled_capabilities()`, `ExecutionPlan`, `JarvisTask`, `Priority`, `RiskLevel`.
- Produces:
  - `PlanValidationError(ValueError)` with `.code == "PLAN_INVALID"`.
  - `JarvisPlanner.create_plan(founder_goal: str, registry: AgentRegistry) -> ExecutionPlan`.

- [ ] **Step 1: Write failing planner tests with mocked LLM**

Create `tests/test_planner.py`; patch `jarvis.planner.chat` and cover:
- valid one-task JSON → valid `ExecutionPlan`;
- valid two-task dependency keys are converted to internal task IDs;
- malformed JSON → `PlanValidationError`;
- missing task key/title/objective/capabilities → `PlanValidationError`;
- duplicate task key → `PlanValidationError`;
- unknown capability → `PlanValidationError`;
- dependency referencing missing key → `PlanValidationError`;
- self dependency → `PlanValidationError`;
- circular dependency → `PlanValidationError`;
- invalid priority/risk string → `PlanValidationError`;
- non-boolean `requires_approval` → `PlanValidationError`;
- blank Founder goal is rejected before calling the LLM.

Use exact mock JSON in tests rather than testing prompt wording.

- [ ] **Step 2: Run and confirm failure**

```powershell
python -m unittest tests.test_planner -v
```

- [ ] **Step 3: Implement planner prompt and strict parser**

`JarvisPlanner.create_plan()` must:
1. reject blank Founder goals;
2. read enabled capability catalog from Registry;
3. call existing `chat(messages)` exactly once;
4. `json.loads()` the returned string;
5. validate top-level object and non-empty `tasks` list;
6. first pass: validate each task and allocate its `JarvisTask.id`;
7. second pass: translate dependency `key` strings to internal task IDs;
8. detect cycles using DFS with `visiting` and `visited` sets;
9. return `ExecutionPlan`.

The system prompt must instruct Qwen to return JSON only and to use only supplied capabilities. The parser remains authoritative if Qwen violates that instruction.

- [ ] **Step 4: Run planner and full tests**

```powershell
python -m unittest tests.test_planner -v
python -m unittest discover -s tests -v
```

- [ ] **Step 5: Commit Task 6**

```powershell
git add jarvis/planner.py tests/test_planner.py
git commit -m "feat: add validated Jarvis execution planner"
```

---

### Task 7: Jarvis Orchestrator Execution Loop

**Files:**
- Create: `jarvis/orchestrator.py`
- Create: `tests/test_orchestrator.py`

**Interfaces:**
- Consumes:
  - `JarvisPlanner.create_plan()`
  - `AgentRegistry`
  - `JarvisRouter.route()`
  - `TaskManager`
  - `ApprovalService`
  - `MessageBus`
  - `AgentMessage`, `MessageKind`, `TaskStatus`
- Produces:
  - `JarvisOrchestrator.start(founder_goal: str) -> OrchestratorResult`
  - `JarvisOrchestrator.decide(decision: ApprovalDecision, *, explicit_confirmation: bool = False, change_context: dict[str, Any] | None = None) -> OrchestratorResult`
  - `JarvisOrchestrator.state -> OrchestratorState`
  - `JarvisOrchestrator.active_plan -> ExecutionPlan | None`

- [ ] **Step 1: Write failing orchestrator integration tests**

Create `tests/test_orchestrator.py` using fake `BaseAgent` classes and a fake planner that returns pre-built `ExecutionPlan` objects. Cover:
- two sequential tasks execute and route to different agents by capability;
- routing never depends on Producer/Researcher/Game Director names;
- agent receives a `MessageKind.TASK` with `payload["task_id"]` and `payload["input_data"]`;
- successful agent result marks task complete and unlocks dependent task;
- agent `FAILED` result makes orchestrator `FAILED` and does not run dependents;
- missing route returns `FAILED` with `error_code="NO_ROUTE"`;
- HIGH protected operation stops before agent execution;
- APPROVE after pre-execution gate resumes and executes the task;
- CRITICAL approval without explicit confirmation remains waiting/fails the decision call safely;
- post-result `requires_approval=True` executes agent, stores result, then waits before unlocking dependents;
- APPROVE after post-result gate marks task complete and resumes dependents;
- REJECT marks gated task rejected and leaves dependents blocked;
- CHANGE returns `WAITING_APPROVAL` result with `change_context` and does not autonomously replan;
- orchestrator returns `COMPLETED` only after every task completes;
- disabled or risk-disallowed agents are never executed.

- [ ] **Step 2: Run and confirm failure**

```powershell
python -m unittest tests.test_orchestrator -v
```

- [ ] **Step 3: Implement constructor and state guards**

Use this constructor boundary:

```python
class JarvisOrchestrator:
    def __init__(
        self,
        *,
        planner: JarvisPlanner,
        registry: AgentRegistry,
        router: JarvisRouter,
        task_manager: TaskManager,
        approvals: ApprovalService,
        bus: MessageBus,
    ) -> None:
        ...
```

`start()` is allowed only from `IDLE`; `decide()` is allowed only from `WAITING_APPROVAL` with an active pending approval.

- [ ] **Step 4: Implement one synchronous execution loop**

Private `_run_until_blocked()` must repeatedly:
1. return `COMPLETED` if `task_manager.is_complete()`;
2. return `FAILED` if `task_manager.has_failed()`;
3. obtain `ready_tasks()` and select the first task deterministically by `(priority rank descending, created_at, id)`;
4. call `approvals.evaluate(task.operation, task.risk_level)`;
5. for pre-execution HIGH/CRITICAL, set task `WAITING_APPROVAL`, create pending approval, set orchestrator `WAITING_APPROVAL`, return;
6. route using effective risk;
7. instantiate agent from Registry;
8. `task_manager.start()`;
9. publish `AgentMessage(sender="jarvis", recipient=agent.name, kind=TASK, ...)`;
10. receive that task message for the agent and call `agent.handle()`;
11. publish the returned result to MessageBus;
12. if agent result status is `FAILED`, call `task_manager.fail()` and return `FAILED`;
13. if result is not addressed back to `jarvis`, fail closed;
14. if task requires post-result approval or result itself sets `requires_approval=True`, save result through `wait_for_approval()`, begin pending post-result gate, return `WAITING_APPROVAL`;
15. otherwise call `task_manager.complete()` and continue loop.

No recursive orchestration calls; use the loop so long plans do not grow the Python call stack.

- [ ] **Step 5: Implement Founder decisions**

`decide()` behavior:
- `APPROVE` pre-execution → release gate, restore task to `READY`, continue `_run_until_blocked()`;
- `APPROVE` post-result → mark task complete with stored result, release gate, continue;
- `REJECT` → task manager rejects task, release gate, set orchestrator `FAILED`, return `error_code="APPROVAL_REJECTED"`;
- `CHANGE` → keep execution stopped, release the pending gate only after snapshotting change context into result/audit, keep state `WAITING_APPROVAL`, return context to caller without calling Planner again;
- CRITICAL `APPROVE` requires `explicit_confirmation=True`.

- [ ] **Step 6: Run orchestrator and full tests**

```powershell
python -m unittest tests.test_orchestrator -v
python -m unittest discover -s tests -v
```

Expected: all existing and new tests pass.

- [ ] **Step 7: Commit Task 7**

```powershell
git add jarvis/orchestrator.py tests/test_orchestrator.py
git commit -m "feat: add Jarvis dynamic orchestration loop"
```

---

### Task 8: Wire Existing Agents into Registry and Migrate `main.py`

**Files:**
- Modify: `main.py`
- Modify: `JARVIS_STATUS.md`
- Test: existing `tests/test_main.py`
- Test: `tests/test_orchestrator.py`

**Interfaces:**
- Consumes: current `ProducerAgent`, `ResearcherAgent`, `GameDirectorAgent`, new Registry/Planner/Router/TaskManager/ApprovalService/Orchestrator.
- Produces: active CLI path using `JarvisOrchestrator`; legacy `core/workflow.py` remains importable but is no longer the active `main.py` path.

- [ ] **Step 1: Add/adjust a failing `main.py` behavior test**

Update `tests/test_main.py` so it still verifies import safety and also patches the orchestrator bootstrap rather than expecting `run_discovery_workflow()` to be the active path.

The CLI test must verify Founder decisions are normalized case-insensitively to `ApprovalDecision.APPROVE`, `CHANGE`, or `REJECT` and that CRITICAL confirmation is asked only when the returned pending context requires it.

- [ ] **Step 2: Run `main.py` tests and confirm the migration test fails**

```powershell
python -m unittest tests.test_main -v
```

Expected: new migration assertion fails while current fixed workflow is still active.

- [ ] **Step 3: Add explicit startup registrations in `main.py`**

Register existing agents with capabilities sufficient for current discovery behavior, for example:

```python
AgentRegistration(
    name="producer",
    agent_class=ProducerAgent,
    capabilities=frozenset({"production_planning", "research_coordination"}),
    allowed_risk_levels=frozenset({RiskLevel.LOW, RiskLevel.MEDIUM}),
)
AgentRegistration(
    name="researcher",
    agent_class=ResearcherAgent,
    capabilities=frozenset({"market_research", "competitor_analysis", "concept_analysis"}),
    allowed_risk_levels=frozenset({RiskLevel.LOW, RiskLevel.MEDIUM}),
)
AgentRegistration(
    name="game_director",
    agent_class=GameDirectorAgent,
    capabilities=frozenset({"game_direction", "concept_selection"}),
    allowed_risk_levels=frozenset({RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH}),
)
```

Keep registration explicit. Do not scan the `agents/` directory.

- [ ] **Step 4: Replace active fixed workflow bootstrap**

`main()` should construct:

```text
MessageBus
AgentRegistry
JarvisPlanner
JarvisRouter
TaskManager
ApprovalService
JarvisOrchestrator
```

Then call `orchestrator.start(founder_request)` and print structured state/result information. When state is `WAITING_APPROVAL`, ask for `APPROVE / CHANGE / REJECT` and call `orchestrator.decide(...)`.

Do not delete `core/workflow.py`.

- [ ] **Step 5: Update `JARVIS_STATUS.md` to match reality**

Make these facts explicit:
- Agent Contract v1 branch was pushed to GitHub successfully;
- Orchestrator v1 architecture is implemented when this task is complete;
- list created `jarvis/` components;
- record actual final test count from the test command, not an estimate;
- record the current commit SHA with `git rev-parse HEAD` after the implementation commit;
- next engineering step becomes Developer + Tester + Reviewer bootstrap team, then Git Worker, then Agent Factory.

Remove the stale line claiming the feature branch has not been pushed.

- [ ] **Step 6: Run full verification**

Run exactly:

```powershell
python -m unittest discover -s tests -v
python -m compileall agents core jarvis main.py
git diff --check
```

Expected:
- every unittest passes;
- `compileall` reports no syntax failures;
- `git diff --check` prints nothing.

Then inspect:

```powershell
git status --short
git diff --stat
```

Expected: only intended Orchestrator/main/status changes are present.

- [ ] **Step 7: Perform one local smoke run with Ollama**

Run:

```powershell
python main.py
```

Use a Founder goal such as:

```text
Find a simple Roblox game opportunity and prepare a recommendation.
```

Acceptance criteria:
- Planner returns a valid structured plan using registered capabilities;
- Router chooses agents by capabilities rather than a hard-coded sequence;
- LOW/MEDIUM work proceeds automatically;
- a HIGH recommendation/decision checkpoint reaches `WAITING_APPROVAL` rather than continuing silently;
- malformed Planner output fails closed instead of continuing with guessed work.

Do not commit any generated local logs/cache files.

- [ ] **Step 8: Commit migration and status**

```powershell
git add main.py JARVIS_STATUS.md tests/test_main.py
git commit -m "feat: activate Jarvis Orchestrator v1"
```

- [ ] **Step 9: Final verification at committed HEAD**

```powershell
python -m unittest discover -s tests -v
python -m compileall agents core jarvis main.py
git diff --check
git status --short
git rev-parse --short HEAD
```

Expected: tests pass, compilation succeeds, diff check is clean, working tree is clean, and the short SHA is recorded for the push/verification step.

- [ ] **Step 10: Push feature branch**

```powershell
git push origin agent/agent-contract-v1
```

After push, verify `jarvis/models.py`, `jarvis/orchestrator.py`, `tests/test_orchestrator.py`, and the final commit SHA directly from GitHub before merging to `main`.

---

## Plan Self-Review

**Spec coverage:** All approved v1 requirements map to Tasks 1–8: models/status, Registry, Router, Task Manager, Approval Service, Planner validation, Orchestrator loop, Founder decisions, migration, testing, and source-of-truth status update.

**Scope:** The plan deliberately excludes Agent Factory, Developer/Tester/Reviewer implementation, SQLite, parallel scheduling, Git workers, Game Factory, Roblox publishing, and automatic replanning. Those remain subsequent independently testable milestones.

**Type consistency:** `RiskLevel`, `Priority`, and `TaskStatus` are reused from `core.contracts`; `JarvisTask` is the work record; `AgentMessage` remains the transport envelope; `AgentRegistration.agent_class` creates a `BaseAgent`; Router returns `AgentRegistration`; Orchestrator alone coordinates services and plan completion.

**Failure semantics:** Invalid planning raises `PLAN_INVALID`; routing absence yields `NO_ROUTE`; agent failure yields task/orchestrator failure; rejected prerequisites block dependents; HIGH/CRITICAL gates stop execution before protected side effects; post-result gates prevent dependent work from unlocking before Founder approval.
