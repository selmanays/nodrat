"""ResearchCluster + MessageCluster ORM — #1015 (Pivot Faz 3).

GLOBAL kümeleme: sistemde tek kanonik "CHP" düğümü ("tek sağlayıcı,
çok dinleyici"). `research_clusters` user_id TAŞIMAZ — paylaşımlıdır.
Kullanıcı görünürlüğü `message_clusters ⋈ messages ⋈ conversations
WHERE user_id=?` ile TÜRETİLİR (cross-user sızma yok). Wiki kanonik-
slug modeli + mevcut `entities.entity_normalized` omurgası reuse.

Mevcut `tasks.clustering.*` (haber-OLAY kümeleme, "Olay Kümeleme"
settings grubu) ile KARIŞTIRMA — bu AYRI namespace (araştırma kümesi).

Additive: mevcut tablolara DOKUNMAZ. FK ON DELETE:
- message_clusters.message_id → CASCADE  (mesaj/sohbet silinince üyelik gider)
- message_clusters.cluster_id → RESTRICT (global düğüm korunur)
- message_clusters.user_id   → CASCADE  (KVKK; kullanıcı silinince üyelik gider)
research_clusters düğümü kullanıcı/mesaj silinse de KALIR (paylaşımlı);
boş küme → async soft-deprecate (deprecated_at; S12).

Plan: .claude/plans/...nemli-deep-forest.md rev.12 §4/§7 · S11/S12.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class ResearchCluster(Base):
    """GLOBAL kanonik araştırma kümesi düğümü (paylaşımlı, no user_id)."""

    __tablename__ = "research_clusters"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    cluster_key: Mapped[str] = mapped_column(String(320), nullable=False)
    """Dedup omurgası = '<type>:<entity_normalized-kebab-ascii>'. Wiki
    'iki sayfa asla aynı slug' karşılığı; çakışmada type-prefix ayırır.
    UNIQUE (deprecated_at IS NULL partial index)."""

    cluster_type: Mapped[str] = mapped_column(String(20), nullable=False)
    """entities.entity_type ile hizalı: person|organization|location|
    topic|object|visual_type."""

    canonical_name: Mapped[str] = mapped_column(String(200), nullable=False)
    aliases: Mapped[list[str] | None] = mapped_column(JSONB)

    parent_cluster_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("research_clusters.id", ondelete="SET NULL"),
        nullable=True,
    )
    """GLOBAL hiyerarşi (Faz 6 — aggregate df-asimetri ile doldurulur;
    şimdi additive/NULL — kullanım deseni çıkarımı, ansiklopedi DEĞİL)."""

    centroid_embedding: Mapped[bytes | None] = mapped_column(LargeBinary)
    """bge-m3 (1024×float32) — entity'siz sorgu fallback eşleştirmesi."""

    is_public_figure: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    sensitivity_flag: Mapped[str | None] = mapped_column(String(32))
    """KVKK — health|religion|political vb. (şimdilik NULL; ileri rafine)."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    deprecated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    """Soft-delete (S12 — boş/orphan küme; user-tetikli DEĞİL, async)."""

    __table_args__ = (
        Index(
            "uq_research_clusters_key_active",
            "cluster_key",
            unique=True,
            postgresql_where=text("deprecated_at IS NULL"),
        ),
        Index(
            "idx_research_clusters_type_updated",
            "cluster_type",
            text("updated_at DESC"),
        ),
    )


class MessageCluster(Base):
    """Üyelik — global küme ↔ kullanıcı mesajı (görünürlük user-scoped)."""

    __tablename__ = "message_clusters"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("messages.id", ondelete="CASCADE"),
        nullable=False,
    )
    cluster_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("research_clusters.id", ondelete="RESTRICT"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    mention_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    assigned_via: Mapped[str] = mapped_column(String(20), nullable=False)
    """'entity' (nadir-entity çapa) | 'embedding_fallback'."""
    context: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )

    __table_args__ = (
        UniqueConstraint("message_id", "cluster_id", name="uq_message_cluster"),
        Index("idx_message_clusters_message", "message_id"),
        Index(
            "idx_message_clusters_user_created",
            "user_id",
            text("created_at DESC"),
        ),
        Index("idx_message_clusters_cluster_user", "cluster_id", "user_id"),
    )
