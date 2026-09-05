from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from threading import Event, Lock, Thread
from typing import Callable

from app.agent_loop.schemas import AgentAction
from app.gateway.gateway import ModelGateway
from app.scheduler.schemas import SchedulerState, SchedulerStateStore


class SchedulerService:
    """Quota-aware persistence and resume coordination for paused agent runs."""

    def __init__(
        self,
        gateway: ModelGateway,
        state_store: SchedulerStateStore,
        poll_interval_seconds: float = 30.0,
        resume_callback: Callable[[SchedulerState], None] | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be greater than zero")
        self.gateway = gateway
        self.state_store = state_store
        self.poll_interval_seconds = poll_interval_seconds
        self.resume_callback = resume_callback
        self.sleep = sleep
        self._lock = Lock()
        self._watchers: dict[str, tuple[Thread, Event]] = {}

    def save_state(
        self,
        task_id: str,
        current_task: str,
        current_iteration: int,
        pending_actions: list[AgentAction],
        graph_snapshot_id: str | None = None,
        selected_provider: str | None = None,
        *,
        waiting: bool = True,
        quota_available: bool | None = None,
        last_error: str | None = None,
    ) -> SchedulerState:
        provider = selected_provider or getattr(self.gateway.provider, "provider_name", "unknown")
        state = SchedulerState(
            task_id=task_id,
            current_task=current_task,
            current_iteration=current_iteration,
            pending_actions=pending_actions,
            selected_provider=provider,
            graph_snapshot_id=graph_snapshot_id,
            waiting=waiting,
            quota_available=quota_available,
            last_error=last_error,
        )
        self.state_store.save(state)
        return state

    def restore_state(self, task_id: str) -> SchedulerState | None:
        return self.state_store.load(task_id)

    def check_quota(self, task_id: str) -> bool:
        state = self._required_state(task_id)
        status = self.gateway.quota_status()
        now = datetime.now(timezone.utc)
        state.quota_available = status.available
        state.last_checked_at = now
        state.next_check_at = now + timedelta(seconds=self.poll_interval_seconds)
        state.last_error = status.message if not status.available else None
        self.state_store.save(state)
        return status.available

    def wait_for_reset(self, task_id: str, max_checks: int | None = None) -> SchedulerState:
        """Wait between quota checks and resume once available; never busy-polls."""
        state = self._required_state(task_id)
        checks = 0
        while True:
            if self.check_quota(task_id):
                return self.resume(task_id)
            checks += 1
            if max_checks is not None and checks >= max_checks:
                return self._required_state(task_id)
            self.sleep(self.poll_interval_seconds)

    def resume(self, task_id: str) -> SchedulerState:
        state = self._required_state(task_id)
        state.waiting = False
        state.resumed_at = datetime.now(timezone.utc)
        self.state_store.save(state)
        if self.resume_callback is not None:
            self.resume_callback(state)
        return state

    def start_auto_resume(self, task_id: str) -> None:
        with self._lock:
            if task_id in self._watchers and self._watchers[task_id][0].is_alive():
                return
            stop = Event()

            def watch() -> None:
                while not stop.is_set():
                    state = self._required_state(task_id)
                    if self.check_quota(task_id):
                        self.resume(task_id)
                        return
                    stop.wait(self.poll_interval_seconds)

            thread = Thread(target=watch, name=f"quota-watch-{task_id}", daemon=True)
            self._watchers[task_id] = (thread, stop)
            thread.start()

    def stop_auto_resume(self, task_id: str) -> None:
        with self._lock:
            watcher = self._watchers.pop(task_id, None)
            if watcher is not None:
                watcher[1].set()

    def _required_state(self, task_id: str) -> SchedulerState:
        state = self.restore_state(task_id)
        if state is None:
            raise KeyError(f"No scheduler state found for task: {task_id}")
        return state