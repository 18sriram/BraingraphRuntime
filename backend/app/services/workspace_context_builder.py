from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.git.integration import GitIntegration
from app.models.workspace import Workspace
from app.repositories.graph_repository import GraphRepository
from app.schemas.workspace_context import WorkspaceContext


class WorkspaceContextBuilder:
    """Build the default structured context supplied to model calls."""

    def __init__(self, session: Session, graph: GraphRepository | None = None) -> None:
        self.session = session
        self.graph = graph or GraphRepository()

    def build(self, workspace_id: int, current_task: str | None = None) -> WorkspaceContext:
        workspace = self.session.get(Workspace, workspace_id)
        if workspace is None:
            raise ValueError("Workspace not found")
        branch, modified_files, recent_commits = self._git_context(workspace.project_path)
        relevant_nodes = self._graph_context(workspace_id, current_task)
        task_name = current_task
        if current_task:
            task_node = self.graph.get_node(current_task)
            if task_node is not None:
                task_name = task_node.name
        return WorkspaceContext(
            workspace_id=workspace.id,
            workspace_name=workspace.name,
            project_path=workspace.project_path,
            database_id=workspace.database_id,
            brain_version=workspace.brain_version,
            current_branch=branch,
            modified_files=modified_files,
            recent_commits=recent_commits,
            relevant_graph_nodes=relevant_nodes,
            current_task=task_name,
            generated_at=datetime.now(timezone.utc),
        )

    def _git_context(self, project_path: str) -> tuple[str | None, list[str], list[dict[str, Any]]]:
        try:
            integration = GitIntegration(Path(project_path), self.graph)
            branch = integration.repo.active_branch.name
            modified_files = integration.changed_files()
            commits = [
                {
                    "hash": commit.hexsha,
                    "message": commit.message.strip(),
                    "author": str(commit.author),
                    "committed_at": commit.committed_datetime.isoformat(),
                }
                for commit in integration.repo.iter_commits(max_count=10)
            ]
            return branch, modified_files, commits
        except Exception:
            return None, [], []

    def _graph_context(self, workspace_id: int, current_task: str | None) -> list[dict[str, Any]]:
        nodes = []
        if current_task:
            task_node = self.graph.get_node(current_task)
            if task_node is not None:
                nodes.append(task_node.model_dump(mode="json"))
                context = self.graph.retrieve_subgraph(current_task, max_depth=2, bidirectional=True)
                nodes.extend(node.model_dump(mode="json") for node in context.nodes if node.id != current_task)
        if not nodes:
            for node_type in ("Project", "Task", "File", "Function", "Class", "Import"):
                nodes.extend(
                    node.model_dump(mode="json")
                    for node in self.graph.find_nodes(node_type, {"workspace_id": workspace_id})
                )
        unique_nodes = {node["id"]: node for node in nodes}
        return list(unique_nodes.values())