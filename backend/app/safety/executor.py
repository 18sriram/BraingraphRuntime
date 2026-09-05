from __future__ import annotations

import subprocess
import time
import os
import signal
from pathlib import Path
from typing import Any

from app.agent_loop.schemas import AgentAction
from app.safety.audit import AuditLogger
from app.safety.policy import DeterministicPolicy
from app.safety.schemas import ExecutionReport


class SandboxExecutor:
    """Execute approved file actions in the project and commands in Docker."""

    def __init__(
        self,
        project_root: str | Path = ".",
        docker_image: str = "python:3.12-slim",
        cpu_limit: float = 1.0,
        memory_limit_mb: int = 512,
        timeout_seconds: float = 30.0,
        network_enabled: bool = False,
        audit_logger: AuditLogger | None = None,
    ) -> None:
        self.project_root = Path(project_root).expanduser().resolve()
        self.docker_image = docker_image
        self.cpu_limit = cpu_limit
        self.memory_limit_mb = memory_limit_mb
        self.timeout_seconds = timeout_seconds
        self.network_enabled = network_enabled
        self.audit = audit_logger or AuditLogger()
        self.policy = DeterministicPolicy(self.project_root, network_enabled)

    def execute(self, action: AgentAction) -> dict[str, Any]:
        started = time.monotonic()
        self.audit.log("execution_started", action=action.model_dump(mode="json"))
        try:
            allowed, _, reason = self.policy.evaluate(action)
            if not allowed:
                report = self._report(
                    action,
                    status="blocked",
                    duration_seconds=time.monotonic() - started,
                    stderr=reason,
                    error=reason,
                )
            else:
                report = self._execute(action, started)
            payload = report.model_dump(mode="json")
            self.audit.log("execution_finished", action=action.model_dump(mode="json"), result=payload)
            return payload
        except Exception as error:
            self.audit.log("execution_failed", action=action.model_dump(mode="json"), error=str(error))
            report = self._report(
                action,
                status="failed",
                duration_seconds=time.monotonic() - started,
                stderr=str(error),
                error=str(error),
            )
            return report.model_dump(mode="json")

    def _execute(self, action: AgentAction, started: float) -> ExecutionReport:
        if action.type == "read_file":
            path = self._path(action.parameters.get("path"))
            return self._report(
                action, status="success", duration_seconds=time.monotonic() - started,
                stdout=path.read_text(encoding="utf-8"),
                metadata={"path": str(path.relative_to(self.project_root))},
            )
        if action.type in {"edit_file", "create_file"}:
            path = self._path(action.parameters.get("path"))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(str(action.parameters.get("content", "")), encoding="utf-8")
            return self._report(
                action, status="success", duration_seconds=time.monotonic() - started,
                metadata={"path": str(path.relative_to(self.project_root)), "status": "written"},
            )
        if action.type == "ask_user":
            return self._report(
                action, status="awaiting_user", duration_seconds=time.monotonic() - started,
                metadata={"question": action.parameters.get("question", "")},
            )
        if action.type in {"run_command", "run_tests", "git_commit"}:
            return self._run_in_docker(action, started)
        raise ValueError(f"Unsupported action type: {action.type}")

    def _path(self, value: Any) -> Path:
        if not value or not self.policy.is_project_path(str(value)):
            raise PermissionError("Filesystem path must remain inside the project folder")
        path = Path(value)
        return (path if path.is_absolute() else self.project_root / path).resolve()

    def _run_in_docker(self, action: AgentAction, started: float) -> ExecutionReport:
        command = self._command_for(action)
        network = "bridge" if self.network_enabled else "none"
        docker_command = [
            "docker", "run", "--rm", "--privileged=false", "--security-opt", "no-new-privileges",
            "--cap-drop", "ALL", "--network", network,
            "--cpus", str(self.cpu_limit), "--memory", f"{self.memory_limit_mb}m",
            "--mount", f"type=bind,source={self.project_root},target=/workspace",
            "-w", "/workspace",
            self.docker_image, "sh", "-lc", command,
        ]
        process = subprocess.Popen(
            docker_command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        timed_out = False
        try:
            stdout, stderr = process.communicate(timeout=self.timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(process.pid, signal.SIGKILL)
            stdout, stderr = process.communicate()
        return self._report(
            action,
            status="timeout" if timed_out else ("success" if process.returncode == 0 else "failed"),
            command=command,
            stdout=stdout,
            stderr=stderr,
            exit_code=None if timed_out else process.returncode,
            timed_out=timed_out,
            duration_seconds=time.monotonic() - started,
        )

    def _command_for(self, action: AgentAction) -> str:
        command = str(action.parameters.get("command", "")).strip()
        if command:
            return command
        defaults = {
            "run_tests": "pytest",
            "run_command": "python --version",
            "git_commit": "git status --short",
        }
        return defaults[action.type]

    def _report(
        self,
        action: AgentAction,
        *,
        status: str,
        duration_seconds: float,
        command: str | None = None,
        stdout: str = "",
        stderr: str = "",
        exit_code: int | None = None,
        timed_out: bool = False,
        error: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ExecutionReport:
        return ExecutionReport(
            action_type=action.type,
            command=command,
            status=status,
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            timed_out=timed_out,
            duration_seconds=max(0, duration_seconds),
            sandboxed=action.type in {"run_command", "run_tests", "git_commit"},
            network_enabled=self.network_enabled,
            error=error,
            metadata=metadata or {},
        )
