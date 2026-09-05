from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.schemas.workspace import WorkspaceCreate, WorkspaceDatabaseChange, WorkspaceRead
from app.services.workspace_manager import WorkspaceManager

router = APIRouter(prefix="/api/workspaces", tags=["workspaces"])


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("", response_model=WorkspaceRead, status_code=status.HTTP_201_CREATED)
def register_workspace(payload: WorkspaceCreate, db: Session = Depends(get_db)) -> WorkspaceRead:
    try:
        return WorkspaceManager(db).register_workspace(**payload.model_dump())
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


@router.get("", response_model=list[WorkspaceRead])
def list_workspaces(db: Session = Depends(get_db)) -> list[WorkspaceRead]:
    return WorkspaceManager(db).list_workspaces()


@router.get("/{workspace_id}", response_model=WorkspaceRead)
def get_workspace(workspace_id: int, db: Session = Depends(get_db)) -> WorkspaceRead:
    workspace = WorkspaceManager(db).get_workspace(workspace_id)
    if workspace is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    return workspace


@router.post("/{workspace_id}/switch", response_model=WorkspaceRead)
def switch_workspace(workspace_id: int, db: Session = Depends(get_db)) -> WorkspaceRead:
    try:
        workspace = WorkspaceManager(db).switch_workspace(workspace_id)
    except ConnectionError as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error
    if workspace is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    return workspace


@router.post("/{workspace_id}/database", response_model=WorkspaceRead)
def change_workspace_database(workspace_id: int, payload: WorkspaceDatabaseChange, db: Session = Depends(get_db)) -> WorkspaceRead:
    try:
        workspace = WorkspaceManager(db).change_database(
            workspace_id, payload.database_id, payload.move_existing_graph
        )
    except ConnectionError as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    if workspace is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    return workspace


@router.delete("/{workspace_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_workspace(workspace_id: int, db: Session = Depends(get_db)) -> None:
    if not WorkspaceManager(db).delete_workspace(workspace_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")