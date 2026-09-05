import json

from app.agent_loop.schemas import AgentAction
from app.safety.audit import AuditLogger
from app.safety.engine import ApprovalManager, SafetyEngine
from app.safety.executor import SandboxExecutor
from app.safety.risk import RiskLevel


def test_safety_engine_blocks_dangerous_commands_and_logs(tmp_path) -> None:
    audit_path = tmp_path / "audit.jsonl"
    engine = SafetyEngine(project_root=tmp_path, audit_logger=AuditLogger(audit_path))

    assessment = engine.assess(
        AgentAction(type="run_command", parameters={"command": "rm -rf /"})
    )

    assert assessment.allowed is False
    assert assessment.risk == RiskLevel.CRITICAL
    record = json.loads(audit_path.read_text().splitlines()[0])
    assert record["event"] == "safety_check"
    assert record["allowed"] is False


def test_policy_rejects_network_and_outside_paths(tmp_path) -> None:
    engine = SafetyEngine(project_root=tmp_path)

    network = engine.assess(
        AgentAction(type="run_command", parameters={"command": "curl https://example.com"})
    )
    outside = engine.assess(
        AgentAction(type="read_file", parameters={"path": "../secrets.txt"})
    )

    assert network.allowed is False
    assert outside.allowed is False


def test_high_risk_action_requires_approval(tmp_path) -> None:
    denied = SafetyEngine(project_root=tmp_path)
    approved = SafetyEngine(
        project_root=tmp_path,
        approval_manager=ApprovalManager(lambda assessment: True),
    )
    action = AgentAction(type="git_commit", parameters={"command": "git commit -am update"})

    assert denied.check(action) is False
    assert approved.check(action) is True


def test_sandbox_file_operations_are_project_scoped_and_audited(tmp_path) -> None:
    audit_path = tmp_path / "audit.jsonl"
    executor = SandboxExecutor(project_root=tmp_path, audit_logger=AuditLogger(audit_path))
    action = AgentAction(
        type="create_file",
        parameters={"path": "notes.txt", "content": "hello"},
    )

    result = executor.execute(action)

    assert result["status"] == "success"
    assert (tmp_path / "notes.txt").read_text() == "hello"
    assert len(audit_path.read_text().splitlines()) == 2
