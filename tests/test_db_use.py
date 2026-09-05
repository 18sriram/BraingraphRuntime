from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from bg_cli.main import app


runner = CliRunner()


def test_db_use_changes_workspace_database_and_can_migrate(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    Path(".braingraph").mkdir()
    Path(".braingraph/braingraph.json").write_text(json.dumps({
        "project_name": "HouseEats",
        "workspace_id": 4,
        "database_id": 1,
        "api_url": "http://localhost:8000",
    }), encoding="utf-8")
    calls = []

    def fake_request(method, path, **kwargs):
        calls.append((method, path, kwargs))
        if path == "/api/databases":
            return [{"id": 2, "name": "ResearchDB"}]
        return {"id": 4, "name": "HouseEats", "database_id": 2}

    monkeypatch.setattr("bg_cli.main.request", fake_request)
    result = runner.invoke(app, ["db", "use", "ResearchDB"], input="y\n")

    assert result.exit_code == 0
    assert calls[-1][2]["json"] == {"database_id": 2, "move_existing_graph": True}
    assert json.loads(Path(".braingraph/braingraph.json").read_text())["database_id"] == 2
    assert "Database switched successfully" in result.stdout


def test_db_use_rejects_unknown_database(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    Path(".braingraph").mkdir()
    Path(".braingraph/braingraph.json").write_text(json.dumps({
        "workspace_id": 4,
        "database_id": 1,
        "api_url": "http://localhost:8000",
    }), encoding="utf-8")
    monkeypatch.setattr("bg_cli.main.request", lambda *args, **kwargs: [])

    result = runner.invoke(app, ["db", "use", "MissingDB"])

    assert result.exit_code != 0
    assert "was not found" in result.output
