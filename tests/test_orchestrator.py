from __future__ import annotations

import unittest

from agents.base_agent import BaseAgent
from core.contracts import AgentMessage, MessageKind, Priority, RiskLevel, TaskStatus
from core.message_bus import MessageBus
from jarvis.approvals import ApprovalService
from jarvis.models import (
    AgentRegistration,
    ApprovalDecision,
    ExecutionPlan,
    JarvisTask,
    OrchestratorState,
)
from jarvis.orchestrator import JarvisOrchestrator
from jarvis.planner import PlanValidationError
from jarvis.registry import AgentRegistry
from jarvis.router import JarvisRouter
from jarvis.task_manager import TaskManager


class FakePlanner:
    def __init__(self, plan: ExecutionPlan | None = None, error: Exception | None = None):
        self.plan = plan
        self.error = error
        self.calls = 0

    def create_plan(self, founder_goal: str, registry: AgentRegistry) -> ExecutionPlan:
        self.calls += 1
        if self.error is not None:
            raise self.error
        assert self.plan is not None
        return self.plan


class AlphaAgent(BaseAgent):
    name = "alpha_worker"
    calls: list[AgentMessage] = []

    def _handle(self, message: AgentMessage) -> AgentMessage:
        type(self).calls.append(message)
        return AgentMessage(
            parent_id=message.id,
            sender=self.name,
            recipient="jarvis",
            kind=MessageKind.RESULT,
            objective="Alpha complete",
            payload={"agent": self.name, "task_id": message.payload["task_id"]},
            status=TaskStatus.COMPLETED,
        )


class BetaAgent(BaseAgent):
    name = "beta_worker"
    calls: list[AgentMessage] = []

    def _handle(self, message: AgentMessage) -> AgentMessage:
        type(self).calls.append(message)
        return AgentMessage(
            parent_id=message.id,
            sender=self.name,
            recipient="jarvis",
            kind=MessageKind.RESULT,
            objective="Beta complete",
            payload={"agent": self.name, "task_id": message.payload["task_id"]},
            status=TaskStatus.COMPLETED,
        )


class FailingAgent(BaseAgent):
    name = "failing_worker"
    calls: list[AgentMessage] = []

    def _handle(self, message: AgentMessage) -> AgentMessage:
        type(self).calls.append(message)
        return AgentMessage(
            parent_id=message.id,
            sender=self.name,
            recipient="jarvis",
            kind=MessageKind.ERROR,
            objective="Worker failed",
            payload={"error": "boom"},
            status=TaskStatus.FAILED,
        )


class ApprovalResultAgent(BaseAgent):
    name = "approval_worker"
    calls: list[AgentMessage] = []

    def _handle(self, message: AgentMessage) -> AgentMessage:
        type(self).calls.append(message)
        return AgentMessage(
            parent_id=message.id,
            sender=self.name,
            recipient="jarvis",
            kind=MessageKind.APPROVAL_REQUEST,
            objective="Review result",
            payload={"candidate": "A"},
            status=TaskStatus.WAITING_APPROVAL,
            risk_level=RiskLevel.HIGH,
            requires_approval=True,
        )


class WrongRecipientAgent(BaseAgent):
    name = "wrong_recipient_worker"
    calls: list[AgentMessage] = []

    def _handle(self, message: AgentMessage) -> AgentMessage:
        type(self).calls.append(message)
        return AgentMessage(
            parent_id=message.id,
            sender=self.name,
            recipient="founder",
            kind=MessageKind.RESULT,
            objective="Wrong recipient",
            payload={"ok": True},
            status=TaskStatus.COMPLETED,
        )


class DisabledAgent(BaseAgent):
    name = "disabled_worker"
    calls: list[AgentMessage] = []

    def _handle(self, message: AgentMessage) -> AgentMessage:
        type(self).calls.append(message)
        return message


class JarvisOrchestratorTests(unittest.TestCase):
    def setUp(self) -> None:
        for cls in (
            AlphaAgent,
            BetaAgent,
            FailingAgent,
            ApprovalResultAgent,
            WrongRecipientAgent,
            DisabledAgent,
        ):
            cls.calls = []

    def make_task(
        self,
        task_id: str,
        capability: str,
        *,
        dependencies: tuple[str, ...] = (),
        operation: str | None = None,
        priority: Priority = Priority.NORMAL,
        risk_level: RiskLevel = RiskLevel.LOW,
        requires_approval: bool = False,
        input_data: dict | None = None,
    ) -> JarvisTask:
        return JarvisTask(
            id=task_id,
            plan_key=task_id,
            goal_id="goal-1",
            title=f"Task {task_id}",
            objective=f"Do {task_id}",
            required_capabilities=(capability,),
            dependencies=dependencies,
            operation=operation,
            priority=priority,
            risk_level=risk_level,
            requires_approval=requires_approval,
            input_data={} if input_data is None else input_data,
        )

    def make_plan(self, *tasks: JarvisTask) -> ExecutionPlan:
        return ExecutionPlan(
            goal_id="goal-1",
            goal="Execute the plan",
            summary="Orchestrator test plan",
            tasks=tuple(tasks),
        )

    def make_registry(self, *registrations: AgentRegistration) -> AgentRegistry:
        registry = AgentRegistry()
        for item in registrations:
            registry.register(item)
        return registry

    def registration(
        self,
        name: str,
        agent_class: type[BaseAgent],
        capability: str,
        *,
        enabled: bool = True,
        allowed_risk_levels: frozenset[RiskLevel] = frozenset(RiskLevel),
    ) -> AgentRegistration:
        return AgentRegistration(
            name=name,
            agent_class=agent_class,
            capabilities=frozenset({capability}),
            allowed_risk_levels=allowed_risk_levels,
            enabled=enabled,
        )

    def make_orchestrator(
        self,
        plan: ExecutionPlan,
        registry: AgentRegistry,
        *,
        planner: FakePlanner | None = None,
    ) -> tuple[JarvisOrchestrator, FakePlanner, TaskManager, ApprovalService, MessageBus]:
        fake_planner = planner or FakePlanner(plan)
        task_manager = TaskManager()
        approvals = ApprovalService()
        bus = MessageBus()
        orchestrator = JarvisOrchestrator(
            planner=fake_planner,
            registry=registry,
            router=JarvisRouter(registry),
            task_manager=task_manager,
            approvals=approvals,
            bus=bus,
        )
        return orchestrator, fake_planner, task_manager, approvals, bus

    def test_two_sequential_tasks_route_by_capability_not_fixed_agent_names(self):
        first = self.make_task("first", "alpha_cap")
        second = self.make_task("second", "beta_cap", dependencies=(first.id,))
        registry = self.make_registry(
            self.registration("alpha_worker", AlphaAgent, "alpha_cap"),
            self.registration("beta_worker", BetaAgent, "beta_cap"),
        )
        orchestrator, _, manager, _, _ = self.make_orchestrator(
            self.make_plan(first, second), registry
        )

        result = orchestrator.start("Run both tasks")

        self.assertEqual(result.state, OrchestratorState.COMPLETED)
        self.assertEqual(first.assigned_agent, "alpha_worker")
        self.assertEqual(second.assigned_agent, "beta_worker")
        self.assertEqual(first.status, TaskStatus.COMPLETED)
        self.assertEqual(second.status, TaskStatus.COMPLETED)
        self.assertTrue(manager.is_complete())
        self.assertEqual(len(AlphaAgent.calls), 1)
        self.assertEqual(len(BetaAgent.calls), 1)

    def test_agent_receives_task_message_with_task_id_and_input_data(self):
        task = self.make_task(
            "input-task",
            "alpha_cap",
            input_data={"query": "roblox"},
        )
        registry = self.make_registry(
            self.registration("alpha_worker", AlphaAgent, "alpha_cap")
        )
        orchestrator, _, _, _, _ = self.make_orchestrator(self.make_plan(task), registry)

        orchestrator.start("Run task")

        incoming = AlphaAgent.calls[0]
        self.assertEqual(incoming.kind, MessageKind.TASK)
        self.assertEqual(incoming.sender, "jarvis")
        self.assertEqual(incoming.recipient, "alpha_worker")
        self.assertEqual(incoming.payload["task_id"], task.id)
        self.assertEqual(incoming.payload["input_data"], {"query": "roblox"})

    def test_agent_result_is_collected_from_message_bus(self):
        task = self.make_task("bus-task", "alpha_cap")
        registry = self.make_registry(
            self.registration("alpha_worker", AlphaAgent, "alpha_cap")
        )
        orchestrator, _, _, _, bus = self.make_orchestrator(
            self.make_plan(task), registry
        )

        orchestrator.start("Execute")

        self.assertIsNone(bus.receive("jarvis"))
        self.assertEqual(
            [message.sender for message in bus.history()],
            ["jarvis", "alpha_worker"],
        )

    def test_successful_result_completes_task_and_unlocks_dependency(self):
        first = self.make_task("first", "alpha_cap")
        second = self.make_task("second", "beta_cap", dependencies=(first.id,))
        registry = self.make_registry(
            self.registration("alpha_worker", AlphaAgent, "alpha_cap"),
            self.registration("beta_worker", BetaAgent, "beta_cap"),
        )
        orchestrator, _, _, _, _ = self.make_orchestrator(
            self.make_plan(first, second), registry
        )

        orchestrator.start("Execute")

        self.assertEqual(first.result["agent"], "alpha_worker")
        self.assertEqual(second.status, TaskStatus.COMPLETED)
        self.assertEqual(len(BetaAgent.calls), 1)

    def test_agent_failed_result_fails_plan_and_does_not_run_dependents(self):
        first = self.make_task("first", "fail_cap")
        second = self.make_task("second", "beta_cap", dependencies=(first.id,))
        registry = self.make_registry(
            self.registration("failing_worker", FailingAgent, "fail_cap"),
            self.registration("beta_worker", BetaAgent, "beta_cap"),
        )
        orchestrator, _, _, _, _ = self.make_orchestrator(
            self.make_plan(first, second), registry
        )

        result = orchestrator.start("Execute")

        self.assertEqual(result.state, OrchestratorState.FAILED)
        self.assertEqual(first.status, TaskStatus.FAILED)
        self.assertEqual(second.status, TaskStatus.BLOCKED)
        self.assertEqual(len(BetaAgent.calls), 0)

    def test_missing_route_returns_no_route_and_fails_closed(self):
        task = self.make_task("missing", "missing_cap")
        registry = self.make_registry(
            self.registration("alpha_worker", AlphaAgent, "alpha_cap")
        )
        orchestrator, _, _, _, _ = self.make_orchestrator(self.make_plan(task), registry)

        result = orchestrator.start("Execute")

        self.assertEqual(result.state, OrchestratorState.FAILED)
        self.assertEqual(result.error_code, "NO_ROUTE")
        self.assertEqual(task.status, TaskStatus.FAILED)
        self.assertEqual(len(AlphaAgent.calls), 0)

    def test_high_protected_operation_stops_before_agent_execution(self):
        task = self.make_task("publish", "alpha_cap", operation="publish")
        registry = self.make_registry(
            self.registration("alpha_worker", AlphaAgent, "alpha_cap")
        )
        orchestrator, _, _, approvals, _ = self.make_orchestrator(
            self.make_plan(task), registry
        )

        result = orchestrator.start("Publish something")

        self.assertEqual(result.state, OrchestratorState.WAITING_APPROVAL)
        self.assertEqual(result.pending_task_id, task.id)
        self.assertEqual(task.status, TaskStatus.WAITING_APPROVAL)
        self.assertIsNotNone(approvals.pending)
        self.assertEqual(len(AlphaAgent.calls), 0)

    def test_approve_preexecution_gate_resumes_and_executes_task_once(self):
        task = self.make_task("publish", "alpha_cap", operation="publish")
        registry = self.make_registry(
            self.registration("alpha_worker", AlphaAgent, "alpha_cap")
        )
        orchestrator, _, _, approvals, _ = self.make_orchestrator(
            self.make_plan(task), registry
        )
        orchestrator.start("Publish something")

        result = orchestrator.decide(ApprovalDecision.APPROVE)

        self.assertEqual(result.state, OrchestratorState.COMPLETED)
        self.assertEqual(task.status, TaskStatus.COMPLETED)
        self.assertIsNone(approvals.pending)
        self.assertEqual(len(AlphaAgent.calls), 1)

    def test_critical_approve_without_explicit_confirmation_keeps_waiting(self):
        task = self.make_task("credentials", "alpha_cap", operation="credentials")
        registry = self.make_registry(
            self.registration("alpha_worker", AlphaAgent, "alpha_cap")
        )
        orchestrator, _, _, approvals, _ = self.make_orchestrator(
            self.make_plan(task), registry
        )
        orchestrator.start("Use credentials")

        with self.assertRaises(PermissionError):
            orchestrator.decide(ApprovalDecision.APPROVE)

        self.assertEqual(orchestrator.state, OrchestratorState.WAITING_APPROVAL)
        self.assertIsNotNone(approvals.pending)
        self.assertEqual(task.status, TaskStatus.WAITING_APPROVAL)
        self.assertEqual(len(AlphaAgent.calls), 0)

    def test_critical_approve_with_confirmation_executes_task(self):
        task = self.make_task("credentials", "alpha_cap", operation="credentials")
        registry = self.make_registry(
            self.registration("alpha_worker", AlphaAgent, "alpha_cap")
        )
        orchestrator, _, _, _, _ = self.make_orchestrator(self.make_plan(task), registry)
        orchestrator.start("Use credentials")

        result = orchestrator.decide(
            ApprovalDecision.APPROVE,
            explicit_confirmation=True,
        )

        self.assertEqual(result.state, OrchestratorState.COMPLETED)
        self.assertEqual(len(AlphaAgent.calls), 1)

    def test_post_result_approval_stores_result_and_keeps_dependency_blocked(self):
        first = self.make_task("recommend", "approval_cap", requires_approval=True)
        second = self.make_task("followup", "beta_cap", dependencies=(first.id,))
        registry = self.make_registry(
            self.registration("approval_worker", ApprovalResultAgent, "approval_cap"),
            self.registration("beta_worker", BetaAgent, "beta_cap"),
        )
        orchestrator, _, _, approvals, _ = self.make_orchestrator(
            self.make_plan(first, second), registry
        )

        result = orchestrator.start("Make recommendation")

        self.assertEqual(result.state, OrchestratorState.WAITING_APPROVAL)
        self.assertEqual(first.status, TaskStatus.WAITING_APPROVAL)
        self.assertEqual(first.result, {"candidate": "A"})
        self.assertEqual(second.status, TaskStatus.BLOCKED)
        self.assertEqual(len(BetaAgent.calls), 0)
        self.assertTrue(approvals.pending.result_ready)

    def test_approve_post_result_completes_task_and_resumes_dependents(self):
        first = self.make_task("recommend", "approval_cap", requires_approval=True)
        second = self.make_task("followup", "beta_cap", dependencies=(first.id,))
        registry = self.make_registry(
            self.registration("approval_worker", ApprovalResultAgent, "approval_cap"),
            self.registration("beta_worker", BetaAgent, "beta_cap"),
        )
        orchestrator, _, _, _, _ = self.make_orchestrator(
            self.make_plan(first, second), registry
        )
        orchestrator.start("Make recommendation")

        result = orchestrator.decide(ApprovalDecision.APPROVE)

        self.assertEqual(result.state, OrchestratorState.COMPLETED)
        self.assertEqual(first.status, TaskStatus.COMPLETED)
        self.assertEqual(second.status, TaskStatus.COMPLETED)
        self.assertEqual(len(BetaAgent.calls), 1)

    def test_reject_marks_gated_task_rejected_and_blocks_dependents(self):
        first = self.make_task("publish", "alpha_cap", operation="publish")
        second = self.make_task("followup", "beta_cap", dependencies=(first.id,))
        registry = self.make_registry(
            self.registration("alpha_worker", AlphaAgent, "alpha_cap"),
            self.registration("beta_worker", BetaAgent, "beta_cap"),
        )
        orchestrator, _, _, approvals, _ = self.make_orchestrator(
            self.make_plan(first, second), registry
        )
        orchestrator.start("Publish")

        result = orchestrator.decide(ApprovalDecision.REJECT)

        self.assertEqual(result.state, OrchestratorState.FAILED)
        self.assertEqual(result.error_code, "APPROVAL_REJECTED")
        self.assertEqual(first.status, TaskStatus.REJECTED)
        self.assertEqual(second.status, TaskStatus.BLOCKED)
        self.assertIsNone(approvals.pending)
        self.assertEqual(len(AlphaAgent.calls), 0)
        self.assertEqual(len(BetaAgent.calls), 0)

    def test_change_returns_context_without_replanning_or_execution(self):
        task = self.make_task("publish", "alpha_cap", operation="publish")
        registry = self.make_registry(
            self.registration("alpha_worker", AlphaAgent, "alpha_cap")
        )
        planner = FakePlanner(self.make_plan(task))
        orchestrator, planner, _, approvals, _ = self.make_orchestrator(
            planner.plan, registry, planner=planner
        )
        orchestrator.start("Publish")

        result = orchestrator.decide(
            ApprovalDecision.CHANGE,
            change_context={"request": "use staging first"},
        )

        self.assertEqual(result.state, OrchestratorState.WAITING_APPROVAL)
        self.assertEqual(result.change_context, {"request": "use staging first"})
        self.assertEqual(planner.calls, 1)
        self.assertIsNone(approvals.pending)
        self.assertEqual(task.status, TaskStatus.WAITING_APPROVAL)
        self.assertEqual(len(AlphaAgent.calls), 0)

    def test_higher_priority_ready_task_runs_first(self):
        low = self.make_task("low", "alpha_cap", priority=Priority.LOW)
        high = self.make_task("high", "beta_cap", priority=Priority.HIGH)
        registry = self.make_registry(
            self.registration("alpha_worker", AlphaAgent, "alpha_cap"),
            self.registration("beta_worker", BetaAgent, "beta_cap"),
        )
        orchestrator, _, _, _, bus = self.make_orchestrator(
            self.make_plan(low, high), registry
        )

        orchestrator.start("Execute")

        task_messages = [m for m in bus.history() if m.sender == "jarvis"]
        self.assertEqual(task_messages[0].payload["task_id"], high.id)
        self.assertEqual(task_messages[1].payload["task_id"], low.id)

    def test_disabled_agent_is_never_executed(self):
        task = self.make_task("disabled", "special_cap")
        registry = self.make_registry(
            self.registration(
                "disabled_worker",
                DisabledAgent,
                "special_cap",
                enabled=False,
            )
        )
        orchestrator, _, _, _, _ = self.make_orchestrator(self.make_plan(task), registry)

        result = orchestrator.start("Execute")

        self.assertEqual(result.error_code, "NO_ROUTE")
        self.assertEqual(len(DisabledAgent.calls), 0)

    def test_risk_disallowed_agent_is_never_executed_after_approval(self):
        task = self.make_task(
            "high-risk",
            "alpha_cap",
            risk_level=RiskLevel.HIGH,
        )
        registry = self.make_registry(
            self.registration(
                "alpha_worker",
                AlphaAgent,
                "alpha_cap",
                allowed_risk_levels=frozenset({RiskLevel.LOW}),
            )
        )
        orchestrator, _, _, _, _ = self.make_orchestrator(self.make_plan(task), registry)
        waiting = orchestrator.start("Execute")
        self.assertEqual(waiting.state, OrchestratorState.WAITING_APPROVAL)

        result = orchestrator.decide(ApprovalDecision.APPROVE)

        self.assertEqual(result.state, OrchestratorState.FAILED)
        self.assertEqual(result.error_code, "NO_ROUTE")
        self.assertEqual(len(AlphaAgent.calls), 0)

    def test_result_addressed_somewhere_other_than_jarvis_fails_closed(self):
        task = self.make_task("wrong", "wrong_cap")
        registry = self.make_registry(
            self.registration(
                "wrong_recipient_worker",
                WrongRecipientAgent,
                "wrong_cap",
            )
        )
        orchestrator, _, _, _, _ = self.make_orchestrator(self.make_plan(task), registry)

        result = orchestrator.start("Execute")

        self.assertEqual(result.state, OrchestratorState.FAILED)
        self.assertEqual(result.error_code, "AGENT_PROTOCOL_ERROR")
        self.assertEqual(task.status, TaskStatus.FAILED)

    def test_planner_runtime_failure_fails_closed_with_structured_code(self):
        placeholder = self.make_task("placeholder-runtime", "alpha_cap")
        registry = self.make_registry(
            self.registration("alpha_worker", AlphaAgent, "alpha_cap")
        )
        planner = FakePlanner(
            self.make_plan(placeholder),
            error=RuntimeError("ollama unavailable"),
        )
        orchestrator, _, _, _, _ = self.make_orchestrator(
            planner.plan, registry, planner=planner
        )

        result = orchestrator.start("Execute")

        self.assertEqual(result.state, OrchestratorState.FAILED)
        self.assertEqual(result.error_code, "PLANNER_FAILED")
        self.assertIsNone(orchestrator.active_plan)

    def test_plan_validation_error_fails_start_with_structured_code(self):
        placeholder = self.make_task("placeholder", "alpha_cap")
        registry = self.make_registry(
            self.registration("alpha_worker", AlphaAgent, "alpha_cap")
        )
        planner = FakePlanner(
            self.make_plan(placeholder),
            error=PlanValidationError("bad plan"),
        )
        orchestrator, _, _, _, _ = self.make_orchestrator(
            planner.plan, registry, planner=planner
        )

        result = orchestrator.start("Execute")

        self.assertEqual(result.state, OrchestratorState.FAILED)
        self.assertEqual(result.error_code, "PLAN_INVALID")
        self.assertIsNone(orchestrator.active_plan)

    def test_start_and_decide_enforce_state_guards(self):
        task = self.make_task("simple", "alpha_cap")
        registry = self.make_registry(
            self.registration("alpha_worker", AlphaAgent, "alpha_cap")
        )
        orchestrator, _, _, _, _ = self.make_orchestrator(self.make_plan(task), registry)

        with self.assertRaises(RuntimeError):
            orchestrator.decide(ApprovalDecision.APPROVE)

        orchestrator.start("Execute")
        with self.assertRaises(RuntimeError):
            orchestrator.start("Execute again")


if __name__ == "__main__":
    unittest.main()
