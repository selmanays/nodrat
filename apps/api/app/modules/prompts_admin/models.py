"""AppPrompt + AppPromptHistory ORM models — admin prompts panel (#270 PR-B, MVP-1.2).

docs/engineering/data-model.md (admin prompts management)
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class AppPrompt(Base):
    """Runtime-tunable LLM prompt (current active version).

    Default değer kod tarafındaki `app/prompts/*.py` modüllerinde tutulur;
    DB'de override yoksa caller hardcoded fallback kullanır. Her güncelleme
    yeni `version` üretir, önceki versiyon `app_prompt_history`'ye taşınır.
    """

    __tablename__ = "app_prompts"

    name: Mapped[str] = mapped_column(String(80), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_hint: Mapped[str | None] = mapped_column(String(120), nullable=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AppPromptHistory(Base):
    """Prompt version arşivi — admin diff/rollback için."""

    __tablename__ = "app_prompt_history"
    __table_args__ = (
        Index(
            "idx_app_prompt_history_name_version",
            "name",
            "version",
            unique=True,
        ),
        Index(
            "idx_app_prompt_history_name_created",
            "name",
            text("created_at DESC"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
