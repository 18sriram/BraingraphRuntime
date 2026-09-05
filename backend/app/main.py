from __future__ import annotations

from fastapi import FastAPI

from app.api.routes.graph import router as graph_router
from app.api.routes.dashboard import router as dashboard_router
from app.api.routes.health import router as health_router
from app.api.routes.scheduler import router as scheduler_router
from app.api.routes.databases import router as databases_router
from app.api.routes.workspaces import router as workspaces_router
from app.api.routes.scanner import router as scanner_router
from app.api.routes.workspace_context import router as workspace_context_router
from app.api.routes.agent_runtime import router as agent_runtime_router
from app.api.routes.workflows import router as workflows_router
from app.api.routes.local_models import router as local_models_router
from app.core.database import Base, engine
from app.models.database import Database
from app.models.agent_runtime import AgentRuntimeRecord, AgentTransitionRecord
from app.models.scheduled_prompt import ScheduledPrompt
from app.models.workflow import Workflow, WorkflowNode

app = FastAPI(
    title="BrainGraph Runtime",
    version="0.1.0",
    description="Infrastructure-first local AI orchestration runtime scaffold.",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.include_router(health_router)
app.include_router(graph_router)
app.include_router(scheduler_router)
app.include_router(dashboard_router)
app.include_router(databases_router)
app.include_router(workspaces_router)
app.include_router(scanner_router)
app.include_router(workspace_context_router)
app.include_router(agent_runtime_router)
app.include_router(workflows_router)
app.include_router(local_models_router)


@app.on_event("startup")
def initialize_database() -> None:
    Base.metadata.create_all(bind=engine)


@app.get("/", tags=["meta"]) 
def root() -> dict[str, str]:
    """Return a basic root message for startup verification."""
    return {"message": "BrainGraph Runtime is starting"}
