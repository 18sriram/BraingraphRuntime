from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.services.brain_scanner import BrainScanner
from app.services.database_manager import DatabaseManager
from app.services.workspace_manager import WorkspaceManager
from app.services.graph_backup import GraphBackupService

router = APIRouter(prefix="/api/workspaces", tags=["scanner"])


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/{workspace_id}/scan")
def scan_workspace(workspace_id: int, db: Session = Depends(get_db)) -> dict[str, object]:
    workspace = WorkspaceManager(db).get_workspace(workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    project_path = os.getenv("BRAINGRAPH_SCAN_PATH", workspace.project_path)
    try:
        database_manager = DatabaseManager(db)
        driver = database_manager.create_driver(workspace.database_id)
        try:
            result = BrainScanner(driver, database_manager.get_database_name(workspace.database_id)).scan(
                project_path, workspace_id
            )
        finally:
            driver.close()
    except (OSError, ValueError) as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return {
        "files_scanned": result.files_scanned,
        "files_skipped": result.files_skipped,
        "nodes_created": result.nodes_created,
        "relationships_created": result.relationships_created,
        "errors": result.errors,
    }


@router.get("/{workspace_id}/graph/export")
def export_workspace_graph(workspace_id: int, db: Session = Depends(get_db)) -> dict[str, object]:
    try:
        return GraphBackupService(db).export_workspace(workspace_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post("/{workspace_id}/graph/import")
def import_workspace_graph(workspace_id: int, backup: dict[str, object], db: Session = Depends(get_db)) -> dict[str, object]:
    try:
        return GraphBackupService(db).import_workspace(workspace_id, backup)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error