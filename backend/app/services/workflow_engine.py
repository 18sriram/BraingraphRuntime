from __future__ import annotations

import ast
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import Base
from app.models.workflow import Workflow, WorkflowNode


class WorkflowEngine:
    """Execute workflow graphs stored in SQLite with conditional branching."""

    def __init__(self, session: Session) -> None:
        self.session = session
        if self.session.bind is not None:
            Base.metadata.create_all(bind=self.session.bind)

    def create_workflow(self, name: str) -> Workflow:
        workflow = Workflow(name=name)
        self.session.add(workflow)
        self.session.commit()
        self.session.refresh(workflow)
        return workflow

    def list_workflows(self) -> list[Workflow]:
        return self.session.execute(select(Workflow)).scalars().all()

    def get_workflow(self, workflow_id: int) -> Workflow | None:
        return self.session.get(Workflow, workflow_id)

    def create_node(self, workflow_id: int, *, title: str, type: str, next_success: int | None = None, next_failure: int | None = None, condition: str | None = None, action: str | None = None) -> WorkflowNode:
        workflow = self.get_workflow(workflow_id)
        if workflow is None:
            raise ValueError(f"Workflow {workflow_id} not found")

        node = WorkflowNode(
            workflow_id=workflow_id,
            title=title,
            type=type,
            next_success=next_success,
            next_failure=next_failure,
            condition=condition,
            action=action,
        )
        self.session.add(node)
        self.session.commit()
        self.session.refresh(node)
        return node

    def list_nodes(self, workflow_id: int) -> list[WorkflowNode]:
        workflow = self.get_workflow(workflow_id)
        if workflow is None:
            raise ValueError(f"Workflow {workflow_id} not found")
        return self.session.execute(select(WorkflowNode).where(WorkflowNode.workflow_id == workflow_id)).scalars().all()

    def get_node(self, workflow_id: int, node_id: int) -> WorkflowNode | None:
        return self.session.execute(select(WorkflowNode).where(WorkflowNode.workflow_id == workflow_id, WorkflowNode.id == node_id)).scalar_one_or_none()

    def update_node(self, workflow_id: int, node_id: int, **values: Any) -> WorkflowNode:
        node = self.get_node(workflow_id, node_id)
        if node is None:
            raise ValueError(f"Node {node_id} not found in workflow {workflow_id}")
        for key, value in values.items():
            if hasattr(node, key):
                setattr(node, key, value)
        self.session.add(node)
        self.session.commit()
        self.session.refresh(node)
        return node

    def delete_node(self, workflow_id: int, node_id: int) -> bool:
        node = self.get_node(workflow_id, node_id)
        if node is None:
            return False
        self.session.delete(node)
        self.session.commit()
        return True

    def execute(self, workflow_id: int, context: dict[str, Any] | None = None, start_node_id: int | None = None) -> dict[str, Any]:
        workflow = self.get_workflow(workflow_id)
        if workflow is None:
            raise ValueError(f"Workflow {workflow_id} not found")

        context = dict(context or {})
        nodes_by_id = {node.id: node for node in self.list_nodes(workflow_id)}
        if not nodes_by_id:
            return {"status": "failed", "path": [], "context": context, "message": "No workflow nodes found"}

        current_id = start_node_id or next(iter(nodes_by_id))
        path: list[int] = []
        visited: set[int] = set()
        while current_id in nodes_by_id and current_id not in visited:
            visited.add(current_id)
            path.append(current_id)
            node = nodes_by_id[current_id]

            if node.action:
                context = self._apply_action(context, node.action)

            if node.type == "SUCCESS":
                return {"status": "success", "path": path, "context": context}
            if node.type == "FAILURE":
                return {"status": "failed", "path": path, "context": context}

            if node.type == "WAIT":
                current_id = node.next_success or current_id
                continue

            if node.type == "CONDITION":
                result = self._evaluate_condition(context, node.condition)
                current_id = node.next_success if result else node.next_failure
                continue

            if node.type in {"TASK", "ACTION"}:
                current_id = node.next_success if node.next_success is not None else node.next_failure
                if current_id is None:
                    break
                continue

            if node.next_success is not None:
                current_id = node.next_success
                continue
            break

        return {"status": "completed", "path": path, "context": context}

    def _apply_action(self, context: dict[str, Any], action: str) -> dict[str, Any]:
        safe_context = dict(context)
        namespace = {"context": safe_context, "__builtins__": {}}
        try:
            exec(action, namespace, namespace)
            return namespace["context"]
        except Exception:
            return {**safe_context, "last_error": f"Failed to execute action: {action}"}

    def _evaluate_condition(self, context: dict[str, Any], condition: str | None) -> bool:
        if not condition:
            return False
        try:
            namespace = {"__builtins__": {}, "context": context}
            namespace.update(context)
            return bool(eval(condition, namespace, namespace))
        except Exception:
            return False
