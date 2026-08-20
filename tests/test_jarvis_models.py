import unittest

from core.contracts import Priority, RiskLevel, TaskStatus
from jarvis.agent_contract import AgentContractVersion
from jarvis.models import (
    AgentRegistration,
    ApprovalDecision,
    ApprovalDisposition,
    ExecutionPlan,
    JarvisTask,
    OrchestratorResult,
    OrchestratorState,
    PendingApproval,
)


class JarvisModelTests(unittest.TestCase):
    def make_task(self, **overrides):
        values = {
            "plan_key": "market_research",
            "goal_id": "goal-1",
            "title": "Market research",
            "objective": "Find opportunities",
            "required_capabilities": ("market_research",),
        }
        values.update(overrides)
        return JarvisTask(**values)

    def test_task_status_includes_ready_and_blocked(self):
        self.assertEqual(TaskStatus.READY.value, "ready")
        self.assertEqual(TaskStatus.BLOCKED.value, "blocked")

    def test_jarvis_task_has_safe_defaults(self):
        task = self.make_task()

        self.assertTrue(task.id)
        self.assertEqual(task.status, TaskStatus.PENDING)
        self.assertEqual(task.priority, Priority.NORMAL)
        self.assertEqual(task.risk_level, RiskLevel.LOW)
        self.assertEqual(task.dependencies, ())
        self.assertIsNone(task.assigned_agent)
        self.assertIsNotNone(task.created_at.tzinfo)

    def test_jarvis_task_rejects_blank_identity_and_work_fields(self):
        for field_name in ("plan_key", "goal_id", "title", "objective", "id"):
            with self.subTest(field_name=field_name):
                with self.assertRaises((TypeError, ValueError)):
                    self.make_task(**{field_name: "   "})

    def test_jarvis_task_requires_non_blank_capabilities(self):
        for capabilities in ((), ("",), ("market_research", "   ")):
            with self.subTest(capabilities=capabilities):
                with self.assertRaises(ValueError):
                    self.make_task(required_capabilities=capabilities)

    def test_jarvis_task_rejects_blank_and_self_dependencies(self):
        task_id = "task-123"
        with self.assertRaises(ValueError):
            self.make_task(id=task_id, dependencies=("",))
        with self.assertRaises(ValueError):
            self.make_task(id=task_id, dependencies=(task_id,))

    def test_execution_plan_rejects_empty_tasks(self):
        with self.assertRaises(ValueError):
            ExecutionPlan(
                goal_id="goal-1",
                goal="Find a game",
                summary="Research",
                tasks=(),
            )

    def test_execution_plan_rejects_duplicate_task_keys(self):
        first = self.make_task(plan_key="same", title="A", objective="A")
        second = self.make_task(
            plan_key="same",
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

    def test_execution_plan_rejects_task_from_different_goal(self):
        task = self.make_task(goal_id="goal-2")
        with self.assertRaisesRegex(ValueError, "task goal_id"):
            ExecutionPlan(
                goal_id="goal-1",
                goal="Find a game",
                summary="Research",
                tasks=(task,),
            )

    def test_agent_registration_has_safe_defaults(self):
        registration = AgentRegistration(
            name="researcher",
            agent_class=object,
            capabilities=frozenset({"market_research"}),
            allowed_risk_levels=frozenset({RiskLevel.LOW, RiskLevel.MEDIUM}),
        )

        self.assertIn("market_research", registration.capabilities)
        self.assertTrue(registration.enabled)
        self.assertEqual(registration.metadata, {})

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

    def test_agent_registration_requires_capabilities_and_risk_levels(self):
        with self.assertRaises(ValueError):
            AgentRegistration(
                name="researcher",
                agent_class=object,
                capabilities=frozenset(),
                allowed_risk_levels=frozenset({RiskLevel.LOW}),
            )
        with self.assertRaises(ValueError):
            AgentRegistration(
                name="researcher",
                agent_class=object,
                capabilities=frozenset({"market_research"}),
                allowed_risk_levels=frozenset(),
            )

    def test_orchestrator_and_approval_enums_are_stable(self):
        self.assertEqual(OrchestratorState.WAITING_APPROVAL.value, "waiting_approval")
        self.assertEqual(ApprovalDecision.APPROVE.value, "approve")
        self.assertEqual(ApprovalDisposition.CONTINUE_AUDIT.value, "continue_audit")

    def test_pending_approval_and_result_expose_stable_defaults(self):
        pending = PendingApproval(
            task_id="task-1",
            stage="pre_execution",
            effective_risk=RiskLevel.HIGH,
            requires_explicit_confirmation=False,
        )
        result = OrchestratorResult(
            state=OrchestratorState.WAITING_APPROVAL,
            goal_id="goal-1",
            message="Founder approval required",
            pending_task_id="task-1",
        )

        self.assertFalse(pending.result_ready)
        self.assertEqual(result.change_context, {})
        self.assertIsNone(result.error_code)


if __name__ == "__main__":
    unittest.main()
