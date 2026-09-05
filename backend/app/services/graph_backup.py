from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from app.models.workspace import Workspace
from app.services.database_manager import DatabaseManager


class GraphBackupService:
    """Export and restore a workspace-scoped Neo4j graph."""

    def __init__(self, session: Any) -> None:
        self.session = session
        self.database_manager = DatabaseManager(session)

    def export_workspace(self, workspace_id: int) -> dict[str, Any]:
        workspace = self._workspace(workspace_id)
        driver = self.database_manager.create_driver(workspace.database_id)
        try:
            with driver.session(database=self.database_manager.get_database_name(workspace.database_id)) as graph:
                nodes = [dict(record) for record in graph.run(
                    "MATCH (n:BrainNode {workspace_id: $workspace_id}) "
                    "RETURN n.node_type AS type, n.name AS name, n.path AS path, properties(n) AS properties",
                    workspace_id=workspace_id,
                )]
                relationships = [dict(record) for record in graph.run(
                    "MATCH (source:BrainNode {workspace_id: $workspace_id})-[r]->"
                    "(target:BrainNode {workspace_id: $workspace_id}) "
                    "RETURN source.node_type AS source_type, source.name AS source_name, source.path AS source_path, "
                    "target.node_type AS target_type, target.name AS target_name, target.path AS target_path, "
                    "type(r) AS type, properties(r) AS properties",
                    workspace_id=workspace_id,
                )]
            return {
                "version": 1,
                "exported_at": datetime.now(timezone.utc).isoformat(),
                "workspace": {
                    "id": workspace.id,
                    "name": workspace.name,
                    "project_path": workspace.project_path,
                    "database_id": workspace.database_id,
                    "brain_version": workspace.brain_version,
                },
                "nodes": nodes,
                "relationships": relationships,
                "artifacts": [
                    node for node in nodes
                    if node["type"] in {"GitCommit", "File", "TestReport", "Log"}
                ],
            }
        finally:
            driver.close()

    def import_workspace(self, workspace_id: int, backup: dict[str, Any]) -> dict[str, int]:
        workspace = self._workspace(workspace_id)
        self._validate_backup(backup)
        driver = self.database_manager.create_driver(workspace.database_id)
        node_count = 0
        relationship_count = 0
        try:
            with driver.session(database=self.database_manager.get_database_name(workspace.database_id)) as graph:
                for node in backup["nodes"]:
                    graph.run(
                        "MERGE (n:BrainNode {workspace_id: $workspace_id, node_type: $type, name: $name, path: $path}) "
                        "SET n += $properties",
                        workspace_id=workspace_id,
                        type=node["type"], name=node["name"], path=node.get("path", ""),
                        properties={**node.get("properties", {}), "workspace_id": workspace_id},
                    ).consume()
                    node_count += 1
                for relationship in backup["relationships"]:
                    graph.run(
                        "MATCH (source:BrainNode {workspace_id: $workspace_id, node_type: $source_type, name: $source_name, path: $source_path}) "
                        "MATCH (target:BrainNode {workspace_id: $workspace_id, node_type: $target_type, name: $target_name, path: $target_path}) "
                        f"MERGE (source)-[r:{self._relationship_type(relationship['type'])}]->(target) SET r += $properties",
                        workspace_id=workspace_id,
                        source_type=relationship["source_type"], source_name=relationship["source_name"],
                        source_path=relationship.get("source_path", ""), target_type=relationship["target_type"],
                        target_name=relationship["target_name"], target_path=relationship.get("target_path", ""),
                        properties=relationship.get("properties", {}),
                    ).consume()
                    relationship_count += 1
        finally:
            driver.close()
        return {"nodes": node_count, "relationships": relationship_count}

    def _workspace(self, workspace_id: int) -> Workspace:
        workspace = self.session.get(Workspace, workspace_id)
        if workspace is None:
            raise ValueError("Workspace not found")
        return workspace

    @staticmethod
    def _validate_backup(backup: dict[str, Any]) -> None:
        if backup.get("version") != 1 or not isinstance(backup.get("nodes"), list) or not isinstance(backup.get("relationships"), list):
            raise ValueError("Invalid BrainGraph backup format")
        required = {"type", "name"}
        if any(not required.issubset(node) for node in backup["nodes"]):
            raise ValueError("Backup nodes must contain type and name")

    @staticmethod
    def _relationship_type(value: str) -> str:
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", value):
            raise ValueError("Invalid relationship type in backup")
        return value