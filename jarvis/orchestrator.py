from __future__ import annotations

from typing import Any

from core.contracts import (
    AgentMessage,
    MessageKind,
    Priority,
    RiskLevel,
    TaskStatus,
)
from core.message_bus import MessageBus
from jarvis.approvals import ApprovalService
from jarvis.models import (
    ApprovalDecision,
    ApprovalDisposition,
    ExecutionPlan,
    JarvisTask,
    OrchestratorResult,
    OrchestratorState,
)
from jarvis.planner import JarvisPlanner, PlanValidationError
from jarvis.registry import AgentRegistry
from jarvis.router import JarvisRouter, NoRouteError
from jarvis.task_manager import TaskManager


_PRIORITY_RANK = {
    Priority.LOW: 0,
    Priority.NORMAL: 1,
    Priority.HIGH: 2,
    Priority.CRITICAL: 3,
}

_RISK_RANK = {
    RiskLevel.LOW: 0,
    RiskLevel.MEDIUM: 1,
    RiskLevel.HIGH: 2,
    RiskLevel.CRITICAL: 3,
}


class JarvisOrchestrator:
    def __init__(
        self,
        *,
        planner: JarvisPlanner,
        registry: AgentRegistry,
        router: JarvisRouter,
        task_manager: TaskManager,
        approvals: ApprovalService,
        bus: MessageBus,
    ) -> None:
        self._planner = planner
        self._registry = registry
        self._router = router
        self._task_manager = task_manager
        self._approvals = approvals
        self._bus = bus
        self._state = OrchestratorState.IDLE
        self._active_plan: ExecutionPlan | None = None
        self._preapproved_task_ids: set[str] = set()

    @property
    def state(self) -> OrchestratorState:
        return self._state

    @property
    def active_plan(self) -> ExecutionPlan | None:
        return self._active_plan

    def start(self, founder_goal: str) -> OrchestratorResult:
        if self._state != OrchestratorState.IDLE:
            raise RuntimeError("orchestrator can start only from IDLE")

        self._state = OrchestratorState.PLANNING
        try:
            plan = self._planner.create_plan(founder_goal, self._registry)
            self._task_manager.load_plan(plan)
        except PlanValidationError as exc:
            self._state = OrchestratorState.FAILED
            return self._result(
                message=str(exc) or "Plan validation failed",
                error_code=exc.code,
            )
        except (TypeError, ValueError) as exc:
            self._state = OrchestratorState.FAILED
            return self._result(
                message=str(exc) or "Plan validation failed",
                error_code="PLAN_INVALID",
            )
        except Exception as exc:
            self._state = OrchestratorState.FAILED
            return self._result(
                message=str(exc) or "Planner execution failed",
                error_code="PLANNER_FAILED",
            )

        self._active_plan = plan
        self._state = OrchestratorState.EXECUTING
        return self._run_until_blocked()

    def decide(
        self,
        decision: ApprovalDecision,
        *,
        explicit_confirmation: bool = False,
        change_context: dict[str, Any] | None = None,
    ) -> OrchestratorResult:
        if self._state != OrchestratorState.WAITING_APPROVAL:
            raise RuntimeError("orchestrator is not waiting for approval")
        if not isinstance(decision, ApprovalDecision):
            raise TypeError("decision must be an ApprovalDecision")

        pending = self._approvals.pending
        if pending is None:
            raise RuntimeError("no active pending approval")

        task = self._task_manager.get(pending.task_id)

        if decision == ApprovalDecision.APPROVE:
            self._approvals.decide(
                decision,
                explicit_confirmation=explicit_confirmation,
            )
            self._task_manager.approve(task.id)
            if pending.stage == "pre_execution":
                self._preapproved_task_ids.add(task.id)
            self._state = OrchestratorState.EXECUTING
            return self._run_until_blocked()

        if decision == ApprovalDecision.REJECT:
            self._task_manager.reject(task.id, "Founder rejected approval")
            self._approvals.decide(decision)
            self._state = OrchestratorState.FAILED
            return self._result(
                message=f"Founder rejected task {task.id}",
                error_code="APPROVAL_REJECTED",
            )

        context = {} if change_context is None else dict(change_context)
        self._approvals.decide(
            ApprovalDecision.CHANGE,
            change_context=context,
        )
        self._state = OrchestratorState.WAITING_APPROVAL
        return self._result(
            message=f"Founder requested changes for task {task.id}",
            pending_task_id=task.id,
            change_context=context,
        )

    def _run_until_blocked(self) -> OrchestratorResult:
        while True:
            if self._task_manager.is_complete():
                self._state = OrchestratorState.COMPLETED
                return self._result(message="Execution plan completed")

            if self._task_manager.has_failed():
                self._state = OrchestratorState.FAILED
                return self._result(
                    message="Execution plan failed",
                    error_code="TASK_FAILED",
                )

            ready = self._task_manager.ready_tasks()
            if not ready:
                self._state = OrchestratorState.FAILED
                return self._result(
                    message="Execution plan has no runnable tasks",
                    error_code="NO_READY_TASK",
                )

            task = min(
                ready,
                key=lambda item: (
                    -_PRIORITY_RANK[item.priority],
                    item.created_at,
                    item.id,
                ),
            )

            evaluation = self._approvals.evaluate(
                task.operation,
                task.risk_level,
            )
            preapproved = task.id in self._preapproved_task_ids
            if (
                evaluation.disposition == ApprovalDisposition.WAIT
                and not preapproved
            ):
                self._task_manager.wait_for_approval(task.id)
                self._approvals.begin(
                    task.id,
                    "pre_execution",
                    evaluation,
                )
                self._state = OrchestratorState.WAITING_APPROVAL
                return self._result(
                    message=f"Founder approval required for task {task.id}",
                    pending_task_id=task.id,
                )

            self._preapproved_task_ids.discard(task.id)

            try:
                registration = self._router.route(
                    task,
                    evaluation.effective_risk,
                )
            except NoRouteError:
                self._task_manager.fail(task.id, "no valid agent route")
                self._state = OrchestratorState.FAILED
                return self._result(
                    message=f"No valid route for task {task.id}",
                    error_code="NO_ROUTE",
                )

            agent = self._registry.create(registration.name)
            self._task_manager.start(task.id, registration.name)

            task_message = AgentMessage(
                sender="jarvis",
                recipient=agent.name,
                kind=MessageKind.TASK,
                objective=task.objective,
                payload={
                    "task_id": task.id,
                    "input_data": dict(task.input_data),
                },
                priority=task.priority,
                risk_level=evaluation.effective_risk,
                requires_approval=task.requires_approval,
            )
            self._bus.publish(task_message)
            incoming = self._bus.receive(agent.name)
            if incoming is None:
                return self._fail_running_task(
                    task,
                    "agent task message could not be delivered",
                    error_code="AGENT_PROTOCOL_ERROR",
                )

            try:
                agent_result = agent.handle(incoming)
            except Exception as exc:
                return self._fail_running_task(
                    task,
                    f"agent execution failed: {exc}",
                    error_code="AGENT_FAILED",
                )

            self._bus.publish(agent_result)
            collected_result = self._bus.receive("jarvis")
            if collected_result is None:
                return self._fail_running_task(
                    task,
                    "agent result must be addressed to jarvis",
                    error_code="AGENT_PROTOCOL_ERROR",
                )
            agent_result = collected_result

            if agent_result.status == TaskStatus.FAILED:
                detail = agent_result.payload.get("error", "agent reported failure")
                if not isinstance(detail, str) or not detail.strip():
                    detail = "agent reported failure"
                return self._fail_running_task(
                    task,
                    detail,
                    error_code="AGENT_FAILED",
                )

            if agent_result.recipient != "jarvis":
                return self._fail_running_task(
                    task,
                    "agent result must be addressed to jarvis",
                    error_code="AGENT_PROTOCOL_ERROR",
                )

            if agent_result.status not in {
                TaskStatus.COMPLETED,
                TaskStatus.WAITING_APPROVAL,
            }:
                return self._fail_running_task(
                    task,
                    f"invalid agent result state: {agent_result.status.value}",
                    error_code="AGENT_PROTOCOL_ERROR",
                )

            result_payload = dict(agent_result.payload)
            if task.requires_approval or agent_result.requires_approval:
                suggested_risk = max(
                    task.risk_level,
                    agent_result.risk_level,
                    key=_RISK_RANK.__getitem__,
                )
                post_evaluation = self._approvals.evaluate(
                    task.operation,
                    suggested_risk,
                )
                self._task_manager.wait_for_approval(task.id, result_payload)
                self._approvals.begin(
                    task.id,
                    "post_result",
                    post_evaluation,
                    result_ready=True,
                )
                self._state = OrchestratorState.WAITING_APPROVAL
                return self._result(
                    message=f"Founder approval required for result of task {task.id}",
                    pending_task_id=task.id,
                )

            self._task_manager.complete(task.id, result_payload)

    def _fail_running_task(
        self,
        task: JarvisTask,
        detail: str,
        *,
        error_code: str,
    ) -> OrchestratorResult:
        self._task_manager.fail(task.id, detail)
        self._state = OrchestratorState.FAILED
        return self._result(
            message=detail,
            error_code=error_code,
        )

    def _result(
        self,
        *,
        message: str,
        pending_task_id: str | None = None,
        error_code: str | None = None,
        change_context: dict[str, Any] | None = None,
    ) -> OrchestratorResult:
        goal_id = (
            self._active_plan.goal_id
            if self._active_plan is not None
            else "unplanned"
        )
        return OrchestratorResult(
            state=self._state,
            goal_id=goal_id,
            message=message,
            pending_task_id=pending_task_id,
            error_code=error_code,
            change_context={} if change_context is None else dict(change_context),
        )
