"""EventCluster + EventArticle ORM (#20).

docs/engineering/data-model.md §4.2, §4.3

event_clusters.embedding (vector(1024)) Phase 8.2 PR-8.2-11'de ORM'e tanımlandı.
Migration: 20260501_2300_add_event_clusters.py raw SQL DDL ile yaratıldı
(`embedding vector(1024)` — explicit NOT NULL yok → DB nullable=True).
Write path: `app/modules/clusters/clustering.py:277` raw SQL `INSERT INTO
event_clusters (embedding, ...) VALUES ((:vec)::vector, ...)`.
Read path: hybrid retrieval (raw SQL cosine similarity).
ORM attribute access (`.embedding`) YOK — Mapped declaration sadece
alembic autogenerate metadata için.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
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
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class EventCluster(Base):
    """Aynı olaya ait haberlerin grubu — clustering worker tarafından yönetilir.

    Status state machine: developing → active → cooling → stale → archived
    """

    __tablename__ = "event_clusters"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    canonical_title: Mapped[str] = mapped_column(String(500), nullable=False)
    current_summary: Mapped[str | None] = mapped_column(Text)

    # Phase 8.2 PR-8.2-11: pgvector Vector(1024) ORM declaration
    # Migration: 20260501_2300_add_event_clusters.py raw SQL DDL
    # (`embedding vector(1024)` — DB nullable=True via no explicit NOT NULL).
    # Writer: app/modules/clusters/clustering.py:277 raw SQL (:vec)::vector cast.
    # Reader: raw SQL cosine similarity (retrieval). ORM accessor YOK.
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1024), nullable=True)

    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'developing'")
    )

    importance_score: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))
    freshness_score: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))
    source_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    article_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    articles: Mapped[list[EventArticle]] = relationship(
        back_populates="event", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('developing', 'active', 'cooling', 'stale', 'archived')",
            name="ck_event_clusters_status",
        ),
        Index(
            "idx_event_clusters_status_updated",
            "status",
            text("last_updated_at DESC"),
        ),
        Index(
            "idx_event_clusters_last_seen",
            text("last_seen_at DESC"),
        ),
        # Phase 8.2 PR-8.2-11: pgvector ivfflat index ORM declaration
        # Migration: 20260501_2300_add_event_clusters.py L58-59
        # `CREATE INDEX idx_event_clusters_embedding ON event_clusters
        # USING ivfflat (embedding vector_cosine_ops) WITH (lists = 50)`
        Index(
            "idx_event_clusters_embedding",
            "embedding",
            postgresql_using="ivfflat",
            postgresql_ops={"embedding": "vector_cosine_ops"},
            postgresql_with={"lists": 50},
        ),
    )


class EventArticle(Base):
    """Article ↔ EventCluster many-to-many (relationship_score'lı)."""

    __tablename__ = "event_articles"

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
    article_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("articles.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sources.id"),
        nullable=False,
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    relationship_score: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    event: Mapped[EventCluster] = relationship(back_populates="articles")

    __table_args__ = (
        UniqueConstraint("event_id", "article_id", name="uq_event_articles_event_article"),
        Index("idx_event_articles_event", "event_id"),
        Index("idx_event_articles_article", "article_id"),
    )
