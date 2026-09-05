from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.agent_loop.schemas import AgentState
from app.core.database import Base
from app.services.agent_runtime import AgentRuntime


def test_agent_control_persists_power_pause_resume_and_settings(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'control.db'}")
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    try:
        runtime = AgentRuntime(session, "control-task")
        runtime.create("Build feature", autonomous=True, allow_follow_up_prompts=False)

        assert runtime.transition("power_on").current_state == AgentState.ON
        assert runtime.transition("pause").current_state == AgentState.PAUSED
        assert runtime.transition("set_autonomous", {"autonomous": False}).autonomous is False
        assert runtime.transition("set_follow_up_prompts", {"allow_follow_up_prompts": True}).allow_follow_up_prompts is True
        assert runtime.transition("resume").current_state == AgentState.ON
        assert runtime.transition("emergency_stop").current_state == AgentState.OFF
        assert AgentRuntime.permits_model_call(runtime.get()) is False
    finally:
        session.close()