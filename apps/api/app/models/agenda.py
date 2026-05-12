"""AgendaCard ORM model (#21).

docs/engineering/data-model.md §4.4

embedding vector(1024) DB'de var, ORM type tanımlı değil (raw SQL).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class AgendaCard(Base):
    """Event cluster'dan üretilen kullanıcıya gösterilen gündem kartı.

    Faz 2 LLM (DeepSeek V4 Flash) ile üretilir; Faz 3 user generation buradan beslenir.
    """

    __tablename__ = "agenda_cards"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("event_clusters.id", ondelete="CASCADE"),
        nullable=False,
    )

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    key_points: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    content_angles: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    timeline: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    source_refs: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )

    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'developing'")
    )
    freshness_score: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))
    importance_score: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))

    # embedding column raw SQL ile yazılır

    # #182 — RAPTOR-Lite hierarchical clustering
    level: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'daily'")
    )
    parent_card_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agenda_cards.id", ondelete="SET NULL"),
        nullable=True,
    )

    # #210 — Geographic context (ISO 3166-1 alpha-2 ülke kodu, opsiyonel)
    country: Mapped[str | None] = mapped_column(String(2), nullable=True)

    generated_by_model: Mapped[str | None] = mapped_column(String(80))
    generation_request_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('developing', 'active', 'cooling', 'stale', 'archived')",
            name="ck_agenda_cards_status",
        ),
        CheckConstraint(
            "level IN ('daily', 'weekly', 'monthly')",
            name="agenda_cards_level_check",
        ),
        Index("idx_agenda_cards_event", "event_id"),
        Index("idx_agenda_cards_status_updated", "status", text("updated_at DESC")),
        Index("idx_agenda_cards_level", "level", text("updated_at DESC")),
    )
