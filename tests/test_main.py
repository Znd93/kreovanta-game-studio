from __future__ import annotations

import io
import runpy
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import patch

from core.contracts import RiskLevel
from jarvis.models import ApprovalDecision, OrchestratorResult, OrchestratorState


class FakeOrchestrator:
    def __init__(self, approvals, *, final_state=OrchestratorState.COMPLETED):
        self.approvals = approvals
        self.final_state = final_state
        self.start_calls: list[str] = []
        self.decisions: list[tuple[ApprovalDecision, bool, dict | None]] = []

    def start(self, founder_goal: str) -> OrchestratorResult:
        self.start_calls.append(founder_goal)
        return OrchestratorResult(
            state=OrchestratorState.WAITING_APPROVAL,
            goal_id="goal-1",
            message="Founder approval required",
            pending_task_id="task-1",
        )

    def decide(
        self,
        decision: ApprovalDecision,
        *,
        explicit_confirmation: bool = False,
        change_context: dict | None = None,
    ) -> OrchestratorResult:
        self.decisions.append((decision, explicit_confirmation, change_context))
        self.approvals.pending = None
        return OrchestratorResult(
            state=self.final_state,
            goal_id="goal-1",
            message="Decision applied",
        )


class MainEntryPointTests(unittest.TestCase):
    def load_main_namespace(self):
        output = io.StringIO()
        with redirect_stdout(output):
            namespace = runpy.run_path("main.py", run_name="jarvis_main_test")
        return namespace, output.getvalue()

    def test_loading_main_as_module_has_no_execution_side_effects(self):
        namespace, output = self.load_main_namespace()

        self.assertIn("main", namespace)
        self.assertEqual(output, "")

    def test_legacy_fixed_workflow_is_not_active_main_path(self):
        namespace, _ = self.load_main_namespace()

        self.assertNotIn("run_discovery_workflow", namespace)
        self.assertIn("_build_runtime", namespace)
        self.assertIn("_build_registry", namespace)

    def test_registry_explicitly_registers_current_agents_and_capabilities(self):
        namespace, _ = self.load_main_namespace()
        registry = namespace["_build_registry"]()

        producer = registry.get("producer")
        researcher = registry.get("researcher")
        director = registry.get("game_director")

        self.assertEqual(
            producer.capabilities,
            frozenset({"production_planning", "research_coordination"}),
        )
        self.assertEqual(
            producer.allowed_risk_levels,
            frozenset({RiskLevel.LOW, RiskLevel.MEDIUM}),
        )
        self.assertEqual(
            researcher.capabilities,
            frozenset({"market_research", "competitor_analysis", "concept_analysis"}),
        )
        self.assertEqual(
            director.capabilities,
            frozenset({"game_direction", "concept_selection"}),
        )
        self.assertIn(RiskLevel.HIGH, director.allowed_risk_levels)
        self.assertNotIn(RiskLevel.CRITICAL, director.allowed_risk_levels)

    def test_founder_decisions_normalize_case_insensitively(self):
        namespace, _ = self.load_main_namespace()
        parse = namespace["_parse_founder_decision"]

        cases = {
            "approve": ApprovalDecision.APPROVE,
            " ApPrOvE ": ApprovalDecision.APPROVE,
            "change": ApprovalDecision.CHANGE,
            " ChAnGe ": ApprovalDecision.CHANGE,
            "reject": ApprovalDecision.REJECT,
            " ReJeCt ": ApprovalDecision.REJECT,
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(parse(raw), expected)

        with self.assertRaises(ValueError):
            parse("maybe")

    def test_main_uses_orchestrator_and_noncritical_approval_needs_no_confirmation(self):
        namespace, _ = self.load_main_namespace()
        approvals = SimpleNamespace(
            pending=SimpleNamespace(requires_explicit_confirmation=False)
        )
        orchestrator = FakeOrchestrator(approvals)
        output = io.StringIO()

        with (
            patch.dict(
                namespace["main"].__globals__,
                {"_build_runtime": lambda: (orchestrator, approvals)},
            ),
            patch("builtins.input", side_effect=["aPpRoVe"]) as mock_input,
            redirect_stdout(output),
        ):
            namespace["main"]()

        self.assertEqual(
            orchestrator.start_calls,
            ["Find a simple Roblox game opportunity."],
        )
        self.assertEqual(
            orchestrator.decisions,
            [(ApprovalDecision.APPROVE, False, None)],
        )
        self.assertEqual(mock_input.call_count, 1)
        self.assertIn("WAITING_APPROVAL", output.getvalue())
        self.assertIn("COMPLETED", output.getvalue())

    def test_change_collects_context_without_critical_confirmation(self):
        namespace, _ = self.load_main_namespace()
        approvals = SimpleNamespace(
            pending=SimpleNamespace(requires_explicit_confirmation=True)
        )
        orchestrator = FakeOrchestrator(
            approvals,
            final_state=OrchestratorState.WAITING_APPROVAL,
        )

        with (
            patch.dict(
                namespace["main"].__globals__,
                {"_build_runtime": lambda: (orchestrator, approvals)},
            ),
            patch(
                "builtins.input",
                side_effect=["ChAnGe", "Use staging and re-review"],
            ) as mock_input,
            redirect_stdout(io.StringIO()),
        ):
            namespace["main"]()

        self.assertEqual(
            orchestrator.decisions,
            [
                (
                    ApprovalDecision.CHANGE,
                    False,
                    {"request": "Use staging and re-review"},
                )
            ],
        )
        self.assertEqual(mock_input.call_count, 2)

    def test_critical_approve_requests_explicit_confirmation(self):
        namespace, _ = self.load_main_namespace()
        approvals = SimpleNamespace(
            pending=SimpleNamespace(requires_explicit_confirmation=True)
        )
        orchestrator = FakeOrchestrator(approvals)

        with (
            patch.dict(
                namespace["main"].__globals__,
                {"_build_runtime": lambda: (orchestrator, approvals)},
            ),
            patch("builtins.input", side_effect=["approve", "CONFIRM"]) as mock_input,
            redirect_stdout(io.StringIO()),
        ):
            namespace["main"]()

        self.assertEqual(
            orchestrator.decisions,
            [(ApprovalDecision.APPROVE, True, None)],
        )
        self.assertEqual(mock_input.call_count, 2)

    def test_critical_reject_does_not_request_confirmation(self):
        namespace, _ = self.load_main_namespace()
        approvals = SimpleNamespace(
            pending=SimpleNamespace(requires_explicit_confirmation=True)
        )
        orchestrator = FakeOrchestrator(
            approvals,
            final_state=OrchestratorState.FAILED,
        )

        with (
            patch.dict(
                namespace["main"].__globals__,
                {"_build_runtime": lambda: (orchestrator, approvals)},
            ),
            patch("builtins.input", side_effect=["reject"]) as mock_input,
            redirect_stdout(io.StringIO()),
        ):
            namespace["main"]()

        self.assertEqual(
            orchestrator.decisions,
            [(ApprovalDecision.REJECT, False, None)],
        )
        self.assertEqual(mock_input.call_count, 1)


if __name__ == "__main__":
    unittest.main()
