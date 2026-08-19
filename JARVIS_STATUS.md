# Kreovanta Game Studio / Jarvis — Project Status

**Status:** Jarvis Core v0.x — Agent Contract v1 implemented on feature branch
**Updated:** 2026-08-19
**Primary source of truth:** `Znd93/kreovanta-game-studio`
**Active development branch:** `agent/agent-contract-v1`

## Current Architecture

```text
FOUNDER
  ↓
main.py
  ↓
run_discovery_workflow()
  ↓
MessageBus
  ↓
ProducerAgent
  ↓
MessageBus
  ↓
ResearcherAgent
  ↓
MessageBus
  ↓
GameDirectorAgent
  ↓
MessageBus
  ↓
FOUNDER APPROVAL
```

`main.py` is now an application entry point rather than the place where agent-to-agent handoffs are hard-coded. The current discovery workflow is still synchronous and sequential, but all current agents communicate through the same message contract.

## Implemented Components

### Core

- `core/contracts.py`
  - `AgentMessage`
  - `MessageKind`
  - `TaskStatus`
  - `Priority`
  - `RiskLevel`
  - fail-fast message validation
  - UUID message IDs
  - timezone-aware UTC timestamps
- `core/message_bus.py`
  - in-memory FIFO transport
  - recipient-specific receive
  - append-only history snapshot
- `core/workflow.py`
  - synchronous discovery workflow
  - structured failure propagation
- `core/ollama_client.py`
  - local Ollama transport
  - model: `qwen3:8b`

### Agents

All current agents now inherit `BaseAgent` and use `AgentMessage` for input/output.

- `ProducerAgent`
  - receives Founder request
  - produces Researcher task
  - converts malformed local-LLM JSON into a structured FAILED/ERROR message
- `ResearcherAgent`
  - receives research task
  - returns structured research findings to Game Director
- `GameDirectorAgent`
  - receives research findings
  - returns a HIGH-risk `APPROVAL_REQUEST` to Founder
  - sets `WAITING_APPROVAL`
  - sets `requires_approval=True`

### Base Interface

- `agents/base_agent.py`
  - validates recipient targeting
  - enforces `AgentMessage -> AgentMessage`
  - provides one shared interface for future specialist agents

### Tests

Python standard-library `unittest` suite covers:

- AgentMessage defaults and validation
- MessageBus FIFO and routing behavior
- immutable history snapshots
- BaseAgent recipient validation
- Producer successful JSON output
- Producer malformed JSON protection
- Researcher handoff
- Game Director Founder Approval request
- full Producer → Researcher → Game Director workflow
- workflow failure stop
- `main.py` import safety
- terminal Founder Approval behavior

**Current verified test count:** 29 tests.

## Locked Architecture Decisions

1. Jarvis Core v1 uses Python standard library first.
2. No Pydantic or other mandatory external core dependency yet.
3. MessageBus v1 is in-memory.
4. MessageBus interface is designed so persistence can later be replaced by SQLite without changing agent code.
5. Execution is synchronous first.
6. Message protocol is designed to remain usable when parallel execution is added later.
7. Agents are selected by required judgment/skill; deterministic execution belongs in workers/tools.
8. Jarvis is the orchestrator/team composer, not a fixed sequence of a fixed number of agents.
9. HIGH/CRITICAL operations remain Founder-controlled.
10. GitHub remains the intended project source of truth.

## Current Limitations

- No dynamic planner/router yet.
- No automatic team assembly yet.
- No task graph/dependency scheduler yet.
- No parallel execution yet.
- No SQLite persistence yet.
- MessageBus history is lost when the process exits.
- No reusable Agent Registry yet.
- No Developer/Tester/Reviewer bootstrap team yet.
- No Agent Factory yet.
- No Roblox Master Template/Game Factory yet.
- No Rojo automation pipeline yet.
- No LiveOps/analytics pipeline yet.
- No asset-library/component-library system yet.
- No automated Git worker yet.

## Founder Approval

Current terminal flow still supports:

```text
APPROVE
CHANGE
REJECT
```

Game Director recommendations are represented structurally as:

```text
kind: APPROVAL_REQUEST
status: WAITING_APPROVAL
risk_level: HIGH
requires_approval: true
```

This is the first step toward a reusable approval service.

## Git / Commit State

### Public GitHub `main`

Latest verified public GitHub commit before this feature work:

`5748d47ae0841af575a8ed6628a6f65afb80e895`
`Initial Kreovanta Game Studio agent foundation`

### Local feature branch

Feature branch:

`agent/agent-contract-v1`

Latest verified code commit before this status update:

`cc6afc1`
`feat: route discovery workflow through message bus`

The feature branch has **not yet been pushed to GitHub** because the current ChatGPT GitHub connector can read the public repository but returned HTTP 403 when attempting repository writes.

## Current Task

Complete Agent Contract v1 as a clean, tested feature branch and move the verified changes into the real GitHub repository.

## Exact Next Engineering Step

After Agent Contract v1 is safely in GitHub, build **Jarvis Orchestration v1**, not another hard-coded agent chain.

The next subsystem should introduce the smallest useful foundation for dynamic team composition:

```text
Agent Registry
    ↓
Role / Capability metadata
    ↓
Jarvis Router
    ↓
Select specialist for task
```

The first goal is not full autonomous team generation. The first goal is to let Jarvis select an existing agent by capability instead of `workflow.py` naming Producer, Researcher, and Game Director directly.

After that:

1. Task/dependency model
2. Planner
3. Developer bootstrap agent
4. Tester bootstrap agent
5. Reviewer bootstrap agent
6. Git worker
7. Agent Factory
8. dynamic specialist expansion
9. Roblox Master Template / Game Factory

## Definition of Agent Contract v1 Done

- [x] Shared AgentMessage contract
- [x] Shared BaseAgent interface
- [x] In-memory MessageBus
- [x] Producer refactored
- [x] Researcher refactored
- [x] Game Director refactored
- [x] malformed Producer JSON handled safely
- [x] Founder Approval represented structurally
- [x] current discovery flow routed through MessageBus
- [x] standard-library-only automated test suite
- [x] status documentation updated
- [ ] feature branch pushed to GitHub
