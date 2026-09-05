from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    project_path: str = Field(min_length=1, max_length=1024)
    database_id: int = Field(gt=0)
    brain_version: str = Field(default="1.0", min_length=1, max_length=64)


class WorkspaceDatabaseChange(BaseModel):
    database_id: int = Field(gt=0)
    move_existing_graph: bool = False


class WorkspaceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    project_path: str
    database_id: int
    created_at: datetime
    last_opened: datetime | None
    brain_version: str