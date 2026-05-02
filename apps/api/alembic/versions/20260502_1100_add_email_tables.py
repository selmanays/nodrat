"""Add email_log + email_verification_tokens + password_reset_tokens (#68)

docs/legal/ropa.md §11 (transactional email envanteri)
docs/legal/privacy-policy.md §10 (email retention 1 yıl)

3 tablo:
- email_verification_tokens: email doğrulama (24h TTL)
- password_reset_tokens: şifre sıfırlama (1h TTL)
- email_log: gönderilen tüm transactional email kaydı (audit)

Revision ID: 20260502_1100
Revises: 20260502_0200
Create Date: 2026-05-02 11:00:00 UTC
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID


revision: str = "20260502_1100"
down_revision: Union[str, None] = "20260502_0200"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---- email_verification_tokens ----
    op.create_table(
        "email_verification_tokens",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(128), nullable=False, unique=True),
        sa.Column("email", sa.Text, nullable=False),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "used_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "idx_email_verify_user",
        "email_verification_tokens",
        ["user_id"],
        postgresql_where=sa.text("used_at IS NULL"),
    )
    op.create_index(
        "idx_email_verify_expires",
        "email_verification_tokens",
        ["expires_at"],
    )

    # ---- password_reset_tokens ----
    op.create_table(
        "password_reset_tokens",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(128), nullable=False, unique=True),
        sa.Column(
            "request_ip",
            INET,
            nullable=True,
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "used_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "idx_password_reset_user",
        "password_reset_tokens",
        ["user_id"],
        postgresql_where=sa.text("used_at IS NULL"),
    )
    op.create_index(
        "idx_password_reset_expires",
        "password_reset_tokens",
        ["expires_at"],
    )

    # ---- email_log ----
    op.create_table(
        "email_log",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("recipient", sa.Text, nullable=False),
        sa.Column("sender", sa.Text, nullable=False),
        sa.Column("template", sa.String(64), nullable=False),
        # 'verify' | 'password_reset' | 'welcome' | 'quota_warning' |
        # 'halu_confirmation' | 'kvkk_ack' | 'takedown_ack' | ...
        sa.Column("subject", sa.Text, nullable=False),
        sa.Column(
            "status",
            sa.String(16),
            nullable=False,
            server_default=sa.text("'queued'"),
        ),
        # 'queued' | 'sent' | 'failed' | 'bounced' | 'complained'
        sa.Column(
            "provider",
            sa.String(32),
            nullable=False,
            server_default=sa.text("'resend'"),
        ),
        sa.Column("provider_message_id", sa.Text, nullable=True),
        # Resend message ID for tracing/webhooks
        sa.Column("error", sa.Text, nullable=True),
        sa.Column(
            "metadata_json",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "sent_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'sent', 'failed', 'bounced', 'complained')",
            name="ck_email_log_status",
        ),
    )
    op.create_index(
        "idx_email_log_user_created",
        "email_log",
        ["user_id", sa.text("created_at DESC")],
        postgresql_where=sa.text("user_id IS NOT NULL"),
    )
    op.create_index(
        "idx_email_log_status_created",
        "email_log",
        ["status", sa.text("created_at DESC")],
    )
    op.create_index(
        "idx_email_log_template_created",
        "email_log",
        ["template", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_table("email_log")
    op.drop_table("password_reset_tokens")
    op.drop_table("email_verification_tokens")
