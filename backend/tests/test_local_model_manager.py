from __future__ import annotations

import pytest

from app.local_models.manager import LocalModelManager
from app.local_models.schemas import LocalModel, PullProgress
from app.config.settings import Settings


class FakeLocalProvider:
    name = "fake"

    def __init__(self) -> None:
        self.installs: list[str] = []
        self.removed: list[str] = []

    def available(self) -> bool:
        return True

    def list_models(self) -> list[LocalModel]:
        return [LocalModel(name="qwen3:8b-instruct")]

    def install_model(self, model: str):
        self.installs.append(model)
        yield PullProgress(model=model, status="success")

    def remove_model(self, model: str) -> None:
        self.removed.append(model)


class MissingProvider(FakeLocalProvider):
    def available(self) -> bool:
        return False


class InstallProvider(FakeLocalProvider):
    def __init__(self) -> None:
        super().__init__()
        self.installed = False

    def list_models(self) -> list[LocalModel]:
        return [LocalModel(name="qwen3:8b-instruct")] if self.installed else []

    def install_model(self, model: str):
        self.installs.append(model)
        yield PullProgress(model=model, status="downloading", completed=1, total=2)
        self.installed = True
        yield PullProgress(model=model, status="success", completed=2, total=2)


def test_local_model_manager_defaults_to_qwen_and_manages_models() -> None:
    provider = FakeLocalProvider()
    manager = LocalModelManager(provider=provider, settings=Settings(local_model="qwen3:8b-instruct"))

    assert manager.current_model() == "qwen3:8b-instruct"
    assert manager.check_installed() is True
    assert list(manager.install_model("mistral"))[0].status == "success"
    assert provider.installs == ["mistral"]
    assert manager.set_default("llama3.1") == "llama3.1"
    manager.remove_model("mistral")
    assert provider.removed == ["mistral"]


def test_local_model_manager_rejects_unknown_models() -> None:
    manager = LocalModelManager(provider=FakeLocalProvider())
    with pytest.raises(ValueError):
        manager.set_default("unknown")


def test_first_run_setup_stops_with_install_instructions_when_ollama_missing(tmp_path) -> None:
    output: list[str] = []
    settings = Settings(project_root=str(tmp_path))
    manager = LocalModelManager(provider=MissingProvider(), settings=settings)

    assert manager.first_run_setup(ask=lambda _: "Y", write=output.append) is False
    assert "Install Ollama" in " ".join(output)


def test_first_run_setup_pulls_qwen_and_persists_default(tmp_path) -> None:
    output: list[str] = []
    settings = Settings(project_root=str(tmp_path))
    provider = InstallProvider()
    manager = LocalModelManager(provider=provider, settings=settings)

    assert manager.first_run_setup(ask=lambda _: "Y", write=output.append) is True
    assert provider.installs == ["qwen3:8b-instruct"]
    assert "LOCAL_MODEL=qwen3:8b-instruct" in (tmp_path / ".env").read_text()
    assert "downloading 1/2" in output