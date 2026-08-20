import unittest

from core.contracts import AgentMessage, MessageKind
from core.message_bus import MessageBus


def make_message(sender: str, recipient: str, objective: str) -> AgentMessage:
    return AgentMessage(
        sender=sender,
        recipient=recipient,
        kind=MessageKind.TASK,
        objective=objective,
    )


class MessageBusTests(unittest.TestCase):
    def test_receive_returns_oldest_message_for_recipient(self):
        bus = MessageBus()
        first = make_message("founder", "producer", "first")
        second = make_message("jarvis", "producer", "second")

        bus.publish(first)
        bus.publish(second)

        self.assertIs(bus.receive("producer"), first)
        self.assertIs(bus.receive("producer"), second)

    def test_receive_filters_by_recipient_without_dropping_other_messages(self):
        bus = MessageBus()
        producer_message = make_message("founder", "producer", "producer task")
        researcher_message = make_message("producer", "researcher", "research task")

        bus.publish(producer_message)
        bus.publish(researcher_message)

        self.assertIs(bus.receive("researcher"), researcher_message)
        self.assertIs(bus.receive("producer"), producer_message)

    def test_receive_returns_none_when_recipient_has_no_message(self):
        bus = MessageBus()
        bus.publish(make_message("founder", "producer", "task"))

        self.assertIsNone(bus.receive("researcher"))

    def test_history_keeps_all_published_messages_after_receive(self):
        bus = MessageBus()
        message = make_message("founder", "producer", "task")
        bus.publish(message)
        bus.receive("producer")

        history = bus.history()

        self.assertEqual(history, (message,))
        self.assertIsInstance(history, tuple)

    def test_publish_rejects_non_agent_message(self):
        bus = MessageBus()

        with self.assertRaises(TypeError):
            bus.publish({"recipient": "producer"})

    def test_receive_rejects_blank_recipient(self):
        bus = MessageBus()

        with self.assertRaises(ValueError):
            bus.receive("   ")


if __name__ == "__main__":
    unittest.main()
