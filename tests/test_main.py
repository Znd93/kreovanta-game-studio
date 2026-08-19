import io
import runpy
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from core.contracts import AgentMessage, MessageKind, RiskLevel, TaskStatus


class MainEntryPointTests(unittest.TestCase):
    def load_main_namespace(self):
        output = io.StringIO()
        with (
            patch("agents.producer.chat", return_value='{"producer_message":"x","research_task":"y"}'),
            patch("agents.researcher.chat", return_value="research"),
            patch("agents.game_director.chat", return_value="recommendation"),
            patch("builtins.input", return_value="APPROVE"),
            redirect_stdout(output),
        ):
            namespace = runpy.run_path("main.py", run_name="jarvis_main_test")
        return namespace, output.getvalue()

    def test_loading_main_as_module_has_no_execution_side_effects(self):
        namespace, output = self.load_main_namespace()

        self.assertIn("main", namespace)
        self.assertEqual(output, "")

    def test_main_uses_workflow_and_preserves_founder_approval_terminal(self):
        namespace, _ = self.load_main_namespace()
        run_main = namespace["main"]
        calls = []

        def fake_workflow(*, founder_request, producer, researcher, game_director, bus):
            calls.append(founder_request)
            founder = AgentMessage(
                sender="founder",
                recipient="producer",
                kind=MessageKind.TASK,
                objective="Find opportunity",
                payload={"founder_request": founder_request},
            )
            producer_result = AgentMessage(
                parent_id=founder.id,
                sender="producer",
                recipient="researcher",
                kind=MessageKind.RESULT,
                objective="Research",
                payload={"producer_message": "Starting research", "research_task": "Compare"},
                status=TaskStatus.COMPLETED,
            )
            research_result = AgentMessage(
                parent_id=producer_result.id,
                sender="researcher",
                recipient="game_director",
                kind=MessageKind.RESULT,
                objective="Review",
                payload={"research_findings": "Findings"},
                status=TaskStatus.COMPLETED,
            )
            final = AgentMessage(
                parent_id=research_result.id,
                sender="game_director",
                recipient="founder",
                kind=MessageKind.APPROVAL_REQUEST,
                objective="Approve",
                payload={"recommendation": "Recommendation"},
                status=TaskStatus.WAITING_APPROVAL,
                risk_level=RiskLevel.HIGH,
                requires_approval=True,
            )
            for message in (founder, producer_result, research_result, final):
                bus.publish(message)
            return final

        output = io.StringIO()
        with (
            patch.dict(run_main.__globals__, {"run_discovery_workflow": fake_workflow}),
            patch("builtins.input", return_value="APPROVE"),
            redirect_stdout(output),
        ):
            run_main()

        rendered = output.getvalue()
        self.assertEqual(calls, ["Find a simple Roblox game opportunity."])
        self.assertIn("=== PRODUCER ===", rendered)
        self.assertIn("Starting research", rendered)
        self.assertIn("=== RESEARCHER ===", rendered)
        self.assertIn("Findings", rendered)
        self.assertIn("=== GAME DIRECTOR ===", rendered)
        self.assertIn("Recommendation", rendered)
        self.assertIn("WAITING FOR FOUNDER APPROVAL", rendered)
        self.assertIn("APPROVED", rendered)


if __name__ == "__main__":
    unittest.main()
