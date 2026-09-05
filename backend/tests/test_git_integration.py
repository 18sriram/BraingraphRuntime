from __future__ import annotations

from pathlib import Path

from git import Repo

from app.git.integration import GitIntegration
from app.repositories.graph_repository import GraphRepository


def make_repo(tmp_path: Path) -> Repo:
    repo = Repo.init(tmp_path)
    path = tmp_path / "tracked.txt"
    path.write_text("initial", encoding="utf-8")
    repo.index.add([str(path)])
    repo.index.commit("initial")
    return repo


def test_git_checkpoint_generates_diff_commits_and_stores_metadata(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    graph = GraphRepository()
    integration = GitIntegration(tmp_path, graph)
    (tmp_path / "tracked.txt").write_text("updated", encoding="utf-8")
    (tmp_path / "new.txt").write_text("new", encoding="utf-8")

    assert "updated" in integration.generate_diff()
    checkpoint = integration.checkpoint("task-1", 2, "test-model")

    assert checkpoint is not None
    assert checkpoint.commit_hash == repo.head.commit.hexsha
    assert set(checkpoint.files_changed) == {"tracked.txt", "new.txt"}
    commits = [
        node
        for node in graph.retrieve_subgraph("task-1", 1, bidirectional=True).nodes
        if node.type == "GitCommit"
    ]
    assert commits[0].properties["commit_hash"] == checkpoint.commit_hash
    assert commits[0].properties["iteration"] == 2
    assert commits[0].properties["model_used"] == "test-model"


def test_git_checkpoint_skips_clean_tree_and_rollback_restores_files(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    integration = GitIntegration(tmp_path)
    assert integration.create_commit("no changes") is None
    (tmp_path / "tracked.txt").write_text("changed", encoding="utf-8")
    checkpoint = integration.create_commit("change")
    assert checkpoint is not None
    (tmp_path / "tracked.txt").write_text("broken", encoding="utf-8")

    integration.rollback(checkpoint.commit_hash)

    assert (tmp_path / "tracked.txt").read_text(encoding="utf-8") == "changed"
    assert repo.head.commit.hexsha == checkpoint.commit_hash
