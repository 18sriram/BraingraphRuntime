from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.workflow import Workflow, WorkflowNode
from app.services.workflow_engine import WorkflowEngine

router = APIRouter(prefix="/api/workflows", tags=["workflows"])


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class WorkflowCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)


class WorkflowNodeCreate(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    workflow_id: int = Field(gt=0)
    title: str = Field(min_length=1, max_length=255)
    type: str = Field(pattern=r"^(TASK|CONDITION|ACTION|SUCCESS|FAILURE|WAIT)$")
    next_success: int | None = None
    next_failure: int | None = None
    condition: str | None = None
    action: str | None = None


class WorkflowNodeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    workflow_id: int
    title: str
    type: str
    next_success: int | None
    next_failure: int | None
    condition: str | None
    action: str | None


class WorkflowRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


@router.post("", response_model=WorkflowRead, status_code=status.HTTP_201_CREATED)
def create_workflow(payload: WorkflowCreate, db: Session = Depends(get_db)) -> WorkflowRead:
    workflow = WorkflowEngine(db).create_workflow(payload.name)
    return WorkflowRead.model_validate(workflow)


@router.get("", response_model=list[WorkflowRead])
def list_workflows(db: Session = Depends(get_db)) -> list[WorkflowRead]:
    workflows = WorkflowEngine(db).list_workflows()
    return [WorkflowRead.model_validate(item) for item in workflows]


@router.get("/{workflow_id}", response_model=WorkflowRead)
def get_workflow(workflow_id: int, db: Session = Depends(get_db)) -> WorkflowRead:
    workflow = WorkflowEngine(db).get_workflow(workflow_id)
    if workflow is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")
    return WorkflowRead.model_validate(workflow)


@router.delete("/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_workflow(workflow_id: int, db: Session = Depends(get_db)) -> Response:
    workflow = WorkflowEngine(db).get_workflow(workflow_id)
    if workflow is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")
    db.delete(workflow)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{workflow_id}/nodes", response_model=WorkflowNodeRead, status_code=status.HTTP_201_CREATED)
def create_node(workflow_id: int, payload: WorkflowNodeCreate, db: Session = Depends(get_db)) -> WorkflowNodeRead:
    engine = WorkflowEngine(db)
    if payload.workflow_id != workflow_id:
        payload.workflow_id = workflow_id
    node = engine.create_node(
        workflow_id,
        title=payload.title,
        type=payload.type,
        next_success=payload.next_success,
        next_failure=payload.next_failure,
        condition=payload.condition,
        action=payload.action,
    )
    return WorkflowNodeRead.model_validate(node)


@router.get("/{workflow_id}/nodes", response_model=list[WorkflowNodeRead])
def list_nodes(workflow_id: int, db: Session = Depends(get_db)) -> list[WorkflowNodeRead]:
    engine = WorkflowEngine(db)
    nodes = engine.list_nodes(workflow_id)
    return [WorkflowNodeRead.model_validate(node) for node in nodes]


@router.get("/{workflow_id}/nodes/{node_id}", response_model=WorkflowNodeRead)
def get_node(workflow_id: int, node_id: int, db: Session = Depends(get_db)) -> WorkflowNodeRead:
    engine = WorkflowEngine(db)
    node = engine.get_node(workflow_id, node_id)
    if node is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node not found")
    return WorkflowNodeRead.model_validate(node)


@router.put("/{workflow_id}/nodes/{node_id}", response_model=WorkflowNodeRead)
def update_node(workflow_id: int, node_id: int, payload: WorkflowNodeCreate, db: Session = Depends(get_db)) -> WorkflowNodeRead:
    engine = WorkflowEngine(db)
    data = payload.model_dump(exclude_none=True)
    data.pop("workflow_id", None)
    node = engine.update_node(workflow_id, node_id, **data)
    return WorkflowNodeRead.model_validate(node)


@router.delete("/{workflow_id}/nodes/{node_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_node(workflow_id: int, node_id: int, db: Session = Depends(get_db)) -> Response:
    engine = WorkflowEngine(db)
    if not engine.delete_node(workflow_id, node_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{workflow_id}/execute")
def execute_workflow(workflow_id: int, payload: dict[str, object] | None = None, db: Session = Depends(get_db)) -> dict[str, object]:
    engine = WorkflowEngine(db)
    context = payload.get("context", {}) if payload else {}
    start_node_id = payload.get("start_node_id") if payload else None
    return engine.execute(workflow_id, context=context if isinstance(context, dict) else {}, start_node_id=int(start_node_id) if isinstance(start_node_id, int) else None)
