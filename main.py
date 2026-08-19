from __future__ import annotations

from agents.game_director import GameDirectorAgent
from agents.producer import ProducerAgent
from agents.researcher import ResearcherAgent
from core.contracts import RiskLevel
from core.message_bus import MessageBus
from jarvis.approvals import ApprovalService
from jarvis.models import (
    AgentRegistration,
    ApprovalDecision,
    OrchestratorResult,
    OrchestratorState,
)
from jarvis.orchestrator import JarvisOrchestrator
from jarvis.planner import JarvisPlanner
from jarvis.registry import AgentRegistry
from jarvis.router import JarvisRouter
from jarvis.task_manager import TaskManager


FOUNDER_REQUEST = "Find a simple Roblox game opportunity."


def _build_registry() -> AgentRegistry:
    registry = AgentRegistry()
    registry.register(
        AgentRegistration(
            name="producer",
            agent_class=ProducerAgent,
            capabilities=frozenset(
                {"production_planning", "research_coordination"}
            ),
            allowed_risk_levels=frozenset(
                {RiskLevel.LOW, RiskLevel.MEDIUM}
            ),
        )
    )
    registry.register(
        AgentRegistration(
            name="researcher",
            agent_class=ResearcherAgent,
            capabilities=frozenset(
                {"market_research", "competitor_analysis", "concept_analysis"}
            ),
            allowed_risk_levels=frozenset(
                {RiskLevel.LOW, RiskLevel.MEDIUM}
            ),
        )
    )
    registry.register(
        AgentRegistration(
            name="game_director",
            agent_class=GameDirectorAgent,
            capabilities=frozenset({"game_direction", "concept_selection"}),
            allowed_risk_levels=frozenset(
                {RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH}
            ),
        )
    )
    return registry


def _build_runtime() -> tuple[JarvisOrchestrator, ApprovalService]:
    bus = MessageBus()
    registry = _build_registry()
    planner = JarvisPlanner()
    router = JarvisRouter(registry)
    task_manager = TaskManager()
    approvals = ApprovalService()
    orchestrator = JarvisOrchestrator(
        planner=planner,
        registry=registry,
        router=router,
        task_manager=task_manager,
        approvals=approvals,
        bus=bus,
    )
    return orchestrator, approvals


def _parse_founder_decision(raw: str) -> ApprovalDecision:
    if not isinstance(raw, str):
        raise TypeError("Founder decision must be a string")
    normalized = raw.strip().lower()
    try:
        return ApprovalDecision(normalized)
    except ValueError as exc:
        raise ValueError(
            "Founder decision must be APPROVE, CHANGE, or REJECT"
        ) from exc


def _print_result(result: OrchestratorResult) -> None:
    print("\n=== JARVIS ===")
    print(f"STATE: {result.state.value.upper()}")
    print(f"MESSAGE: {result.message}")
    if result.pending_task_id is not None:
        print(f"PENDING TASK: {result.pending_task_id}")
    if result.error_code is not None:
        print(f"ERROR CODE: {result.error_code}")
    if result.change_context:
        print(f"CHANGE CONTEXT: {result.change_context}")


def main() -> None:
    orchestrator, approvals = _build_runtime()
    result = orchestrator.start(FOUNDER_REQUEST)
    _print_result(result)

    while (
        result.state == OrchestratorState.WAITING_APPROVAL
        and approvals.pending is not None
    ):
        raw_decision = input(
            "\nFounder decision [APPROVE / CHANGE / REJECT]: "
        )
        try:
            decision = _parse_founder_decision(raw_decision)
        except ValueError as exc:
            print(f"INVALID DECISION: {exc}")
            continue

        pending = approvals.pending
        if pending is None:
            break

        explicit_confirmation = False
        change_context = None
        if decision == ApprovalDecision.CHANGE:
            requested_change = input("Describe the requested change: ").strip()
            change_context = {"request": requested_change}
        elif (
            decision == ApprovalDecision.APPROVE
            and pending.requires_explicit_confirmation
        ):
            confirmation = input(
                "CRITICAL approval requires explicit confirmation. "
                "Type CONFIRM to continue: "
            )
            explicit_confirmation = confirmation.strip().upper() == "CONFIRM"

        try:
            result = orchestrator.decide(
                decision,
                explicit_confirmation=explicit_confirmation,
                change_context=change_context,
            )
        except PermissionError as exc:
            print(f"APPROVAL BLOCKED: {exc}")
            break

        _print_result(result)


if __name__ == "__main__":
    main()
