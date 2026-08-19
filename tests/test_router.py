import unittest

from agents.base_agent import BaseAgent
from core.contracts import AgentMessage, RiskLevel
from jarvis.models import AgentRegistration, JarvisTask
from jarvis.registry import AgentRegistry
from jarvis.router import JarvisRouter, NoRouteError


class TestAgent(BaseAgent):
    name = "test_agent"

    def _handle(self, message: AgentMessage) -> AgentMessage:
        return message


def registration(
    name: str,
    capabilities: frozenset[str],
    *,
    allowed_risk_levels: frozenset[RiskLevel] = frozenset(
        {RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL}
    ),
    enabled: bool = True,
) -> AgentRegistration:
    return AgentRegistration(
        name=name,
        agent_class=TestAgent,
        capabilities=capabilities,
        allowed_risk_levels=allowed_risk_levels,
        enabled=enabled,
    )


def task(*capabilities: str) -> JarvisTask:
    return JarvisTask(
        plan_key="route_test",
        goal_id="goal-1",
        title="Route test",
        objective="Choose the best specialist",
        required_capabilities=capabilities,
    )


class JarvisRouterTests(unittest.TestCase):
    def test_exact_capability_match_wins_over_superset(self):
        registry = AgentRegistry()
        registry.register(
            registration("analyst", frozenset({"market_research", "concept_analysis"}))
        )
        registry.register(registration("researcher", frozenset({"market_research"})))

        selected = JarvisRouter(registry).route(task("market_research"), RiskLevel.LOW)

        self.assertEqual(selected.name, "researcher")

    def test_smallest_capability_superset_wins_when_no_exact_match_exists(self):
        registry = AgentRegistry()
        registry.register(
            registration(
                "generalist",
                frozenset({"market_research", "concept_analysis", "game_design"}),
            )
        )
        registry.register(
            registration("specialist", frozenset({"market_research", "concept_analysis"}))
        )

        selected = JarvisRouter(registry).route(task("market_research"), RiskLevel.LOW)

        self.assertEqual(selected.name, "specialist")

    def test_alphabetical_name_breaks_equal_superset_ties(self):
        registry = AgentRegistry()
        registry.register(
            registration("zeta", frozenset({"market_research", "concept_analysis"}))
        )
        registry.register(
            registration("alpha", frozenset({"market_research", "game_design"}))
        )

        selected = JarvisRouter(registry).route(task("market_research"), RiskLevel.LOW)

        self.assertEqual(selected.name, "alpha")

    def test_disabled_agent_is_never_selected(self):
        registry = AgentRegistry()
        registry.register(
            registration(
                "disabled_exact",
                frozenset({"market_research"}),
                enabled=False,
            )
        )
        registry.register(
            registration("enabled_superset", frozenset({"market_research", "analysis"}))
        )

        selected = JarvisRouter(registry).route(task("market_research"), RiskLevel.LOW)

        self.assertEqual(selected.name, "enabled_superset")

    def test_risk_disallowed_agent_is_never_selected(self):
        registry = AgentRegistry()
        registry.register(
            registration(
                "low_only_exact",
                frozenset({"market_research"}),
                allowed_risk_levels=frozenset({RiskLevel.LOW}),
            )
        )
        registry.register(
            registration(
                "high_allowed_superset",
                frozenset({"market_research", "analysis"}),
                allowed_risk_levels=frozenset({RiskLevel.HIGH}),
            )
        )

        selected = JarvisRouter(registry).route(task("market_research"), RiskLevel.HIGH)

        self.assertEqual(selected.name, "high_allowed_superset")

    def test_no_route_error_exposes_task_context(self):
        requested = task("market_research", "concept_analysis")
        error = NoRouteError(requested.id, requested.required_capabilities)

        self.assertTrue(hasattr(error, "task_id"))
        self.assertTrue(hasattr(error, "required_capabilities"))
        self.assertEqual(error.task_id, requested.id)
        self.assertEqual(error.required_capabilities, requested.required_capabilities)
        self.assertEqual(error.args, (requested.id, requested.required_capabilities))

    def test_no_full_match_raises_no_route_error(self):
        registry = AgentRegistry()
        registry.register(registration("artist", frozenset({"visual_art"})))
        requested = task("market_research")

        with self.assertRaises(NoRouteError) as error:
            JarvisRouter(registry).route(requested, RiskLevel.LOW)

        self.assertEqual(error.exception.args, (requested.id, requested.required_capabilities))

    def test_partial_capability_match_is_never_selected(self):
        registry = AgentRegistry()
        registry.register(registration("researcher", frozenset({"market_research"})))
        requested = task("market_research", "concept_analysis")

        with self.assertRaises(NoRouteError):
            JarvisRouter(registry).route(requested, RiskLevel.LOW)


if __name__ == "__main__":
    unittest.main()
