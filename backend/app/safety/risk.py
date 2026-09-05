from __future__ import annotations

import re
from enum import StrEnum

from app.agent_loop.schemas import AgentAction


class RiskLevel(StrEnum):
    SAFE = "SAFE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class RiskClassifier:
    blocked_patterns = re.compile(
        r"(?:rm\s+-rf|shutdown|reboot|mkfs(?:\.|\s)|dd\s+if=|drop\s+database)", re.IGNORECASE
    )
    network_patterns = re.compile(r"(?:curl|wget|nc\s|netcat|ssh\s|scp\s|pip\s+install|npm\s+install)", re.IGNORECASE)

    def classify(self, action: AgentAction) -> RiskLevel:
        if action.type in {"read_file", "ask_user"}:
            return RiskLevel.SAFE
        if action.type in {"edit_file", "create_file", "run_tests"}:
            return RiskLevel.LOW
        if action.type == "git_commit":
            return RiskLevel.HIGH
        command = str(action.parameters.get("command", ""))
        if self.blocked_patterns.search(command):
            return RiskLevel.CRITICAL
        if self.network_patterns.search(command):
            return RiskLevel.HIGH
        return RiskLevel.MEDIUM
