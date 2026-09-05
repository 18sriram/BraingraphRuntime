from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.agent_loop.schemas import AgentState
from app.core.database import SessionLocal
from app.services.agent_runtime import AgentRuntime

router = APIRouter(tags=["dashboard"])


@router.websocket("/ws/dashboard")
async def dashboard_events(websocket: WebSocket, task_id: str | None = None) -> None:
    await websocket.accept()
    database = SessionLocal()
    try:
        while True:
            agent_status = AgentState.IDLE.value
            if task_id is not None:
                record = AgentRuntime(database, task_id).get()
                if record is not None:
                    agent_status = record.current_state
            await websocket.send_json(
                {
                    "type": "heartbeat",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "agent_status": agent_status,
                    "quota": {"used": 64, "limit": 100, "reset": "18 min"},
                }
            )
            try:
                message = await asyncio.wait_for(websocket.receive_json(), timeout=15)
                control_events = {
                    "ON": "power_on",
                    "OFF": "power_off",
                    "STOP": "power_off",
                    "PAUSE": "pause",
                    "RESUME": "resume",
                    "EMERGENCY_STOP": "emergency_stop",
                }
                control = message.get("type")
                if control in control_events and task_id is not None:
                    record = AgentRuntime(database, task_id).transition(control_events[control])
                    await websocket.send_json({"type": "control_ack", "control": control, "agent_status": record.current_state})
                elif control == "AUTONOMOUS_LOOP" and task_id is not None:
                    record = AgentRuntime(database, task_id).transition("set_autonomous", message)
                    await websocket.send_json({"type": "control_ack", "control": control, "autonomous": record.autonomous})
                elif control == "ALLOW_FOLLOW_UP_PROMPTS" and task_id is not None:
                    record = AgentRuntime(database, task_id).transition("set_follow_up_prompts", message)
                    await websocket.send_json({"type": "control_ack", "control": control, "allow_follow_up_prompts": record.allow_follow_up_prompts})
                elif control == "PROMPT_STRATEGY" and task_id is not None:
                    strategy = message.get("strategy")
                    if strategy not in {"first-prompt-only", "autonomous"}:
                        await websocket.send_json({"type": "control_error", "control": control, "reason": "Invalid prompt strategy"})
                    else:
                        record = AgentRuntime(database, task_id).transition("set_autonomous", {"autonomous": strategy == "autonomous", "strategy": strategy})
                        await websocket.send_json({"type": "control_ack", "control": control, "strategy": strategy, "autonomous": record.autonomous})
            except asyncio.TimeoutError:
                pass
            await asyncio.sleep(5)
    except (WebSocketDisconnect, RuntimeError):
        return
    finally:
        database.close()
