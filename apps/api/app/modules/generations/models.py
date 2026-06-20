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
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
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
    """ENTITY_DF_SQL çapa tipi = ham entities.entity_type; resolver +
    cluster_assigner yalnız person|org|place|event filtreler (dedup
    cluster_key üzerinden, bu alandan değil)."""

    canonical_name: Mapped[str] = mapped_column(String(200), nullable=False)
    aliases: Mapped[list[str] | None] = mapped_column(JSONB)

    parent_cluster_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("research_clusters.id", ondelete="SET NULL"),
        nullable=True,
    )
    """GLOBAL hiyerarşi (Faz 6 — aggregate df-asimetri ile doldurulur;
    şimdi additive/NULL — kullanım deseni çıkarımı, ansiklopedi DEĞİL)."""

    canonical_entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    """Küme-merkezli abonelik (Faz 0) — kümeyi kanonik varlığa demirler.
    `canonical_entities` raw-SQL-only tablo → hard FK YOK (soft ref, entities
    deseni). Sorgu→küme çözümü bu anchor üzerinden kalıcılaşır."""

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
        Index(
            "idx_research_clusters_canonical_entity",
            "canonical_entity_id",
            postgresql_where=text("canonical_entity_id IS NOT NULL"),
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


# -----------------------------------------------------------------------------
# Küme-merkezli abonelik vizyonu — Faz 0 iskeleti (additive, davranış no-op).
# Karar (founder, 2026-06-19): birim=ResearchCluster + canonical_entity anchor;
# artefakt=ayrı tablolar; sahiplik=generations modülü.
# -----------------------------------------------------------------------------
class UserClusterSubscription(Base):
    """Kullanıcı↔küme AÇIK, çıkılabilir abonelik (Faz 0).

    Bugünkü örtük üyelik (`message_clusters` JOIN) yerine niyet katmanı:
    sorgu→küme çözümünde otomatik abone (`source='auto_query'`), kullanıcı
    çıkabilir (`unsubscribed_at` soft-delete; satır SİLİNMEZ → geçmiş + KVKK).
    Bir kullanıcı bir küme için en fazla TEK canlı abonelik (partial unique).
    """

    __tablename__ = "user_cluster_subscriptions"

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
    cluster_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("research_clusters.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    """'active' | 'paused' | 'unsubscribed'."""
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="auto_query")
    """'auto_query' (sorgu→küme oto-abone) | 'manual'."""
    preferences: Mapped[dict | None] = mapped_column(JSONB)
    """Bildirim tercihleri (hangi trend_state'te uyar, mute vb.)."""
    subscribed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    unsubscribed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )

    __table_args__ = (
        Index(
            "uq_user_cluster_sub_live",
            "user_id",
            "cluster_id",
            unique=True,
            postgresql_where=text("unsubscribed_at IS NULL"),
        ),
        Index(
            "idx_user_cluster_sub_user_live",
            "user_id",
            postgresql_where=text("unsubscribed_at IS NULL"),
        ),
        Index("idx_user_cluster_sub_cluster", "cluster_id"),
    )


class Artifact(Base):
    """Küme-bağlı paylaşılabilir artefakt (X gönderisi/thread/canvas) — Faz 0.

    Çıktı = sohbet turu DEĞİL, küme-bağlı versiyonlanabilir artefakt.
    `head_revision_id` en güncel revizyona soft işaretçi (app-maintained,
    hard FK YOK → circular-FK önlenir). `origin_message_id` legacy mesaj
    köprüsü (mesaj silinse de artefakt KALIR).
    """

    __tablename__ = "artifacts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
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
    artifact_type: Mapped[str] = mapped_column(String(16), nullable=False)
    """'post' | 'thread' | 'canvas'."""
    head_revision_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    """En güncel revizyon işaretçisi (app-maintained; hard FK YOK — circular)."""
    origin_message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("messages.id", ondelete="SET NULL"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )

    __table_args__ = (
        Index(
            "idx_artifacts_cluster_created",
            "cluster_id",
            text("created_at DESC"),
        ),
        Index(
            "idx_artifacts_user_created",
            "user_id",
            text("created_at DESC"),
        ),
        Index(
            "idx_artifacts_origin_message",
            "origin_message_id",
            postgresql_where=text("origin_message_id IS NOT NULL"),
        ),
    )


class ArtifactRevision(Base):
    """Artefakt sürüm/revizyon zinciri (DAG) — Faz 0.

    Her revizyon immutable snapshot; revizyon-vs-yeni ayrımı + DPO çiftleri
    (Faz 3) bu zincirden türetilir. `query_embedding` KOPYALANIR, asla yeniden
    hesaplanmaz (embedding HARD-STOP).
    """

    __tablename__ = "artifact_revisions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    artifact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("artifacts.id", ondelete="CASCADE"),
        nullable=False,
    )
    revision_seq: Mapped[int] = mapped_column(Integer, nullable=False)
    parent_revision_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("artifact_revisions.id", ondelete="SET NULL"),
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    revision_intent: Mapped[str] = mapped_column(String(24), nullable=False)
    """'initial' | 'quick_shorter' | 'quick_rewrite' | 'quick_longer' |
    'multi_share' | 'freetext' | 'edit' | 'system'. (freetext/edit = manuel
    kullanıcı düzeltmesi → SFT artefakt-curator DPO sinyali.)"""
    sources_used: Mapped[list | None] = mapped_column(JSONB)
    effective_query: Mapped[str | None] = mapped_column(Text)
    query_embedding: Mapped[bytes | None] = mapped_column(LargeBinary)
    """bge-m3 — KOPYALANIR (Faz 3), asla re-embed edilmez."""
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )

    __table_args__ = (
        UniqueConstraint("artifact_id", "revision_seq", name="uq_artifact_revision_seq"),
        Index(
            "idx_artifact_revisions_artifact",
            "artifact_id",
            "revision_seq",
        ),
    )


# T8-15 (2026-05-28): moved from app/models/research_cache_telemetry.py.
# Generate-hattı prompt-cache segment ledger'ı (#981). İzole tablo: yalnız
# generate (research) hattı; billing ledger (usage_events) ve RAG hattından ayrı.
# KVKK: yalnız token SAYISI + id'ler — içerik/soru metni ASLA yazılmaz.
# docs/engineering/data-model.md §4.6 (#981)
class ResearchCacheTelemetry(Base):
    """Tek research LLM çağrısı için cache + segment ölçümü (best-effort yazılır)."""

    __tablename__ = "research_cache_telemetry"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Lineage — user_id KVKK silme hakkı için SET NULL; conversation_id FK YOK
    # (provider_call_logs.generation_id paterni — volume/cross-faz).
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    call_type: Mapped[str] = mapped_column(String(32), nullable=False)
    """'tool_round' | 'forced_final' | 'condense' | 'followup' | 'unknown'."""
    call_seq: Mapped[int | None] = mapped_column(SmallInteger)
    """Generation-turn içi çağrı sırası (1..N)."""

    tools_present: Mapped[bool | None] = mapped_column(Boolean)
    """tools schema payload'da var mıydı (Senaryo B forced-final tanısı)."""
    model: Mapped[str | None] = mapped_column(String(120))

    # Provider GERÇEK totalleri (ground truth — segment drift doğrulaması)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    cached_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)

    # Segment token sayıları — YAKLAŞIK (≈chars/4); amaç trend/atıf, fatura
    # DEĞİL. Σseg ≈ input_tokens drift'i kendisi bir sinyaldir.
    seg_system: Mapped[int | None] = mapped_column(Integer)
    seg_tools_schema: Mapped[int | None] = mapped_column(Integer)
    seg_msg1_static: Mapped[int | None] = mapped_column(Integer)
    seg_msg1_history: Mapped[int | None] = mapped_column(Integer)
    seg_msg1_question: Mapped[int | None] = mapped_column(Integer)
    seg_rag_tool: Mapped[int | None] = mapped_column(Integer)
    seg_assistant_intermediate: Mapped[int | None] = mapped_column(Integer)

    latency_ms: Mapped[int | None] = mapped_column(Integer)
    success: Mapped[bool | None] = mapped_column(Boolean)

    __table_args__ = (
        Index("idx_cct_created", text("created_at DESC")),
        Index(
            "idx_cct_user_created",
            "user_id",
            text("created_at DESC"),
            postgresql_where=text("user_id IS NOT NULL"),
        ),
        Index("idx_cct_conversation", "conversation_id"),
        Index("idx_cct_calltype_created", "call_type", text("created_at DESC")),
    )
