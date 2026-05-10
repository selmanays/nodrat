"""Source + SourceConfig + SourceHealth modelleri (Faz 1).

docs/engineering/data-model.md §3.1, §3.2, §3.3
docs/legal/compliance-brief.md §4 — Compliance fields (tos_acknowledged, robots_txt_compliant)
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
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
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class Source(Base):
    """Haber kaynağı (RSS / Category page / Manual).

    Compliance: tos_acknowledged + robots_txt_compliant zorunlu (Legal §4).
    """

    __tablename__ = "sources"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    domain: Mapped[str] = mapped_column(String(180), nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    """'rss' | 'category_page' | 'manual'"""

    base_url: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(
        String(10), nullable=False, server_default=text("'tr'")
    )
    country: Mapped[str] = mapped_column(
        String(8), nullable=False, server_default=text("'TR'")
    )
    category: Mapped[str | None] = mapped_column(String(80))

    reliability_score: Mapped[Decimal] = mapped_column(
        Numeric(3, 2), nullable=False, server_default=text("0.70")
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("FALSE")
    )
    crawl_interval_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("30")
    )

    last_crawled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Conditional GET — bandwidth optimize + 304 Not Modified path (#565)
    etag: Mapped[str | None] = mapped_column(String(255))
    last_modified: Mapped[str | None] = mapped_column(String(255))

    # Realtime polling (Faz 2+ adaptive tier ön schema; bu PR sadece data foundation)
    realtime_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("FALSE")
    )
    polling_tier: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'normal'")
    )
    """'hot' | 'normal' | 'cold' | 'hibernate' — Faz 3'te apply edilir.

    Faz 2'de (#578) shadow mode'da hesap `would_be_tier`'a yazılır;
    `app_settings.rss.tier_shadow_mode=false` + `tier_apply_enabled=true`
    olduğunda polling_tier = would_be_tier transition'ı işler.
    """

    consecutive_unchanged: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    """Peş peşe 304 Not Modified sayacı — tier kararında kullanılır."""

    # Adaptive tier shadow mode (#578 Faz 2)
    would_be_tier: Mapped[str | None] = mapped_column(String(16))
    """Shadow mode'da hesaplanan tier ('hot'|'normal'|'cold'|'hibernate'); apply
    edilmez. Faz 3'te `polling_tier` ile senkronize edilir."""

    tier_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    """En son `polling_tier` değişimi (dwell-time guard için 15 dk minimum)."""

    tier_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    """compute_tier telemetrisi: items_1h, items_6h, last_item_at,
    hours_since_new, consecutive_unchanged, computed_at. Admin UI'da gösterilir."""

    # Compliance (Legal §4)
    robots_txt_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    robots_txt_compliant: Mapped[bool | None] = mapped_column(Boolean)
    tos_acknowledged: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("FALSE")
    )

    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationships
    configs: Mapped[list[SourceConfig]] = relationship(
        back_populates="source", cascade="all, delete-orphan"
    )
    health: Mapped[SourceHealth | None] = relationship(
        back_populates="source",
        uselist=False,
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        CheckConstraint(
            "type IN ('rss', 'category_page', 'manual')",
            name="ck_sources_type",
        ),
        CheckConstraint(
            "reliability_score >= 0.0 AND reliability_score <= 1.0",
            name="ck_sources_reliability_range",
        ),
        CheckConstraint(
            "polling_tier IN ('hot', 'normal', 'cold', 'hibernate')",
            name="ck_sources_polling_tier",
        ),
        CheckConstraint(
            "would_be_tier IS NULL OR "
            "would_be_tier IN ('hot', 'normal', 'cold', 'hibernate')",
            name="ck_sources_would_be_tier",
        ),
        Index(
            "idx_sources_active",
            "is_active",
            postgresql_where=text("is_active = TRUE"),
        ),
        Index("idx_sources_type", "type"),
        Index("idx_sources_domain", "domain"),
    )


class SourceConfig(Base):
    """Kaynak konfigürasyonu — versiyonlu, tek aktif (partial unique)."""

    __tablename__ = "source_configs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sources.id", ondelete="CASCADE"),
        nullable=False,
    )
    config_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    """selectors, RSS field maps, pagination — schema docs/engineering/architecture.md"""

    version: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("FALSE")
    )

    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    source: Mapped[Source] = relationship(back_populates="configs")

    __table_args__ = (
        UniqueConstraint(
            "source_id", "version", name="uq_source_configs_source_version"
        ),
        Index(
            "idx_source_configs_active",
            "source_id",
            postgresql_where=text("is_active = TRUE"),
        ),
        Index(
            "uniq_source_configs_one_active",
            "source_id",
            unique=True,
            postgresql_where=text("is_active = TRUE"),
        ),
    )


class SourceHealth(Base):
    """1:1 latest health snapshot per source."""

    __tablename__ = "source_health"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sources.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    last_status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'unknown'")
    )
    """'green' | 'yellow' | 'red' | 'unknown'"""

    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_count_24h: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    avg_fetch_ms: Mapped[int | None] = mapped_column(Integer)
    avg_extract_confidence: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))
    last_error: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    source: Mapped[Source] = relationship(back_populates="health")

    __table_args__ = (
        CheckConstraint(
            "last_status IN ('green', 'yellow', 'red', 'unknown')",
            name="ck_source_health_status",
        ),
        Index("idx_source_health_status", "last_status"),
    )
