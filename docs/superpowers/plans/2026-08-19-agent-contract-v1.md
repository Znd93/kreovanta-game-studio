# Agent Contract v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the hard-coded agent handoffs with one standard-library `AgentMessage` protocol, an in-memory MessageBus, a shared BaseAgent interface, and a tested synchronous workflow.

**Architecture:** `AgentMessage` is the stable protocol boundary. `MessageBus` transports messages without routing policy, while `main.py` remains a temporary synchronous orchestrator. Producer, Researcher, and Game Director all consume and return the same message type so a future Jarvis router can replace `main.py` without changing agent contracts.

**Tech Stack:** Python 3 standard library only (`dataclasses`, `enum`, `uuid`, `datetime`, `abc`, `json`, `unittest`, `unittest.mock`).

**Spec:** `docs/superpowers/specs/2026-08-19-agent-contract-v1-design.md`

## Global Constraints

- Python standard library only.
- MessageBus v1 is in-memory.
- MessageBus interface remains replaceable by SQLite later without changing agent code.
- Execution remains synchronous in v1 but the message contract is parallel-ready.
- Existing Founder Approval behavior remains available.
- Do not add new specialist agents, persistence, router, Agent Factory, or unrelated refactors.

---

### Task 1: AgentMessage Contract

**Files:**
- Create: `core/contracts.py`
- Create: `tests/test_contracts.py`

**Interfaces:**
- Produces: `MessageKind`, `TaskStatus`, `Priority`, `RiskLevel`, `AgentMessage`.
- `AgentMessage` fields match the approved spec exactly.

- [ ] **Step 1: Write failing contract tests**

Tests must prove UUID/default timestamp generation, enum defaults, validation of empty sender/recipient/objective, payload/metadata type validation, and explicit parent IDs.

- [ ] **Step 2: Run the contract tests and verify RED**

Run: `python -m unittest tests.test_contracts -v`

Expected: import failure because `core.contracts` does not exist.

- [ ] **Step 3: Implement the minimal contract**

Create string-backed enums and a dataclass whose `__post_init__` fails fast on invalid required fields or non-dict payload/metadata values. UTC timestamps must be timezone-aware.

- [ ] **Step 4: Run contract tests and verify GREEN**

Run: `python -m unittest tests.test_contracts -v`

Expected: all contract tests pass.

- [ ] **Step 5: Commit**

Commit message: `feat: add agent message contract`

---

### Task 2: In-Memory MessageBus and BaseAgent

**Files:**
- Modify: `core/message_bus.py`
- Create: `agents/base_agent.py`
- Create: `tests/test_message_bus.py`
- Create: `tests/test_base_agent.py`

**Interfaces:**
- Consumes: `AgentMessage` from `core.contracts`.
- Produces: `MessageBus.publish(message)`, `MessageBus.receive(recipient)`, `MessageBus.history()`.
- Produces: abstract `BaseAgent.handle(message)` and `_handle(message)` contract.

- [ ] **Step 1: Write failing MessageBus tests**

Cover FIFO behavior, recipient filtering, no-message behavior, type rejection, and tuple history snapshots that retain all published messages even after receive.

- [ ] **Step 2: Run MessageBus tests and verify RED**

Run: `python -m unittest tests.test_message_bus -v`

Expected: missing `MessageBus` implementation.

- [ ] **Step 3: Implement minimal MessageBus**

Use two in-memory lists: pending queue and append-only history. No orchestration or LLM logic.

- [ ] **Step 4: Run MessageBus tests and verify GREEN**

Run: `python -m unittest tests.test_message_bus -v`

- [ ] **Step 5: Write failing BaseAgent tests**

Use a tiny test subclass to prove matching recipients are accepted, mismatched recipients raise `ValueError`, and non-`AgentMessage` input raises `TypeError`.

- [ ] **Step 6: Run BaseAgent tests and verify RED**

Run: `python -m unittest tests.test_base_agent -v`

- [ ] **Step 7: Implement BaseAgent**

Define an abstract agent with a fixed `name`, public validation in `handle`, and role-specific implementation in `_handle`.

- [ ] **Step 8: Run MessageBus + BaseAgent tests and verify GREEN**

Run: `python -m unittest tests.test_message_bus tests.test_base_agent -v`

- [ ] **Step 9: Commit**

Commit message: `feat: add message bus and base agent`

---

### Task 3: Refactor Existing Agents to AgentMessage

**Files:**
- Modify: `agents/producer.py`
- Modify: `agents/researcher.py`
- Modify: `agents/game_director.py`
- Create: `tests/test_agents.py`

**Interfaces:**
- `ProducerAgent.handle(AgentMessage) -> AgentMessage`
- `ResearcherAgent.handle(AgentMessage) -> AgentMessage`
- `GameDirectorAgent.handle(AgentMessage) -> AgentMessage`
- Preserve compatibility wrapper functions `run_producer`, `run_researcher`, `run_game_director` only where useful for external callers, but the new workflow must use class agents and `AgentMessage`.

- [ ] **Step 1: Write failing Producer tests**

Patch the module-local `chat` function. Verify successful JSON becomes a completed RESULT addressed to `researcher`. Verify malformed JSON becomes a FAILED ERROR message rather than raising.

- [ ] **Step 2: Run Producer tests and verify RED**

Run: `python -m unittest tests.test_agents.ProducerAgentTests -v`

- [ ] **Step 3: Implement ProducerAgent minimally**

Read `founder_request` from payload, invoke existing prompt, parse JSON safely, and return structured messages. Missing input must return a structured FAILED ERROR message.

- [ ] **Step 4: Run Producer tests and verify GREEN**

- [ ] **Step 5: Write failing Researcher tests**

Verify `research_task` is sent to chat and output becomes a completed RESULT to `game_director`. Missing payload key returns FAILED ERROR.

- [ ] **Step 6: Run Researcher tests and verify RED**

- [ ] **Step 7: Implement ResearcherAgent minimally**

- [ ] **Step 8: Run Researcher tests and verify GREEN**

- [ ] **Step 9: Write failing Game Director tests**

Verify research findings become an `APPROVAL_REQUEST` addressed to `founder`, with `WAITING_APPROVAL`, `HIGH` risk, and `requires_approval=True`. Missing input returns FAILED ERROR.

- [ ] **Step 10: Run Game Director tests and verify RED**

- [ ] **Step 11: Implement GameDirectorAgent minimally**

- [ ] **Step 12: Run all agent tests and verify GREEN**

Run: `python -m unittest tests.test_agents -v`

- [ ] **Step 13: Commit**

Commit message: `refactor: standardize existing agents`

---

### Task 4: Synchronous Workflow and Founder Gate

**Files:**
- Create: `core/workflow.py`
- Modify: `main.py`
- Create: `tests/test_workflow.py`

**Interfaces:**
- Produces: `run_discovery_workflow(founder_request: str, producer, researcher, game_director, bus) -> AgentMessage`.
- Final return is the Founder-directed approval request from Game Director.
- `main.py` retains terminal `APPROVE / CHANGE / REJECT` interaction after the workflow returns.

- [ ] **Step 1: Write failing workflow test**

Use real agent classes with their `chat` functions patched. Assert the final message is WAITING_APPROVAL and bus history records founder task, producer result, researcher result, and director approval request in order.

- [ ] **Step 2: Run workflow test and verify RED**

Run: `python -m unittest tests.test_workflow -v`

- [ ] **Step 3: Implement minimal synchronous workflow**

The workflow publishes each message, receives by recipient, calls the correct agent, and stops with a descriptive runtime error if an expected bus handoff is missing or an agent returns FAILED.

- [ ] **Step 4: Run workflow test and verify GREEN**

- [ ] **Step 5: Refactor main.py to call the workflow**

Keep the visible Producer/Researcher/Game Director output sections and Founder decision behavior. `main.py` must not manually parse agent-specific payload formats beyond displaying them.

- [ ] **Step 6: Run complete test suite**

Run: `python -m unittest discover -s tests -v`

Expected: all tests pass with no external package installation.

- [ ] **Step 7: Commit**

Commit message: `feat: route discovery workflow through message bus`

---

### Task 5: Status Documentation and Final Verification

**Files:**
- Create or update: `JARVIS_STATUS.md`

**Interfaces:**
- Documentation only; must identify the latest verified feature commit and exact next engineering step.

- [ ] **Step 1: Write/update status document**

Record Agent Contract v1 as implemented only after all tests are green. Record current limitations: in-memory only, synchronous only, no dynamic router, no persistence, no Agent Factory.

- [ ] **Step 2: Verify repository state**

Run: `git status -sb`

Expected: only the intended status-document change is uncommitted.

- [ ] **Step 3: Run complete test suite again**

Run: `python -m unittest discover -s tests -v`

Expected: all tests pass.

- [ ] **Step 4: Commit**

Commit message: `docs: update jarvis status after agent contract v1`

- [ ] **Step 5: Inspect final history and diff**

Run: `git log --oneline --decorate -8` and `git diff master...HEAD --stat`.
