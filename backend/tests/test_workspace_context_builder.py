from __future__ import annotations

from pathlib import Path

from git import Repo
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.workspace import Workspace
from app.repositories.graph_repository import GraphRepository
from app.schemas.graph import GraphNodeCreate, GraphRelationshipCreate
from app.services.workspace_context_builder import WorkspaceContextBuilder


def test_workspace_context_contains_workspace_git_and_graph_data(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    repository = Repo.init(project)
    tracked = project / "main.py"
    tracked.write_text("print('hello')", encoding="utf-8")
    repository.index.add([str(tracked)])
    repository.index.commit("initial project")
    tracked.write_text("print('changed')", encoding="utf-8")

    engine = create_engine(f"sqlite:///{tmp_path / 'context.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    graph = GraphRepository()
    task = graph.create_node(GraphNodeCreate(type="Task", name="Review project", properties={"workspace_id": 5}))
    file_node = graph.create_node(GraphNodeCreate(type="File", name="main.py", properties={"workspace_id": 5}))
    graph.create_relationship(GraphRelationshipCreate(
        source_id=task.id, target_id=file_node.id, type="CONTAINS"
    ))
    session.add(Workspace(name="Project", project_path=str(project), database_id=9, brain_version="1.0"))
    session.commit()
    workspace_id = session.query(Workspace).one().id

    try:
        context = WorkspaceContextBuilder(session, graph).build(workspace_id, current_task=task.id)
        assert context.workspace_name == "Project"
        assert context.database_id == 9
        assert context.current_branch == "master" or context.current_branch == "main"
        assert "main.py" in context.modified_files
        assert context.recent_commits[0]["message"] == "initial project"
        assert any(node["id"] == task.id for node in context.relevant_graph_nodes)
        assert context.current_task == "Review project"
    finally:
        session.close()
