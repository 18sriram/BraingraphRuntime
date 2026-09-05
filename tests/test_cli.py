from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from bg_cli.main import app


runner = CliRunner()


def test_init_creates_workspace_layout(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    calls = []

    def fake_request(api, method, path, **kwargs):
        calls.append((method, path))
        if path == "/api/databases":
            return [{"id": 7, "name": "local", "host": "localhost", "bolt_port": 7687}]
        return {"id": 11, "brain_version": "1.0"}

    monkeypatch.setattr("bg_cli.main.request_at", fake_request)
    result = runner.invoke(app, ["init"], input="Demo Project\n1\n")

    assert result.exit_code == 0
    metadata_file = Path(".braingraph/braingraph.json")
    assert metadata_file.exists()
    assert Path(".braingraph/logs").is_dir()
    assert Path(".braingraph/artifacts").is_dir()
    assert Path(".braingraph/checkpoints").is_dir()
    assert Path(".braingraph/state.json").exists()
    metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
    assert metadata["project_name"] == "Demo Project"
    assert metadata["workspace_id"] == 11
    assert metadata["database_id"] == 7
    assert ("POST", "/api/workspaces/11/switch") in calls
    assert "Available Databases:" in result.stdout
    assert "1. local" in result.stdout
    assert "✓ Workspace created" in result.stdout
    assert "✓ Neo4j attached" in result.stdout
    assert "✓ BrainGraph initialized" in result.stdout


def test_graph_import_sends_backup_to_workspace_database(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    Path(".braingraph").mkdir()
    Path(".braingraph/braingraph.json").write_text(json.dumps({"workspace_id": 4, "api_url": "http://localhost:8000"}), encoding="utf-8")
    snapshot = {
        "version": 1,
        "workspace": {"id": 4, "name": "Demo"},
        "nodes": [{"type": "File", "name": "main.py", "properties": {}}],
        "relationships": [],
        "artifacts": [],
    }
    Path("snapshot.json").write_text(json.dumps(snapshot), encoding="utf-8")
    calls = []

    def fake_request(method, path, **kwargs):
        calls.append((method, path, kwargs))
        return {"nodes": 1, "relationships": 0}

    monkeypatch.setattr("bg_cli.main.request", fake_request)

    result = runner.invoke(app, ["graph", "import", "snapshot.json"])

    assert result.exit_code == 0
    assert calls[0][1] == "/api/workspaces/4/graph/import"
    assert calls[0][2]["json"] == snapshot


def test_start_selects_provider_and_initializes_runtime(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    Path(".braingraph").mkdir()
    Path(".braingraph/braingraph.json").write_text(json.dumps({
        "project_name": "Demo Project",
        "workspace_id": 11,
        "database_id": 7,
        "brain_version": "1.0",
        "created_at": "2026-09-01T00:00:00+00:00",
        "api_url": "http://localhost:8000",
    }), encoding="utf-8")
    calls = []

    class HealthyResponse:
        is_success = False

    monkeypatch.setattr("bg_cli.main.httpx.get", lambda *args, **kwargs: HealthyResponse())
    monkeypatch.setattr("bg_cli.main.wait_for_api", lambda base_url: calls.append(("wait", base_url)))
    monkeypatch.setattr("bg_cli.main.compose", lambda command, environment=None: calls.append((command, environment)))
    monkeypatch.setattr("bg_cli.main.webbrowser.open", lambda url: calls.append(("browser", url)))

    def fake_request(method, path, **kwargs):
        calls.append((method, path))
        if path.endswith("/switch"):
            return {"id": 11, "name": "Demo Project", "database_id": 7}
        if path.endswith("/scan"):
            return {"files_scanned": 1, "files_skipped": 0, "nodes_created": 2, "relationships_created": 1, "errors": []}
        if path == "/api/databases":
            return [{"id": 7, "name": "LocalNeo4j"}]
        return {"nodes": [], "edges": []}

    monkeypatch.setattr("bg_cli.main.request", fake_request)
    result = runner.invoke(app, ["start", "--provider", "claude"])

    assert result.exit_code == 0
    assert (["up", "-d"], {"MODEL_PROVIDER": "anthropic", "BRAINGRAPH_WORKSPACE_PATH": str(tmp_path)}) in calls
    assert ("POST", "/api/workspaces/11/switch") in calls
    assert ("POST", "/api/workspaces/11/scan") in calls
    assert ("GET", "/api/databases") in calls
    assert ("GET", "/graph") in calls
    assert ("browser", "http://localhost:3000") in calls
    assert json.loads(Path(".braingraph/state.json").read_text())["scheduler"] == "running"
    assert "Provider  : Claude" in result.stdout
    assert "BrainGraph Runtime v1.0" in result.stdout
    assert "Database  : LocalNeo4j" in result.stdout
