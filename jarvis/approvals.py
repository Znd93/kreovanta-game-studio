from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from core.contracts import RiskLevel
from jarvis.models import (
    ApprovalDecision,
    ApprovalDisposition,
    ApprovalEvaluation,
    PendingApproval,
)


_POLICY_MINIMUMS = {
    "publish": RiskLevel.HIGH,
    "delete_important_data": RiskLevel.HIGH,
    "credentials": RiskLevel.CRITICAL,
    "security_policy_change": RiskLevel.CRITICAL,
    "locked_core_change": RiskLevel.CRITICAL,
    "paid_action": RiskLevel.CRITICAL,
}

_RISK_RANK = {
    RiskLevel.LOW: 0,
    RiskLevel.MEDIUM: 1,
    RiskLevel.HIGH: 2,
    RiskLevel.CRITICAL: 3,
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ApprovalService:
    def __init__(self) -> None:
        self._pending: PendingApproval | None = None
        self._pending_evaluation: ApprovalEvaluation | None = None
        self._audit: list[dict[str, Any]] = []

    @property
    def pending(self) -> PendingApproval | None:
        return self._pending

    def evaluate(
        self,
        operation: str | None,
        suggested_risk: RiskLevel,
    ) -> ApprovalEvaluation:
        policy_risk = _POLICY_MINIMUMS.get(operation, RiskLevel.LOW)
        effective_risk = max(
            suggested_risk,
            policy_risk,
            key=_RISK_RANK.__getitem__,
        )

        if effective_risk == RiskLevel.LOW:
            disposition = ApprovalDisposition.CONTINUE
        elif effective_risk == RiskLevel.MEDIUM:
            disposition = ApprovalDisposition.CONTINUE_AUDIT
        else:
            disposition = ApprovalDisposition.WAIT

        evaluation = ApprovalEvaluation(
            suggested_risk=suggested_risk,
            policy_risk=policy_risk,
            effective_risk=effective_risk,
            disposition=disposition,
            requires_explicit_confirmation=(effective_risk == RiskLevel.CRITICAL),
        )

        if disposition == ApprovalDisposition.CONTINUE_AUDIT:
            self._audit.append(
                {
                    "task_id": None,
                    "stage": None,
                    "suggested_risk": suggested_risk,
                    "policy_risk": policy_risk,
                    "effective_risk": effective_risk,
                    "action": "evaluate",
                    "disposition": disposition,
                    "decision": None,
                    "timestamp": _utc_now(),
                }
            )

        return evaluation

    def begin(
        self,
        task_id: str,
        stage: str,
        evaluation: ApprovalEvaluation,
        result_ready: bool = False,
    ) -> PendingApproval:
        if self._pending is not None:
            raise RuntimeError("a pending approval already exists")

        pending = PendingApproval(
            task_id=task_id,
            stage=stage,
            effective_risk=evaluation.effective_risk,
            requires_explicit_confirmation=evaluation.requires_explicit_confirmation,
            result_ready=result_ready,
        )
        self._pending = pending
        self._pending_evaluation = evaluation
        self._audit.append(
            {
                "task_id": pending.task_id,
                "stage": pending.stage,
                "suggested_risk": evaluation.suggested_risk,
                "policy_risk": evaluation.policy_risk,
                "effective_risk": evaluation.effective_risk,
                "action": "begin",
                "disposition": evaluation.disposition,
                "decision": None,
                "timestamp": _utc_now(),
            }
        )
        return pending

    def decide(
        self,
        decision: ApprovalDecision,
        *,
        explicit_confirmation: bool = False,
        change_context: dict[str, Any] | None = None,
    ) -> PendingApproval | None:
        pending = self._pending
        if pending is None:
            raise RuntimeError("no pending approval")

        evaluation = self._pending_evaluation
        if evaluation is None:
            raise RuntimeError("pending approval evaluation is missing")

        if (
            decision == ApprovalDecision.APPROVE
            and pending.requires_explicit_confirmation
            and not explicit_confirmation
        ):
            raise PermissionError("explicit confirmation required for critical approval")

        entry: dict[str, Any] = {
            "task_id": pending.task_id,
            "stage": pending.stage,
            "suggested_risk": evaluation.suggested_risk,
            "policy_risk": evaluation.policy_risk,
            "effective_risk": evaluation.effective_risk,
            "action": "decision",
            "disposition": evaluation.disposition,
            "decision": decision,
            "timestamp": _utc_now(),
        }
        if decision == ApprovalDecision.CHANGE:
            entry["change_context"] = (
                None if change_context is None else dict(change_context)
            )
        self._audit.append(entry)

        self._pending = None
        self._pending_evaluation = None
        return pending

    def audit_log(self) -> tuple[dict[str, Any], ...]:
        return tuple(entry.copy() for entry in self._audit)
