import unittest

from agents.base_agent import BaseAgent
from core.contracts import AgentMessage, MessageKind


class EchoAgent(BaseAgent):
    name = "echo"

    def _handle(self, message: AgentMessage) -> AgentMessage:
        return AgentMessage(
            parent_id=message.id,
            sender=self.name,
            recipient=message.sender,
            kind=MessageKind.RESULT,
            objective="Echo complete",
            payload={"objective": message.objective},
        )


class BaseAgentTests(unittest.TestCase):
    def test_handle_accepts_message_addressed_to_agent(self):
        agent = EchoAgent()
        incoming = AgentMessage(
            sender="founder",
            recipient="echo",
            kind=MessageKind.TASK,
            objective="test",
        )

        result = agent.handle(incoming)

        self.assertEqual(result.sender, "echo")
        self.assertEqual(result.parent_id, incoming.id)

    def test_handle_rejects_message_for_different_recipient(self):
        agent = EchoAgent()
        incoming = AgentMessage(
            sender="founder",
            recipient="someone_else",
            kind=MessageKind.TASK,
            objective="test",
        )

        with self.assertRaises(ValueError):
            agent.handle(incoming)

    def test_handle_rejects_non_agent_message(self):
        agent = EchoAgent()

        with self.assertRaises(TypeError):
            agent.handle({"recipient": "echo"})


if __name__ == "__main__":
    unittest.main()
