from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from core.contracts import Priority, RiskLevel
from core.ollama_client import chat
from jarvis.models import ExecutionPlan, JarvisTask
from jarvis.registry import AgentRegistry


class PlanValidationError(ValueError):
    code = "PLAN_INVALID"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.code = "PLAN_INVALID"


_SYSTEM_PROMPT = """You are the Jarvis planning component.
Return JSON only. Do not use markdown or explanatory text.
Create a non-empty execution plan using only the enabled capabilities supplied by Jarvis.
Each task must contain key, title, objective, required_capabilities, dependencies,
priority, risk_level, and requires_approval. operation may be null.
Dependency values must reference task keys from the same plan.
"""


def _invalid(message: str) -> PlanValidationError:
    return PlanValidationError(message)


def _require_non_blank_string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _invalid(f"{field_name} must be a non-blank string")
    return value


def _parse_enum(value: object, enum_type: type, field_name: str):
    if not isinstance(value, str):
        raise _invalid(f"{field_name} must be a string")
    try:
        return enum_type(value)
    except ValueError as exc:
        raise _invalid(f"invalid {field_name}: {value}") from exc


class JarvisPlanner:
    def create_plan(
        self,
        founder_goal: str,
        registry: AgentRegistry,
    ) -> ExecutionPlan:
        goal = _require_non_blank_string(founder_goal, "founder_goal")
        if not isinstance(registry, AgentRegistry):
            raise TypeError("registry must be an AgentRegistry")

        enabled_capabilities = registry.enabled_capabilities()
        capability_list = sorted(enabled_capabilities)
        response = chat(
            [
                {
                    "role": "system",
                    "content": (
                        f"{_SYSTEM_PROMPT}\n"
                        f"Enabled capabilities: {json.dumps(capability_list)}"
                    ),
                },
                {"role": "user", "content": goal},
            ]
        )

        if not isinstance(response, str):
            raise _invalid("planner response must be a JSON string")
        try:
            payload = json.loads(response)
        except (json.JSONDecodeError, TypeError) as exc:
            raise _invalid("planner response is not valid JSON") from exc

        if not isinstance(payload, dict):
            raise _invalid("planner response must be a JSON object")

        summary = _require_non_blank_string(payload.get("summary"), "summary")
        raw_tasks = payload.get("tasks")
        if not isinstance(raw_tasks, list) or not raw_tasks:
            raise _invalid("tasks must be a non-empty list")

        goal_id = str(uuid4())
        tasks_by_key: dict[str, JarvisTask] = {}
        dependency_keys: dict[str, tuple[str, ...]] = {}
        ordered_tasks: list[JarvisTask] = []

        for index, raw_task in enumerate(raw_tasks):
            if not isinstance(raw_task, dict):
                raise _invalid(f"tasks[{index}] must be an object")

            key = _require_non_blank_string(raw_task.get("key"), "task key")
            if key in tasks_by_key:
                raise _invalid(f"duplicate task key: {key}")

            title = _require_non_blank_string(raw_task.get("title"), "task title")
            objective = _require_non_blank_string(
                raw_task.get("objective"),
                "task objective",
            )

            raw_capabilities = raw_task.get("required_capabilities")
            if not isinstance(raw_capabilities, list) or not raw_capabilities:
                raise _invalid("required_capabilities must be a non-empty list")
            capabilities: list[str] = []
            for capability in raw_capabilities:
                normalized = _require_non_blank_string(
                    capability,
                    "required capability",
                )
                if normalized not in enabled_capabilities:
                    raise _invalid(f"unknown capability: {normalized}")
                capabilities.append(normalized)

            raw_dependencies = raw_task.get("dependencies", [])
            if not isinstance(raw_dependencies, list):
                raise _invalid("dependencies must be a list")
            dependencies: list[str] = []
            for dependency in raw_dependencies:
                dependency_key = _require_non_blank_string(
                    dependency,
                    "dependency key",
                )
                if dependency_key == key:
                    raise _invalid(f"task cannot depend on itself: {key}")
                dependencies.append(dependency_key)

            operation = raw_task.get("operation")
            if operation is not None:
                operation = _require_non_blank_string(operation, "operation")

            priority = _parse_enum(
                raw_task.get("priority", Priority.NORMAL.value),
                Priority,
                "priority",
            )
            risk_level = _parse_enum(
                raw_task.get("risk_level", RiskLevel.LOW.value),
                RiskLevel,
                "risk_level",
            )

            requires_approval = raw_task.get("requires_approval", False)
            if not isinstance(requires_approval, bool):
                raise _invalid("requires_approval must be a boolean")

            try:
                task = JarvisTask(
                    plan_key=key,
                    goal_id=goal_id,
                    title=title,
                    objective=objective,
                    operation=operation,
                    required_capabilities=tuple(capabilities),
                    dependencies=(),
                    priority=priority,
                    risk_level=risk_level,
                    requires_approval=requires_approval,
                )
            except (TypeError, ValueError) as exc:
                raise _invalid(f"invalid task {key}: {exc}") from exc

            tasks_by_key[key] = task
            dependency_keys[key] = tuple(dependencies)
            ordered_tasks.append(task)

        for key, task in tasks_by_key.items():
            resolved_dependencies: list[str] = []
            for dependency_key in dependency_keys[key]:
                dependency_task = tasks_by_key.get(dependency_key)
                if dependency_task is None:
                    raise _invalid(
                        f"unknown dependency key {dependency_key} for task {key}"
                    )
                resolved_dependencies.append(dependency_task.id)
            task.dependencies = tuple(resolved_dependencies)

        self._validate_acyclic(ordered_tasks)

        try:
            return ExecutionPlan(
                goal_id=goal_id,
                goal=goal,
                summary=summary,
                tasks=tuple(ordered_tasks),
            )
        except (TypeError, ValueError) as exc:
            raise _invalid(f"invalid execution plan: {exc}") from exc

    @staticmethod
    def _validate_acyclic(tasks: list[JarvisTask]) -> None:
        tasks_by_id = {task.id: task for task in tasks}
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(task_id: str) -> None:
            if task_id in visited:
                return
            if task_id in visiting:
                raise _invalid("circular dependency detected")

            visiting.add(task_id)
            task = tasks_by_id[task_id]
            for dependency_id in task.dependencies:
                visit(dependency_id)
            visiting.remove(task_id)
            visited.add(task_id)

        for task in tasks:
            visit(task.id)
