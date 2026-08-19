# Agent Contract v1 Design

## Purpose

Replace the current hard-coded, incompatible handoff between Producer, Researcher, and Game Director with a common protocol that every current and future Jarvis specialist can use.

This iteration does **not** add new specialist agents, persistence, parallel execution, a router, Agent Factory, or SQLite storage. It establishes the smallest stable contract those future systems can build on.

## Locked Constraints

- Jarvis Core v1 uses Python standard library only.
- MessageBus v1 stores messages in memory.
- The MessageBus interface must allow a later persistent implementation without changing agent code.
- Execution is synchronous in v1.
- The contract must remain compatible with future parallel execution.
- Existing Founder Approval behavior must remain intact.

## Architecture

The shared protocol is an `AgentMessage` dataclass in `core/contracts.py`. All agents accept an `AgentMessage` and return an `AgentMessage` through a common `BaseAgent.handle()` interface.

`MessageBus` owns message transport/history only. It does not decide which agent should run. Orchestration stays outside the bus so a future Jarvis router/planner can replace the current sequential flow without changing the message protocol.

```text
Founder
  ↓
main.py (temporary orchestration)
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
Founder Approval
```

## AgentMessage Contract

`AgentMessage` contains:

- `id: str` — UUID-generated message identifier.
- `parent_id: str | None` — causal parent message.
- `sender: str` — role/system that produced the message.
- `recipient: str` — intended role/system.
- `kind: MessageKind` — semantic purpose of the message.
- `objective: str` — concise task/result objective.
- `payload: dict[str, Any]` — role-specific structured content.
- `status: TaskStatus` — lifecycle state.
- `priority: Priority` — scheduling importance.
- `risk_level: RiskLevel` — approval/security classification.
- `requires_approval: bool` — explicit approval gate flag.
- `created_at: datetime` — UTC creation timestamp.
- `metadata: dict[str, Any]` — extensible non-core metadata.

Enums:

`MessageKind`: `TASK`, `RESULT`, `APPROVAL_REQUEST`, `DECISION`, `ERROR`.

`TaskStatus`: `PENDING`, `RUNNING`, `COMPLETED`, `FAILED`, `WAITING_APPROVAL`, `REJECTED`.

`Priority`: `LOW`, `NORMAL`, `HIGH`, `CRITICAL`.

`RiskLevel`: `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`.

The dataclass validates required text fields and payload/metadata types in `__post_init__`. Invalid messages raise `ValueError` or `TypeError` immediately rather than propagating corrupted state.

## MessageBus v1

`core/message_bus.py` exposes:

- `publish(message: AgentMessage) -> None`
- `receive(recipient: str) -> AgentMessage | None`
- `history() -> tuple[AgentMessage, ...]`

Behavior:

- `publish` appends in FIFO order.
- `receive` returns and removes the oldest queued message for the requested recipient.
- `history` is append-only for the lifetime of the bus and returns an immutable tuple snapshot.
- The bus uses no LLM and contains no orchestration policy.

A later SQLite-backed bus can implement the same methods.

## BaseAgent

`agents/base_agent.py` defines an abstract `BaseAgent` with:

- `name: str`
- `handle(message: AgentMessage) -> AgentMessage`

It validates that incoming `recipient` matches the agent name. Concrete agents implement role-specific processing in `_handle()`.

## Existing Agent Refactor

### ProducerAgent

Input payload:

```python
{"founder_request": "Find a simple Roblox game opportunity."}
```

The local LLM remains instructed to return its existing JSON object. Parsing is wrapped safely. Malformed JSON returns an `ERROR`/`FAILED` message instead of crashing Jarvis.

Successful output is a `RESULT` message for `researcher` with payload:

```python
{
    "producer_message": "...",
    "research_task": "...",
}
```

### ResearcherAgent

Consumes `research_task` from payload and returns a `RESULT` message for `game_director` with:

```python
{"research_findings": "..."}
```

### GameDirectorAgent

Consumes `research_findings` and returns an `APPROVAL_REQUEST` message for `founder` with:

```python
{"recommendation": "..."}
```

Its status is `WAITING_APPROVAL`, risk is `HIGH`, and `requires_approval=True`.

## main.py Compatibility Flow

`main.py` remains the temporary orchestrator for this iteration. It creates the initial Founder task, publishes/receives messages through the bus, invokes the relevant agents synchronously, and preserves terminal APPROVE / CHANGE / REJECT handling.

The objective is not to make `main.py` final. The objective is to prove the contract before a later Jarvis router/task manager replaces it.

## Error Handling

- Invalid `AgentMessage` construction fails fast.
- Producer malformed JSON is converted into a structured failed/error message.
- Missing expected payload keys produce a structured failed/error message.
- `MessageBus.receive()` returns `None` when no message exists for the recipient.
- Ollama transport errors are not swallowed by this iteration; they remain infrastructure failures handled at the application boundary in a future reliability iteration.

## Testing

Use Python's built-in `unittest` so the core remains dependency-free.

Tests cover:

1. AgentMessage defaults, IDs, UTC timestamps, validation, and enums.
2. MessageBus FIFO routing, recipient filtering, and immutable history snapshots.
3. BaseAgent recipient validation.
4. Producer success and malformed-JSON failure using a patched local `chat` function.
5. Researcher handoff shape.
6. Game Director approval-request shape and HIGH risk classification.
7. One end-to-end synchronous workflow test with all LLM calls patched, proving the existing Producer → Researcher → Game Director → Founder gate still works through the new contract.

## Definition of Done

- All three existing agents use `AgentMessage`.
- All three inherit the same base interface.
- MessageBus works in memory.
- Producer malformed JSON cannot crash the workflow.
- Founder Approval remains represented explicitly by `WAITING_APPROVAL` and `requires_approval=True`.
- Full test suite passes using only Python standard library.
- No new specialist agents or unrelated architecture are added in this iteration.
