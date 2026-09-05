from __future__ import annotations

from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.database import Database
from app.models.workspace import Workspace
from app.services.database_manager import DatabaseManager


class WorkspaceManager:
    """Register project folders and open them against their Neo4j database."""

    def __init__(self, session: Session, database_manager: DatabaseManager | None = None) -> None:
        self.session = session
        self.database_manager = database_manager or DatabaseManager(session)

    def register_workspace(self, name: str, project_path: str, database_id: int, brain_version: str = "1.0") -> Workspace:
        normalized_path = str(Path(project_path).expanduser().resolve(strict=False))
        if self.session.get(Database, database_id) is None:
            raise ValueError("Assigned database not found")
        workspace = Workspace(
            name=name,
            project_path=normalized_path,
            database_id=database_id,
            brain_version=brain_version,
        )
        self.session.add(workspace)
        try:
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            raise ValueError(f"A workspace for {normalized_path!r} already exists") from None
        self.session.refresh(workspace)
        return workspace

    def get_workspace(self, workspace_id: int) -> Workspace | None:
        return self.session.get(Workspace, workspace_id)

    def list_workspaces(self) -> list[Workspace]:
        return list(self.session.scalars(select(Workspace).order_by(Workspace.name)))

    def switch_workspace(self, workspace_id: int) -> Workspace | None:
        workspace = self.get_workspace(workspace_id)
        if workspace is None:
            return None
        if not self.database_manager.test_connection(workspace.database_id):
            raise ConnectionError("Unable to connect to the workspace Neo4j database")
        workspace.last_opened = datetime.utcnow()
        self.session.commit()
        self.session.refresh(workspace)
        return workspace

    def delete_workspace(self, workspace_id: int) -> bool:
        workspace = self.get_workspace(workspace_id)
        if workspace is None:
            return False
        self.session.delete(workspace)
        self.session.commit()
        return True

    def change_database(self, workspace_id: int, database_id: int, move_existing_graph: bool = False) -> Workspace | None:
        workspace = self.get_workspace(workspace_id)
        if workspace is None:
            return None
        if self.session.get(Database, database_id) is None:
            raise ValueError("Assigned database not found")
        if not self.database_manager.test_connection(database_id):
            raise ConnectionError("Unable to connect to the target Neo4j database")
        if move_existing_graph:
            self.database_manager.migrate_graph(workspace.database_id, database_id, workspace.id)
        workspace.database_id = database_id
        self.session.commit()
        self.session.refresh(workspace)
        return workspace