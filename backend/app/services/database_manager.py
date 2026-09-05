from __future__ import annotations

import os
from pathlib import Path

from cryptography.fernet import Fernet
from neo4j import GraphDatabase
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.database import Database


class DatabaseManager:
    """Manage local Neo4j connections and their encrypted credentials."""

    def __init__(self, session: Session, secret_key: str | None = None, key_file: str | Path = ".database.key") -> None:
        self.session = session
        self.fernet = Fernet(self._get_secret(secret_key, key_file))

    @staticmethod
    def _get_secret(secret_key: str | None, key_file: str | Path) -> bytes:
        configured = secret_key or os.getenv("DATABASE_ENCRYPTION_KEY")
        if configured:
            return configured.encode()
        path = Path(key_file)
        if path.exists():
            return path.read_bytes().strip()
        key = Fernet.generate_key()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(key)
        try:
            path.chmod(0o600)
        except OSError:
            pass
        return key

    def add_database(self, name: str, host: str, bolt_port: int, username: str, password: str, default_database: str = "neo4j") -> Database:
        database = Database(
            name=name,
            host=host,
            bolt_port=bolt_port,
            username=username,
            encrypted_password=self.fernet.encrypt(password.encode()).decode(),
            default_database=default_database,
        )
        self.session.add(database)
        try:
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            raise ValueError(f"A database named {name!r} already exists") from None
        self.session.refresh(database)
        return database

    def remove_database(self, database_id: int) -> bool:
        database = self._get(database_id)
        if database is None:
            return False
        self.session.delete(database)
        self.session.commit()
        return True

    def update_database(self, database_id: int, **fields: object) -> Database | None:
        database = self._get(database_id)
        if database is None:
            return None
        password = fields.pop("password", None)
        for field, value in fields.items():
            if value is not None and hasattr(database, field):
                setattr(database, field, value)
        if password is not None:
            database.encrypted_password = self.fernet.encrypt(str(password).encode()).decode()
        try:
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            raise ValueError("A database with that name already exists") from None
        self.session.refresh(database)
        return database

    def list_databases(self) -> list[Database]:
        return list(self.session.scalars(select(Database).order_by(Database.name)))

    def set_active(self, database_id: int) -> Database | None:
        database = self._get(database_id)
        if database is None:
            return None
        self.session.execute(update(Database).values(is_active=False))
        database.is_active = True
        self.session.commit()
        self.session.refresh(database)
        return database

    def get_active(self) -> Database | None:
        return self.session.scalar(select(Database).where(Database.is_active.is_(True)))

    def test_connection(self, database_id: int) -> bool:
        database = self._get(database_id)
        if database is None:
            return False
        password = self.fernet.decrypt(database.encrypted_password.encode()).decode()
        driver = self.create_driver(database_id)
        try:
            driver.verify_connectivity()
            return True
        except Exception:
            return False
        finally:
            driver.close()

    def create_driver(self, database_id: int):
        database = self._get(database_id)
        if database is None:
            raise ValueError("Database not found")
        password = self.fernet.decrypt(database.encrypted_password.encode()).decode()
        return GraphDatabase.driver(
            f"bolt://{database.host}:{database.bolt_port}",
            auth=(database.username, password),
        )

    def get_database_name(self, database_id: int) -> str:
        database = self._get(database_id)
        if database is None:
            raise ValueError("Database not found")
        return database.default_database

    def migrate_graph(self, source_database_id: int, target_database_id: int, workspace_id: int) -> int:
        """Copy this workspace's BrainNode graph between configured Neo4j databases."""
        if source_database_id == target_database_id:
            return 0
        source = self.create_driver(source_database_id)
        target = self.create_driver(target_database_id)
        try:
            source_name = self.get_database_name(source_database_id)
            target_name = self.get_database_name(target_database_id)
            with source.session(database=source_name) as source_session:
                nodes = list(source_session.run(
                    "MATCH (n:BrainNode {workspace_id: $workspace_id}) "
                    "RETURN labels(n) AS labels, properties(n) AS properties",
                    workspace_id=workspace_id,
                ))
                relationships = list(source_session.run(
                    "MATCH (source:BrainNode {workspace_id: $workspace_id})-[r]->"
                    "(target:BrainNode {workspace_id: $workspace_id}) "
                    "RETURN source.node_type AS source_type, source.name AS source_name, "
                    "source.path AS source_path, target.node_type AS target_type, "
                    "target.name AS target_name, target.path AS target_path, type(r) AS relationship_type, "
                    "properties(r) AS properties",
                    workspace_id=workspace_id,
                ))
            with target.session(database=target_name) as target_session:
                for node in nodes:
                    target_session.run(
                        "MERGE (n:BrainNode {node_type: $node_type, name: $name, path: $path, workspace_id: $workspace_id}) "
                        "SET n += $properties",
                        node_type=node["properties"].get("node_type", "Unknown"),
                        name=node["properties"].get("name", ""), path=node["properties"].get("path", ""),
                        workspace_id=workspace_id, properties=node["properties"],
                    ).consume()
                for relationship in relationships:
                    target_session.run(
                        "MATCH (source:BrainNode {node_type: $source_type, name: $source_name, path: $source_path, workspace_id: $workspace_id}) "
                        "MATCH (target:BrainNode {node_type: $target_type, name: $target_name, path: $target_path, workspace_id: $workspace_id}) "
                        f"MERGE (source)-[r:{relationship['relationship_type']}]->(target) SET r += $properties",
                        source_type=relationship["source_type"], source_name=relationship["source_name"],
                        source_path=relationship["source_path"], target_type=relationship["target_type"],
                        target_name=relationship["target_name"], target_path=relationship["target_path"],
                        workspace_id=workspace_id, properties=relationship["properties"],
                    ).consume()
            return len(nodes)
        finally:
            source.close()
            target.close()

    def _get(self, database_id: int) -> Database | None:
        return self.session.get(Database, database_id)