import unittest

from core.contracts import RiskLevel
from jarvis.approvals import ApprovalService
from jarvis.models import ApprovalDecision, ApprovalDisposition


class ApprovalServiceTests(unittest.TestCase):
    def setUp(self):
        self.service = ApprovalService()

    def test_low_risk_continues(self):
        evaluation = self.service.evaluate(None, RiskLevel.LOW)
        self.assertEqual(evaluation.policy_risk, RiskLevel.LOW)
        self.assertEqual(evaluation.effective_risk, RiskLevel.LOW)
        self.assertEqual(evaluation.disposition, ApprovalDisposition.CONTINUE)
        self.assertFalse(evaluation.requires_explicit_confirmation)

    def test_medium_risk_continues_with_audit_entry(self):
        evaluation = self.service.evaluate(None, RiskLevel.MEDIUM)
        self.assertEqual(evaluation.disposition, ApprovalDisposition.CONTINUE_AUDIT)
        log = self.service.audit_log()
        self.assertEqual(len(log), 1)
        self.assertEqual(log[0]["suggested_risk"], RiskLevel.MEDIUM)
        self.assertEqual(log[0]["effective_risk"], RiskLevel.MEDIUM)
        self.assertEqual(log[0]["disposition"], ApprovalDisposition.CONTINUE_AUDIT)
        self.assertIn("timestamp", log[0])

    def test_high_risk_waits_for_founder(self):
        evaluation = self.service.evaluate(None, RiskLevel.HIGH)
        self.assertEqual(evaluation.disposition, ApprovalDisposition.WAIT)
        self.assertFalse(evaluation.requires_explicit_confirmation)

    def test_critical_risk_waits_and_requires_explicit_confirmation(self):
        evaluation = self.service.evaluate(None, RiskLevel.CRITICAL)
        self.assertEqual(evaluation.disposition, ApprovalDisposition.WAIT)
        self.assertTrue(evaluation.requires_explicit_confirmation)

    def test_publish_policy_raises_low_to_high(self):
        evaluation = self.service.evaluate("publish", RiskLevel.LOW)
        self.assertEqual(evaluation.policy_risk, RiskLevel.HIGH)
        self.assertEqual(evaluation.effective_risk, RiskLevel.HIGH)
        self.assertEqual(evaluation.disposition, ApprovalDisposition.WAIT)

    def test_credentials_policy_raises_low_to_critical(self):
        evaluation = self.service.evaluate("credentials", RiskLevel.LOW)
        self.assertEqual(evaluation.policy_risk, RiskLevel.CRITICAL)
        self.assertEqual(evaluation.effective_risk, RiskLevel.CRITICAL)
        self.assertTrue(evaluation.requires_explicit_confirmation)

    def test_policy_never_lowers_higher_suggested_risk(self):
        evaluation = self.service.evaluate("publish", RiskLevel.CRITICAL)
        self.assertEqual(evaluation.policy_risk, RiskLevel.HIGH)
        self.assertEqual(evaluation.effective_risk, RiskLevel.CRITICAL)

    def test_begin_rejects_second_pending_gate(self):
        evaluation = self.service.evaluate(None, RiskLevel.HIGH)
        first = self.service.begin("task-1", "pre_execution", evaluation)
        self.assertIs(self.service.pending, first)
        with self.assertRaisesRegex(RuntimeError, "pending approval"):
            self.service.begin("task-2", "pre_execution", evaluation)

    def test_critical_approve_without_confirmation_keeps_gate_pending(self):
        evaluation = self.service.evaluate(None, RiskLevel.CRITICAL)
        pending = self.service.begin("task-1", "pre_execution", evaluation)
        with self.assertRaises(PermissionError):
            self.service.decide(ApprovalDecision.APPROVE)
        self.assertIs(self.service.pending, pending)

    def test_critical_approve_with_confirmation_releases_gate(self):
        evaluation = self.service.evaluate(None, RiskLevel.CRITICAL)
        pending = self.service.begin("task-1", "pre_execution", evaluation)
        released = self.service.decide(
            ApprovalDecision.APPROVE,
            explicit_confirmation=True,
        )
        self.assertIs(released, pending)
        self.assertIsNone(self.service.pending)

    def test_reject_releases_gate_and_returns_pending_context(self):
        evaluation = self.service.evaluate(None, RiskLevel.HIGH)
        pending = self.service.begin("task-1", "post_result", evaluation, result_ready=True)
        released = self.service.decide(ApprovalDecision.REJECT)
        self.assertIs(released, pending)
        self.assertIsNone(self.service.pending)

    def test_change_records_change_context_and_releases_gate(self):
        evaluation = self.service.evaluate(None, RiskLevel.HIGH)
        pending = self.service.begin("task-1", "pre_execution", evaluation)
        context = {"request": "use another approach"}
        released = self.service.decide(
            ApprovalDecision.CHANGE,
            change_context=context,
        )
        self.assertIs(released, pending)
        self.assertIsNone(self.service.pending)
        decision_entry = self.service.audit_log()[-1]
        self.assertEqual(decision_entry["decision"], ApprovalDecision.CHANGE)
        self.assertEqual(decision_entry["change_context"], context)

    def test_audit_log_returns_snapshot_copies(self):
        self.service.evaluate(None, RiskLevel.MEDIUM)
        first = self.service.audit_log()
        first[0]["tampered"] = True
        second = self.service.audit_log()
        self.assertNotIn("tampered", second[0])


if __name__ == "__main__":
    unittest.main()
