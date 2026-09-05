from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.api.routes.scheduler import get_scheduler
from app.gateway.schemas import ProviderStatus
from app.main import app
from app.scheduler.schemas import SchedulerStateStore
from app.scheduler.service import SchedulerService


class FakeGateway:
    provider = type("Provider", (), {"provider_name": "test-provider"})()

    def __init__(self, available: list[bool]) -> None:
        self.available = available

    def quota_status(self) -> ProviderStatus:
        return ProviderStatus(provider="test-provider", available=self.available.pop(0))


def test_scheduler_persists_and_restores_all_required_state(tmp_path: Path) -> None:
    service = SchedulerService(FakeGateway([True]), SchedulerStateStore(str(tmp_path / "state.json")))
    state = service.save_state(
        task_id="task-1",
        current_task="Fix authentication",
        current_iteration=3,
        pending_actions=[{"type": "run_tests", "parameters": {}}],
        graph_snapshot_id="snapshot-3",
        waiting=True,
    )

    restored = service.restore_state("task-1")

    assert restored == state
    assert restored.selected_provider == "test-provider"
    assert restored.pending_actions[0].type == "run_tests"


def test_wait_for_reset_uses_configured_interval_and_resumes(tmp_path: Path) -> None:
    delays: list[float] = []
    service = SchedulerService(
        FakeGateway([False, True]),
        SchedulerStateStore(str(tmp_path / "state.json")),
        poll_interval_seconds=12,
        sleep=delays.append,
    )
    service.save_state("task-1", "Fix authentication", 1, [], waiting=True)

    resumed = service.wait_for_reset("task-1")

    assert delays == [12]
    assert resumed.waiting is False
    assert resumed.resumed_at is not None


def test_scheduler_status_endpoint_returns_persisted_state(tmp_path: Path, monkeypatch) -> None:
    state_store = SchedulerStateStore(str(tmp_path / "state.json"))
    service = SchedulerService(FakeGateway([True]), state_store)
    service.save_state("task-1", "Fix authentication", 2, [], graph_snapshot_id="snapshot-2")
    monkeypatch.setattr("app.api.routes.scheduler.get_scheduler", lambda: service)

    response = TestClient(app).get("/scheduler/task-1")

    assert response.status_code == 200
    assert response.json()["state"]["current_iteration"] == 2
    assert response.json()["state"]["graph_snapshot_id"] == "snapshot-2"