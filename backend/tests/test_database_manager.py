from __future__ import annotations

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.main import app
from app.models.database import Database
from app.services.database_manager import DatabaseManager


def make_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'databases.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)()


def test_manager_encrypts_password_and_switches_active_database(tmp_path) -> None:
    session = make_session(tmp_path)
    try:
        manager = DatabaseManager(session, secret_key=Fernet.generate_key().decode(), key_file=tmp_path / "key")
        first = manager.add_database("first", "localhost", 7687, "neo4j", "secret")
        second = manager.add_database("second", "localhost", 8687, "neo4j", "other-secret")

        assert first.encrypted_password != "secret"
        assert manager.set_active(first.id).is_active is True
        assert manager.set_active(second.id).id == second.id
        assert manager.get_active().id == second.id
        assert all(database.is_active is (database.id == second.id) for database in manager.list_databases())
    finally:
        session.close()


def test_manager_uses_local_key_file(tmp_path) -> None:
    session = make_session(tmp_path)
    key_file = tmp_path / "key"
    try:
        manager = DatabaseManager(session, key_file=key_file)
        database = manager.add_database("local", "localhost", 7687, "neo4j", "secret")
        assert key_file.exists()
        assert manager.fernet.decrypt(database.encrypted_password.encode()) == b"secret"
    finally:
        session.close()


def test_database_routes_do_not_return_password(tmp_path, monkeypatch) -> None:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'api.db'}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override_get_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    from app.api.routes.databases import get_db
    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setenv("DATABASE_ENCRYPTION_KEY", Fernet.generate_key().decode())
    try:
        with TestClient(app) as client:
            response = client.post("/api/databases", json={
                "name": "api-db",
                "host": "localhost",
                "username": "neo4j",
                "password": "secret",
            })
            assert response.status_code == 201
            assert "password" not in response.json()
            assert client.get("/api/databases/active").status_code == 404
            assert client.post(f"/api/databases/{response.json()['id']}/activate").status_code == 200
            assert client.get("/api/databases/active").json()["name"] == "api-db"
    finally:
        app.dependency_overrides.clear()
