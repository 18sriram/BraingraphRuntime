from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field

from app.local_models.manager import LocalModelManager

router = APIRouter(prefix="/api/local-models", tags=["local-models"])


class ModelRequest(BaseModel):
    model: str = Field(min_length=1)


def manager() -> LocalModelManager:
    return LocalModelManager()


@router.get("/status")
def status() -> dict[str, object]:
    current = manager()
    available = current.available()
    installed = False
    if available:
        try:
            installed = current.check_installed()
        except Exception:
            installed = False
    return {
        "provider": current.provider.name,
        "available": available,
        "default_model": current.current_model(),
        "installed": installed,
        "message": current.installation_message() if available else "Ollama is not installed or not running. Install Ollama, then retry.",
    }


@router.get("")
def list_models() -> list[dict[str, object]]:
    try:
        return [model.model_dump(mode="json") for model in manager().list_models()]
    except Exception as error:
        raise HTTPException(status_code=503, detail=f"Local model provider unavailable: {error}") from error


@router.get("/current")
def current_model() -> dict[str, str]:
    current = manager()
    return {"model": current.current_model()}


@router.post("/default")
def set_default(payload: ModelRequest) -> dict[str, str]:
    try:
        return {"model": manager().set_default(payload.model)}
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/install")
def install_model(payload: ModelRequest) -> dict[str, object]:
    current = manager()
    try:
        progress = list(current.install_model(payload.model))
    except Exception as error:
        raise HTTPException(status_code=503, detail=f"Unable to install local model: {error}") from error
    return {"model": payload.model, "progress": [item.model_dump(mode="json") for item in progress]}


@router.get("/pull-progress")
def pull_progress(model: str | None = None) -> dict[str, object]:
    current = manager()
    try:
        progress = list(current.pull_progress(model))
    except Exception as error:
        raise HTTPException(status_code=503, detail=f"Unable to retrieve pull progress: {error}") from error
    return {"model": model or current.current_model(), "progress": [item.model_dump(mode="json") for item in progress]}


@router.delete("/{model}", status_code=204)
def remove_model(model: str) -> Response:
    try:
        manager().remove_model(model)
    except Exception as error:
        raise HTTPException(status_code=503, detail=f"Unable to remove local model: {error}") from error
    return Response(status_code=204)
