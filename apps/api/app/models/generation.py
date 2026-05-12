"""Generation + UsageEvent + SavedGeneration ORM (#27).

docs/engineering/data-model.md §5.1, §5.2, §5.3
PRD §3.6, §3.7
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class Generation(Base):
    """Kullanıcı üretim kaydı — pipeline state machine + lineage + output.

    State machine: queued → running → completed | failed | insufficient_data
    """

    __tablename__ = "generations"

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

    request_text: Mapped[str] = mapped_column(Text, nullable=False)
    """Kullanıcının doğal dildeki isteği — Query Planner input'u."""

    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    """'current' | 'weekly' | 'archive' | 'comparison'"""

    output_type: Mapped[str] = mapped_column(String(32), nullable=False)
    """'x_post' | 'x_thread' | 'summary' | 'analysis' | 'headline' | ..."""

    tone: Mapped[str | None] = mapped_column(String(32))
    """'tarafsız' | 'eleştirel' | 'mizahi' | 'kurumsal' | ..."""

    length: Mapped[str | None] = mapped_column(String(16))
    """'short' | 'medium' | 'long'"""

    show_sources: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("TRUE")
    )

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'queued'")
    )
    """'queued' | 'running' | 'completed' | 'failed' | 'insufficient_data'"""

    # Pipeline lineage
    retrieval_plan_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    """Query Planner output — structured plan."""

    used_agenda_card_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)),
        server_default=text("'{}'::uuid[]"),
    )
    used_chunk_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)),
        server_default=text("'{}'::uuid[]"),
    )

    # Output
    output_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    """{posts: [...], summary: ..., sources: [...], warnings: [...]}"""

    warnings: Mapped[list[str]] = mapped_column(
        JSONB, server_default=text("'[]'::jsonb")
    )

    # Provider tracking
    model_provider: Mapped[str | None] = mapped_column(String(80))
    model_name: Mapped[str | None] = mapped_column(String(120))
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    cost_estimate_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))

    # Style (Faz 5 — FK sonra eklenecek, şimdi sadece kolon)
    style_profile_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    # Quality flags
    halu_flagged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    halu_flagged_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
    )

    # User actions
    saved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # SFT telemetry (#563) — Trendyol-LLM-7B-chat-v4.1.0 üzerine
    # domain-spesifik fine-tune için altın etiketleme sinyalleri.
    user_action: Mapped[str | None] = mapped_column(String(20))
    """'copied' | 'posted' | 'edited' | 'regenerated' | 'kept' | 'deleted'"""

    action_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    time_to_action_sec: Mapped[int | None] = mapped_column(Integer)

    edited_text: Mapped[str | None] = mapped_column(Text)
    """Kullanıcının nihai düzenlenmiş metni — DPO için."""

    edit_distance: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    """Levenshtein normalize 0-1 (0=identik, 1=tamamen farklı)."""

    sft_eligible: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    """ETL filter flag — `_recompute_sft_eligibility` helper günceller."""

    sft_excluded_reason: Mapped[str | None] = mapped_column(String(64))
    """Eligible değilse audit nedeni:
    'no_consent' | 'consent_revoked' | 'wrong_action' |
    'edit_too_large' | 'halu_flagged' | 'review_buffer' | 'pii_secondary_hit'."""

    # Timing
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # #739 — TTFT observability: stream'da ilk SSE 'first_token' event timestamp'i.
    # TTFT = first_token_at - created_at. p50/p95 dashboard metric.
    first_token_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "mode IN ('current', 'weekly', 'archive', 'comparison')",
            name="ck_generations_mode",
        ),
        CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed', 'insufficient_data')",
            name="ck_generations_status",
        ),
        CheckConstraint(
            "user_action IS NULL OR user_action IN "
            "('copied', 'posted', 'edited', 'regenerated', 'kept', 'deleted')",
            name="ck_generations_user_action",
        ),
        CheckConstraint(
            "edit_distance IS NULL OR (edit_distance >= 0 AND edit_distance <= 1)",
            name="ck_generations_edit_distance",
        ),
        Index("idx_generations_user_created", "user_id", text("created_at DESC")),
        Index("idx_generations_status", "status", text("created_at DESC")),
        Index(
            "idx_generations_saved",
            "user_id",
            text("saved_at DESC"),
            postgresql_where=text("saved_at IS NOT NULL"),
        ),
        Index("idx_generations_mode", "mode", text("created_at DESC")),
        Index(
            "idx_generations_sft_eligible",
            "sft_eligible",
            text("created_at DESC"),
            postgresql_where=text("sft_eligible = true"),
        ),
    )


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
        Index(
            "idx_usage_events_user_created", "user_id", text("created_at DESC")
        ),
        Index("idx_usage_events_type", "event_type", text("created_at DESC")),
        Index(
            "idx_usage_events_user_type_created",
            "user_id",
            "event_type",
            text("created_at DESC"),
        ),
    )


class SavedGeneration(Base):
    """Kullanıcı favori — generation × user UNIQUE."""

    __tablename__ = "saved_generations"

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
    generation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("generations.id", ondelete="CASCADE"),
        nullable=False,
    )
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "user_id", "generation_id", name="uq_saved_generations_user_gen"
        ),
        Index("idx_saved_generations_user", "user_id", text("created_at DESC")),
    )
