from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
import time
import webbrowser
from typing import Any

import httpx
import typer

app = typer.Typer(help="BrainGraph workspace CLI.")
db_app = typer.Typer(help="Manage Neo4j databases.")
workspace_app = typer.Typer(help="Manage project workspaces.")
graph_app = typer.Typer(help="Export and import graph snapshots.")
app.add_typer(db_app, name="db")
app.add_typer(workspace_app, name="workspace")
app.add_typer(graph_app, name="graph")


def workspace_root() -> Path:
    return Path.cwd()


def metadata_dir() -> Path:
    return workspace_root() / ".braingraph"


def metadata_file() -> Path:
    return metadata_dir() / "braingraph.json"


def load_metadata() -> dict[str, Any]:
    if not metadata_file().exists():
        raise typer.BadParameter("This directory is not a BrainGraph workspace. Run 'bg init' first.")
    return json.loads(metadata_file().read_text(encoding="utf-8"))


def api_url() -> str:
    return str(load_metadata().get("api_url", os.getenv("BRAINGRAPH_API_URL", "http://localhost:8000"))).rstrip("/")


def request(method: str, path: str, **kwargs: Any) -> Any:
    return request_at(api_url(), method, path, **kwargs)


def request_at(base_url: str, method: str, path: str, **kwargs: Any) -> Any:
    try:
        response = httpx.request(method, f"{base_url.rstrip('/')}{path}", timeout=10, **kwargs)
        response.raise_for_status()
    except httpx.HTTPError as error:
        raise typer.ClickException(f"BrainGraph API request failed: {error}") from error
    return response.json() if response.content else None


def save_metadata(metadata: dict[str, Any]) -> None:
    metadata_file().write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")


def runtime_root() -> Path:
    configured = os.getenv("BRAINGRAPH_RUNTIME_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    if (workspace_root() / "docker-compose.yml").exists():
        return workspace_root()
    return Path(__file__).resolve().parents[1]


def compose(command: list[str], environment: dict[str, str] | None = None) -> None:
    if shutil.which("docker") is None:
        raise typer.ClickException("Docker is not installed or is not available in PATH")
    try:
        process_environment = os.environ.copy()
        if environment:
            process_environment.update(environment)
        subprocess.run(["docker", "compose", *command], cwd=runtime_root(), check=True, env=process_environment)
    except subprocess.CalledProcessError as error:
        raise typer.ClickException(f"Docker Compose failed with exit code {error.returncode}") from error


@app.command()
def init(
    api: str = typer.Option("http://localhost:8000", "--api", help="BrainGraph API base URL."),
) -> None:
    """Initialize the current directory as a BrainGraph workspace."""
    root = workspace_root()
    project_name = typer.prompt("Project Name")
    databases = request_at(api, "GET", "/api/databases")
    if not databases:
        raise typer.ClickException("No databases are registered. Add one with 'bg db add' first.")
    typer.echo("\nAvailable Databases:\n")
    for index, database in enumerate(databases, start=1):
        typer.echo(f"{index}. {database['name']}")
    selection = typer.prompt("\nChoose", type=int)
    if selection < 1 or selection > len(databases):
        raise typer.BadParameter(f"Select a number from 1 to {len(databases)}")
    selected_database = databases[selection - 1]
    try:
        workspace = request_at(api, "POST", "/api/workspaces", json={
            "name": project_name,
            "project_path": str(root),
            "database_id": selected_database["id"],
        })
    except typer.ClickException:
        raise
    opened_workspace = request_at(api, "POST", f"/api/workspaces/{workspace['id']}/switch")
    metadata_dir().mkdir(exist_ok=True)
    (metadata_dir() / "logs").mkdir(exist_ok=True)
    (metadata_dir() / "artifacts").mkdir(exist_ok=True)
    (metadata_dir() / "checkpoints").mkdir(exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    save_metadata({
        "project_name": project_name,
        "workspace_id": opened_workspace["id"],
        "database_id": selected_database["id"],
        "brain_version": workspace.get("brain_version", "1.0"),
        "created_at": now,
        "api_url": api.rstrip("/"),
    })
    (metadata_dir() / "state.json").write_text(json.dumps({
        "status": "initialized",
        "workspace_id": opened_workspace["id"],
        "database_id": selected_database["id"],
        "last_opened": None,
    }, indent=2) + "\n", encoding="utf-8")
    scan = request_at(api, "POST", f"/api/workspaces/{opened_workspace['id']}/scan")
    (metadata_dir() / "state.json").write_text(json.dumps({
        "status": "initialized",
        "workspace_id": opened_workspace["id"],
        "database_id": selected_database["id"],
        "last_opened": None,
        "scan": scan,
    }, indent=2) + "\n", encoding="utf-8")
    typer.echo("\n✓ Workspace created")
    typer.echo("✓ Neo4j attached")
    typer.echo("✓ BrainGraph initialized")


def wait_for_api(base_url: str, attempts: int = 30) -> None:
    for _ in range(attempts):
        try:
            response = httpx.get(f"{base_url.rstrip('/')}/health", timeout=2)
            if response.is_success:
                return
        except httpx.HTTPError:
            pass
        time.sleep(1)
    raise typer.ClickException("BrainGraph API did not become ready")


@app.command()
def start(
    provider: str = typer.Option("openai", "--provider", case_sensitive=False),
) -> None:
    """Start the current workspace runtime and open its dashboard."""
    metadata = load_metadata()
    normalized_provider = provider.lower()
    provider_name = {"openai": "openai", "claude": "anthropic", "gemini": "gemini"}.get(normalized_provider)
    if provider_name is None:
        raise typer.BadParameter("Provider must be one of: openai, claude, gemini")
    base_url = api_url()
    state_path = metadata_dir() / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    try:
        response = httpx.get(f"{base_url}/health", timeout=2)
        already_running = response.is_success and state.get("status") == "running"
    except httpx.HTTPError:
        already_running = False
    if not already_running:
        compose(["up", "-d"], {
            "MODEL_PROVIDER": provider_name,
            "BRAINGRAPH_WORKSPACE_PATH": str(workspace_root()),
        })
        wait_for_api(base_url)
    opened = request("POST", f"/api/workspaces/{metadata['workspace_id']}/switch")
    scan = request("POST", f"/api/workspaces/{metadata['workspace_id']}/scan")
    databases = request("GET", "/api/databases")
    database = next((item for item in databases if item["id"] == opened["database_id"]), None)
    database_name = database["name"] if database is not None else str(opened["database_id"])
    graph = request("GET", "/graph")
    (metadata_dir() / "graph.json").write_text(json.dumps(graph, indent=2) + "\n", encoding="utf-8")
    now = datetime.now(timezone.utc).isoformat()
    state.update({
        "status": "running",
        "workspace_id": opened["id"],
        "database_id": opened["database_id"],
        "provider": provider_name,
        "watched_path": str(workspace_root()),
        "scheduler": "running",
        "brain_graph": "initialized",
        "scan": scan,
        "started_at": state.get("started_at", now),
    })
    state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    webbrowser.open("http://localhost:3000")
    provider_label = {"openai": "OpenAI", "anthropic": "Claude", "gemini": "Gemini"}[provider_name]
    typer.echo("\nBrainGraph Runtime v1.0")
    typer.echo(f"Workspace : {opened['name']}")
    typer.echo(f"Directory : {workspace_root()}")
    typer.echo(f"Database  : {database_name}")
    typer.echo(f"Provider  : {provider_label}")
    typer.echo(f"Watching {scan.get('files_scanned', 0) + scan.get('files_skipped', 0)} files...")
    typer.echo("Dashboard:\nhttp://localhost:3000")
    typer.echo("Status:\nREADY")


@app.command()
def stop() -> None:
    """Stop the local BrainGraph services without deleting volumes."""
    load_metadata()
    compose(["stop"])


@app.command()
def status() -> None:
    """Show local service and current workspace status."""
    load_metadata()
    try:
        metadata = load_metadata()
        workspace = request("GET", f"/api/workspaces/{metadata['workspace_id']}")
        databases = request("GET", "/api/databases")
        database = next((item for item in databases if item["id"] == workspace["database_id"]), None)
        state_path = metadata_dir() / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
        scan = state.get("scan", {})
        provider = {"openai": "OpenAI", "anthropic": "Claude", "gemini": "Gemini"}.get(state.get("provider", "openai"), state.get("provider", "OpenAI"))
        typer.echo(f"Workspace : {workspace['name']}")
        typer.echo(f"Database  : {database['name'] if database else workspace['database_id']}")
        typer.echo(f"Provider  : {provider}")
        typer.echo(f"Files     : {scan.get('files_scanned', 0) + scan.get('files_skipped', 0)}")
        typer.echo(f"Nodes     : {scan.get('nodes_created', 0)}")
        typer.echo(f"Relationships : {scan.get('relationships_created', 0)}")
        typer.echo("Scheduler : Running" if state.get("scheduler") == "running" else "Scheduler : Stopped")
        typer.echo("Agent     : Idle")
    except typer.ClickException as error:
        typer.echo(str(error), err=True)


@db_app.command("list")
def db_list() -> None:
    typer.echo(json.dumps(request("GET", "/api/databases"), indent=2))


@db_app.command("add")
def db_add(
    name: str = typer.Option(..., prompt="Database Name"),
    host: str = typer.Option("localhost", prompt="Host"),
    bolt_port: int = typer.Option(7687, prompt="Bolt Port"),
    username: str = typer.Option("neo4j", prompt="Username"),
    password: str = typer.Option(..., prompt="Password", hide_input=True),
    default_database: str = typer.Option("neo4j", prompt="Database name"),
) -> None:
    database = request("POST", "/api/databases", json={
        "name": name,
        "host": host,
        "bolt_port": bolt_port,
        "username": username,
        "password": password,
        "default_database": default_database,
    })
    connected = request("POST", f"/api/databases/{database['id']}/test")
    if not connected.get("connected"):
        raise typer.ClickException("Database was saved but the connection test failed")
    typer.echo("✓ Connected")
    typer.echo("✓ Saved")


@db_app.command("use")
def db_use(database_name: str = typer.Argument(...)) -> None:
    metadata = load_metadata()
    databases = request("GET", "/api/databases")
    database = next((item for item in databases if item["name"].casefold() == database_name.casefold()), None)
    if database is None:
        raise typer.BadParameter(f"Database {database_name!r} was not found")
    move_graph = typer.confirm("Move existing graph?", default=False)
    workspace_id = metadata.get("workspace_id")
    if workspace_id is None:
        raise typer.ClickException("This workspace has no registered workspace ID")
    workspace = request("POST", f"/api/workspaces/{workspace_id}/database", json={
        "database_id": database["id"],
        "move_existing_graph": move_graph,
    })
    metadata["database_id"] = database["id"]
    save_metadata(metadata)
    typer.echo(json.dumps(workspace, indent=2))
    typer.echo("Database switched successfully")


@workspace_app.command("list")
def workspace_list() -> None:
    typer.echo(json.dumps(request("GET", "/api/workspaces"), indent=2))


@workspace_app.command("open")
def workspace_open() -> None:
    metadata = load_metadata()
    workspaces = request("GET", "/api/workspaces")
    current_path = str(workspace_root().resolve())
    matching = next((item for item in workspaces if item["project_path"] == current_path), None)
    if matching is None:
        raise typer.ClickException("Current directory is not registered. Register it through POST /api/workspaces first.")
    opened = request("POST", f"/api/workspaces/{matching['id']}/switch")
    metadata["workspace_id"] = opened["id"]
    save_metadata(metadata)
    typer.echo(json.dumps(opened, indent=2))


@graph_app.command("export")
def graph_export(output: Path = typer.Option(Path("braingraph_export.json"), "--output", "-o")) -> None:
    metadata = load_metadata()
    snapshot = request("GET", f"/api/workspaces/{metadata['workspace_id']}/graph/export")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
    typer.echo(f"Exported graph snapshot to {output}")


@graph_app.command("import")
def graph_import(input_file: Path = typer.Argument(..., exists=True, readable=True)) -> None:
    try:
        snapshot = json.loads(input_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise typer.BadParameter(f"Invalid graph JSON: {error}") from error
    if (
        not isinstance(snapshot, dict)
        or not isinstance(snapshot.get("nodes"), list)
        or not isinstance(snapshot.get("relationships"), list)
    ):
        raise typer.BadParameter("Graph backup must contain 'nodes' and 'relationships' arrays")
    metadata = load_metadata()
    result = request("POST", f"/api/workspaces/{metadata['workspace_id']}/graph/import", json=snapshot)
    typer.echo(json.dumps(result, indent=2))
    typer.echo(f"Imported graph backup from {input_file}")


if __name__ == "__main__":
    app()