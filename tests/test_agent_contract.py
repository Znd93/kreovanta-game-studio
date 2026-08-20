import unittest

from core.contracts import AgentMessage, MessageKind, Priority, RiskLevel, TaskStatus
from jarvis.agent_contract import (
    AgentContractError,
    AgentContractVersion,
    AgentTaskRequest,
    AgentTaskResult,
    request_from_message,
    request_to_message,
    result_from_message,
    result_to_message,
)


class AgentTaskRequestTests(unittest.TestCase):
    def make_request(self, **overrides) -> AgentTaskRequest:
        values = {
            "task_id": "task-a",
            "goal_id": "goal-1",
            "title": "Implement feature",
            "objective": "Implement the requested feature",
            "required_capabilities": ("code_implementation",),
            "operation": "code_change",
            "priority": Priority.NORMAL,
            "risk_level": RiskLevel.LOW,
            "requires_approval": False,
            "input_data": {"repository": "example/repo"},
            "dependency_results": {},
        }
        values.update(overrides)
        return AgentTaskRequest(**values)

    def test_valid_request_is_accepted(self):
        request = self.make_request()

        self.assertEqual(request.task_id, "task-a")
        self.assertEqual(request.required_capabilities, ("code_implementation",))
        self.assertEqual(request.dependency_results, {})

    def test_request_rejects_blank_task_id(self):
        with self.assertRaises(ValueError):
            self.make_request(task_id="   ")

    def test_request_rejects_empty_capabilities(self):
        with self.assertRaises(ValueError):
            self.make_request(required_capabilities=())

    def test_request_rejects_invalid_dependency_results(self):
        with self.assertRaises(TypeError):
            self.make_request(dependency_results={"task-z": "not-a-dict"})


class AgentTaskResultTests(unittest.TestCase):
    def make_result(self, **overrides) -> AgentTaskResult:
        values = {
            "task_id": "task-a",
            "status": TaskStatus.COMPLETED,
            "output_data": {"artifact": "x"},
            "summary": "Completed work",
            "error": None,
            "risk_level": RiskLevel.LOW,
            "requires_approval": False,
        }
        values.update(overrides)
        return AgentTaskResult(**values)

    def test_valid_completed_result_is_accepted(self):
        result = self.make_result()

        self.assertEqual(result.status, TaskStatus.COMPLETED)
        self.assertEqual(result.output_data, {"artifact": "x"})

    def test_failed_result_requires_error(self):
        with self.assertRaises(ValueError):
            self.make_result(status=TaskStatus.FAILED, error=None)

    def test_completed_result_rejects_error(self):
        with self.assertRaises(ValueError):
            self.make_result(error="unexpected")

    def test_result_rejects_orchestration_owned_status(self):
        with self.assertRaises(ValueError):
            self.make_result(status=TaskStatus.RUNNING)


class AgentContractVersionTests(unittest.TestCase):
    def test_version_values_are_stable(self):
        self.assertEqual(AgentContractVersion.LEGACY_V1.value, "legacy_v1")
        self.assertEqual(
            AgentContractVersion.JARVIS_NATIVE_V1.value,
            "jarvis_native_v1",
        )


class AgentContractSerializationTests(unittest.TestCase):
    def make_request(self) -> AgentTaskRequest:
        return AgentTaskRequest(
            task_id="task-a",
            goal_id="goal-1",
            title="Implement feature",
            objective="Implement the requested feature",
            required_capabilities=("code_implementation",),
            operation="code_change",
            priority=Priority.HIGH,
            risk_level=RiskLevel.MEDIUM,
            requires_approval=False,
            input_data={"repository": "example/repo"},
            dependency_results={
                "task-parent": {
                    "summary": "Prepared input",
                    "output_data": {"artifact": "x"},
                }
            },
        )

    def test_request_round_trip_preserves_contract(self):
        request = self.make_request()

        message = request_to_message(request, recipient="developer")
        parsed = request_from_message(message)

        self.assertEqual(message.sender, "jarvis")
        self.assertEqual(message.recipient, "developer")
        self.assertEqual(message.kind, MessageKind.TASK)
        self.assertEqual(
            message.payload["contract_version"],
            AgentContractVersion.JARVIS_NATIVE_V1.value,
        )
        self.assertEqual(parsed, request)

    def test_request_rejects_wrong_contract_version(self):
        request = self.make_request()
        message = request_to_message(request, recipient="developer")
        message.payload["contract_version"] = "legacy_v1"

        with self.assertRaises(AgentContractError):
            request_from_message(message)

    def test_request_rejects_wrong_message_kind(self):
        request = self.make_request()
        message = request_to_message(request, recipient="developer")
        message.kind = MessageKind.RESULT

        with self.assertRaises(AgentContractError):
            request_from_message(message)

    def test_completed_result_round_trip_maps_message_kind(self):
        result = AgentTaskResult(
            task_id="task-a",
            status=TaskStatus.COMPLETED,
            output_data={"files_changed": ["x.py"]},
            summary="Implemented change",
            error=None,
            risk_level=RiskLevel.LOW,
            requires_approval=False,
        )

        message = result_to_message(
            result,
            sender="developer",
            parent_id="message-1",
        )
        parsed = result_from_message(message, expected_task_id="task-a")

        self.assertEqual(message.kind, MessageKind.RESULT)
        self.assertEqual(message.recipient, "jarvis")
        self.assertEqual(parsed, result)

    def test_failed_result_maps_error_kind(self):
        result = AgentTaskResult(
            task_id="task-a",
            status=TaskStatus.FAILED,
            output_data={},
            summary="Implementation failed",
            error="compile error",
            risk_level=RiskLevel.LOW,
            requires_approval=False,
        )

        message = result_to_message(
            result,
            sender="developer",
            parent_id="message-1",
        )

        self.assertEqual(message.kind, MessageKind.ERROR)

    def test_waiting_result_maps_approval_kind(self):
        result = AgentTaskResult(
            task_id="task-a",
            status=TaskStatus.WAITING_APPROVAL,
            output_data={"candidate": "x"},
            summary="Founder review required",
            error=None,
            risk_level=RiskLevel.HIGH,
            requires_approval=True,
        )

        message = result_to_message(
            result,
            sender="reviewer",
            parent_id="message-1",
        )

        self.assertEqual(message.kind, MessageKind.APPROVAL_REQUEST)

    def test_result_rejects_task_id_mismatch(self):
        result = AgentTaskResult(
            task_id="task-a",
            status=TaskStatus.COMPLETED,
            output_data={},
            summary="Done",
            error=None,
            risk_level=RiskLevel.LOW,
            requires_approval=False,
        )
        message = result_to_message(
            result,
            sender="developer",
            parent_id="message-1",
        )

        with self.assertRaises(AgentContractError):
            result_from_message(message, expected_task_id="task-b")


if __name__ == "__main__":
    unittest.main()
