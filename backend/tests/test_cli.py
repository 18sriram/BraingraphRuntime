from __future__ import annotations

from app.cli import build_parser


def test_cli_exposes_requested_commands() -> None:
    parser = build_parser()
    assert parser.parse_args(["agent", "on"]).agent_command == "on"
    assert parser.parse_args(["agent", "off"]).agent_command == "off"
    assert parser.parse_args(["agent", "pause"]).agent_command == "pause"
    assert parser.parse_args(["agent", "resume"]).agent_command == "resume"
    assert parser.parse_args(["agent", "status"]).agent_command == "status"
    assert parser.parse_args(["schedule", "--prompt", "Fix", "--strategy", "autonomous"]).strategy == "autonomous"
    assert parser.parse_args(["workflow", "list"]).workflow_command == "list"
    assert parser.parse_args(["workflow", "create", "build"]).workflow_command == "create"
    assert parser.parse_args(["workflow", "run", "1"]).workflow_command == "run"
    assert parser.parse_args(["workflow", "visualize", "1"]).workflow_command == "visualize"