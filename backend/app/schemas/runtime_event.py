from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class RuntimeEventBase(BaseModel):
    event_type: str = Field(..., min_length=1, max_length=100)
    source: str = Field(..., min_length=1, max_length=100)
    message: str = Field(..., min_length=1)
    metadata: Optional[dict[str, Any]] = None


class RuntimeEventCreate(RuntimeEventBase):
    pass


class RuntimeEventRead(RuntimeEventBase):
    id: int
    created_at: datetime
    metadata: Optional[dict[str, Any]] = None
