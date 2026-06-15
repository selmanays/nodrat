"""Trend Intelligence kalıcı tabloları — ORM modelleri (Faz 2 PR-2a, #1505).

4 tablo: topics (kalıcı kimlik) · topic_clusters (topic↔event_cluster bağı) ·
trend_snapshots (zaman-serisi, idempotency key'li) · trend_signals (burst).

**Parity:** alembic check AKTİF strict gate (Phase 8.2). Bu modeller migration
20260615_*_add_trend_tables.py ile BİREBİR eşleşmeli (event_clusters PR-8.2-11
ivfflat deseni). Comment YOK (drift kaynağı). `app/models/__init__.py`'ye kayıt
ZORUNLU (env.py `from app.models import *` → Base.metadata).

**FK kararı:** `trend_snapshots.subject_id` ve `topic_clusters.event_cluster_id`
hard FK İÇERMEZ — history subject'i (cluster archive/silinme) aşar; CASCADE
snapshot/topic geçmişini yok ederdi. Integrity writer + nightly orphan report
(PR-2b) ile sağlanır. `topic_clusters.topic_id` → topics gerçek FK (CASCADE).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Topic(Base):
    """Kalıcı trend konusu kimliği — recur eden konu tek kimlikte birikir.

    seed: entity-anchored öncelik (NER person/org/event baskınlığı) → eşik altı
    cluster-anchored (canonical_title). centroid = üye cluster embedding ortalaması.
    """

    __tablename__ = "topics"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    slug: Mapped[str] = mapped_column(String(160), nullable=False)
    label: Mapped[str] = mapped_column(String(300), nullable=False)
    topic_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    anchor_entity_normalized: Mapped[str | None] = mapped_column(String(200))
    anchor_entity_type: Mapped[str | None] = mapped_column(String(20))
    centroid_embedding: Mapped[list[float] | None] = mapped_column(Vector(1024), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'active'"))
    merged_into_topic_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("topics.id", ondelete="SET NULL"), nullable=True
    )
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    article_count_total: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    cluster_count_total: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    admin_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("slug", name="uq_topics_slug"),
        CheckConstraint(
            "topic_kind IN ('entity', 'event', 'keyword', 'manual')",
            name="ck_topics_kind",
        ),
        CheckConstraint(
            "status IN ('active', 'dormant', 'merged', 'archived')",
            name="ck_topics_status",
        ),
        Index("idx_topics_status_last_seen", "status", text("last_seen_at DESC")),
        Index("idx_topics_anchor", "anchor_entity_normalized", "anchor_entity_type"),
        Index(
            "idx_topics_centroid",
            "centroid_embedding",
            postgresql_using="ivfflat",
            postgresql_ops={"centroid_embedding": "vector_cosine_ops"},
            postgresql_with={"lists": 50},
        ),
    )


class TopicCluster(Base):
    """Kalıcı topic ↔ transient event_cluster bağı (atama kaydı).

    event_cluster_id hard FK YOK (cluster archive/silinme history'yi aşar).
    """

    __tablename__ = "topic_clusters"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    topic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("topics.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_cluster_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    assignment_score: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    assigned_by: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'auto'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("topic_id", "event_cluster_id", name="uq_topic_clusters_topic_event"),
        CheckConstraint(
            "assigned_by IN ('auto', 'admin_merge', 'admin_split')",
            name="ck_topic_clusters_assigned_by",
        ),
        Index("idx_topic_clusters_event", "event_cluster_id"),
    )


class TrendSnapshot(Base):
    """Zaman-serisi: subject (topic/cluster) başına bucket başına supply metrikleri.

    UNIQUE(subject_type,subject_id,bucket_start,algo_version) = idempotency key
    (worker upsert ON CONFLICT). subject_id hard FK YOK (history subject'i aşar).
    Demand kolonları (Faz 4) burada YOK — yalnız supply.
    """

    __tablename__ = "trend_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    subject_type: Mapped[str] = mapped_column(String(16), nullable=False)
    subject_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    bucket_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    bucket_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    algo_version: Mapped[int] = mapped_column(SmallInteger, nullable=False)

    article_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    cumulative_article_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    unique_source_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    source_diversity: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    velocity_1h: Mapped[Decimal | None] = mapped_column(Numeric(8, 3))
    velocity_6h: Mapped[Decimal | None] = mapped_column(Numeric(8, 3))
    velocity_24h: Mapped[Decimal | None] = mapped_column(Numeric(8, 3))
    acceleration: Mapped[Decimal | None] = mapped_column(Numeric(8, 3))
    burst_score: Mapped[Decimal | None] = mapped_column(Numeric(6, 3))
    novelty_score: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    credibility_score: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    trend_state: Mapped[str | None] = mapped_column(String(12))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "subject_type",
            "subject_id",
            "bucket_start",
            "algo_version",
            name="uq_trend_snapshots_subject_bucket_algo",
        ),
        CheckConstraint(
            "subject_type IN ('topic', 'cluster', 'entity')",
            name="ck_trend_snapshots_subject_type",
        ),
        CheckConstraint(
            "trend_state IS NULL OR trend_state IN ('breaking', 'developing', 'stable', 'fading')",
            name="ck_trend_snapshots_trend_state",
        ),
        Index(
            "idx_trend_snapshots_bucket_burst",
            text("bucket_start DESC"),
            text("burst_score DESC"),
        ),
        Index(
            "idx_trend_snapshots_subject_bucket",
            "subject_id",
            text("bucket_start DESC"),
        ),
        Index("idx_trend_snapshots_bucket", "bucket_start"),
    )


class TrendSignal(Base):
    """Kesikli tespit edilen sinyal (v1: burst). status = admin feedback (PR-2c+)."""

    __tablename__ = "trend_signals"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    subject_type: Mapped[str] = mapped_column(String(16), nullable=False)
    subject_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    signal_type: Mapped[str] = mapped_column(String(24), nullable=False)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    bucket_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    algo_version: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    magnitude: Mapped[Decimal | None] = mapped_column(Numeric(6, 3))
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'new'"))
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "subject_type",
            "subject_id",
            "signal_type",
            "detected_at",
            "algo_version",
            name="uq_trend_signals_dedup",
        ),
        CheckConstraint(
            "subject_type IN ('topic', 'cluster', 'entity')",
            name="ck_trend_signals_subject_type",
        ),
        CheckConstraint(
            "signal_type IN ('burst', 'demand_spike', 'new_actor', 'source_spike', 'sustained')",
            name="ck_trend_signals_signal_type",
        ),
        CheckConstraint(
            "status IN ('new', 'approved', 'dismissed', 'merged', 'split')",
            name="ck_trend_signals_status",
        ),
        Index("idx_trend_signals_recent", text("detected_at DESC"), "signal_type"),
        Index("idx_trend_signals_status", "status", text("detected_at DESC")),
    )
