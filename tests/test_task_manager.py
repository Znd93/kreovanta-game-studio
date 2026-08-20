from __future__ import annotations

import unittest
from datetime import timezone

from core.contracts import TaskStatus
from jarvis.models import ExecutionPlan, JarvisTask
from jarvis.task_manager import TaskManager


def make_task(
    task_id: str,
    *,
    dependencies: tuple[str, ...] = (),
    plan_key: str | None = None,
) -> JarvisTask:
    return JarvisTask(
        id=task_id,
        plan_key=plan_key or task_id,
        goal_id="goal-1",
        title=f"Task {task_id}",
        objective=f"Do {task_id}",
        required_capabilities=("work",),
        dependencies=dependencies,
    )


def make_plan(*tasks: JarvisTask) -> ExecutionPlan:
    return ExecutionPlan(
        goal_id="goal-1",
        goal="Execute work",
        summary="Task manager test plan",
        tasks=tuple(tasks),
    )


class TaskManagerTests(unittest.TestCase):
    def test_root_task_becomes_ready_after_load_plan(self) -> None:
        task = make_task("a")
        manager = TaskManager()

        manager.load_plan(make_plan(task))

        self.assertEqual(task.status, TaskStatus.READY)
        self.assertIs(manager.get("a"), task)
        self.assertEqual(manager.ready_tasks(), (task,))

    def test_dependent_task_starts_blocked(self) -> None:
        root = make_task("a")
        dependent = make_task("b", dependencies=(root.id,))
        manager = TaskManager()

        manager.load_plan(make_plan(root, dependent))

        self.assertEqual(root.status, TaskStatus.READY)
        self.assertEqual(dependent.status, TaskStatus.BLOCKED)
        self.assertEqual(manager.ready_tasks(), (root,))

    def test_all_dependencies_must_complete_before_ready(self) -> None:
        first = make_task("a")
        second = make_task("b")
        dependent = make_task("c", dependencies=(first.id, second.id))
        manager = TaskManager()
        manager.load_plan(make_plan(first, second, dependent))

        manager.start(first.id, "worker-a")
        manager.complete(first.id, {"ok": True})

        self.assertEqual(dependent.status, TaskStatus.BLOCKED)

        manager.start(second.id, "worker-b")
        manager.complete(second.id, {"ok": True})

        self.assertEqual(dependent.status, TaskStatus.READY)

    def test_completing_prerequisite_unlocks_dependent(self) -> None:
        root = make_task("a")
        dependent = make_task("b", dependencies=(root.id,))
        manager = TaskManager()
        manager.load_plan(make_plan(root, dependent))
        manager.start(root.id, "worker")

        manager.complete(root.id, {"value": 1})

        self.assertEqual(root.status, TaskStatus.COMPLETED)
        self.assertEqual(dependent.status, TaskStatus.READY)

    def test_start_only_accepts_ready(self) -> None:
        root = make_task("a")
        dependent = make_task("b", dependencies=(root.id,))
        manager = TaskManager()
        manager.load_plan(make_plan(root, dependent))

        with self.assertRaises(RuntimeError):
            manager.start(dependent.id, "worker")

    def test_start_records_assigned_agent_and_timezone_aware_utc_timestamp(self) -> None:
        task = make_task("a")
        manager = TaskManager()
        manager.load_plan(make_plan(task))

        started = manager.start(task.id, "researcher")

        self.assertEqual(started.status, TaskStatus.RUNNING)
        self.assertEqual(started.assigned_agent, "researcher")
        self.assertIsNotNone(started.started_at)
        assert started.started_at is not None
        self.assertEqual(started.started_at.tzinfo, timezone.utc)
        self.assertIsNotNone(started.started_at.utcoffset())

    def test_start_rejects_blank_agent_name(self) -> None:
        task = make_task("a")
        manager = TaskManager()
        manager.load_plan(make_plan(task))

        with self.assertRaises(ValueError):
            manager.start(task.id, "   ")

    def test_complete_only_accepts_running(self) -> None:
        task = make_task("a")
        manager = TaskManager()
        manager.load_plan(make_plan(task))

        with self.assertRaises(RuntimeError):
            manager.complete(task.id, {"ok": True})

    def test_complete_records_result_and_timezone_aware_utc_timestamp(self) -> None:
        task = make_task("a")
        manager = TaskManager()
        manager.load_plan(make_plan(task))
        manager.start(task.id, "worker")

        completed = manager.complete(task.id, {"answer": 42})

        self.assertEqual(completed.status, TaskStatus.COMPLETED)
        self.assertEqual(completed.result, {"answer": 42})
        self.assertIsNotNone(completed.completed_at)
        assert completed.completed_at is not None
        self.assertEqual(completed.completed_at.tzinfo, timezone.utc)
        self.assertIsNotNone(completed.completed_at.utcoffset())

    def test_fail_marks_failed_and_has_failed(self) -> None:
        task = make_task("a")
        manager = TaskManager()
        manager.load_plan(make_plan(task))
        manager.start(task.id, "worker")

        failed = manager.fail(task.id, "boom")

        self.assertEqual(failed.status, TaskStatus.FAILED)
        self.assertEqual(failed.error, "boom")
        self.assertTrue(manager.has_failed())

    def test_fail_accepts_ready_task_for_preexecution_failure(self) -> None:
        task = make_task("a")
        manager = TaskManager()
        manager.load_plan(make_plan(task))

        failed = manager.fail(task.id, "no route")

        self.assertEqual(failed.status, TaskStatus.FAILED)

    def test_failed_dependency_keeps_downstream_blocked(self) -> None:
        root = make_task("a")
        dependent = make_task("b", dependencies=(root.id,))
        manager = TaskManager()
        manager.load_plan(make_plan(root, dependent))

        manager.fail(root.id, "no route")

        self.assertEqual(dependent.status, TaskStatus.BLOCKED)
        self.assertEqual(manager.ready_tasks(), ())

    def test_reject_marks_rejected_and_has_failed(self) -> None:
        task = make_task("a")
        manager = TaskManager()
        manager.load_plan(make_plan(task))
        manager.wait_for_approval(task.id)

        rejected = manager.reject(task.id, "Founder rejected")

        self.assertEqual(rejected.status, TaskStatus.REJECTED)
        self.assertEqual(rejected.error, "Founder rejected")
        self.assertTrue(manager.has_failed())

    def test_rejected_dependency_keeps_downstream_blocked(self) -> None:
        root = make_task("a")
        dependent = make_task("b", dependencies=(root.id,))
        manager = TaskManager()
        manager.load_plan(make_plan(root, dependent))
        manager.wait_for_approval(root.id)

        manager.reject(root.id, "No")

        self.assertEqual(dependent.status, TaskStatus.BLOCKED)

    def test_wait_for_approval_preserves_post_result_without_unlocking_dependents(self) -> None:
        root = make_task("a")
        dependent = make_task("b", dependencies=(root.id,))
        manager = TaskManager()
        manager.load_plan(make_plan(root, dependent))
        manager.start(root.id, "worker")

        waiting = manager.wait_for_approval(root.id, {"candidate": "A"})

        self.assertEqual(waiting.status, TaskStatus.WAITING_APPROVAL)
        self.assertEqual(waiting.result, {"candidate": "A"})
        self.assertEqual(dependent.status, TaskStatus.BLOCKED)
        self.assertEqual(manager.ready_tasks(), ())

    def test_approve_completes_post_result_task_and_unlocks_dependent(self) -> None:
        root = make_task("a")
        dependent = make_task("b", dependencies=(root.id,))
        manager = TaskManager()
        manager.load_plan(make_plan(root, dependent))
        manager.start(root.id, "worker")
        manager.wait_for_approval(root.id, {"candidate": "A"})

        approved = manager.approve(root.id)

        self.assertEqual(approved.status, TaskStatus.COMPLETED)
        self.assertEqual(approved.result, {"candidate": "A"})
        self.assertIsNotNone(approved.completed_at)
        self.assertEqual(dependent.status, TaskStatus.READY)

    def test_approve_preexecution_task_restores_ready_without_completion(self) -> None:
        task = make_task("a")
        manager = TaskManager()
        manager.load_plan(make_plan(task))
        manager.wait_for_approval(task.id)

        approved = manager.approve(task.id)

        self.assertEqual(approved.status, TaskStatus.READY)
        self.assertIsNone(approved.completed_at)
        self.assertEqual(manager.ready_tasks(), (task,))

    def test_reject_only_accepts_waiting_approval(self) -> None:
        task = make_task("a")
        manager = TaskManager()
        manager.load_plan(make_plan(task))

        with self.assertRaises(RuntimeError):
            manager.reject(task.id, "No")

    def test_is_complete_true_only_when_every_task_completed(self) -> None:
        first = make_task("a")
        second = make_task("b", dependencies=(first.id,))
        manager = TaskManager()
        manager.load_plan(make_plan(first, second))

        self.assertFalse(manager.is_complete())
        manager.start(first.id, "worker")
        manager.complete(first.id, {})
        self.assertFalse(manager.is_complete())
        manager.start(second.id, "worker")
        manager.complete(second.id, {})
        self.assertTrue(manager.is_complete())
        self.assertFalse(manager.has_failed())

    def test_missing_dependency_id_raises_value_error(self) -> None:
        task = make_task("a", dependencies=("missing",))
        manager = TaskManager()

        with self.assertRaisesRegex(ValueError, "missing dependency"):
            manager.load_plan(make_plan(task))

    def test_duplicate_task_id_raises_value_error(self) -> None:
        first = make_task("same", plan_key="first")
        second = make_task("same", plan_key="second")
        manager = TaskManager()

        with self.assertRaisesRegex(ValueError, "duplicate task id"):
            manager.load_plan(make_plan(first, second))

    def test_second_active_plan_load_is_rejected(self) -> None:
        manager = TaskManager()
        manager.load_plan(make_plan(make_task("a")))

        with self.assertRaises(RuntimeError):
            manager.load_plan(make_plan(make_task("b")))

    def test_get_unknown_task_raises_key_error(self) -> None:
        manager = TaskManager()
        manager.load_plan(make_plan(make_task("a")))

        with self.assertRaises(KeyError):
            manager.get("missing")


if __name__ == "__main__":
    unittest.main()
