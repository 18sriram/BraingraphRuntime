from __future__ import annotations

from neo4j import GraphDatabase

from app.config.settings import get_settings

settings = get_settings()


def get_graph_driver():
    """Create a Neo4j driver instance for graph-backed runtime memory.

    This is intentionally infrastructure-focused and does not implement any domain
    logic yet. The driver is created lazily so that startup remains simple.
    """
    return GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
        database=None,
    )
