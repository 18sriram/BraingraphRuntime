from __future__ import annotations

import importlib
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

_GIT_BIN_CANDIDATES = [
    os.environ.get("GIT_PYTHON_GIT_EXECUTABLE"),
    shutil.which("git"),
    "/usr/bin/git",
    "/usr/local/bin/git",
]


def _resolve_git_executable() -> str:
    for candidate in _GIT_BIN_CANDIDATES:
        if not candidate:
            continue
        git_path = Path(candidate).expanduser()
        if git_path.exists() and git_path.is_file():
            os.environ["GIT_PYTHON_GIT_EXECUTABLE"] = str(git_path)
            return str(git_path)
    raise RuntimeError(
        "Git is not installed or not available in PATH. "
        "Install git and ensure it is executable before using GitIntegration."
    )


def _load_git_module():
    git_path = _resolve_git_executable()
    try:
        git = importlib.import_module("git")
        git.refresh(path=git_path)
        return git
    except Exception as exc:  # pragma: no cover - depends on external git installation
        raise RuntimeError(f"Unable to initialize GitPython with git at {git_path!r}") from exc


try:
    git_module = importlib.import_module("git")
    InvalidGitRepositoryError = git_module.exc.InvalidGitRepositoryError
    NoSuchPathError = git_module.exc.NoSuchPathError
except Exception:  # pragma: no cover - only reached if GitPython cannot import at all
    class InvalidGitRepositoryError(Exception):
        pass

    class NoSuchPathError(Exception):
        pass

from app.memory.engine import ArtifactMemory
from app.repositories.graph_repository import GraphRepository


@dataclass(frozen=True)
class GitCheckpoint:
    commit_hash: str
    message: str
    files_changed: list[str]
    diff: str
    task_id: str | None = None
    iteration: int | None = None
    model_used: str | None = None


class GitIntegration:
    """Git checkpoints and metadata bridge for the graph-backed runtime."""

    def __init__(self, project_root: str | Path, graph: GraphRepository | None = None) -> None:
        self.project_root = Path(project_root).expanduser().resolve()
        git_module = _load_git_module()
        Repo = getattr(git_module, "Repo", None)
        if Repo is None:
            raise RuntimeError("GitPython is not installed correctly; 'git.Repo' is unavailable.")
        try:
            self.repo = Repo(self.project_root, search_parent_directories=False)
        except (InvalidGitRepositoryError, NoSuchPathError) as error:
            raise ValueError(f"Project folder is not a Git repository: {self.project_root}") from error
        self.artifacts = ArtifactMemory(graph)

    def generate_diff(self) -> str:
        return self.repo.git.diff("HEAD")

    def changed_files(self) -> list[str]:
        changed = self.repo.git.status("--porcelain").splitlines()
        return [line[3:] for line in changed if len(line) >= 4]

    def create_commit(
        self,
        message: str,
        *,
        task_id: str | None = None,
        iteration: int | None = None,
        model_used: str | None = None,
    ) -> GitCheckpoint | None:
        files = self.changed_files()
        diff = self.generate_diff()
        if not files:
            return None
        self.repo.git.add(all=True)
        commit = self.repo.index.commit(message)
        checkpoint = GitCheckpoint(
            commit_hash=commit.hexsha,
            message=message,
            files_changed=files,
            diff=diff,
            task_id=task_id,
            iteration=iteration,
            model_used=model_used,
        )
        if task_id is not None:
            self.artifacts.store_commit(
                name=commit.hexsha,
                task_id=task_id,
                properties={
                    "commit_hash": commit.hexsha,
                    "message": message,
                    "files_changed": files,
                    "task_id": task_id,
                    "iteration": iteration,
                    "model_used": model_used,
                    "diff": diff,
                },
            )
        return checkpoint

    def checkpoint(
        self,
        task_id: str,
        iteration: int,
        model_used: str,
        message: str = "chore: automatic agent checkpoint",
    ) -> GitCheckpoint | None:
        return self.create_commit(
            message,
            task_id=task_id,
            iteration=iteration,
            model_used=model_used,
        )

    def rollback(self, commit_hash: str, *, paths: list[str] | None = None) -> None:
        if paths:
            self.repo.git.restore("--source", commit_hash, "--", *paths)
        else:
            self.repo.git.reset("--hard", commit_hash)
