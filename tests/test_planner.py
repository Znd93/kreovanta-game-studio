from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from agents.base_agent import BaseAgent
from core.contracts import AgentMessage, Priority, RiskLevel
from jarvis.models import AgentRegistration, ExecutionPlan
from jarvis.planner import JarvisPlanner, PlanValidationError
from jarvis.registry import AgentRegistry


class PlannerAgent(BaseAgent):
    name = "planner_test_agent"

    def _handle(self, message: AgentMessage) -> AgentMessage:
        return message


def make_registry(*capabilities: str) -> AgentRegistry:
    registry = AgentRegistry()
    registry.register(
        AgentRegistration(
            name="planner_test_agent",
            agent_class=PlannerAgent,
            capabilities=frozenset(capabilities),
            allowed_risk_levels=frozenset(RiskLevel),
        )
    )
    return registry


def plan_json(*tasks: dict, summary: str = "Plan the requested work") -> str:
    return json.dumps({"summary": summary, "tasks": list(tasks)})


def task_json(
    key: str = "research",
    *,
    title: str = "Research",
    objective: str = "Research the opportunity",
    required_capabilities: list[str] | None = None,
    dependencies: list[str] | None = None,
    operation: str | None = None,
    priority: str = "normal",
    risk_level: str = "low",
    requires_approval: bool = False,
) -> dict:
    return {
        "key": key,
        "title": title,
        "objective": objective,
        "operation": operation,
        "required_capabilities": (
            ["market_research"]
            if required_capabilities is None
            else required_capabilities
        ),
        "dependencies": [] if dependencies is None else dependencies,
        "priority": priority,
        "risk_level": risk_level,
        "requires_approval": requires_approval,
    }


class JarvisPlannerTests(unittest.TestCase):
    @patch("jarvis.planner.chat")
    def test_valid_one_task_json_returns_execution_plan(self, mock_chat):
        mock_chat.return_value = plan_json(task_json())
        registry = make_registry("market_research")

        plan = JarvisPlanner().create_plan("Find a Roblox opportunity", registry)

        self.assertIsInstance(plan, ExecutionPlan)
        self.assertEqual(plan.goal, "Find a Roblox opportunity")
        self.assertEqual(plan.summary, "Plan the requested work")
        self.assertEqual(len(plan.tasks), 1)
        task = plan.tasks[0]
        self.assertEqual(task.plan_key, "research")
        self.assertEqual(task.required_capabilities, ("market_research",))
        self.assertEqual(task.dependencies, ())
        self.assertEqual(task.priority, Priority.NORMAL)
        self.assertEqual(task.risk_level, RiskLevel.LOW)
        self.assertFalse(task.requires_approval)
        mock_chat.assert_called_once()

    @patch("jarvis.planner.chat")
    def test_dependency_keys_are_converted_to_internal_task_ids(self, mock_chat):
        mock_chat.return_value = plan_json(
            task_json(key="research"),
            task_json(
                key="concept",
                title="Concept",
                objective="Choose a concept",
                required_capabilities=["concept_analysis"],
                dependencies=["research"],
            ),
        )
        registry = make_registry("market_research", "concept_analysis")

        plan = JarvisPlanner().create_plan("Choose a game", registry)

        first, second = plan.tasks
        self.assertNotEqual(first.id, first.plan_key)
        self.assertEqual(second.dependencies, (first.id,))

    @patch("jarvis.planner.chat")
    def test_malformed_json_raises_plan_validation_error(self, mock_chat):
        mock_chat.return_value = "not-json"

        with self.assertRaises(PlanValidationError) as error:
            JarvisPlanner().create_plan(
                "Find a game",
                make_registry("market_research"),
            )

        self.assertEqual(error.exception.code, "PLAN_INVALID")

    @patch("jarvis.planner.chat")
    def test_top_level_must_be_object_with_nonempty_tasks(self, mock_chat):
        registry = make_registry("market_research")
        for payload in ("[]", json.dumps({}), json.dumps({"summary": "x", "tasks": []})):
            with self.subTest(payload=payload):
                mock_chat.return_value = payload
                with self.assertRaises(PlanValidationError):
                    JarvisPlanner().create_plan("Find a game", registry)

    @patch("jarvis.planner.chat")
    def test_summary_must_be_nonblank_string(self, mock_chat):
        registry = make_registry("market_research")
        for summary in (None, "", "   ", 123):
            with self.subTest(summary=summary):
                payload = {"tasks": [task_json()]}
                if summary is not None:
                    payload["summary"] = summary
                mock_chat.return_value = json.dumps(payload)
                with self.assertRaises(PlanValidationError):
                    JarvisPlanner().create_plan("Find a game", registry)

    @patch("jarvis.planner.chat")
    def test_missing_required_task_fields_are_rejected(self, mock_chat):
        registry = make_registry("market_research")
        for field in ("key", "title", "objective", "required_capabilities"):
            with self.subTest(field=field):
                item = task_json()
                del item[field]
                mock_chat.return_value = plan_json(item)
                with self.assertRaises(PlanValidationError):
                    JarvisPlanner().create_plan("Find a game", registry)

    @patch("jarvis.planner.chat")
    def test_duplicate_task_key_is_rejected(self, mock_chat):
        mock_chat.return_value = plan_json(task_json(), task_json())

        with self.assertRaises(PlanValidationError):
            JarvisPlanner().create_plan(
                "Find a game",
                make_registry("market_research"),
            )

    @patch("jarvis.planner.chat")
    def test_unknown_capability_is_rejected(self, mock_chat):
        mock_chat.return_value = plan_json(
            task_json(required_capabilities=["unknown_capability"])
        )

        with self.assertRaises(PlanValidationError):
            JarvisPlanner().create_plan(
                "Find a game",
                make_registry("market_research"),
            )

    @patch("jarvis.planner.chat")
    def test_missing_dependency_key_is_rejected(self, mock_chat):
        mock_chat.return_value = plan_json(
            task_json(dependencies=["missing"])
        )

        with self.assertRaises(PlanValidationError):
            JarvisPlanner().create_plan(
                "Find a game",
                make_registry("market_research"),
            )

    @patch("jarvis.planner.chat")
    def test_self_dependency_is_rejected(self, mock_chat):
        mock_chat.return_value = plan_json(
            task_json(key="research", dependencies=["research"])
        )

        with self.assertRaises(PlanValidationError):
            JarvisPlanner().create_plan(
                "Find a game",
                make_registry("market_research"),
            )

    @patch("jarvis.planner.chat")
    def test_circular_dependency_is_rejected(self, mock_chat):
        mock_chat.return_value = plan_json(
            task_json(key="a", dependencies=["b"]),
            task_json(key="b", dependencies=["a"]),
        )

        with self.assertRaises(PlanValidationError):
            JarvisPlanner().create_plan(
                "Find a game",
                make_registry("market_research"),
            )

    @patch("jarvis.planner.chat")
    def test_invalid_priority_or_risk_string_is_rejected(self, mock_chat):
        registry = make_registry("market_research")
        for field, value in (("priority", "urgent"), ("risk_level", "extreme")):
            with self.subTest(field=field):
                item = task_json()
                item[field] = value
                mock_chat.return_value = plan_json(item)
                with self.assertRaises(PlanValidationError):
                    JarvisPlanner().create_plan("Find a game", registry)

    @patch("jarvis.planner.chat")
    def test_requires_approval_must_be_boolean(self, mock_chat):
        item = task_json()
        item["requires_approval"] = "false"
        mock_chat.return_value = plan_json(item)

        with self.assertRaises(PlanValidationError):
            JarvisPlanner().create_plan(
                "Find a game",
                make_registry("market_research"),
            )

    @patch("jarvis.planner.chat")
    def test_blank_founder_goal_is_rejected_before_llm_call(self, mock_chat):
        registry = make_registry("market_research")

        for goal in ("", "   "):
            with self.subTest(goal=goal):
                with self.assertRaises(PlanValidationError):
                    JarvisPlanner().create_plan(goal, registry)
        mock_chat.assert_not_called()

    @patch("jarvis.planner.chat")
    def test_task_field_types_and_empty_capabilities_are_rejected(self, mock_chat):
        registry = make_registry("market_research")
        invalid_items = [
            task_json(key="   "),
            task_json(required_capabilities=[]),
            task_json(required_capabilities=["   "]),
            {**task_json(), "dependencies": "research"},
            {**task_json(), "operation": 123},
        ]

        for item in invalid_items:
            with self.subTest(item=item):
                mock_chat.return_value = plan_json(item)
                with self.assertRaises(PlanValidationError):
                    JarvisPlanner().create_plan("Find a game", registry)


if __name__ == "__main__":
    unittest.main()
