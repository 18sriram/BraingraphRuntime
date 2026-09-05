from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Callable

from app.config.settings import Settings, get_settings
from app.local_models.provider import create_local_provider
from app.local_models.provider import LocalModelProvider
from app.local_models.schemas import LocalModel, PullProgress


class LocalModelManager:
    """Provider-neutral manager for the local orchestration model."""

    SUPPORTED_MODELS = ("qwen3:8b-instruct", "llama3.1", "llama3.3", "mistral", "deepseek-r1", "gemma")
    DEFAULT_MODEL = "qwen3:8b-instruct"

    def __init__(self, provider: LocalModelProvider | None = None, settings: Settings | None = None) -> None:
        settings = settings or get_settings()
        self.settings = settings
        self.default_model_name = settings.local_model or self.DEFAULT_MODEL
        self.provider = provider or create_local_provider(settings)

    def list_models(self) -> list[LocalModel]:
        return self.provider.list_models()

    def install_model(self, model: str | None = None) -> Iterator[PullProgress]:
        selected = model or self.default_model_name
        self._validate_model(selected)
        return self.provider.install_model(selected)

    def remove_model(self, model: str) -> None:
        self.provider.remove_model(model)

    def set_default(self, model: str) -> str:
        self._validate_model(model)
        self.default_model_name = model
        self._persist_default(model)
        return model

    def first_run_setup(
        self,
        *,
        ask: Callable[[str], str] = input,
        write: Callable[[str], None] = print,
    ) -> bool:
        """Ensure Ollama and the default Qwen model exist before runtime startup."""
        self.default_model_name = self.DEFAULT_MODEL
        if not self.available():
            write("Ollama is not installed or not running.")
            write("Install Ollama from https://ollama.com/download, start it, then run `bg start` again.")
            return False
        if self.check_installed(self.default_model_name):
            self.set_default(self.default_model_name)
            return True

        answer = ask(f"Install default model {self.default_model_name}? Y/N ").strip().lower()
        if answer not in {"y", "yes"}:
            write(f"{self.default_model_name} is required for the local orchestrator. Runtime stopped.")
            return False
        write(f"Installing {self.default_model_name}...")
        for progress in self.install_model(self.default_model_name):
            details = progress.status
            if progress.completed is not None and progress.total:
                details = f"{details} {progress.completed}/{progress.total}"
            write(details)
        if not self.check_installed(self.default_model_name):
            write(f"Model installation did not complete. Run `ollama pull {self.default_model_name}` and retry.")
            return False
        self.set_default(self.default_model_name)
        write(f"{self.default_model_name} is installed and configured as the default local model.")
        return True

    def current_model(self) -> str:
        return self.default_model_name

    def check_installed(self, model: str | None = None) -> bool:
        selected = model or self.default_model_name
        return any(item.name == selected for item in self.list_models())

    def pull_progress(self, model: str | None = None) -> Iterator[PullProgress]:
        return self.install_model(model)

    def available(self) -> bool:
        return self.provider.available()

    def installation_message(self) -> str | None:
        if not self.available():
            return "Ollama is not installed or not running. Install Ollama, then retry."
        if not self.check_installed():
            return f"Local model {self.current_model()} is missing. Install it with: ollama pull {self.current_model()}"
        return None

    def _validate_model(self, model: str) -> None:
        if model not in self.SUPPORTED_MODELS:
            raise ValueError(f"Unsupported local model {model!r}; choose from {', '.join(self.SUPPORTED_MODELS)}")

    def _persist_default(self, model: str) -> None:
        env_path = Path(self.settings.project_root).expanduser().resolve() / ".env"
        lines = env_path.read_text().splitlines() if env_path.exists() else []
        replacement = f"LOCAL_MODEL={model}"
        for index, line in enumerate(lines):
            if line.startswith("LOCAL_MODEL="):
                lines[index] = replacement
                break
        else:
            lines.append(replacement)
        env_path.write_text("\n".join(lines) + "\n")
