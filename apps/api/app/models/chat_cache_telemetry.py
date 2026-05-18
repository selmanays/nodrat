"""ChatCacheTelemetry ORM — generate-hattı prompt-cache segment ledger'ı (#981).

`provider_call_logs` token TOPLAMINI tutar ama KOMPOZİSYONU (system / tools
schema / msg1 / rag-tool / assistant-ara) tutmaz → cache-miss nedene
atfedilemez, regresyon yakalanamaz. Bu tablo IZOLE: yalnız generate (chat)
hattı; billing ledger (`usage_events`) ve RAG-oluşturma hattından ayrı.

KVKK: yalnız token SAYISI + id'ler — içerik/soru metni ASLA yazılmaz.
docs/engineering/data-model.md §4.6 (#981)
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
    SmallInteger,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class ChatCacheTelemetry(Base):
    """Tek chat LLM çağrısı için cache + segment ölçümü (best-effort yazılır)."""

    __tablename__ = "chat_cache_telemetry"

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
