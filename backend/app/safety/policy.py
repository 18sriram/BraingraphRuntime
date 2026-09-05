from __future__ import annotations

from pathlib import Path

from app.agent_loop.schemas import AgentAction
from app.safety.risk import RiskClassifier, RiskLevel


class DeterministicPolicy:
    blocked_commands = ("rm -rf", "shutdown", "reboot", "mkfs", "dd if=", "drop database")

    def __init__(self, project_root: str | Path = ".", network_enabled: bool = False) -> None:
        self.project_root = Path(project_root).expanduser().resolve()
        self.network_enabled = network_enabled
        self.risk_classifier = RiskClassifier()

    def evaluate(self, action: AgentAction) -> tuple[bool, RiskLevel, str]:
        risk = self.risk_classifier.classify(action)
        if risk == RiskLevel.CRITICAL:
            return False, risk, "Command matches a blocked command policy"
        command = str(action.parameters.get("command", ""))
        if not self.network_enabled and self.risk_classifier.network_patterns.search(command):
            return False, risk, "Network access is disabled by policy"
        for key in ("path", "file", "cwd"):
            if key in action.parameters and not self.is_project_path(str(action.parameters[key])):
                return False, RiskLevel.CRITICAL, f"{key} is outside the project folder"
        return True, risk, "Allowed by deterministic policy"

    def is_project_path(self, value: str) -> bool:
        path = Path(value)
        candidate = path if path.is_absolute() else self.project_root / path
        try:
            candidate.resolve().relative_to(self.project_root)
            return True
        except ValueError:
            return False
