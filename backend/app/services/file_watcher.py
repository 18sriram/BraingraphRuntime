from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from app.repositories.graph_repository import GraphRepository
from app.schemas.graph import GraphNode, GraphNodeCreate


class FileWatcher(FileSystemEventHandler):
    """Mirror supported workspace file changes into Brain Graph File nodes."""

    SUPPORTED_EXTENSIONS = {".py", ".ts", ".tsx", ".json", ".md"}
    LANGUAGE_BY_EXTENSION = {
        ".py": "python",
        ".ts": "typescript",
        ".tsx": "typescriptreact",
        ".json": "json",
        ".md": "markdown",
    }

    def __init__(self, workspace_path: str | Path, workspace_id: int, graph: GraphRepository) -> None:
        super().__init__()
        self.workspace_path = Path(workspace_path).expanduser().resolve()
        self.workspace_id = workspace_id
        self.graph = graph
        self.observer: Observer | None = None

    def start(self) -> None:
        if self.observer is not None and self.observer.is_alive():
            return
        self.observer = Observer()
        self.observer.schedule(self, str(self.workspace_path), recursive=True)
        self.observer.start()

    def stop(self) -> None:
        if self.observer is None:
            return
        self.observer.stop()
        self.observer.join(timeout=5)
        self.observer = None

    def on_created(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._upsert(Path(event.src_path))

    def on_modified(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._upsert(Path(event.src_path))

    def on_deleted(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._archive(Path(event.src_path))

    def _upsert(self, path: Path) -> GraphNode | None:
        if path.suffix.lower() not in self.SUPPORTED_EXTENSIONS or not path.is_file():
            return None
        resolved_path = path.resolve()
        properties = {
            "path": str(resolved_path),
            "hash": hashlib.sha256(path.read_bytes()).hexdigest(),
            "language": self.LANGUAGE_BY_EXTENSION[path.suffix.lower()],
            "last_modified": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
            "workspace_id": self.workspace_id,
            "archived": False,
        }
        existing = self.graph.find_nodes("File", {"path": str(resolved_path), "workspace_id": self.workspace_id})
        if existing:
            return self.graph.update_node(existing[0].id, {"name": str(resolved_path), "properties": properties})
        return self.graph.create_node(GraphNodeCreate(type="File", name=str(resolved_path), properties=properties))

    def _archive(self, path: Path) -> GraphNode | None:
        resolved_path = str(path.expanduser().resolve())
        existing = self.graph.find_nodes("File", {"path": resolved_path, "workspace_id": self.workspace_id})
        if not existing:
            return None
        node = existing[0]
        properties = dict(node.properties)
        properties["archived"] = True
        properties["last_modified"] = datetime.now(timezone.utc).isoformat()
        return self.graph.update_node(node.id, {"properties": properties})