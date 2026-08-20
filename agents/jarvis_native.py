from __future__ import annotations

from abc import abstractmethod

from agents.base_agent import BaseAgent
from core.contracts import AgentMessage
from jarvis.agent_contract import (
    AgentContractError,
    AgentTaskRequest,
    AgentTaskResult,
    request_from_message,
    result_to_message,
)


class JarvisNativeAgent(BaseAgent):
    def _handle(self, message: AgentMessage) -> AgentMessage:
        request = request_from_message(message)
        result = self._execute(request)

        if not isinstance(result, AgentTaskResult):
            raise AgentContractError(
                "_execute() must return an AgentTaskResult"
            )
        if result.task_id != request.task_id:
            raise AgentContractError(
                "native agent result task_id must match request task_id"
            )

        return result_to_message(
            result,
            sender=self.name,
            parent_id=message.id,
        )

    @abstractmethod
    def _execute(
        self,
        request: AgentTaskRequest,
    ) -> AgentTaskResult:
        raise NotImplementedError
