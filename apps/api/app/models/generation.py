"""UsageEvent ORM (#27, #800 S1B post-cleanup).

NOT: Generation + SavedGeneration sınıfları #800 S1B'de KALDIRILDI
(research-only migration). Sadece UsageEvent kalır — quota tracking + cost
ledger için. `generation_id` kolonu DB'de nullable kalır (migration
20260514_1700) ama modelde tanımlı değil; tarihçe veri "anonim" referans.

docs/engineering/data-model.md §5.2 (UsageEvent)
PRD §3.7 (quota)
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class UsageEvent(Base):
    """Quota tracking + cost ledger — sliding window query'ler için index'li."""

    __tablename__ = "usage_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    """'generation' | 'embedding' | 'login' | 'save' | 'export'"""

    provider: Mapped[str | None] = mapped_column(String(80))
    model: Mapped[str | None] = mapped_column(String(120))
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))

    event_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata", JSONB, server_default=text("'{}'::jsonb")
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("idx_usage_events_user_created", "user_id", text("created_at DESC")),
        Index("idx_usage_events_type", "event_type", text("created_at DESC")),
        Index(
            "idx_usage_events_user_type_created",
            "user_id",
            "event_type",
            text("created_at DESC"),
        ),
    )
