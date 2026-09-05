from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    project_path: Mapped[str] = mapped_column(String(1024), unique=True, nullable=False)
    database_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    last_opened: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    brain_version: Mapped[str] = mapped_column(String(64), nullable=False, default="1.0")