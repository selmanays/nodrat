"""TrainingSample ORM — SFT curated dataset (#567).

docs/engineering/data-model.md §5.4 (training_samples)
wiki/concepts/sft-data-pipeline.md (pipeline mimarisi)

ETL worker (apps/api/app/workers/tasks/sft_curator.py) ham generations
log'undan altın etiketlenmiş satırları curated training dataset'ine
dönüştürür. Trendyol-LLM-7B-chat-v4.1.0 üzerine domain-spesifik
fine-tune için.

KVKK md.11 cascade: user_id FK ON DELETE CASCADE — kullanıcı consent
revoke veya soft delete yaptığında ilgili training_samples otomatik
silinir.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class TrainingSample(Base):
    """SFT curated dataset row.

    Bir generation × task_type kombinasyonu için tek satır
    (UNIQUE constraint ile worker idempotent).
    """

    __tablename__ = "training_samples"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    # S1B (#800): generations tablosu DROP edildi — generation_id NULL
    # bırakıldı (FK kaldırıldı), tarihçe veri "anonim" korunur.
    generation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )
    # S1B (#800): yeni chat-derived sample'lar messages tablosuna bağlı
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("messages.id", ondelete="CASCADE"),
        nullable=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    task_type: Mapped[str] = mapped_column(String(32), nullable=False)
    """'content_generator' (legacy) | 'chat_answer' (yeni) | 'query_planner' | 'style_analyzer'"""

    # S1B (#800): SFT vs DPO sample tipi
    sample_type: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'sft'")
    )
    """'sft' | 'dpo_chosen' | 'dpo_rejected'"""

    prompt_version: Mapped[str] = mapped_column(String(32), nullable=False)
    """Audit — eğitim sırasında hangi prompt sürümü kullanılmıştı."""

    input_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    """ChatML format {messages: [{role, content}, ...]}"""

    output_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    """LLM çıktısı (parsed JSON)."""

    edited_output: Mapped[str | None] = mapped_column(Text)
    """DPO için kullanıcının nihai metni (varsa)."""

    quality_signals: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    """{citation_supported_ratio, edit_distance, time_to_action_sec,
       schema_valid, source_count, char_count}"""

    sft_split: Mapped[str] = mapped_column(String(8), nullable=False)
    """'train' | 'val' | 'test' — deterministic hash(generation_id) % 100"""

    curated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    exported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    """HF Hub push edilince doldurulur (#569 admin SFT dashboard)."""

    __table_args__ = (
        CheckConstraint(
            "task_type IN ('content_generator', 'chat_answer', 'query_planner', 'style_analyzer')",
            name="ck_training_samples_task_type",
        ),
        CheckConstraint(
            "sample_type IN ('sft', 'dpo_chosen', 'dpo_rejected')",
            name="training_samples_sample_type_check",
        ),
        CheckConstraint(
            "sft_split IN ('train', 'val', 'test')",
            name="ck_training_samples_sft_split",
        ),
        # UNIQUE (generation_id, task_type) — S1B'de DROP edildi
        # UNIQUE (message_id, task_type, sample_type) — migration 20260514_1900 partial index
        Index("idx_training_samples_task", "task_type", "sft_split"),
        Index("idx_training_samples_user", "user_id"),
        Index("idx_training_samples_curated", text("curated_at DESC")),
    )
