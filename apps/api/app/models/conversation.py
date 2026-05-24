"""Conversation + Message ORM (#793 S1 — Perplexity-style research UX).

docs/engineering/data-model.md §6 (yeni section, conversation-mode)

Mevcut `generations` tablosu korunur (backward compat — admin/billing).
S1B (#800): Generation tablosu DROP edildi (research-only migration). messages
artık standalone — generation_id kolonu/FK yok. SFT + DPO doğrudan messages
üzerinden çalışır.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    LargeBinary,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class Conversation(Base):
    """Bir sohbet birimi — user-bound, ordered messages.

    Title ilk mesajdan auto-generate (50 char özet). Summary son N mesajdan
    LLM özeti — context budget korumak için (4+ mesaj sonrası).
    """

    __tablename__ = "conversations"

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
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str | None] = mapped_column(
        String(500),
        comment="Son N mesaj özeti — context budget korumak için.",
    )
    """Son N mesaj özeti — context budget korumak için (4+ mesaj sonrası)."""

    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
    )

    # Relationships
    messages: Mapped[list[Message]] = relationship(
        "Message",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
    )

    __table_args__ = (Index("idx_conversations_user_updated", "user_id", text("updated_at DESC")),)


class Message(Base):
    """User query veya assistant cevap.

    Assistant mesajları:
    - `sources_used` LLM tarafından kullanılan kaynaklar [{article_id, chunk_id, ...}]
    - `sources_considered` LLM'in gördüğü ama kullanmadığı (follow-up reuse için)
    - `query_embedding` user query bge-m3 embedding (BYTEA — raw float32 bytes)
    - `thinking_steps` SSE event log
    - `halu_flagged_*` halüsinasyon bildirimi (S1B)
    - `user_action`, `edit_distance`, `edited_content` SFT quality signal (S1B)
    - `sft_eligible`, `sft_excluded_reason` SFT pipeline (S1B)
    - `dpo_rejected`, `dpo_chosen_content` DPO training (S1B)
    """

    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        comment="'user' | 'assistant'",
    )
    """'user' | 'assistant'"""

    content: Mapped[str] = mapped_column(Text, nullable=False)

    sources_used: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSONB,
        comment="[{article_id, chunk_id, url, title, relevance}, ...] — generator tarafından kullanılan",
    )
    sources_considered: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSONB,
        comment="LLM'in gördüğü ama kullanmadığı kaynaklar — follow-up reuse için",
    )
    query_embedding: Mapped[bytes | None] = mapped_column(
        LargeBinary,
        comment="User query bge-m3 embedding (raw bytes) — follow-up relatedness için",
    )
    """User query bge-m3 embedding (1024 × float32 = 4096 bytes) —
    follow-up relatedness için cosine similarity."""

    effective_query: Mapped[str | None] = mapped_column(Text)
    """#1013 (Faz 2a) — condense (#833) sonrası standalone/bağlamlı
    sorgu metni. Ham user content L1 follow-up'ta bağlama bağımlı
    olabilir; bu alan eğitim çiftini self-contained tutar (RAM'de
    üretilip atılıyordu → SFT INPUT bütünlüğü, L1 önkoşulu). Assistant
    mesajına yazılır; None ise ham content'e düşülür (geriye-uyum)."""

    thinking_steps: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSONB,
        comment="SSE thinking event log — ['planner: ...', 'hyde: ...', ...]",
    )
    """SSE thinking event log — [{phase, detail, latency_ms}, ...]."""

    followup_suggestions: Mapped[list[str] | None] = mapped_column(JSONB)
    """#961 — cevap-sonrası 5 dinamik takip/keşif sorusu (assistant
    mesajına ait; ayrı non-blocking LLM call ürünü). Geçmiş yüklemede
    gösterilir; ileride SFT/DPO sinyali. Selamlama/kimlik/meta veya
    degrade'de None."""

    # ---- Halu flag (S1B) ----
    halu_flagged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    halu_flagged_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
    )
    halu_flagged_reason: Mapped[str | None] = mapped_column(Text)

    # ---- User action (SFT signal) ----
    user_action: Mapped[str | None] = mapped_column(String(16))
    """'copied' | 'posted' | 'edited' | 'none'"""
    user_action_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    edit_distance: Mapped[float | None] = mapped_column(Numeric(3, 2))
    edited_content: Mapped[str | None] = mapped_column(Text)

    # ---- SFT eligibility ----
    sft_eligible: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    sft_excluded_reason: Mapped[str | None] = mapped_column(String(64))
    sft_recomputed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # ---- DPO (halu-rejected pair için) ----
    dpo_rejected: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    dpo_chosen_content: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
    )

    conversation: Mapped[Conversation] = relationship("Conversation", back_populates="messages")

    __table_args__ = (
        CheckConstraint(
            "role IN ('user', 'assistant')",
            name="messages_role_check",
        ),
        Index("idx_messages_conv_created", "conversation_id", "created_at"),
        # S1B (#800): generation_id kolonu kaldırıldı (research-only migration);
        # SFT + DPO index'leri migration 20260514_1800'de eklendi (orada def).
    )
