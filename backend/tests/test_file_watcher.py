from __future__ import annotations

import hashlib
from pathlib import Path

from watchdog.events import FileCreatedEvent, FileDeletedEvent, FileModifiedEvent

from app.repositories.graph_repository import GraphRepository
from app.services.file_watcher import FileWatcher


def test_file_watcher_creates_updates_and_archives_supported_files(tmp_path: Path) -> None:
    graph = GraphRepository()
    watcher = FileWatcher(tmp_path, workspace_id=42, graph=graph)
    file_path = tmp_path / "main.py"
    file_path.write_text("print('first')", encoding="utf-8")

    watcher.on_created(FileCreatedEvent(str(file_path)))
    nodes = graph.find_nodes("File", {"path": str(file_path.resolve()), "workspace_id": 42})
    assert len(nodes) == 1
    assert nodes[0].properties["hash"] == hashlib.sha256(b"print('first')").hexdigest()
    assert nodes[0].properties["language"] == "python"
    assert nodes[0].properties["archived"] is False

    file_path.write_text("print('second')", encoding="utf-8")
    watcher.on_modified(FileModifiedEvent(str(file_path)))
    nodes = graph.find_nodes("File", {"path": str(file_path.resolve()), "workspace_id": 42})
    assert len(nodes) == 1
    assert nodes[0].properties["hash"] == hashlib.sha256(b"print('second')").hexdigest()

    file_path.unlink()
    watcher.on_deleted(FileDeletedEvent(str(file_path)))
    archived = graph.find_nodes("File", {"path": str(file_path.resolve()), "workspace_id": 42})[0]
    assert archived.properties["archived"] is True


def test_file_watcher_ignores_unsupported_files(tmp_path: Path) -> None:
    graph = GraphRepository()
    watcher = FileWatcher(tmp_path, workspace_id=43, graph=graph)
    file_path = tmp_path / "image.png"
    file_path.write_bytes(b"data")

    watcher.on_created(FileCreatedEvent(str(file_path)))

    assert graph.find_nodes("File", {"workspace_id": 43}) == []
