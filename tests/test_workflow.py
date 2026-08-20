import unittest
from unittest.mock import patch

from agents.game_director import GameDirectorAgent
from agents.producer import ProducerAgent
from agents.researcher import ResearcherAgent
from core.contracts import MessageKind, RiskLevel, TaskStatus
from core.message_bus import MessageBus
from core.workflow import run_discovery_workflow


class DiscoveryWorkflowTests(unittest.TestCase):
    @patch("agents.game_director.chat")
    @patch("agents.researcher.chat")
    @patch("agents.producer.chat")
    def test_full_workflow_routes_messages_to_founder_approval(
        self,
        producer_chat,
        researcher_chat,
        director_chat,
    ):
        producer_chat.return_value = (
            '{"producer_message":"Researching",'
            '"research_task":"Compare current simple Roblox opportunities"}'
        )
        researcher_chat.return_value = "Three concepts compared"
        director_chat.return_value = "Recommend the low-complexity obby"
        bus = MessageBus()

        final_message = run_discovery_workflow(
            founder_request="Find a simple Roblox game opportunity.",
            producer=ProducerAgent(),
            researcher=ResearcherAgent(),
            game_director=GameDirectorAgent(),
            bus=bus,
        )

        self.assertEqual(final_message.recipient, "founder")
        self.assertEqual(final_message.kind, MessageKind.APPROVAL_REQUEST)
        self.assertEqual(final_message.status, TaskStatus.WAITING_APPROVAL)
        self.assertEqual(final_message.risk_level, RiskLevel.HIGH)
        self.assertTrue(final_message.requires_approval)

        history = bus.history()
        self.assertEqual(len(history), 4)
        self.assertEqual(
            [(message.sender, message.recipient) for message in history],
            [
                ("founder", "producer"),
                ("producer", "researcher"),
                ("researcher", "game_director"),
                ("game_director", "founder"),
            ],
        )
        self.assertEqual(history[1].parent_id, history[0].id)
        self.assertEqual(history[2].parent_id, history[1].id)
        self.assertEqual(history[3].parent_id, history[2].id)

    @patch("agents.producer.chat")
    def test_workflow_stops_on_failed_agent_message(self, producer_chat):
        producer_chat.return_value = "invalid json"
        bus = MessageBus()

        with self.assertRaisesRegex(RuntimeError, "Producer failed"):
            run_discovery_workflow(
                founder_request="Find a game",
                producer=ProducerAgent(),
                researcher=ResearcherAgent(),
                game_director=GameDirectorAgent(),
                bus=bus,
            )

        self.assertEqual(len(bus.history()), 2)
        self.assertEqual(bus.history()[-1].status, TaskStatus.FAILED)


if __name__ == "__main__":
    unittest.main()
