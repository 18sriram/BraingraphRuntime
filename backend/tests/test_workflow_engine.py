from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.database import Base
from app.models.workflow import Workflow, WorkflowNode
from app.main import app
from app.services.workflow_engine import WorkflowEngine


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)()


def test_workflow_engine_traverses_condition_branch_from_sqlite_data() -> None:
    session = _session()
    workflow = Workflow(name="deployment")
    session.add(workflow)
    session.commit()
    session.refresh(workflow)

    start = WorkflowNode(
        workflow_id=workflow.id,
        title="Start",
        type="TASK",
        next_success=0,
        next_failure=0,
        condition=None,
        action="context['status'] = 'ok'",
    )
    condition = WorkflowNode(
        workflow_id=workflow.id,
        title="Check status",
        type="CONDITION",
        next_success=0,
        next_failure=0,
        condition="context.get('status') == 'ok'",
        action=None,
    )
    success = WorkflowNode(
        workflow_id=workflow.id,
        title="Deploy",
        type="SUCCESS",
        next_success=None,
        next_failure=None,
        condition=None,
        action=None,
    )
    failure = WorkflowNode(
        workflow_id=workflow.id,
        title="Abort",
        type="FAILURE",
        next_success=None,
        next_failure=None,
        condition=None,
        action=None,
    )
    session.add_all([start, condition, success, failure])
    session.commit()

    # mirror the graph connections by updating the persisted rows
    start.next_success = condition.id
    condition.next_success = success.id
    condition.next_failure = failure.id
    session.add_all([start, condition])
    session.commit()

    engine = WorkflowEngine(session)
    result = engine.execute(workflow.id, context={"status": "ok"}, start_node_id=start.id)

    assert result["path"] == [start.id, condition.id, success.id]
    assert result["status"] == "success"


def test_workflow_routes_support_crud() -> None:
    session = _session()
    app.dependency_overrides.clear()

    def override_db():
        yield session

    app.dependency_overrides["app.api.routes.workflows.get_db"] = override_db

    client = TestClient(app)
    create_payload = {"name": "build"}
    response = client.post("/api/workflows", json=create_payload)
    assert response.status_code == 201
    workflow_id = response.json()["id"]

    node_payload = {
        "workflow_id": workflow_id,
        "title": "Check test result",
        "type": "CONDITION",
        "condition": "passed == True",
        "next_success": None,
        "next_failure": None,
        "action": None,
    }
    response = client.post(f"/api/workflows/{workflow_id}/nodes", json=node_payload)
    assert response.status_code == 201
    node = response.json()
    assert node["title"] == "Check test result"

    response = client.get(f"/api/workflows/{workflow_id}/nodes")
    assert response.status_code == 200
    assert len(response.json()) == 1

    app.dependency_overrides.clear()
