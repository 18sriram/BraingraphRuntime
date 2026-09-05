from fastapi.testclient import TestClient

from app.main import app


def test_dashboard_websocket_sends_live_heartbeat() -> None:
    with TestClient(app).websocket_connect("/ws/dashboard") as websocket:
        event = websocket.receive_json()

    assert event["type"] == "heartbeat"
    assert event["agent_status"] == "IDLE"
    assert event["quota"]["limit"] == 100
