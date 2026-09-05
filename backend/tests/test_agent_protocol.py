import pytest
from pydantic import ValidationError

from app.agent_loop.protocol import MalformedLLMResponse, parse_llm_response, serialize_llm_response
from app.agent_loop.schemas import AgentAction, AgentPlan


VALID_RESPONSE = {
    "status": "in_progress",
    "reason": "Need to inspect the failing test",
    "actions": [{"type": "read_file", "parameters": {"path": "auth.py"}}],
    "expected_result": "Identify the authentication failure",
    "confidence": 0.75,
}


def test_protocol_parses_and_serializes_json_only() -> None:
    response = parse_llm_response(__import__("json").dumps(VALID_RESPONSE))

    assert response.actions[0].type == "read_file"
    serialized = serialize_llm_response(response)
    assert parse_llm_response(serialized) == response


@pytest.mark.parametrize(
    "content",
    [
        "Here is the JSON: {}",
        "```json\n{}\n```",
        '{"status":"in_progress"}',
        '{"status":"in_progress","reason":"x","actions":[{"type":"delete_file"}],"expected_result":"x","confidence":0.5}',
    ],
)
def test_protocol_rejects_malformed_responses(content: str) -> None:
    with pytest.raises(MalformedLLMResponse):
        parse_llm_response(content)


def test_protocol_rejects_extra_fields_and_invalid_confidence() -> None:
    with pytest.raises(ValidationError):
        AgentPlan.model_validate({**VALID_RESPONSE, "unexpected": True})
    with pytest.raises(ValidationError):
        AgentPlan.model_validate({**VALID_RESPONSE, "confidence": 1.1})
    with pytest.raises(ValidationError):
        AgentAction.model_validate({"type": "run_tests", "parameters": {}, "name": "legacy"})
