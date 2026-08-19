import unittest
from datetime import datetime, timezone

from core.contracts import (
    AgentMessage,
    MessageKind,
    Priority,
    RiskLevel,
    TaskStatus,
)


class AgentMessageTests(unittest.TestCase):
    def test_defaults_generate_identity_and_utc_timestamp(self):
        message = AgentMessage(
            sender="founder",
            recipient="producer",
            kind=MessageKind.TASK,
            objective="Find a game opportunity",
        )

        self.assertTrue(message.id)
        self.assertIsNone(message.parent_id)
        self.assertEqual(message.payload, {})
        self.assertEqual(message.metadata, {})
        self.assertEqual(message.status, TaskStatus.PENDING)
        self.assertEqual(message.priority, Priority.NORMAL)
        self.assertEqual(message.risk_level, RiskLevel.LOW)
        self.assertFalse(message.requires_approval)
        self.assertIsInstance(message.created_at, datetime)
        self.assertIsNotNone(message.created_at.tzinfo)
        self.assertEqual(message.created_at.utcoffset(), timezone.utc.utcoffset(message.created_at))

    def test_explicit_parent_id_is_preserved(self):
        message = AgentMessage(
            parent_id="parent-123",
            sender="producer",
            recipient="researcher",
            kind=MessageKind.RESULT,
            objective="Research opportunity",
        )

        self.assertEqual(message.parent_id, "parent-123")

    def test_required_text_fields_reject_blank_values(self):
        valid = {
            "sender": "founder",
            "recipient": "producer",
            "kind": MessageKind.TASK,
            "objective": "Find a game",
        }

        for field in ("sender", "recipient", "objective"):
            with self.subTest(field=field):
                kwargs = dict(valid)
                kwargs[field] = "   "
                with self.assertRaises(ValueError):
                    AgentMessage(**kwargs)

    def test_payload_and_metadata_must_be_dicts(self):
        base = {
            "sender": "founder",
            "recipient": "producer",
            "kind": MessageKind.TASK,
            "objective": "Find a game",
        }

        with self.assertRaises(TypeError):
            AgentMessage(**base, payload=[])

        with self.assertRaises(TypeError):
            AgentMessage(**base, metadata=[])

    def test_enum_fields_require_correct_enum_types(self):
        base = {
            "sender": "founder",
            "recipient": "producer",
            "kind": MessageKind.TASK,
            "objective": "Find a game",
        }

        with self.assertRaises(TypeError):
            AgentMessage(**{**base, "kind": "task"})

        with self.assertRaises(TypeError):
            AgentMessage(**base, status="pending")

        with self.assertRaises(TypeError):
            AgentMessage(**base, priority="normal")

        with self.assertRaises(TypeError):
            AgentMessage(**base, risk_level="low")

    def test_all_contract_enums_expose_expected_values(self):
        self.assertEqual(
            {item.value for item in MessageKind},
            {"task", "result", "approval_request", "decision", "error"},
        )
        self.assertEqual(
            {item.value for item in TaskStatus},
            {
                "pending",
                "ready",
                "running",
                "completed",
                "failed",
                "blocked",
                "waiting_approval",
                "rejected",
            },
        )
        self.assertEqual(
            {item.value for item in Priority},
            {"low", "normal", "high", "critical"},
        )
        self.assertEqual(
            {item.value for item in RiskLevel},
            {"low", "medium", "high", "critical"},
        )


if __name__ == "__main__":
    unittest.main()
