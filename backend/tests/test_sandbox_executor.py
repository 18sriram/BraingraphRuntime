from __future__ import annotations

import subprocess

from app.agent_loop.schemas import AgentAction
from app.safety.audit import AuditLogger
from app.safety.executor import SandboxExecutor


class FakeProcess:
    pid = 123
    returncode = 0

    def __init__(self, timeout: bool = False) -> None:
        self.timeout = timeout
        self.killed = False

    def communicate(self, timeout: float | None = None) -> tuple[str, str]:
        if self.timeout and not self.killed:
            raise subprocess.TimeoutExpired("docker", timeout)
        return "out", "err"


def test_docker_command_has_limits_mount_and_no_privileges(tmp_path, monkeypatch) -> None:
    process = FakeProcess()
    captured: list[str] = []

    def fake_popen(command, **kwargs):
        captured.extend(command)
        return process

    monkeypatch.setattr("app.safety.executor.subprocess.Popen", fake_popen)
    executor = SandboxExecutor(project_root=tmp_path, audit_logger=AuditLogger(tmp_path / "audit.jsonl"))

    report = executor.execute(
        AgentAction(type="run_command", parameters={"command": "python --version"})
    )

    assert report["status"] == "success"
    assert report["stdout"] == "out"
    assert report["stderr"] == "err"
    assert report["exit_code"] == 0
    assert "--privileged=false" in captured
    assert "--cap-drop" in captured and "ALL" in captured
    assert "--network" in captured and "none" in captured
    assert "--mount" in captured
    assert str(tmp_path) in captured[captured.index("--mount") + 1]
    assert "-v" not in captured


def test_timeout_kills_process_group_and_returns_report(tmp_path, monkeypatch) -> None:
    process = FakeProcess(timeout=True)
    monkeypatch.setattr("app.safety.executor.subprocess.Popen", lambda command, **kwargs: process)
    monkeypatch.setattr("app.safety.executor.os.killpg", lambda pid, signal: setattr(process, "killed", True))
    executor = SandboxExecutor(
        project_root=tmp_path,
        timeout_seconds=0.01,
        audit_logger=AuditLogger(tmp_path / "audit.jsonl"),
    )

    report = executor.execute(
        AgentAction(type="run_command", parameters={"command": "npm test"})
    )

    assert report["status"] == "timeout"
    assert report["timed_out"] is True
    assert report["exit_code"] is None
    assert process.killed is True


def test_supported_command_families_are_passed_to_docker(tmp_path) -> None:
    executor = SandboxExecutor(project_root=tmp_path)

    assert executor._command_for(AgentAction(type="run_tests")) == "pytest"
    assert executor._command_for(AgentAction(type="run_command", parameters={"command": "python -m unittest"})) == "python -m unittest"
    assert executor._command_for(AgentAction(type="run_command", parameters={"command": "npm run build"})) == "npm run build"
    assert executor._command_for(AgentAction(type="run_command", parameters={"command": "pip install -r requirements.txt"})) == "pip install -r requirements.txt"
