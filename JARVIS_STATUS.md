# Kreovanta Game Studio / Jarvis — Project Status

**Status:** Jarvis Orchestrator v1 implemented; active CLI migrated to dynamic orchestration
**Updated:** 2026-08-20
**Primary source of truth:** `Znd93/kreovanta-game-studio`
**Active development branch:** `agent/agent-contract-v1`

## Current Architecture

```text
FOUNDER GOAL
    ↓
main.py
    ↓
JarvisOrchestrator
    ↓
JarvisPlanner (local Ollama / qwen3:8b)
    ↓
strict JSON parser + plan validation
    ↓
ExecutionPlan
    ↓
TaskManager
    ↓
READY task selection
    ↓
ApprovalService (pre-execution gate)
    ↓
JarvisRouter ← AgentRegistry
    ↓
registered specialist agent
    ↓
MessageBus
    ↓
AgentMessage result
    ↓
ApprovalService (post-result gate when required)
    ↓
TaskManager
    ↓
continue / WAITING_APPROVAL / FAILED / COMPLETED
```

The active `main.py` path no longer calls the fixed Producer → Researcher → Game Director workflow. `core/workflow.py` remains available as a legacy/reference path only and is intentionally not deleted in Orchestrator v1.

## Implemented Jarvis Components

### `jarvis/models.py`

- `JarvisTask`
- `ExecutionPlan`
- `AgentRegistration`
- `OrchestratorState`
- `ApprovalDecision`
- `ApprovalDisposition`
- `ApprovalEvaluation`
- `PendingApproval`
- `OrchestratorResult`

### `jarvis/registry.py`

- explicit agent registration
- duplicate-name rejection
- capability catalog
- enabled/disabled filtering
- allowed-risk filtering
- deterministic candidate ordering

### `jarvis/router.py`

- deterministic capability routing
- exact capability match preferred
- smallest capability superset fallback
- alphabetical tie-break
- disabled/risk-disallowed agents excluded
- fail-closed `NoRouteError`

### `jarvis/task_manager.py`

- active-plan task state authority
- `READY`, `BLOCKED`, `RUNNING`, `WAITING_APPROVAL`, terminal states
- dependency enforcement
- downstream unlock only after prerequisite completion
- downstream blocking after failure/rejection
- pre-execution and post-result approval transitions
- plan completion/failure calculation

### `jarvis/approvals.py`

Risk policy:

```text
LOW      → CONTINUE
MEDIUM   → CONTINUE_AUDIT
HIGH     → WAIT → Founder Approval
CRITICAL → WAIT → Founder Approval → explicit confirmation
```

Protected operation minimums:

```text
publish                → HIGH
delete_important_data  → HIGH
credentials            → CRITICAL
security_policy_change → CRITICAL
locked_core_change     → CRITICAL
paid_action            → CRITICAL
```

Planner/agent suggested risk can never lower the policy minimum.

### `jarvis/planner.py`

- local Ollama-backed structured planner
- JSON-only contract
- enabled capability catalog supplied to Planner
- malformed JSON rejected
- non-empty task plan required
- required task fields validated
- duplicate task keys rejected
- unavailable capabilities rejected
- dependency keys converted to internal task IDs
- missing/self/circular dependencies rejected
- priority/risk values validated
- approval flags validated
- `PlanValidationError.code == "PLAN_INVALID"`

### `jarvis/orchestrator.py`

- deterministic synchronous execution loop
- Planner → TaskManager → Approval → Router → Agent → MessageBus → Result
- priority-aware READY-task selection
- generic task delivery with `task_id` and `input_data`
- agent results collected through MessageBus
- pre-execution HIGH/CRITICAL gates
- post-result approval gates
- CRITICAL explicit confirmation
- APPROVE resume
- REJECT fail/block behavior
- CHANGE context without automatic replanning
- structured `NO_ROUTE`, agent/protocol, and approval failures
- disabled or unauthorized agents never execute
- plan becomes `COMPLETED` only through TaskManager completion

## Active CLI / Startup Registry

`main.py` now constructs:

```text
MessageBus
AgentRegistry
JarvisPlanner
JarvisRouter
TaskManager
ApprovalService
JarvisOrchestrator
```

Current explicit startup registrations:

### Producer

```text
production_planning
research_coordination
Risk: LOW / MEDIUM
```

### Researcher

```text
market_research
competitor_analysis
concept_analysis
Risk: LOW / MEDIUM
```

### Game Director

```text
game_direction
concept_selection
Risk: LOW / MEDIUM / HIGH
```

No directory scanning or implicit registration is used.

Founder decisions are normalized case-insensitively and CHANGE collects a Founder-provided change request:

```text
APPROVE
CHANGE
REJECT
```

CRITICAL approval asks for explicit `CONFIRM` only when the active pending gate requires explicit confirmation.

## Verification State

Task 8 implementation verification:

```text
Task 8 main tests:       8 / 8 PASS
Task 7 orchestrator:    21 / 21 PASS
Full regression:       137 / 137 PASS
compileall:             PASS
git diff --check:       PASS
```

The test count is the actual count from the full local verification command, not an estimate.

## Git / Commit State

Feature branch:

```text
agent/agent-contract-v1
```

Last verified GitHub canonical commit before Task 7/8:

```text
45202f66e02eda112ba250727aa2b7dda49f3c19
feat: add validated Jarvis execution planner
```

Task 7 implementation commit:

```text
4339a9b2b60379174ec7a10d5b8f16ddb9ff070c
feat: add Jarvis dynamic orchestration loop
```

Task 8 implementation commit:

```text
8ad3a1302dd3d8b6669e06c575a2e9f62c54f96e
feat: migrate CLI to Jarvis orchestrator
```

`JARVIS_STATUS.md` is finalized in a separate documentation commit so it can reference the actual Task 7 and Task 8 implementation SHAs without a self-referential commit hash.

## Locked Architecture Decisions

1. Python standard library first for Jarvis Core v1.
2. Execution is synchronous in v1.
3. MessageBus remains in-memory in v1.
4. Planner is advisory; deterministic validation is authoritative.
5. TaskManager is the only source of truth for task state and plan completion.
6. Agent Registry is explicit; no module scanning.
7. Router selects by capability and allowed risk, never by LLM-selected Python class.
8. Planner/agent risk can never reduce policy minimum risk.
9. HIGH operations require Founder approval.
10. CRITICAL operations require Founder approval plus explicit confirmation.
11. Failures, invalid plans, unavailable routes, and rejected approvals fail closed.
12. No automatic replanning after CHANGE or failure in v1.
13. No parallel task execution in v1.
14. `core/workflow.py` remains as a reversible legacy/reference path during migration cleanup.
15. GitHub remains the project source of truth.

## Known Limitations / Deferred Work

- no parallel execution
- no SQLite persistence
- MessageBus history is process-local
- no automatic retry/reassignment/replanning
- no Git Worker yet
- no Agent Factory yet
- no Developer/Tester/Reviewer bootstrap team yet
- no automatic code-writing agents in Orchestrator v1
- no Roblox publishing or Game Factory pipeline
- no Rojo automation pipeline
- no LiveOps/analytics pipeline
- no asset-library/component-library system

The currently registered Producer, Researcher, and Game Director retain their original Agent Contract v1 domain-specific payload expectations. Orchestrator v1 deliberately does not add hard-coded payload translation or dependency-result transformation for those legacy agent roles. New bootstrap agents should be written natively against the generic Jarvis task contract rather than adding role-specific logic to the Orchestrator.

## Orchestrator v1 Definition of Done

- [x] structured validated Planner
- [x] explicit Registry
- [x] deterministic capability Router
- [x] TaskManager dependency state machine
- [x] Founder Approval policy service
- [x] HIGH pre-execution gates
- [x] CRITICAL explicit confirmation
- [x] post-result approval gates
- [x] APPROVE resume
- [x] REJECT blocks dependent work
- [x] CHANGE returns context without autonomous replanning
- [x] dynamic synchronous Orchestrator execution loop
- [x] active `main.py` migrated away from fixed workflow
- [x] current agents explicitly registered
- [x] legacy `core/workflow.py` retained for reversible cleanup
- [x] full standard-library regression suite green locally

## Exact Next Engineering Step

Bootstrap the first Jarvis-native engineering team:

```text
Developer Agent
Tester Agent
Reviewer Agent
    ↓
Git Worker
    ↓
Agent Factory
    ↓
Dynamic specialist expansion
    ↓
Roblox Master Template / Game Factory
```

The next agents should consume the generic Jarvis task contract directly so Jarvis can execute real work without reintroducing fixed role-to-role handoff logic into the core orchestrator.
