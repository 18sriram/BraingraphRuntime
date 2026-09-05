from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.agent_loop.schemas import AgentAction
from app.safety.audit import AuditLogger
from app.safety.parser import ActionParser
from app.safety.policy import DeterministicPolicy
from app.safety.risk import RiskLevel


@dataclass(frozen=True)
class SafetyAssessment:
    action: AgentAction
    allowed: bool
    risk: RiskLevel
    reason: str
    requires_approval: bool


class ApprovalManager:
    def __init__(self, approver=None) -> None:
        self.approver = approver

    def approve(self, assessment: SafetyAssessment) -> bool:
        if not assessment.requires_approval:
            return assessment.allowed
        return bool(self.approver and self.approver(assessment))


class SafetyEngine:
    def __init__(
        self,
        project_root: str | Path = ".",
        network_enabled: bool = False,
        audit_logger: AuditLogger | None = None,
        approval_manager: ApprovalManager | None = None,
    ) -> None:
        self.parser = ActionParser()
        self.policy = DeterministicPolicy(project_root, network_enabled)
        self.audit = audit_logger or AuditLogger()
        self.approvals = approval_manager or ApprovalManager()

    def assess(self, action: AgentAction | dict[str, object]) -> SafetyAssessment:
        parsed = self.parser.parse(action)
        allowed, risk, reason = self.policy.evaluate(parsed)
        assessment = SafetyAssessment(
            action=parsed,
            allowed=allowed,
            risk=risk,
            reason=reason,
            requires_approval=allowed and risk in {RiskLevel.HIGH, RiskLevel.CRITICAL},
        )
        approved = self.approvals.approve(assessment)
        result = assessment.allowed and approved
        self.audit.log(
            "safety_check",
            action=parsed.model_dump(mode="json"),
            risk=risk.value,
            allowed=result,
            reason=reason if result else (reason if not allowed else "Approval denied"),
        )
        return SafetyAssessment(
            action=parsed,
            allowed=result,
            risk=risk,
            reason=reason if result else (reason if not allowed else "Approval denied"),
            requires_approval=assessment.requires_approval,
        )

    def check(self, action: AgentAction | dict[str, object]) -> bool:
        return self.assess(action).allowed
