from __future__ import annotations

from core.contracts import RiskLevel
from jarvis.models import AgentRegistration, JarvisTask
from jarvis.registry import AgentRegistry


class NoRouteError(RuntimeError):
    pass


class JarvisRouter:
    def __init__(self, registry: AgentRegistry) -> None:
        self._registry = registry

    def route(
        self,
        task: JarvisTask,
        effective_risk: RiskLevel,
    ) -> AgentRegistration:
        required = frozenset(task.required_capabilities)
        candidates = self._registry.candidates(required, effective_risk)

        if not candidates:
            raise NoRouteError(task.id, task.required_capabilities)

        return min(
            candidates,
            key=lambda item: (
                0 if item.capabilities == required else 1,
                len(item.capabilities - required),
                item.name,
            ),
        )
