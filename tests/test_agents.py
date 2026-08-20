import unittest
from unittest.mock import patch

from core.contracts import AgentMessage, MessageKind, RiskLevel, TaskStatus
from agents.producer import ProducerAgent
from agents.researcher import ResearcherAgent
from agents.game_director import GameDirectorAgent


class ProducerAgentTests(unittest.TestCase):
    def make_message(self, payload=None):
        return AgentMessage(
            sender="founder",
            recipient="producer",
            kind=MessageKind.TASK,
            objective="Find a simple Roblox game opportunity",
            payload=payload if payload is not None else {
                "founder_request": "Find a simple Roblox game opportunity."
            },
        )

    @patch("agents.producer.chat")
    def test_success_returns_completed_result_for_researcher(self, mock_chat):
        mock_chat.return_value = (
            '{"producer_message":"Starting research",'
            '"research_task":"Compare simple Roblox opportunities"}'
        )
        incoming = self.make_message()

        result = ProducerAgent().handle(incoming)

        self.assertEqual(result.parent_id, incoming.id)
        self.assertEqual(result.sender, "producer")
        self.assertEqual(result.recipient, "researcher")
        self.assertEqual(result.kind, MessageKind.RESULT)
        self.assertEqual(result.status, TaskStatus.COMPLETED)
        self.assertEqual(result.payload["producer_message"], "Starting research")
        self.assertEqual(
            result.payload["research_task"],
            "Compare simple Roblox opportunities",
        )
        self.assertIn("Find a simple Roblox game opportunity.", mock_chat.call_args.args[0][1]["content"])

    @patch("agents.producer.chat")
    def test_malformed_json_returns_failed_error_message(self, mock_chat):
        mock_chat.return_value = "not-json"
        incoming = self.make_message()

        result = ProducerAgent().handle(incoming)

        self.assertEqual(result.kind, MessageKind.ERROR)
        self.assertEqual(result.status, TaskStatus.FAILED)
        self.assertEqual(result.parent_id, incoming.id)
        self.assertEqual(result.recipient, "founder")
        self.assertIn("error", result.payload)

    @patch("agents.producer.chat")
    def test_missing_founder_request_returns_failed_error_without_llm_call(self, mock_chat):
        incoming = self.make_message(payload={})

        result = ProducerAgent().handle(incoming)

        self.assertEqual(result.kind, MessageKind.ERROR)
        self.assertEqual(result.status, TaskStatus.FAILED)
        mock_chat.assert_not_called()

    @patch("agents.producer.chat")
    def test_missing_expected_llm_json_keys_returns_failed_error(self, mock_chat):
        mock_chat.return_value = '{"producer_message":"Starting research"}'
        incoming = self.make_message()

        result = ProducerAgent().handle(incoming)

        self.assertEqual(result.kind, MessageKind.ERROR)
        self.assertEqual(result.status, TaskStatus.FAILED)
        self.assertIn("research_task", result.payload["error"])


class ResearcherAgentTests(unittest.TestCase):
    def make_message(self, payload=None):
        return AgentMessage(
            sender="producer",
            recipient="researcher",
            kind=MessageKind.RESULT,
            objective="Research the opportunity",
            payload=payload if payload is not None else {
                "research_task": "Compare simple Roblox opportunities"
            },
            status=TaskStatus.COMPLETED,
        )

    @patch("agents.researcher.chat")
    def test_success_returns_completed_result_for_game_director(self, mock_chat):
        mock_chat.return_value = "Research findings"
        incoming = self.make_message()

        result = ResearcherAgent().handle(incoming)

        self.assertEqual(result.parent_id, incoming.id)
        self.assertEqual(result.sender, "researcher")
        self.assertEqual(result.recipient, "game_director")
        self.assertEqual(result.kind, MessageKind.RESULT)
        self.assertEqual(result.status, TaskStatus.COMPLETED)
        self.assertEqual(result.payload, {"research_findings": "Research findings"})
        self.assertEqual(
            mock_chat.call_args.args[0][1]["content"],
            "Compare simple Roblox opportunities",
        )

    @patch("agents.researcher.chat")
    def test_missing_research_task_returns_failed_error_without_llm_call(self, mock_chat):
        incoming = self.make_message(payload={})

        result = ResearcherAgent().handle(incoming)

        self.assertEqual(result.kind, MessageKind.ERROR)
        self.assertEqual(result.status, TaskStatus.FAILED)
        self.assertEqual(result.recipient, "producer")
        mock_chat.assert_not_called()

    @patch("agents.researcher.chat")
    def test_blank_research_response_returns_failed_error(self, mock_chat):
        mock_chat.return_value = "   "
        incoming = self.make_message()

        result = ResearcherAgent().handle(incoming)

        self.assertEqual(result.kind, MessageKind.ERROR)
        self.assertEqual(result.status, TaskStatus.FAILED)



class GameDirectorAgentTests(unittest.TestCase):
    def make_message(self, payload=None):
        return AgentMessage(
            sender="researcher",
            recipient="game_director",
            kind=MessageKind.RESULT,
            objective="Review Roblox opportunity research",
            payload=payload if payload is not None else {
                "research_findings": "Strong opportunity found"
            },
            status=TaskStatus.COMPLETED,
        )

    @patch("agents.game_director.chat")
    def test_success_returns_high_risk_founder_approval_request(self, mock_chat):
        mock_chat.return_value = "Build the obby concept"
        incoming = self.make_message()

        result = GameDirectorAgent().handle(incoming)

        self.assertEqual(result.parent_id, incoming.id)
        self.assertEqual(result.sender, "game_director")
        self.assertEqual(result.recipient, "founder")
        self.assertEqual(result.kind, MessageKind.APPROVAL_REQUEST)
        self.assertEqual(result.status, TaskStatus.WAITING_APPROVAL)
        self.assertEqual(result.risk_level, RiskLevel.HIGH)
        self.assertTrue(result.requires_approval)
        self.assertEqual(result.payload, {"recommendation": "Build the obby concept"})
        self.assertEqual(mock_chat.call_args.args[0][1]["content"], "Strong opportunity found")

    @patch("agents.game_director.chat")
    def test_missing_research_findings_returns_failed_error_without_llm_call(self, mock_chat):
        incoming = self.make_message(payload={})

        result = GameDirectorAgent().handle(incoming)

        self.assertEqual(result.kind, MessageKind.ERROR)
        self.assertEqual(result.status, TaskStatus.FAILED)
        self.assertEqual(result.recipient, "researcher")
        mock_chat.assert_not_called()

    @patch("agents.game_director.chat")
    def test_blank_recommendation_returns_failed_error(self, mock_chat):
        mock_chat.return_value = "   "
        incoming = self.make_message()

        result = GameDirectorAgent().handle(incoming)

        self.assertEqual(result.kind, MessageKind.ERROR)
        self.assertEqual(result.status, TaskStatus.FAILED)


if __name__ == "__main__":
    unittest.main()
