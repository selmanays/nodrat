"""TakedownRequest ORM (#35).

docs/legal/opinion-integration.md §3.4
docs/legal/incident-response.md §3 (24h SLA)
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
    func,
    text,
)
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class TakedownRequest(Base):
    """4 takedown form: abuse / takedown / copyright / privacy_request."""

    __tablename__ = "takedown_requests"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    ticket_id: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        unique=True,
        server_default=text(
            "'TKD-' || EXTRACT(YEAR FROM NOW()) || '-' || "
            "LPAD(NEXTVAL('takedown_ticket_seq')::text, 6, '0')"
        ),
    )
    """TKD-2026-NNNNNN format (auto-generated, server-side sequence)."""

    request_type: Mapped[str] = mapped_column(String(32), nullable=False)
    """'abuse' | 'takedown' | 'copyright' | 'privacy_request'"""

    requester_name: Mapped[str | None] = mapped_column(String(180))
    requester_email: Mapped[str] = mapped_column(Text, nullable=False)
    requester_phone: Mapped[str | None] = mapped_column(String(40))
    requester_organization: Mapped[str | None] = mapped_column(String(180))
    authority_claim: Mapped[str | None] = mapped_column(Text)
    """'telif sahibiyim', 'KVKK ilgili kişiyim', vb."""

    subject_url: Mapped[str | None] = mapped_column(Text)
    subject_article_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    subject_generation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    description: Mapped[str] = mapped_column(Text, nullable=False)
    # Phase 8.2 PR-8.2-9 modify_nullable drift fix:
    # Migration 20260502_0200_add_takedown_requests.py'da `sa.Column("evidence_urls", JSONB,
    # server_default=...)` — sa.Column DEFAULT'u nullable=True (DB allows NULL).
    # Önceki ORM `Mapped[list[str]]` non-Optional → SQLAlchemy nullable=False çıkardı; bu
    # autogenerate modify_nullable drift yaratıyordu.
    # Insert path audit (PR-8.2-9 scope):
    #   - app_me.py L558: `evidence_urls=[]` (boş liste)
    #   - legal/routes.py L178: _validate_evidence_urls(...) → list[str]
    #   - legal/routes.py L211: `req.evidence_urls or []` (defensif `or []`)
    # Pratikte hiç None yazılmıyor; server_default '[]'::jsonb.
    # Tip sistemini DB ile hizala (Optional). Read path yok (model obj üzerinden okunmuyor).
    evidence_urls: Mapped[list[str] | None] = mapped_column(
        JSONB, server_default=text("'[]'::jsonb")
    )

    status: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default=text("'submitted'")
    )
    """submitted → triaging → investigating → action_taken | rejected | closed"""

    priority: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'normal'")
    )
    """low | normal | high | critical"""

    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    triaged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    investigating_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sla_due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    action_taken: Mapped[str | None] = mapped_column(Text)
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    internal_notes: Mapped[str | None] = mapped_column(Text)

    ip_address: Mapped[Any | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "request_type IN ('abuse', 'takedown', 'copyright', 'privacy_request')",
            name="ck_takedown_requests_type",
        ),
        CheckConstraint(
            "status IN ('submitted', 'triaging', 'investigating', "
            "'action_taken', 'rejected', 'closed')",
            name="ck_takedown_requests_status",
        ),
        CheckConstraint(
            "priority IN ('low', 'normal', 'high', 'critical')",
            name="ck_takedown_requests_priority",
        ),
        Index(
            "idx_takedown_status_sla",
            "status",
            "sla_due_at",
            postgresql_where=text("status IN ('submitted', 'triaging', 'investigating')"),
        ),
        Index(
            "idx_takedown_type_created",
            "request_type",
            text("created_at DESC"),
        ),
        Index(
            "idx_takedown_assigned",
            "assigned_to",
            postgresql_where=text("assigned_to IS NOT NULL"),
        ),
    )
