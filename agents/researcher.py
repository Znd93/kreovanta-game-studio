from agents.base_agent import BaseAgent
from core.contracts import AgentMessage, MessageKind, TaskStatus
from core.ollama_client import chat


SYSTEM_PROMPT = """
You are the Researcher for Kreovanta Roblox Game Studio.

Your job is to:
- investigate Roblox game opportunities
- identify simple, proven gameplay loops
- compare multiple concepts
- focus on ideas that are realistic for a small team
- look for ways to improve existing successful concepts
- report findings to the Game Director
- never approve a game for production yourself

Important:
If you do not have live internet data, clearly label your findings as hypothesis-based and not verified current trends.

Keep responses structured and concise.
"""


class ResearcherAgent(BaseAgent):
    name = "researcher"

    def _handle(self, message: AgentMessage) -> AgentMessage:
        research_task = message.payload.get("research_task")
        if not isinstance(research_task, str) or not research_task.strip():
            return self._error(message, "payload must contain a non-blank research_task")

        response = chat(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": research_task},
            ]
        )
        if not isinstance(response, str) or not response.strip():
            return self._error(message, "researcher response cannot be blank")

        return AgentMessage(
            parent_id=message.id,
            sender=self.name,
            recipient="game_director",
            kind=MessageKind.RESULT,
            objective="Review Roblox opportunity research",
            payload={"research_findings": response},
            status=TaskStatus.COMPLETED,
        )

    def _error(self, message: AgentMessage, detail: str) -> AgentMessage:
        return AgentMessage(
            parent_id=message.id,
            sender=self.name,
            recipient=message.sender,
            kind=MessageKind.ERROR,
            objective="Researcher failed to produce findings",
            payload={"error": detail},
            status=TaskStatus.FAILED,
        )


def run_researcher(task: str) -> str:
    """Compatibility wrapper for the original prototype API."""
    result = ResearcherAgent().handle(
        AgentMessage(
            sender="producer",
            recipient="researcher",
            kind=MessageKind.RESULT,
            objective="Research the opportunity",
            payload={"research_task": task},
            status=TaskStatus.COMPLETED,
        )
    )
    if result.status is TaskStatus.FAILED:
        raise ValueError(result.payload["error"])
    return result.payload["research_findings"]
