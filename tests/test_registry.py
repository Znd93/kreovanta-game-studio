import unittest

from agents.base_agent import BaseAgent
from core.contracts import AgentMessage, RiskLevel
from jarvis.models import AgentRegistration
from jarvis.registry import AgentRegistry


class ResearcherAgent(BaseAgent):
    name = "researcher"

    def _handle(self, message: AgentMessage) -> AgentMessage:
        return message


class AnalystAgent(BaseAgent):
    name = "analyst"

    def _handle(self, message: AgentMessage) -> AgentMessage:
        return message


class DisabledAgent(BaseAgent):
    name = "disabled"

    def _handle(self, message: AgentMessage) -> AgentMessage:
        return message


class MismatchedAgent(BaseAgent):
    name = "different_name"

    def _handle(self, message: AgentMessage) -> AgentMessage:
        return message


def registration(
    name: str,
    agent_class: type = ResearcherAgent,
    *,
    capabilities: frozenset[str] = frozenset({"market_research"}),
    allowed_risk_levels: frozenset[RiskLevel] = frozenset(
        {RiskLevel.LOW, RiskLevel.MEDIUM}
    ),
    enabled: bool = True,
) -> AgentRegistration:
    return AgentRegistration(
        name=name,
        agent_class=agent_class,
        capabilities=capabilities,
        allowed_risk_levels=allowed_risk_levels,
        enabled=enabled,
    )


class AgentRegistryTests(unittest.TestCase):
    def test_register_and_get_registration(self):
        registry = AgentRegistry()
        item = registration("researcher")

        registry.register(item)

        self.assertIs(registry.get("researcher"), item)

    def test_duplicate_name_is_rejected(self):
        registry = AgentRegistry()
        registry.register(registration("researcher"))

        with self.assertRaisesRegex(
            ValueError,
            "agent already registered: researcher",
        ):
            registry.register(registration("researcher"))

    def test_unknown_get_and_create_raise_key_error(self):
        registry = AgentRegistry()

        with self.assertRaises(KeyError) as get_error:
            registry.get("missing")
        self.assertEqual(get_error.exception.args, ("missing",))

        with self.assertRaises(KeyError) as create_error:
            registry.create("missing")
        self.assertEqual(create_error.exception.args, ("missing",))

    def test_registration_requires_base_agent_subclass(self):
        registry = AgentRegistry()
        item = registration("invalid", object)

        with self.assertRaises(TypeError):
            registry.register(item)

    def test_disabled_registration_is_excluded_from_candidates_and_capabilities(self):
        registry = AgentRegistry()
        registry.register(
            registration(
                "disabled",
                DisabledAgent,
                capabilities=frozenset({"disabled_capability"}),
                enabled=False,
            )
        )
        registry.register(registration("researcher"))

        self.assertEqual(
            registry.enabled_capabilities(),
            frozenset({"market_research"}),
        )
        self.assertEqual(
            registry.candidates(
                frozenset({"disabled_capability"}),
                RiskLevel.LOW,
            ),
            (),
        )

    def test_candidates_require_all_capabilities(self):
        registry = AgentRegistry()
        registry.register(
            registration(
                "analyst",
                AnalystAgent,
                capabilities=frozenset({"market_research", "concept_analysis"}),
            )
        )
        registry.register(registration("researcher"))

        candidates = registry.candidates(
            frozenset({"market_research", "concept_analysis"}),
            RiskLevel.LOW,
        )

        self.assertEqual([item.name for item in candidates], ["analyst"])

    def test_candidates_require_allowed_risk_level(self):
        registry = AgentRegistry()
        registry.register(
            registration(
                "researcher",
                allowed_risk_levels=frozenset({RiskLevel.LOW}),
            )
        )

        self.assertEqual(
            registry.candidates(
                frozenset({"market_research"}),
                RiskLevel.HIGH,
            ),
            (),
        )

    def test_candidates_are_sorted_by_registration_name(self):
        registry = AgentRegistry()
        registry.register(registration("zeta", ResearcherAgent))
        registry.register(registration("alpha", AnalystAgent))

        candidates = registry.candidates(
            frozenset({"market_research"}),
            RiskLevel.LOW,
        )

        self.assertEqual([item.name for item in candidates], ["alpha", "zeta"])

    def test_create_returns_registered_base_agent_instance(self):
        registry = AgentRegistry()
        registry.register(registration("researcher"))

        instance = registry.create("researcher")

        self.assertIsInstance(instance, BaseAgent)
        self.assertIsInstance(instance, ResearcherAgent)
        self.assertEqual(instance.name, "researcher")

    def test_create_rejects_instance_name_mismatch(self):
        registry = AgentRegistry()
        registry.register(registration("expected_name", MismatchedAgent))

        with self.assertRaises(ValueError):
            registry.create("expected_name")


if __name__ == "__main__":
    unittest.main()
