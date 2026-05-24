"""AgendaCard ORM model (#21).

docs/engineering/data-model.md §4.4

embedding vector(1024) Phase 8.2 PR-8.2-11'de ORM'e tanımlandı.
Migration: 20260502_0000_add_agenda_cards.py raw SQL DDL ile yaratıldı
(`embedding vector(1024)` — explicit NOT NULL yok → DB nullable=True).
Write path: `app/modules/rag/tasks/raptor.py:406` raw SQL `UPDATE agenda_cards
SET embedding = (:vec)::vector WHERE id = :id`.
Read path: hybrid retrieval (raw SQL cosine similarity) + citation.py.
ORM attribute access (`.embedding`) YOK — Mapped declaration sadece
alembic autogenerate metadata için.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pgvector.sqlalchemy import Vector
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
from sqlalchemy.orm import Mapped, mapped_column

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

    # Phase 8.2 PR-8.2-11: pgvector Vector(1024) ORM declaration
    # Migration: 20260502_0000_add_agenda_cards.py raw SQL DDL
    # (`embedding vector(1024)` — DB nullable=True via no explicit NOT NULL).
    # Writer: app/modules/rag/tasks/raptor.py:406 raw SQL (:vec)::vector cast.
    # Reader: raw SQL cosine similarity (retrieval) + citation.py reuse.
    # ORM accessor YOK — Mapped declaration sadece alembic metadata için.
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1024), nullable=True)

    # #182 — RAPTOR-Lite hierarchical clustering
    level: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'daily'"))
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
        # Phase 8.2 PR-8.2-4 expression hizalama (add_index drift fix):
        # Migration `["level", "updated_at"]` PLAIN columns (DESC YOK) —
        # önceki `text("updated_at DESC")` autogenerate add_index drift
        # yaratıyordu. Düzeltildi.
        # Migration: 20260502_1700_add_agenda_hierarchy.py
        Index(
            "idx_agenda_cards_level",
            "level",
            "updated_at",
            postgresql_using="btree",
        ),
        # ============================================================
        # Phase 8.2 PR-8.2-4: 4 missing index — DB'de zaten mevcut
        # ============================================================
        # GIN trgm — full-text fuzzy search (pg_trgm extension)
        # Migration: 20260502_1500_add_chunks_trgm_index.py
        Index(
            "idx_agenda_cards_title_trgm",
            "title",
            postgresql_using="gin",
            postgresql_ops={"title": "gin_trgm_ops"},
        ),
        Index(
            "idx_agenda_cards_summary_trgm",
            "summary",
            postgresql_using="gin",
            postgresql_ops={"summary": "gin_trgm_ops"},
        ),
        # Hierarchy parent — partial (NULL bırakılabilir root-level card)
        # Migration: 20260502_1700_add_agenda_hierarchy.py
        Index(
            "idx_agenda_cards_parent",
            "parent_card_id",
            postgresql_where=text("parent_card_id IS NOT NULL"),
        ),
        # Country filter — partial (NULL bırakılabilir global card)
        # Migration: 20260502_1900_add_agenda_country.py
        Index(
            "idx_agenda_cards_country",
            "country",
            postgresql_where=text("country IS NOT NULL"),
        ),
        # Phase 8.2 PR-8.2-11: pgvector ivfflat index ORM declaration
        # Migration: 20260502_0000_add_agenda_cards.py L58-59
        # `CREATE INDEX idx_agenda_cards_embedding ON agenda_cards
        # USING ivfflat (embedding vector_cosine_ops) WITH (lists = 50)`
        Index(
            "idx_agenda_cards_embedding",
            "embedding",
            postgresql_using="ivfflat",
            postgresql_ops={"embedding": "vector_cosine_ops"},
            postgresql_with={"lists": 50},
        ),
    )
