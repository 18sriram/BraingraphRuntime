from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/graph", tags=["graph"])


@router.get("", summary="Return the graph payload used by the frontend")
def get_graph() -> dict[str, list[dict[str, object]]]:
    """Return a minimal graph payload for UI bootstrapping.

    This is infrastructure scaffolding for the frontend graph view and does not yet
    implement real persistence; the graph repository is planned for the next layer.
    """
    return {
        "nodes": [
            {
                "id": "project-1",
                "type": "Project",
                "label": "BrainGraph Runtime",
                "properties": {"status": "active"},
            },
            {
                "id": "task-1",
                "type": "Task",
                "label": "Implement graph repository",
                "properties": {"priority": "high"},
            },
            {
                "id": "decision-1",
                "type": "Decision",
                "label": "Use Neo4j for graph memory",
                "properties": {"category": "architecture"},
            },
            {
                "id": "file-1",
                "type": "File",
                "label": "graph_repository.py",
                "properties": {"path": "backend/app/repositories"},
            },
            {
                "id": "error-1",
                "type": "Error",
                "label": "Docker permission issue",
                "properties": {"severity": "medium"},
            },
            {
                "id": "experiment-1",
                "type": "Experiment",
                "label": "Graph validation run",
                "properties": {"result": "pass"},
            },
        ],
        "edges": [
            {"id": "edge-1", "source": "project-1", "target": "task-1", "label": "HAS_TASK"},
            {"id": "edge-2", "source": "project-1", "target": "decision-1", "label": "HAS_DECISION"},
            {"id": "edge-3", "source": "task-1", "target": "file-1", "label": "CONTAINS"},
            {"id": "edge-4", "source": "error-1", "target": "task-1", "label": "CAUSED"},
            {"id": "edge-5", "source": "experiment-1", "target": "task-1", "label": "GENERATED_BY"},
        ],
    }
