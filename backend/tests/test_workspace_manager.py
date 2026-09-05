from __future__ import annotations

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.routes.databases import get_db as get_database_db
from app.api.routes.workspaces import get_db
from app.core.database import Base
from app.main import app
from app.services.database_manager import DatabaseManager
from app.services.workspace_manager import WorkspaceManager


def make_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'workspaces.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)()


def test_workspace_path_is_unique_and_switch_connects(tmp_path) -> None:
    session = make_session(tmp_path)
    try:
        manager = DatabaseManager(session, secret_key=Fernet.generate_key().decode(), key_file=tmp_path / "key")
        database = manager.add_database("local", "localhost", 7687, "neo4j", "secret")
        connection_calls: list[int] = []

        class FakeDatabaseManager:
            def test_connection(self, database_id: int) -> bool:
                connection_calls.append(database_id)
                return True

        workspace_manager = WorkspaceManager(session, FakeDatabaseManager())
        workspace = workspace_manager.register_workspace("Project", str(tmp_path / "project"), database.id)
        assert workspace.project_path == str((tmp_path / "project").resolve())
        assert workspace_manager.switch_workspace(workspace.id).last_opened is not None
        assert connection_calls == [database.id]

        try:
            workspace_manager.register_workspace("Duplicate", str(tmp_path / "project"), database.id)
        except ValueError as error:
            assert "already exists" in str(error)
        else:
            raise AssertionError("duplicate project paths must be rejected")
    finally:
        session.close()


def test_switch_does_not_open_when_neo4j_is_unavailable(tmp_path) -> None:
    session = make_session(tmp_path)
    try:
        manager = DatabaseManager(session, secret_key=Fernet.generate_key().decode(), key_file=tmp_path / "key")
        database = manager.add_database("local", "localhost", 7687, "neo4j", "secret")

        class OfflineDatabaseManager:
            def test_connection(self, database_id: int) -> bool:
                return False

        workspace_manager = WorkspaceManager(session, OfflineDatabaseManager())
        workspace = workspace_manager.register_workspace("Project", str(tmp_path / "project"), database.id)
        try:
            workspace_manager.switch_workspace(workspace.id)
        except ConnectionError:
            pass
        else:
            raise AssertionError("offline databases must prevent workspace switching")
        assert workspace_manager.get_workspace(workspace.id).last_opened is None
    finally:
        session.close()


def test_workspace_switch_route_returns_last_opened(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'api.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override_get_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_database_db] = override_get_db
    try:
        with TestClient(app) as client:
            database = client.post("/api/databases", json={
                "name": "local",
                "host": "localhost",
                "username": "neo4j",
                "password": "secret",
            }).json()
            workspace = client.post("/api/workspaces", json={
                "name": "Project",
                "project_path": str(tmp_path / "project"),
                "database_id": database["id"],
            }).json()
            response = client.post(f"/api/workspaces/{workspace['id']}/switch")
            assert response.status_code == 503
    finally:
        app.dependency_overrides.clear()
