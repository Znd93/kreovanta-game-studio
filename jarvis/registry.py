from __future__ import annotations

from agents.base_agent import BaseAgent
from agents.jarvis_native import JarvisNativeAgent
from core.contracts import RiskLevel
from jarvis.agent_contract import AgentContractVersion
from jarvis.models import AgentRegistration


class AgentRegistry:
    def __init__(self) -> None:
        self._registrations: dict[str, AgentRegistration] = {}

    def register(self, registration: AgentRegistration) -> None:
        if not isinstance(registration, AgentRegistration):
            raise TypeError("registration must be an AgentRegistration")
        if not issubclass(registration.agent_class, BaseAgent):
            raise TypeError("agent_class must be a BaseAgent subclass")
        if (
            registration.contract_version
            == AgentContractVersion.JARVIS_NATIVE_V1
            and not issubclass(
                registration.agent_class,
                JarvisNativeAgent,
            )
        ):
            raise TypeError(
                "JARVIS_NATIVE_V1 agent_class must be a "
                "JarvisNativeAgent subclass"
            )
        if registration.name in self._registrations:
            raise ValueError(f"agent already registered: {registration.name}")
        self._registrations[registration.name] = registration

    def get(self, name: str) -> AgentRegistration:
        try:
            return self._registrations[name]
        except KeyError:
            raise KeyError(name) from None

    def create(self, name: str) -> BaseAgent:
        registration = self.get(name)
        instance = registration.agent_class()
        if not isinstance(instance, BaseAgent):
            raise TypeError("created agent must be a BaseAgent")
        if instance.name != registration.name:
            raise ValueError(
                "created agent name does not match registration name: "
                f"{instance.name!r} != {registration.name!r}"
            )
        return instance

    def enabled_capabilities(self) -> frozenset[str]:
        capabilities: set[str] = set()
        for registration in self._registrations.values():
            if registration.enabled:
                capabilities.update(registration.capabilities)
        return frozenset(capabilities)

    def candidates(
        self,
        required_capabilities: frozenset[str],
        risk_level: RiskLevel,
    ) -> tuple[AgentRegistration, ...]:
        matches = (
            registration
            for registration in self._registrations.values()
            if registration.enabled
            and required_capabilities.issubset(registration.capabilities)
            and risk_level in registration.allowed_risk_levels
        )
        return tuple(sorted(matches, key=lambda registration: registration.name))
