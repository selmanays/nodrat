"""Add takedown_requests (#35)

docs/legal/opinion-integration.md §3.4 (4 takedown endpoint)
docs/legal/incident-response.md §3 (24h SLA)

4 form type: abuse, takedown, copyright, privacy_request
State: submitted → triaging → investigating → action_taken | rejected | closed
SLA: 24h triage, 7-30 days resolution

Revision ID: 20260502_0200
Revises: 20260502_0100
Create Date: 2026-05-02 02:00:00 UTC
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID


revision: str = "20260502_0200"
down_revision: Union[str, None] = "20260502_0100"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # auto-increment ticket sequence (TKD-2026-NNNNNN)
    op.execute("CREATE SEQUENCE IF NOT EXISTS takedown_ticket_seq START 1")

    op.create_table(
        "takedown_requests",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "ticket_id",
            sa.String(20),
            nullable=False,
            unique=True,
            server_default=sa.text(
                "'TKD-' || EXTRACT(YEAR FROM NOW()) || '-' || LPAD(NEXTVAL('takedown_ticket_seq')::text, 6, '0')"
            ),
        ),
        sa.Column("request_type", sa.String(32), nullable=False),
        # 'abuse' | 'takedown' | 'copyright' | 'privacy_request'
        sa.Column("requester_name", sa.String(180)),
        sa.Column("requester_email", sa.Text, nullable=False),
        sa.Column("requester_phone", sa.String(40)),
        sa.Column("requester_organization", sa.String(180)),
        # Authority claim — telif sahibi mi, KVKK ilgili kişi mi
        sa.Column("authority_claim", sa.Text),
        sa.Column("subject_url", sa.Text),
        sa.Column("subject_article_id", UUID(as_uuid=True)),
        sa.Column("subject_generation_id", UUID(as_uuid=True)),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("evidence_urls", JSONB, server_default=sa.text("'[]'::jsonb")),
        # State
        sa.Column(
            "status",
            sa.String(24),
            nullable=False,
            server_default=sa.text("'submitted'"),
        ),
        sa.Column(
            "priority",
            sa.String(16),
            nullable=False,
            server_default=sa.text("'normal'"),
        ),
        # Lifecycle
        sa.Column(
            "submitted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("triaged_at", sa.DateTime(timezone=True)),
        sa.Column("investigating_at", sa.DateTime(timezone=True)),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column(
            "sla_due_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW() + INTERVAL '24 hours'"),
        ),
        # Action
        sa.Column("action_taken", sa.Text),
        sa.Column("rejection_reason", sa.Text),
        sa.Column(
            "assigned_to",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
        ),
        sa.Column("internal_notes", sa.Text),
        # Anti-spam
        sa.Column("ip_address", INET),
        sa.Column("user_agent", sa.Text),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint(
            "request_type IN ('abuse', 'takedown', 'copyright', 'privacy_request')",
            name="ck_takedown_requests_type",
        ),
        sa.CheckConstraint(
            "status IN ('submitted', 'triaging', 'investigating', "
            "'action_taken', 'rejected', 'closed')",
            name="ck_takedown_requests_status",
        ),
        sa.CheckConstraint(
            "priority IN ('low', 'normal', 'high', 'critical')",
            name="ck_takedown_requests_priority",
        ),
    )

    op.create_index(
        "idx_takedown_status_sla",
        "takedown_requests",
        ["status", "sla_due_at"],
        postgresql_where=sa.text(
            "status IN ('submitted', 'triaging', 'investigating')"
        ),
    )
    op.create_index(
        "idx_takedown_type_created",
        "takedown_requests",
        ["request_type", sa.text("created_at DESC")],
    )
    op.create_index(
        "idx_takedown_assigned",
        "takedown_requests",
        ["assigned_to"],
        postgresql_where=sa.text("assigned_to IS NOT NULL"),
    )
    op.execute(
        "CREATE TRIGGER trg_takedown_requests_updated_at BEFORE UPDATE ON takedown_requests "
        "FOR EACH ROW EXECUTE FUNCTION trg_set_updated_at();"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_takedown_requests_updated_at ON takedown_requests")
    op.drop_index("idx_takedown_assigned", table_name="takedown_requests")
    op.drop_index("idx_takedown_type_created", table_name="takedown_requests")
    op.drop_index("idx_takedown_status_sla", table_name="takedown_requests")
    op.drop_table("takedown_requests")
    op.execute("DROP SEQUENCE IF EXISTS takedown_ticket_seq")
