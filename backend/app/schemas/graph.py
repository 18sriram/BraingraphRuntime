from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

NodeType = Literal[
    "Project",
    "Goal",
    "Task",
    "Decision",
    "File",
    "Function",
    "Error",
    "Experiment",
    "Result",
    "Observation",
    "Execution",
    "Constraint",
    "Model",
    "GitCommit",
    "TestReport",
    "Log",
    "AgentExecution",
    "Prompt",
    "Response",
    "Iteration",
]

RelationshipType = Literal[
    "HAS_GOAL",
    "HAS_TASK",
    "HAS_DECISION",
    "CONTAINS",
    "MODIFIES",
    "DEPENDS_ON",
    "CAUSED",
    "SOLVED_BY",
    "GENERATED_BY",
    "REFERENCES",
    "EXECUTED_FOR",
    "HAS_PROMPT",
    "HAS_RESPONSE",
    "HAS_ITERATION",
    "GENERATED",
    "OBSERVED",
    "SOLVED",
    "FAILED",
    "LINKED_TO_TASK",
]


class GraphNodeBase(BaseModel):
    type: NodeType
    name: str = Field(..., min_length=1, max_length=255)
    properties: dict[str, Any] = Field(default_factory=dict)


class GraphNodeCreate(GraphNodeBase):
    pass


class GraphNode(GraphNodeBase):
    id: str


class GraphRelationshipBase(BaseModel):
    source_id: str
    target_id: str
    type: RelationshipType
    properties: dict[str, Any] = Field(default_factory=dict)


class GraphRelationshipCreate(GraphRelationshipBase):
    pass


class GraphRelationship(GraphRelationshipBase):
    id: str


class GraphSubgraph(BaseModel):
    nodes: list[GraphNode]
    relationships: list[GraphRelationship]
