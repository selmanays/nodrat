"""Otomasyon Stüdyosu — veri modeli (Faz 5.0, #1779).

Kullanıcı abone olduğu kümeye KURAL koyar; küme breaking/developing trend-state'ine
girince (Faz 5.1 beat) oto-kaynaklı artefakt üretilir (Faz 5.2), ONAY KUYRUĞUna düşer
(Faz 5.3), opsiyonel sosyal paylaşılır (Faz 5.4 — en son, en sıkı kapı).

Faz 5.0 = SAF İSKELE: 3 tablo, hiçbir okuyucu/yazıcı kod yok → davranış no-op.
social_accounts paylaşım fazına (5.4) kadar BOŞ kalır.

Güvenlik (sonraki fazlarda zorlanır): kaynaksız-asla oto-paylaşma · onay-kuyruğu
VARSAYILAN (mode) · full-auto çoklu-kapı opt-in · token Fernet-şifreli (5.4) ·
user-scoped · soft-delete (KVKK/opt-out izi).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class SocialAccount(Base):
    """Bağlı sosyal hesap (OAuth). Faz 5.4'e kadar BOŞ. Token Fernet-şifreli (bytea)."""

    __tablename__ = "social_accounts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(16), nullable=False)
    """'x' (Twitter) — ilk sağlayıcı; genişletilebilir."""
    provider_user_id: Mapped[str | None] = mapped_column(String(128))
    handle: Mapped[str | None] = mapped_column(String(64))
    access_token: Mapped[bytes | None] = mapped_column(LargeBinary)
    """Fernet-şifreli (5.4 doldurur); PLAINTEXT saklanmaz/loglanmaz."""
    refresh_token: Mapped[bytes | None] = mapped_column(LargeBinary)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scopes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'connected'")
    )
    """'connected' | 'revoked' | 'error'."""
    connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("provider IN ('x')", name="ck_social_accounts_provider"),
        CheckConstraint(
            "status IN ('connected','revoked','error')", name="ck_social_accounts_status"
        ),
        Index(
            "uq_social_accounts_user_provider_live",
            "user_id",
            "provider",
            unique=True,
            postgresql_where=text("revoked_at IS NULL"),
        ),
    )


class AutomationRule(Base):
    """Kullanıcı↔küme otomasyon kuralı. Küme başına TEK canlı kural (partial unique)."""

    __tablename__ = "automation_rules"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    cluster_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("research_clusters.id", ondelete="RESTRICT"),
        nullable=False,
    )
    trigger_config: Mapped[dict] = mapped_column(JSONB, nullable=False)
    """{states:['breaking'], min_article_count?:int, window_seconds:86400}."""
    action_config: Mapped[dict] = mapped_column(JSONB, nullable=False)
    """{generate_artifact:bool, artifact_type:'post'|'thread', share:bool}."""
    mode: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'approval_queue'")
    )
    """'approval_queue' (VARSAYILAN) | 'full_auto' (çoklu-kapı opt-in)."""
    social_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("social_accounts.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'active'"))
    """'active' | 'paused' | 'disabled'."""
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    last_triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("mode IN ('approval_queue','full_auto')", name="ck_automation_rules_mode"),
        CheckConstraint(
            "status IN ('active','paused','disabled')", name="ck_automation_rules_status"
        ),
        Index(
            "uq_automation_rules_user_cluster_live",
            "user_id",
            "cluster_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("idx_automation_rules_cluster", "cluster_id"),
        Index(
            "idx_automation_rules_user_live",
            "user_id",
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )


class AutomationRun(Base):
    """Kural tetiklenince oluşan koşum (kuyruk öğesi). dedupe_key idempotency."""

    __tablename__ = "automation_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    rule_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("automation_rules.id", ondelete="CASCADE"), nullable=False
    )
    cluster_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("research_clusters.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False, server_default=text("'queued'"))
    """queued|pending|skipped_no_sources|skipped_quota|skipped_no_consent|posted|rejected|failed."""
    artifact_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("artifacts.id", ondelete="SET NULL")
    )
    dedupe_key: Mapped[str] = mapped_column(String(160), nullable=False)
    """rule+küme+gün başına tek koşum (idempotency; ON CONFLICT DO NOTHING)."""
    error: Mapped[str | None] = mapped_column(Text)
    triggered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('queued','pending','skipped_no_sources','skipped_quota',"
            "'skipped_no_consent','posted','rejected','failed')",
            name="ck_automation_runs_status",
        ),
        UniqueConstraint("dedupe_key", name="uq_automation_runs_dedupe"),
        Index("idx_automation_runs_rule_created", "rule_id", text("created_at DESC")),
        Index("idx_automation_runs_status", "status"),
    )
