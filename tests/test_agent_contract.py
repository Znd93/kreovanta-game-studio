import unittest

from core.contracts import Priority, RiskLevel, TaskStatus
from jarvis.agent_contract import (
    AgentContractVersion,
    AgentTaskRequest,
    AgentTaskResult,
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


if __name__ == "__main__":
    unittest.main()
