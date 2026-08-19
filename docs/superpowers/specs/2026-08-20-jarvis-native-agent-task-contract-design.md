# Jarvis-native Agent Task Contract — Design Specification

**Date:** 2026-08-20  
**Phase:** Bootstrap Engineering Team — Task 1  
**Status:** Founder-approved design  
**Repository:** `Znd93/kreovanta-game-studio`  
**Branch:** `agent/agent-contract-v1`

## 1. Purpose

Task 1 introduces the generic task protocol that all new Jarvis-native specialists will use. The goal is to let Jarvis scale from the current legacy agents to Developer, Tester, Reviewer, Git Worker, and later 30+ specialists without adding role-specific workflow logic to `JarvisOrchestrator`.

This task is contract infrastructure only. It does not implement any engineering specialist behavior.

## 2. Architectural Boundary

The existing `AgentMessage` remains the transport contract. The new Jarvis-native task protocol is layered above it.

```text
JarvisTask
    ↓
AgentTaskRequest
    ↓ serialize
AgentMessage
    ↓ MessageBus
Jarvis-native Agent
    ↓
AgentTaskResult
    ↓ serialize
AgentMessage
    ↓ MessageBus
JarvisOrchestrator
    ↓ validate
TaskManager
```

Authority remains separated:

```text
Planner          → proposes work
AgentTaskRequest → defines assigned work
Specialist       → performs specialist work
AgentTaskResult  → reports outcome
ApprovalService  → controls authorization
TaskManager      → controls task state
Orchestrator     → controls execution order
Router           → controls specialist selection
```

Founder lock: agents produce results; the Orchestrator decides what happens next.

## 3. Contract Placement

New protocol definitions belong in `jarvis/agent_contract.py` and include:

- `AgentContractVersion`
- `AgentTaskRequest`
- `AgentTaskResult`
- `AgentContractError`
- deterministic request/result serialization and deserialization
- deterministic request/result validation

A new Jarvis-native base agent belongs in `agents/jarvis_native.py`.

Existing `core/contracts.py::AgentMessage` remains the transport model.

## 4. Contract Versioning

Agent registrations explicitly declare which task protocol they use.

```text
AgentContractVersion
├── LEGACY_V1
└── JARVIS_NATIVE_V1
```

`AgentRegistration.contract_version` defaults to `LEGACY_V1` so current agents and existing tests remain compatible unless explicitly migrated.

All new specialists must register with `JARVIS_NATIVE_V1`.

Contract-version branching is permitted. Agent-name workflow branching is prohibited.

## 5. AgentTaskRequest

```text
AgentTaskRequest
├── task_id: str
├── goal_id: str
├── title: str
├── objective: str
├── required_capabilities: tuple[str, ...]
├── operation: str | None
├── priority: Priority
├── risk_level: RiskLevel
├── requires_approval: bool
├── input_data: dict
└── dependency_results: dict[str, dict]
```

Field semantics:

- `task_id`: exact Jarvis task identity.
- `goal_id`: Founder-goal identity for tracing and future persistence/audit.
- `title`: human-readable task title.
- `objective`: the specialist's primary work instruction.
- `required_capabilities`: capabilities that caused routing eligibility.
- `operation`: operation classification used by Jarvis policy.
- `priority`: task priority.
- `risk_level`: effective risk after Jarvis policy evaluation.
- `requires_approval`: whether the task/result is subject to approval handling.
- `input_data`: flexible task-specific inputs.
- `dependency_results`: outputs of completed prerequisite tasks keyed by dependency task ID.

The request is top-level immutable using `@dataclass(frozen=True, slots=True)`. Nested dictionaries do not need deep immutability in v1.

The contract must not contain workflow-role fields such as `assigned_agent`, `next_agent`, `previous_agent`, `workflow_stage`, or `expected_next_role`.

## 6. Dependency Result Flow

Dependency outputs flow through the task dependency graph, not through direct agent-to-agent routing.

```text
current task
    ↓
task.dependencies
    ↓
TaskManager.get(dependency_id)
    ↓
verify dependency COMPLETED
    ↓
collect stored result
    ↓
AgentTaskRequest.dependency_results
```

Example:

```python
dependency_results = {
    "task-a": {
        "summary": "Implemented feature",
        "output_data": {
            "files_changed": ["example.py"]
        }
    },
    "task-b": {
        "summary": "Tests passed",
        "output_data": {
            "tests_run": 42,
            "passed": 42,
            "failed": 0
        }
    }
}
```

The dependency result keys must match the current task's declared dependency IDs exactly. Missing, extra, or injected dependency IDs are protocol errors.

`input_data` and `dependency_results` remain separate and are never automatically merged.

## 7. AgentTaskResult

```text
AgentTaskResult
├── task_id: str
├── status: TaskStatus
├── output_data: dict
├── summary: str
├── error: str | None
├── risk_level: RiskLevel
└── requires_approval: bool
```

Allowed agent result statuses in v1:

```text
COMPLETED
FAILED
WAITING_APPROVAL
```

Agents cannot set orchestration-owned states such as `READY`, `RUNNING`, `BLOCKED`, or `REJECTED`.

Result invariants:

```text
COMPLETED        → error must be None
FAILED           → error must be a non-blank string
WAITING_APPROVAL → error must be None
```

`result.task_id` must match the corresponding request task ID.

`output_data` is opaque specialist data. The Orchestrator stores it and passes it downstream without interpreting specialist-specific keys.

`summary` is mandatory human-readable context for audit, UI, persistence, and downstream understanding.

## 8. Risk and Approval Semantics

Agents may escalate risk after inspecting the real work. They may never reduce policy authority.

Post-result risk uses the strongest applicable level among:

- task/effective risk
- agent-reported result risk
- ApprovalService policy minimum

An agent may set `requires_approval=True`, but `False` never bypasses approval already required by task or policy.

Agents cannot authorize their own protected operations.

## 9. Result Storage

Completed native tasks store a stable generic result:

```python
{
    "summary": "Implemented requested change",
    "output_data": {
        "files_changed": ["..."]
    }
}
```

Downstream dependencies therefore receive human-readable summary plus machine-readable output without transport/control metadata such as status, error, risk, or approval flags.

## 10. JarvisNativeAgent

```text
BaseAgent
    ↓
JarvisNativeAgent
    ↓
DeveloperAgent / TesterAgent / ReviewerAgent / future specialists
```

Its responsibility is:

```text
AgentMessage
    ↓
deserialize + validate
    ↓
AgentTaskRequest
    ↓
_execute(request)
    ↓
AgentTaskResult
    ↓
validate + serialize
    ↓
AgentMessage → jarvis
```

New specialists implement only a typed specialist execution method equivalent to:

```python
def _execute(self, request: AgentTaskRequest) -> AgentTaskResult:
    ...
```

Specialists do not need direct knowledge of MessageBus, Router, TaskManager, ApprovalService, or downstream agent selection.

## 11. AgentMessage Mapping

`AgentMessage` remains transport authority for fields it already owns. Native serialization must not duplicate those control fields inside payload.

Request mapping:

```text
AgentTaskRequest.objective         → AgentMessage.objective
AgentTaskRequest.priority          → AgentMessage.priority
AgentTaskRequest.risk_level        → AgentMessage.risk_level
AgentTaskRequest.requires_approval → AgentMessage.requires_approval
```

Request payload carries:

```text
contract_version
task_id
goal_id
title
required_capabilities
operation
input_data
dependency_results
```

Result mapping:

```text
AgentTaskResult.status            → AgentMessage.status
AgentTaskResult.risk_level        → AgentMessage.risk_level
AgentTaskResult.requires_approval → AgentMessage.requires_approval
```

Result payload carries:

```text
contract_version
task_id
summary
output_data
error
```

## 12. Deterministic MessageKind Mapping

```text
COMPLETED        → MessageKind.RESULT
FAILED           → MessageKind.ERROR
WAITING_APPROVAL → MessageKind.APPROVAL_REQUEST
```

The native adapter creates transport messages from typed results. Specialists do not choose arbitrary message-kind/status combinations.

## 13. Orchestrator Integration

`JarvisOrchestrator` gains only generic protocol responsibilities:

1. Collect completed dependency results through `task.dependencies` and TaskManager.
2. Dispatch by `registration.contract_version`.
3. Deserialize and validate native results before TaskManager state changes.

```text
LEGACY_V1        → current compatibility path
JARVIS_NATIVE_V1 → AgentTaskRequest path
```

No specialist-specific parsing or branching is allowed in the Orchestrator.

## 14. Legacy Compatibility

Producer, Researcher, and Game Director retain their current role-specific payload expectations during Task 1.

Task 1 does not partially migrate them.

Both protocols coexist while new engineering specialists are native from day one.

## 15. Fail-Closed Protocol Rules

The native protocol rejects malformed or inconsistent traffic, including:

- wrong contract version
- wrong message kind
- wrong recipient
- blank required identifiers
- malformed capabilities
- malformed input data
- malformed dependency results
- dependency key mismatch
- invalid result status
- `FAILED` without a non-blank error
- `COMPLETED` with an error
- `WAITING_APPROVAL` with an error
- result task ID mismatch
- malformed output data

Protocol violations become:

```text
AGENT_PROTOCOL_ERROR
→ current task FAILED
→ dependent tasks remain BLOCKED
```

Jarvis does not autonomously repair, reinterpret, replan, or reroute malformed native results in v1.

## 16. Test Strategy

Task 1 requires three test layers.

### 16.1 Contract unit tests

At minimum:

- valid `AgentTaskRequest` accepted
- blank task ID rejected
- empty capabilities rejected
- invalid dependency results rejected
- valid `COMPLETED` result accepted
- `FAILED` without error rejected
- `COMPLETED` with error rejected
- invalid agent result status rejected

### 16.2 Native agent protocol tests

Use a fake Jarvis-native agent to verify:

```text
AgentMessage
→ typed request
→ typed result
→ AgentMessage
```

Also verify fail-closed behavior for wrong contract version, wrong message kind, wrong task ID, and malformed output.

### 16.3 Orchestrator integration tests

Verify generic dependency propagation:

```text
Task A
    ↓ stores result
Task B depends on A
    ↓ receives A through dependency_results
```

Also verify an `A → B → C` native chain where dependencies and capabilities alone determine workflow order, with no agent-name workflow branching.

## 17. Regression Requirements

Task 1 implementation is complete only when:

```text
new Task 1 tests PASS
all existing 137 regression tests PASS
compileall PASS
git diff --check PASS
```

The 137 existing tests are a baseline, not a replacement for the new Task 1 tests.

## 18. Explicit Out of Scope

Task 1 does not implement:

- Developer Agent
- Tester Agent
- Reviewer Agent
- Git Worker
- filesystem worker
- Git write permissions
- automatic code execution
- automatic test execution
- automatic commit or push
- Agent Factory
- legacy-agent migration
- parallel execution
- automatic retries
- automatic replanning
- Roblox publishing
- Rojo automation
- Game Factory behavior

## 19. Definition of Done

- [ ] Typed `AgentTaskRequest` exists.
- [ ] Typed `AgentTaskResult` exists.
- [ ] Explicit `AgentContractVersion` exists.
- [ ] `JarvisNativeAgent` exists.
- [ ] Native request serialization/deserialization is validated.
- [ ] Native result serialization/deserialization is validated.
- [ ] Dependency results flow generically through task dependencies.
- [ ] Dependency-result completeness is enforced.
- [ ] Result task-ID correlation is enforced.
- [ ] Native protocol violations fail closed.
- [ ] Legacy agents remain operational.
- [ ] No agent-name workflow branching is introduced.
- [ ] No Developer/Tester/Reviewer implementation is included.
- [ ] New Task 1 tests pass.
- [ ] Existing 137 regression tests remain green.
- [ ] `compileall` passes.
- [ ] `git diff --check` passes.

## 20. Locked Decisions

1. `AgentMessage` is the transport contract.
2. `AgentTaskRequest` and `AgentTaskResult` are the Jarvis-native task contract.
3. `AgentRegistration` explicitly declares contract version.
4. Existing agents default to `LEGACY_V1`.
5. New specialists use `JARVIS_NATIVE_V1`.
6. The Orchestrator owns orchestration.
7. Specialists own only specialist work.
8. TaskManager owns task state.
9. ApprovalService owns authorization.
10. Router owns specialist selection.
11. Agents never choose downstream agents or tasks.
12. Agents never modify dependency state.
13. Agents never bypass Founder approval.
14. Agents may escalate risk but cannot reduce policy minimums.
15. Dependency outputs flow through the task graph.
16. `input_data` and `dependency_results` remain separate.
17. Top-level native requests are immutable.
18. Control fields use `AgentMessage` transport fields rather than duplicated payload fields.
19. Contract-version branching is allowed; agent-name workflow branching is forbidden.
20. Malformed native protocol traffic fails closed.
21. No autonomous protocol repair, replanning, or rerouting is added in v1.

## 21. Next Engineering Step

After this specification is reviewed and approved, create a detailed implementation plan for Task 1. Implementation begins only after that plan is accepted.

After Task 1 is implemented and verified, the next bootstrap task is **Task 2 — Developer Agent**, built directly on `JarvisNativeAgent`, `AgentTaskRequest`, and `AgentTaskResult` without new specialist-specific Orchestrator logic.
