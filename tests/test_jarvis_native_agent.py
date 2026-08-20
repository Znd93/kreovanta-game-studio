import unittest

from agents.jarvis_native import JarvisNativeAgent
from core.contracts import Priority, RiskLevel, TaskStatus
from jarvis.agent_contract import (
    AgentContractError,
    AgentTaskRequest,
    AgentTaskResult,
    request_to_message,
    result_from_message,
)


class EchoNativeAgent(JarvisNativeAgent):
    name = "echo_native"
    requests: list[AgentTaskRequest] = []

    def _execute(
        self,
        request: AgentTaskRequest,
    ) -> AgentTaskResult:
        type(self).requests.append(request)
        return AgentTaskResult(
            task_id=request.task_id,
            status=TaskStatus.COMPLETED,
            output_data={"received": request.input_data},
            summary="Echo complete",
            error=None,
            risk_level=request.risk_level,
            requires_approval=False,
        )


class WrongTaskNativeAgent(JarvisNativeAgent):
    name = "wrong_task"

    def _execute(
        self,
        request: AgentTaskRequest,
    ) -> AgentTaskResult:
        return AgentTaskResult(
            task_id="different-task",
            status=TaskStatus.COMPLETED,
            output_data={},
            summary="Wrong task",
            error=None,
            risk_level=RiskLevel.LOW,
            requires_approval=False,
        )


class JarvisNativeAgentTests(unittest.TestCase):
    def setUp(self):
        EchoNativeAgent.requests = []

    def make_request(self) -> AgentTaskRequest:
        return AgentTaskRequest(
            task_id="task-a",
            goal_id="goal-1",
            title="Echo",
            objective="Echo input",
            required_capabilities=("echo",),
            operation=None,
            priority=Priority.NORMAL,
            risk_level=RiskLevel.LOW,
            requires_approval=False,
            input_data={"value": 7},
            dependency_results={},
        )

    def test_handle_converts_transport_to_typed_request_and_back(self):
        request = self.make_request()
        message = request_to_message(
            request,
            recipient=EchoNativeAgent.name,
        )

        result_message = EchoNativeAgent().handle(message)
        result = result_from_message(
            result_message,
            expected_task_id=request.task_id,
        )

        self.assertEqual(EchoNativeAgent.requests, [request])
        self.assertEqual(
            result.output_data,
            {"received": {"value": 7}},
        )

    def test_wrong_result_task_id_fails_closed(self):
        request = self.make_request()
        message = request_to_message(
            request,
            recipient=WrongTaskNativeAgent.name,
        )

        with self.assertRaises(AgentContractError):
            WrongTaskNativeAgent().handle(message)


if __name__ == "__main__":
    unittest.main()
