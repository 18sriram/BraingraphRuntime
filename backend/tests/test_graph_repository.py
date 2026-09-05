from app.repositories.graph_repository import (
    DecisionRepository,
    ExperimentRepository,
    GraphRepository,
    TaskRepository,
)
from app.schemas.graph import GraphNodeCreate, GraphRelationshipCreate


def test_graph_repository_supports_crud_and_traversal() -> None:
    repo = GraphRepository()

    project = repo.create_node(
        GraphNodeCreate(
            type="Project",
            name="BrainGraph Runtime",
            properties={"status": "active"},
        )
    )
    goal = repo.create_node(
        GraphNodeCreate(
            type="Goal",
            name="Deliver MVP",
            properties={"priority": "high"},
        )
    )

    repo.create_relationship(
        GraphRelationshipCreate(
            source_id=project.id,
            target_id=goal.id,
            type="HAS_GOAL",
        )
    )

    neighbors = repo.get_neighbors(project.id)
    assert {neighbor.id for neighbor in neighbors} == {goal.id}

    subgraph = repo.retrieve_subgraph(project.id, max_depth=1)
    assert project.id in {node.id for node in subgraph.nodes}
    assert goal.id in {node.id for node in subgraph.nodes}

    updated_project = repo.update_node(
        project.id,
        {"name": "BrainGraph Runtime v2", "properties": {"status": "archived"}},
    )
    assert updated_project.name == "BrainGraph Runtime v2"
    assert updated_project.properties["status"] == "archived"

    assert repo.delete_node(goal.id) is True
    assert repo.get_node(goal.id) is None


def test_task_decision_and_experiment_repositories() -> None:
    task_repo = TaskRepository()
    decision_repo = DecisionRepository()
    experiment_repo = ExperimentRepository()

    task = task_repo.create_task("Implement graph repository", project_id=None)
    assert task.type == "Task"
    assert task.name == "Implement graph repository"

    decision = decision_repo.create_decision("Use Neo4j for memory")
    assert decision.type == "Decision"

    experiment = experiment_repo.create_experiment("Initial graph validation")
    assert experiment.type == "Experiment"
    assert experiment.name == "Initial graph validation"
