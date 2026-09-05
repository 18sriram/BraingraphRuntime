import httpx

from app.agent_loop.dependencies import InMemoryStateStore
from app.agent_loop.engine import AgentLoopEngine
from app.gateway.gateway import ModelGateway
from app.gateway.providers import OpenAIProvider
from app.gateway.schemas import ChatRequest
from app.memory.context_builder import ContextBuilder
from app.repositories.graph_repository import GraphRepository
from app.schemas.graph import GraphNodeCreate


def make_gateway(responses: list[str]) -> ModelGateway:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": responses.pop(0)}}]}, request=request)

    provider = OpenAIProvider(
        "test-key",
        "https://api.openai.com/v1",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    return ModelGateway(provider=provider)


def test_agent_loop_executes_and_persists_successful_iteration() -> None:
    graph = GraphRepository()
    task = graph.create_node(GraphNodeCreate(type="Task", name="Fix authentication"))
    store = InMemoryStateStore()
    engine = AgentLoopEngine(
        gateway=make_gateway(['{"status": "in_progress", "reason": "Tests are needed", "actions": [{"type": "run_tests", "parameters": {}}], "expected_result": "Tests pass", "confidence": 0.8}']),
        context_builder=ContextBuilder(graph),
        state_store=store,
        graph=graph,
    )

    run = engine.run(task.id, "Fix authentication", max_iterations=1)

    assert run.state.state == "FAILED"
    assert run.state.iteration == 1
    assert store.get(task.id).state == "FAILED"
    assert any(node.type == "Result" for node in graph.retrieve_subgraph(task.id, 1).nodes)


def test_agent_loop_stops_when_model_reports_objective_achieved() -> None:
    graph = GraphRepository()
    task = graph.create_node(GraphNodeCreate(type="Task", name="Fix authentication"))
    engine = AgentLoopEngine(
        gateway=make_gateway(['{"status": "success", "reason": "The objective is complete", "actions": [], "expected_result": "Authentication works", "confidence": 1.0}']),
        context_builder=ContextBuilder(graph),
        graph=graph,
    )

    run = engine.run(task.id, "Fix authentication")

    assert run.state.state == "SUCCESS"
    assert run.state.iteration == 0


def test_agent_loop_can_pause_before_planning() -> None:
    graph = GraphRepository()
    task = graph.create_node(GraphNodeCreate(type="Task", name="Fix authentication"))
    engine = AgentLoopEngine(gateway=make_gateway([]), graph=graph)

    run = engine.run(task.id, "Fix authentication", pause_requested=True)

    assert run.state.state == "PAUSED"
