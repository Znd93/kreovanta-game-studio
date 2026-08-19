from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from core.contracts import TaskStatus
from jarvis.models import ExecutionPlan, JarvisTask


_TERMINAL_FAILURE_STATES = frozenset({TaskStatus.FAILED, TaskStatus.REJECTED})


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _require_non_blank(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if not value.strip():
        raise ValueError(f"{field_name} cannot be blank")
    return value


class TaskManager:
    def __init__(self) -> None:
        self._plan: ExecutionPlan | None = None
        self._tasks: dict[str, JarvisTask] = {}
        self._post_result_approvals: set[str] = set()

    def load_plan(self, plan: ExecutionPlan) -> None:
        if not isinstance(plan, ExecutionPlan):
            raise TypeError("plan must be an ExecutionPlan")
        if self._plan is not None and not self.is_complete() and not self.has_failed():
            raise RuntimeError("an active plan is already loaded")

        tasks: dict[str, JarvisTask] = {}
        for task in plan.tasks:
            if task.id in tasks:
                raise ValueError(f"duplicate task id: {task.id}")
            tasks[task.id] = task

        for task in plan.tasks:
            for dependency_id in task.dependencies:
                if dependency_id not in tasks:
                    raise ValueError(
                        f"missing dependency: {dependency_id} for task {task.id}"
                    )

        for task in plan.tasks:
            task.status = (
                TaskStatus.READY if not task.dependencies else TaskStatus.BLOCKED
            )

        self._plan = plan
        self._tasks = tasks
        self._post_result_approvals.clear()

    def get(self, task_id: str) -> JarvisTask:
        try:
            return self._tasks[task_id]
        except KeyError:
            raise KeyError(task_id) from None

    def ready_tasks(self) -> tuple[JarvisTask, ...]:
        return tuple(
            task for task in self._tasks.values() if task.status == TaskStatus.READY
        )

    def start(self, task_id: str, agent_name: str) -> JarvisTask:
        task = self.get(task_id)
        _require_non_blank(agent_name, "agent_name")
        self._require_status(task, TaskStatus.READY, operation="start")

        task.status = TaskStatus.RUNNING
        task.assigned_agent = agent_name
        task.started_at = _utc_now()
        return task

    def complete(self, task_id: str, result: dict[str, Any]) -> JarvisTask:
        task = self.get(task_id)
        if not isinstance(result, dict):
            raise TypeError("result must be a dict")
        self._require_status(task, TaskStatus.RUNNING, operation="complete")

        task.result = dict(result)
        task.error = None
        task.status = TaskStatus.COMPLETED
        task.completed_at = _utc_now()
        self._post_result_approvals.discard(task.id)
        self._refresh_blocked_tasks()
        return task

    def fail(self, task_id: str, error: str) -> JarvisTask:
        task = self.get(task_id)
        _require_non_blank(error, "error")
        if task.status not in {
            TaskStatus.READY,
            TaskStatus.RUNNING,
            TaskStatus.WAITING_APPROVAL,
        }:
            raise RuntimeError(
                f"cannot fail task {task.id} from state {task.status.value}"
            )

        task.status = TaskStatus.FAILED
        task.error = error
        self._post_result_approvals.discard(task.id)
        self._refresh_blocked_tasks()
        return task

    def wait_for_approval(
        self,
        task_id: str,
        result: dict[str, Any] | None = None,
    ) -> JarvisTask:
        task = self.get(task_id)
        if result is not None and not isinstance(result, dict):
            raise TypeError("result must be a dict or None")

        if task.status == TaskStatus.READY:
            if result is not None:
                raise RuntimeError(
                    "pre-execution approval cannot include a task result"
                )
            self._post_result_approvals.discard(task.id)
        elif task.status == TaskStatus.RUNNING:
            if result is None:
                raise RuntimeError("post-result approval requires a result")
            task.result = dict(result)
            self._post_result_approvals.add(task.id)
        else:
            raise RuntimeError(
                f"cannot wait for approval from state {task.status.value}"
            )

        task.status = TaskStatus.WAITING_APPROVAL
        return task

    def approve(self, task_id: str) -> JarvisTask:
        task = self.get(task_id)
        self._require_status(
            task,
            TaskStatus.WAITING_APPROVAL,
            operation="approve",
        )

        if task.id in self._post_result_approvals:
            self._post_result_approvals.remove(task.id)
            task.status = TaskStatus.COMPLETED
            task.completed_at = _utc_now()
            self._refresh_blocked_tasks()
        else:
            task.status = TaskStatus.READY

        return task

    def reject(self, task_id: str, reason: str) -> JarvisTask:
        task = self.get(task_id)
        _require_non_blank(reason, "reason")
        self._require_status(
            task,
            TaskStatus.WAITING_APPROVAL,
            operation="reject",
        )

        task.status = TaskStatus.REJECTED
        task.error = reason
        self._post_result_approvals.discard(task.id)
        self._refresh_blocked_tasks()
        return task

    def is_complete(self) -> bool:
        return self._plan is not None and all(
            task.status == TaskStatus.COMPLETED for task in self._tasks.values()
        )

    def has_failed(self) -> bool:
        return self._plan is not None and any(
            task.status in _TERMINAL_FAILURE_STATES for task in self._tasks.values()
        )

    def _refresh_blocked_tasks(self) -> None:
        for task in self._tasks.values():
            if task.status != TaskStatus.BLOCKED:
                continue

            dependencies = tuple(self._tasks[dependency_id] for dependency_id in task.dependencies)
            if any(
                dependency.status in _TERMINAL_FAILURE_STATES
                for dependency in dependencies
            ):
                continue
            if all(
                dependency.status == TaskStatus.COMPLETED
                for dependency in dependencies
            ):
                task.status = TaskStatus.READY

    @staticmethod
    def _require_status(
        task: JarvisTask,
        expected: TaskStatus,
        *,
        operation: str,
    ) -> None:
        if task.status != expected:
            raise RuntimeError(
                f"cannot {operation} task {task.id} from state {task.status.value}"
            )
