from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


MemoryLayer = Literal["graph", "artifact", "episodic"]


class MemoryReference(BaseModel):
    id: str
    type: str
    name: str
    properties: dict[str, Any] = Field(default_factory=dict)


class RelevantContext(BaseModel):
    task: str
    task_reference: MemoryReference
    files: list[str] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    experiments: list[str] = Field(default_factory=list)
    graph_memory: list[MemoryReference] = Field(default_factory=list)
    artifact_memory: list[MemoryReference] = Field(default_factory=list)
    episodic_memory: list[MemoryReference] = Field(default_factory=list)
    relationships: list[dict[str, Any]] = Field(default_factory=list)
