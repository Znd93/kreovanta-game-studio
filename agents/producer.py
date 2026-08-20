import json

from agents.base_agent import BaseAgent
from core.contracts import AgentMessage, MessageKind, TaskStatus
from core.ollama_client import chat


SYSTEM_PROMPT = """
You are the Producer of Kreovanta Roblox Game Studio.

Your job is to:
- understand the Founder's request
- break the work into clear tasks
- delegate research work to the Researcher
- never approve major game plans yourself
- always send major plans back to the Founder for approval

Return ONLY valid JSON in this exact format:

{
  "producer_message": "short explanation of what you are doing",
  "research_task": "specific task for the Researcher"
}

Do not add markdown.
Do not add extra text.
"""


class ProducerAgent(BaseAgent):
    name = "producer"

    def _handle(self, message: AgentMessage) -> AgentMessage:
        founder_request = message.payload.get("founder_request")
        if not isinstance(founder_request, str) or not founder_request.strip():
            return self._error(message, "payload must contain a non-blank founder_request")

        response = chat(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": founder_request},
            ]
        )

        try:
            parsed = json.loads(response)
        except (json.JSONDecodeError, TypeError) as exc:
            return self._error(message, f"invalid producer JSON: {exc}")

        if not isinstance(parsed, dict):
            return self._error(message, "producer response must be a JSON object")

        producer_message = parsed.get("producer_message")
        research_task = parsed.get("research_task")
        if not isinstance(producer_message, str) or not producer_message.strip():
            return self._error(message, "producer response missing producer_message")
        if not isinstance(research_task, str) or not research_task.strip():
            return self._error(message, "producer response missing research_task")

        return AgentMessage(
            parent_id=message.id,
            sender=self.name,
            recipient="researcher",
            kind=MessageKind.RESULT,
            objective="Research the selected Roblox game opportunity",
            payload={
                "producer_message": producer_message,
                "research_task": research_task,
            },
            status=TaskStatus.COMPLETED,
        )

    def _error(self, message: AgentMessage, detail: str) -> AgentMessage:
        return AgentMessage(
            parent_id=message.id,
            sender=self.name,
            recipient=message.sender,
            kind=MessageKind.ERROR,
            objective="Producer failed to create a research task",
            payload={"error": detail},
            status=TaskStatus.FAILED,
        )


def run_producer(founder_request: str) -> dict:
    """Compatibility wrapper for the original prototype API."""
    result = ProducerAgent().handle(
        AgentMessage(
            sender="founder",
            recipient="producer",
            kind=MessageKind.TASK,
            objective="Find a simple Roblox game opportunity",
            payload={"founder_request": founder_request},
        )
    )
    if result.status is TaskStatus.FAILED:
        raise ValueError(result.payload["error"])
    return result.payload
