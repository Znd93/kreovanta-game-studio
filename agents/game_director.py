from agents.base_agent import BaseAgent
from core.contracts import AgentMessage, MessageKind, RiskLevel, TaskStatus
from core.ollama_client import chat


SYSTEM_PROMPT = """
You are the Game Director of Kreovanta Roblox Game Studio.

Your job is to:
- review research findings
- compare concepts
- identify the strongest game opportunity
- explain why the concept could be fun
- define the core gameplay loop
- identify major risks
- recommend what should move forward
- never approve production yourself
- always send the final recommendation to the Founder for approval

You must:
- distinguish verified facts from assumptions
- avoid inventing live Roblox trend data
- keep the recommendation practical for a small Roblox development team
- prioritize simple, addictive, expandable gameplay

Keep responses structured and concise.
"""


class GameDirectorAgent(BaseAgent):
    name = "game_director"

    def _handle(self, message: AgentMessage) -> AgentMessage:
        research_findings = message.payload.get("research_findings")
        if not isinstance(research_findings, str) or not research_findings.strip():
            return self._error(message, "payload must contain non-blank research_findings")

        response = chat(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": research_findings},
            ]
        )
        if not isinstance(response, str) or not response.strip():
            return self._error(message, "game director recommendation cannot be blank")

        return AgentMessage(
            parent_id=message.id,
            sender=self.name,
            recipient="founder",
            kind=MessageKind.APPROVAL_REQUEST,
            objective="Approve the recommended Roblox game concept",
            payload={"recommendation": response},
            status=TaskStatus.WAITING_APPROVAL,
            risk_level=RiskLevel.HIGH,
            requires_approval=True,
        )

    def _error(self, message: AgentMessage, detail: str) -> AgentMessage:
        return AgentMessage(
            parent_id=message.id,
            sender=self.name,
            recipient=message.sender,
            kind=MessageKind.ERROR,
            objective="Game Director failed to produce a recommendation",
            payload={"error": detail},
            status=TaskStatus.FAILED,
        )


def run_game_director(research_findings: str) -> str:
    """Compatibility wrapper for the original prototype API."""
    result = GameDirectorAgent().handle(
        AgentMessage(
            sender="researcher",
            recipient="game_director",
            kind=MessageKind.RESULT,
            objective="Review Roblox opportunity research",
            payload={"research_findings": research_findings},
            status=TaskStatus.COMPLETED,
        )
    )
    if result.status is TaskStatus.FAILED:
        raise ValueError(result.payload["error"])
    return result.payload["recommendation"]
