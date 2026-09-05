from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Callable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.agent_loop.schemas import AgentState
from app.models.agent_runtime import AgentRuntimeRecord, AgentTransitionRecord


class AgentRuntime:
    """Durable event-driven state machine for autonomous agent execution."""

    TRANSITIONS: dict[AgentState, dict[str, AgentState]] = {
        AgentState.OFF: {"prepare": AgentState.READY, "power_on": AgentState.ON, "power_off": AgentState.OFF, "set_autonomous": AgentState.OFF, "set_follow_up_prompts": AgentState.OFF},
        AgentState.ON: {"pause": AgentState.PAUSED, "emergency_stop": AgentState.OFF, "power_off": AgentState.OFF, "set_autonomous": AgentState.ON, "set_follow_up_prompts": AgentState.ON},
        AgentState.READY: {"quota_unavailable": AgentState.WAITING_FOR_QUOTA, "send_first_prompt": AgentState.SENDING_FIRST_PROMPT, "stop": AgentState.OFF, "power_off": AgentState.OFF},
        AgentState.WAITING_FOR_QUOTA: {"quota_available": AgentState.SENDING_FIRST_PROMPT, "pause": AgentState.PAUSED, "stop": AgentState.OFF, "power_off": AgentState.OFF},
        AgentState.SENDING_FIRST_PROMPT: {"prompt_sent": AgentState.PLANNING, "failure": AgentState.FAILED, "pause": AgentState.PAUSED, "power_off": AgentState.OFF},
        AgentState.PLANNING: {"plan_ready": AgentState.EXECUTING, "success": AgentState.SUCCESS, "failure": AgentState.FAILED, "pause": AgentState.PAUSED, "abort": AgentState.ABORTED, "power_off": AgentState.OFF},
        AgentState.EXECUTING: {"actions_complete": AgentState.OBSERVING, "failure": AgentState.FAILED, "pause": AgentState.PAUSED, "abort": AgentState.ABORTED, "power_off": AgentState.OFF},
        AgentState.OBSERVING: {"observation_ready": AgentState.DECISION, "failure": AgentState.FAILED},
        AgentState.DECISION: {"continue": AgentState.UPDATING_MEMORY, "success": AgentState.SUCCESS, "pause": AgentState.PAUSED, "abort": AgentState.ABORTED},
        AgentState.UPDATING_MEMORY: {"memory_updated": AgentState.PLANNING, "failure": AgentState.FAILED},
        AgentState.PAUSED: {"resume": AgentState.ON, "stop": AgentState.OFF, "power_off": AgentState.OFF, "abort": AgentState.ABORTED, "emergency_stop": AgentState.OFF, "set_autonomous": AgentState.PAUSED, "set_follow_up_prompts": AgentState.PAUSED},
        AgentState.SUCCESS: {"stop": AgentState.OFF},
        AgentState.FAILED: {"retry": AgentState.READY, "stop": AgentState.OFF},
        AgentState.ABORTED: {"stop": AgentState.OFF},
        AgentState.IDLE: {"prepare": AgentState.READY},
        AgentState.WAITING_QUOTA: {"quota_available": AgentState.SENDING_FIRST_PROMPT},
    }

    def __init__(self, session: Session, task_id: str, event_publisher: Callable[[dict[str, Any]], None] | None = None) -> None:
        self.session = session
        self.task_id = task_id
        self.event_publisher = event_publisher

    def create(self, objective: str, workspace_id: int | None = None, autonomous: bool = False, allow_follow_up_prompts: bool = True) -> AgentRuntimeRecord:
        record = AgentRuntimeRecord(task_id=self.task_id, objective=objective, workspace_id=workspace_id, current_state=AgentState.OFF, autonomous=autonomous, allow_follow_up_prompts=allow_follow_up_prompts, payload_json="{}")
        self.session.add(record)
        try:
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            raise ValueError(f"Runtime already exists for task {self.task_id!r}") from None
        self.session.refresh(record)
        return record

    def get(self) -> AgentRuntimeRecord | None:
        return self.session.query(AgentRuntimeRecord).filter_by(task_id=self.task_id).one_or_none()

    def transition(self, event: str, payload: dict[str, Any] | None = None) -> AgentRuntimeRecord:
        record = self.get()
        if record is None:
            raise ValueError("Agent runtime not found")
        current = AgentState(record.current_state)
        target = self.TRANSITIONS.get(current, {}).get(event)
        if target is None:
            raise ValueError(f"Event {event!r} is not valid from state {current.value}")
        data = payload or {}
        record.current_state = target
        if "autonomous" in data:
            record.autonomous = bool(data["autonomous"])
        if "allow_follow_up_prompts" in data:
            record.allow_follow_up_prompts = bool(data["allow_follow_up_prompts"])
        record.payload_json = json.dumps(data)
        record.iteration += int(data.get("iteration_increment", 0))
        record.updated_at = datetime.utcnow()
        self.session.add(AgentTransitionRecord(task_id=record.task_id, from_state=current.value, to_state=target.value, event=event, payload_json=json.dumps(data)))
        self.session.commit()
        self.session.refresh(record)
        if self.event_publisher is not None:
            self.event_publisher({"type": "agent_transition", "task_id": record.task_id, "from_state": current.value, "to_state": target.value, "event": event, "payload": data})
        return record

    @staticmethod
    def as_dict(record: AgentRuntimeRecord) -> dict[str, Any]:
        return {"task_id": record.task_id, "workspace_id": record.workspace_id, "objective": record.objective, "state": record.current_state, "iteration": record.iteration, "autonomous": record.autonomous, "allow_follow_up_prompts": record.allow_follow_up_prompts, "payload": json.loads(record.payload_json), "updated_at": record.updated_at}

    @staticmethod
    def permits_model_call(record: AgentRuntimeRecord) -> bool:
        return record.current_state == AgentState.ON

    @staticmethod
    def permits_execution(record: AgentRuntimeRecord) -> bool:
        return record.current_state in {AgentState.ON, AgentState.PAUSED}