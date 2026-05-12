"""ProviderCallLog ORM model — LLM/embedding çağrı ledger'ı.

docs/engineering/data-model.md §4.5
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class ProviderCallLog(Base):
    """Tek LLM/embedding/rerank/vision çağrısı kaydı.

    Faz 2'den itibaren her provider call sonrası INSERT edilir.
    Cost tracking + alarm + admin dashboard üzerinden okunur.
    """

    __tablename__ = "provider_call_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    """provider.name — örn: 'local_bge_m3', 'deepseek', 'anthropic_haiku',
    'nim_rerank', 'nim_vlm'."""

    model: Mapped[str | None] = mapped_column(String(120))
    """API'ye gönderilen model adı — örn: 'BAAI/bge-m3' (local), 'deepseek-v4-flash'."""

    operation: Mapped[str] = mapped_column(String(64), nullable=False)
    """'chat' | 'embedding' | 'rerank' | 'vision'"""

    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    cached_tokens: Mapped[int | None] = mapped_column(Integer)
    """#171 — DeepSeek prompt cache hit token sayısı (cache miss = input - cached)."""

    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    """USD cinsinden maliyet (provider tablosundan hesap edilir)"""

    latency_ms: Mapped[int | None] = mapped_column(Integer)

    # Lineage (PII redaction'a tabi - user_id var ama LLM provider'a gönderilmez)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
    )
    generation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    """Faz 3 generations.id — şimdilik FK yok (cross-faz dependency)"""

    article_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    """Hangi article için yapıldı (embedding/clean) — FK yok (volume)"""

    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        Index(
            "idx_provider_call_logs_created",
            text("created_at DESC"),
        ),
        Index(
            "idx_provider_call_logs_user_created",
            "user_id",
            text("created_at DESC"),
            postgresql_where=text("user_id IS NOT NULL"),
        ),
        Index(
            "idx_provider_call_logs_provider_created",
            "provider",
            text("created_at DESC"),
        ),
    )
