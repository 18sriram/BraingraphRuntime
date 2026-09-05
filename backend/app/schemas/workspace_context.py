from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class WorkspaceContext(BaseModel):
    workspace_id: int
    workspace_name: str
    project_path: str
    database_id: int
    brain_version: str
    current_branch: str | None = None
    modified_files: list[str] = Field(default_factory=list)
    recent_commits: list[dict[str, Any]] = Field(default_factory=list)
    relevant_graph_nodes: list[dict[str, Any]] = Field(default_factory=list)
    current_task: str | None = None
    generated_at: datetime