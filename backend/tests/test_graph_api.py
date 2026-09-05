from fastapi.testclient import TestClient

from app.main import app


def test_graph_api_returns_graph_payload() -> None:
    client = TestClient(app)
    response = client.get("/graph")

    assert response.status_code == 200
    payload = response.json()
    assert "nodes" in payload
    assert "edges" in payload
    assert isinstance(payload["nodes"], list)
    assert isinstance(payload["edges"], list)
