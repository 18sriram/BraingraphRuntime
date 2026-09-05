from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/health", tags=["health"])


@router.get("", summary="Runtime health status")
def health_check() -> dict[str, str]:
    """Return a minimal status payload for infrastructure monitoring."""
    return {"status": "ok"}
