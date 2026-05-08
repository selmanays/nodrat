"""CrawlerJob + FailedJob (DLQ) + AdminAuditLog modelleri.

docs/engineering/data-model.md §3.6, §3.7, §5.4
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
    SmallInteger,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class CrawlerJob(Base):
    """Worker queue ledger — Celery dispatch buradan idempotent yapılır."""

    __tablename__ = "crawler_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    job_type: Mapped[str] = mapped_column(String(64), nullable=False)
    """source.fetch_rss | source.fetch_category | article.discover |
       article.fetch_detail | article.extract | article.clean |
       media.download | media.hash | article.dedupe | source.healthcheck"""

    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'queued'")
    )
    """'queued' | 'running' | 'succeeded' | 'failed' | 'dead'"""

    priority: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default=text("50")
    )
    payload_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )

    attempt_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    max_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("3")
    )

    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)

    source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sources.id", ondelete="CASCADE"),
    )
    article_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("articles.id", ondelete="CASCADE"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'dead')",
            name="ck_crawler_jobs_status",
        ),
    )


class FailedJob(Base):
    """Dead Letter Queue — admin retry / mark resolved akışı."""

    __tablename__ = "failed_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    original_job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    job_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sources.id", ondelete="SET NULL"),
    )
    article_url: Mapped[str | None] = mapped_column(Text)

    error_message: Mapped[str] = mapped_column(Text, nullable=False)
    stack_trace: Mapped[str | None] = mapped_column(Text)
    """Sadece admin görebilir."""

    severity: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'error'")
    )
    """error | warning | permanent_info — #445.

    permanent_info: RSS re-emit gibi "hata değil ama log'lanması gereken"
    olaylar. Default sorguda admin sayfasında görünmez (alarm yorgunluğu
    önlenir). Yazılırken resolved_at=now() ile auto-resolve edilir.
    """

    retry_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    last_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    resolution_note: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AdminAuditLog(Base):
    """Admin işlem audit log'u — Legal §8.3 (KVKK uyumu)."""

    __tablename__ = "admin_audit_log"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    actor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
    )
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    """source.create | source.update | source.delete | source.activate |
       source.deactivate | article.reprocess | user.role_change |
       provider.config_change | takedown.process | data_export | account_delete"""

    target_type: Mapped[str | None] = mapped_column(String(80))
    """'source' | 'article' | 'user' | 'provider' | 'takedown_request'"""

    target_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    # SQL column name "metadata" — Python attribute "event_metadata"
    # ('metadata' SQLAlchemy declarative API'de rezerve)
    event_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata", JSONB, server_default=text("'{}'::jsonb")
    )

    ip_address: Mapped[Any | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index(
            "idx_admin_audit_log_actor_created",
            "actor_id",
            text("created_at DESC"),
        ),
        Index(
            "idx_admin_audit_log_action_created",
            "action",
            text("created_at DESC"),
        ),
        Index(
            "idx_admin_audit_log_target",
            "target_type",
            "target_id",
            postgresql_where=text("target_id IS NOT NULL"),
        ),
    )
