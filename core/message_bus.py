from __future__ import annotations

from core.contracts import AgentMessage


class MessageBus:
    def __init__(self) -> None:
        self._pending: list[AgentMessage] = []
        self._history: list[AgentMessage] = []

    def publish(self, message: AgentMessage) -> None:
        if not isinstance(message, AgentMessage):
            raise TypeError("message must be an AgentMessage")
        self._pending.append(message)
        self._history.append(message)

    def receive(self, recipient: str) -> AgentMessage | None:
        if not isinstance(recipient, str):
            raise TypeError("recipient must be a string")
        if not recipient.strip():
            raise ValueError("recipient cannot be blank")

        for index, message in enumerate(self._pending):
            if message.recipient == recipient:
                return self._pending.pop(index)
        return None

    def history(self) -> tuple[AgentMessage, ...]:
        return tuple(self._history)
