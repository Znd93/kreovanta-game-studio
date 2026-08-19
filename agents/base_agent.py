from __future__ import annotations

from abc import ABC, abstractmethod

from core.contracts import AgentMessage


class BaseAgent(ABC):
    name: str

    def handle(self, message: AgentMessage) -> AgentMessage:
        if not isinstance(message, AgentMessage):
            raise TypeError("message must be an AgentMessage")
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("agent name must be a non-blank string")
        if message.recipient != self.name:
            raise ValueError(
                f"message recipient {message.recipient!r} does not match agent {self.name!r}"
            )

        result = self._handle(message)
        if not isinstance(result, AgentMessage):
            raise TypeError("agent _handle() must return an AgentMessage")
        return result

    @abstractmethod
    def _handle(self, message: AgentMessage) -> AgentMessage:
        raise NotImplementedError
