"""Style profile + style sample ORM (#52, Faz 5).

docs/engineering/data-model.md §7.1-7.2
PRD §5

Status workflow:
    pending     — yeni oluştu, sample 0
    analyzing   — Celery task çalışıyor (Style Analyzer LLM)
    ready       — rules_json doldu, generation'da kullanılabilir
    failed      — analyzer başarısız, error_message dolu

Source types:
    manual          — kullanıcı UI'dan tek tek metin ekledi
    csv_import      — toplu CSV upload
    public_account  — kamuya açık hesaptan örnek (manuel kopyala)
    x_personal      — kullanıcı kendi X hesabından (henüz disabled)
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
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class StyleProfile(Base):
    __tablename__ = "style_profiles"
    __table_args__ = (
        CheckConstraint(
            "source_type IN ('manual', 'csv_import', 'public_account', 'x_personal')",
            name="ck_style_profiles_source_type",
        ),
        CheckConstraint(
            "status IN ('pending', 'analyzing', 'ready', 'failed')",
            name="ck_style_profiles_status",
        ),
        # Phase 8.2 PR-8.2-5: DB'de mevcut user list query hot path
        # Migration: 20260509_0700_style_profiles_schema.py
        Index(
            "idx_style_profiles_user",
            "user_id",
            sql_text("created_at DESC"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sql_text("gen_random_uuid()"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=sql_text("'pending'")
    )
    style_summary: Mapped[str | None] = mapped_column(Text)
    rules_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=sql_text("'{}'::jsonb")
    )
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=sql_text("0"))
    error_message: Mapped[str | None] = mapped_column(Text)
    analyzed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    samples: Mapped[list[StyleSample]] = relationship(
        back_populates="profile",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class StyleSample(Base):
    __tablename__ = "style_samples"
    __table_args__ = (
        # Phase 8.2 PR-8.2-5: DB'de mevcut FK lookup index
        # Migration: 20260509_0700_style_profiles_schema.py
        Index("idx_style_samples_profile", "style_profile_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sql_text("gen_random_uuid()"),
    )
    style_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("style_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text)
    char_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=sql_text("0"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    profile: Mapped[StyleProfile] = relationship(back_populates="samples")
