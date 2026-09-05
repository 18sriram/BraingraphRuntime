from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import Base, SessionLocal, engine
from app.gateway.gateway import ModelGateway
from app.models.workspace import Workspace
from app.services.agent_runtime import AgentRuntime
from app.services.first_prompt_scheduler import FirstPromptScheduler
from app.services.workflow_engine import WorkflowEngine
from app.local_models.manager import LocalModelManager


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bg", description="BrainGraph Runtime CLI")
    commands = parser.add_subparsers(dest="command", required=True)

    agent = commands.add_parser("agent", help="Control the current workspace agent")
    agent_commands = agent.add_subparsers(dest="agent_command", required=True)
    for name in ("on", "off", "pause", "resume", "status"):
        agent_commands.add_parser(name)
    commands.add_parser("start", help="Run first-run local orchestrator setup")

    schedule = commands.add_parser("schedule", help="Schedule a prompt for the current workspace")
    schedule.add_argument("--prompt", required=True)
    schedule.add_argument("--provider", default="openai")
    schedule.add_argument("--execute-at", type=datetime.fromisoformat)
    schedule.add_argument("--strategy", choices=("first-prompt-only", "autonomous"), default="first-prompt-only")

    workflow = commands.add_parser("workflow", help="Manage current-workspace workflows")
    workflow_commands = workflow.add_subparsers(dest="workflow_command", required=True)
    workflow_commands.add_parser("list")
    create = workflow_commands.add_parser("create")
    create.add_argument("name")
    run = workflow_commands.add_parser("run")
    run.add_argument("workflow_id", type=int)
    run.add_argument("--context", default="{}")
    visualize = workflow_commands.add_parser("visualize")
    visualize.add_argument("workflow_id", type=int)

    local = commands.add_parser("local-model", help="Manage the local orchestration model")
    local_commands = local.add_subparsers(dest="local_command", required=True)
    for name in ("status", "list", "current", "pull-progress"):
        local_commands.add_parser(name)
    install = local_commands.add_parser("install")
    install.add_argument("model", nargs="?")
    remove = local_commands.add_parser("remove")
    remove.add_argument("model")
    default = local_commands.add_parser("set-default")
    default.add_argument("model")
    return parser


def _current_workspace(session: Any) -> Workspace:
    current_path = str(Path.cwd().resolve())
    workspace = session.execute(select(Workspace).where(Workspace.project_path == current_path)).scalar_one_or_none()
    if workspace is None:
        raise ValueError(f"No workspace registered for {current_path}")
    return workspace


def _runtime(session: Any, workspace: Workspace) -> AgentRuntime:
    return AgentRuntime(session, f"workspace:{workspace.id}")


def _ensure_runtime(session: Any, workspace: Workspace) -> AgentRuntime:
    runtime = _runtime(session, workspace)
    if runtime.get() is None:
        runtime.create(f"Agent for workspace {workspace.name}", workspace_id=workspace.id)
    return runtime


def _runtime_json(runtime: AgentRuntime) -> None:
    record = runtime.get()
    if record is None:
        raise ValueError("Agent runtime not found for current workspace")
    print(json.dumps(AgentRuntime.as_dict(record), default=str, sort_keys=True))


def _agent_command(args: argparse.Namespace, session: Any, workspace: Workspace) -> None:
    if args.agent_command == "status":
        _runtime_json(_runtime(session, workspace))
        return
    runtime = _ensure_runtime(session, workspace)
    event = {"on": "power_on", "off": "power_off", "pause": "pause", "resume": "resume"}[args.agent_command]
    _runtime_json_after(runtime, event)


def _runtime_json_after(runtime: AgentRuntime, event: str) -> None:
    print(json.dumps(AgentRuntime.as_dict(runtime.transition(event)), default=str, sort_keys=True))


def _schedule(args: argparse.Namespace, session: Any, workspace: Workspace) -> None:
    settings = get_settings()
    record = FirstPromptScheduler(session, ModelGateway(settings=settings)).schedule_prompt(
        workspace_id=workspace.id,
        first_prompt=args.prompt,
        provider=args.provider,
        scheduled_time=args.execute_at,
        autonomy_enabled=args.strategy == "autonomous",
    )
    print(json.dumps({"id": record.id, "strategy": args.strategy, "status": record.status}, sort_keys=True))


def _workflow(args: argparse.Namespace, session: Any) -> None:
    service = WorkflowEngine(session)
    if args.workflow_command == "list":
        print(json.dumps([{"id": item.id, "name": item.name} for item in service.list_workflows()], sort_keys=True))
    elif args.workflow_command == "create":
        workflow = service.create_workflow(args.name)
        print(json.dumps({"id": workflow.id, "name": workflow.name}, sort_keys=True))
    elif args.workflow_command == "run":
        try:
            context = json.loads(args.context)
        except json.JSONDecodeError as error:
            raise ValueError("--context must be valid JSON") from error
        if not isinstance(context, dict):
            raise ValueError("--context must be a JSON object")
        print(json.dumps(service.execute(args.workflow_id, context=context), default=str, sort_keys=True))
    else:
        workflow = service.get_workflow(args.workflow_id)
        if workflow is None:
            raise ValueError(f"Workflow {args.workflow_id} not found")
        nodes = service.list_nodes(workflow.id)
        print(json.dumps({"id": workflow.id, "name": workflow.name, "nodes": [
            {"id": node.id, "title": node.title, "type": node.type, "next_success": node.next_success, "next_failure": node.next_failure}
            for node in nodes
        ]}, sort_keys=True))


def _local_model(args: argparse.Namespace) -> None:
    manager = LocalModelManager()
    if args.local_command == "status":
        available = manager.available()
        installed = manager.check_installed() if available else False
        print(json.dumps({"provider": manager.provider.name, "available": available, "model": manager.current_model(), "installed": installed, "message": manager.installation_message()}, sort_keys=True))
    elif args.local_command == "list":
        print(json.dumps([item.model_dump(mode="json") for item in manager.list_models()], sort_keys=True))
    elif args.local_command == "current":
        print(manager.current_model())
    elif args.local_command == "set-default":
        print(manager.set_default(args.model))
    elif args.local_command == "remove":
        manager.remove_model(args.model)
        print(args.model)
    else:
        for item in manager.pull_progress(getattr(args, "model", None)):
            print(item.model_dump_json())


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        if args.command == "start":
            if not LocalModelManager().first_run_setup():
                return
            print("BrainGraph Runtime is ready.")
            return
        if args.command == "local-model":
            _local_model(args)
            return
        workspace = _current_workspace(session)
        if args.command == "agent":
            _agent_command(args, session, workspace)
        elif args.command == "schedule":
            _schedule(args, session, workspace)
        else:
            _workflow(args, session)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    finally:
        session.close()


if __name__ == "__main__":
    main()
