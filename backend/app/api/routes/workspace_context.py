from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.schemas.workspace_context import WorkspaceContext
from app.services.workspace_context_builder import WorkspaceContextBuilder

router = APIRouter(prefix="/api/workspaces", tags=["workspace-context"])


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/{workspace_id}/context", response_model=WorkspaceContext)
def get_workspace_context(workspace_id: int, task: str | None = None, db: Session = Depends(get_db)) -> WorkspaceContext:
    try:
        return WorkspaceContextBuilder(db).build(workspace_id, current_task=task)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error