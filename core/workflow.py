from __future__ import annotations

from agents.base_agent import BaseAgent
from core.contracts import AgentMessage, MessageKind, TaskStatus
from core.message_bus import MessageBus


def _run_stage(
    *,
    stage_name: str,
    recipient: str,
    agent: BaseAgent,
    bus: MessageBus,
) -> AgentMessage:
    incoming = bus.receive(recipient)
    if incoming is None:
        raise RuntimeError(f"{stage_name}: expected message for {recipient}")

    result = agent.handle(incoming)
    bus.publish(result)

    if result.status is TaskStatus.FAILED:
        detail = result.payload.get("error", "unknown error")
        raise RuntimeError(f"{stage_name} failed: {detail}")

    return result


def run_discovery_workflow(
    *,
    founder_request: str,
    producer: BaseAgent,
    researcher: BaseAgent,
    game_director: BaseAgent,
    bus: MessageBus,
) -> AgentMessage:
    if not isinstance(founder_request, str) or not founder_request.strip():
        raise ValueError("founder_request must be a non-blank string")

    founder_task = AgentMessage(
        sender="founder",
        recipient="producer",
        kind=MessageKind.TASK,
        objective="Find a simple Roblox game opportunity",
        payload={"founder_request": founder_request},
    )
    bus.publish(founder_task)

    _run_stage(
        stage_name="Producer",
        recipient="producer",
        agent=producer,
        bus=bus,
    )
    _run_stage(
        stage_name="Researcher",
        recipient="researcher",
        agent=researcher,
        bus=bus,
    )
    return _run_stage(
        stage_name="Game Director",
        recipient="game_director",
        agent=game_director,
        bus=bus,
    )
