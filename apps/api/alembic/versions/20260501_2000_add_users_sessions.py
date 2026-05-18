"""Add users + sessions tables

docs/engineering/data-model.md §2.1, §2.2
docs/legal/opinion-integration.md §3.5 (4 KVKK consent fields)

Revision ID: 20260501_2000
Revises: 20260501_1900
Create Date: 2026-05-01 20:00:00 UTC

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import CITEXT, INET, UUID

# revision identifiers
revision: str = "20260501_2000"
down_revision: str | None = "20260501_1900"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ---- users -----------------------------------------------------------
    op.create_table(
        "users",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("email", CITEXT, nullable=False, unique=True),
        sa.Column("password_hash", sa.Text, nullable=False),
        sa.Column("full_name", sa.String(120)),
        sa.Column("role", sa.String(32), nullable=False, server_default=sa.text("'user'")),
        sa.Column("tier", sa.String(32), nullable=False, server_default=sa.text("'free'")),
        sa.Column("locale", sa.String(10), nullable=False, server_default=sa.text("'tr-TR'")),
        sa.Column("email_verified", sa.Boolean, nullable=False, server_default=sa.text("FALSE")),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("TRUE")),
        # KVKK 4 consent timestamps
        sa.Column("kvkk_acknowledgment_at", sa.DateTime(timezone=True)),
        sa.Column("data_processing_consent_at", sa.DateTime(timezone=True)),
        sa.Column("foreign_transfer_consent_at", sa.DateTime(timezone=True)),
        sa.Column("marketing_consent_at", sa.DateTime(timezone=True)),
        # 2FA
        sa.Column("totp_secret", sa.Text),
        sa.Column("totp_enabled", sa.Boolean, nullable=False, server_default=sa.text("FALSE")),
        # Tracking
        sa.Column("last_login_at", sa.DateTime(timezone=True)),
        sa.Column("last_login_ip", INET),
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
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
    )

    op.create_index(
        "idx_users_role",
        "users",
        ["role"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "idx_users_tier",
        "users",
        ["tier"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "idx_users_email_verified",
        "users",
        ["email_verified"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # updated_at trigger
    op.execute(
        """
        CREATE OR REPLACE FUNCTION trg_set_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        "CREATE TRIGGER trg_users_updated_at BEFORE UPDATE ON users "
        "FOR EACH ROW EXECUTE FUNCTION trg_set_updated_at();"
    )

    # ---- sessions --------------------------------------------------------
    op.create_table(
        "sessions",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.Text, nullable=False, unique=True),
        sa.Column("user_agent", sa.Text),
        sa.Column("ip_address", INET),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )

    op.create_index(
        "idx_sessions_user_id",
        "sessions",
        ["user_id"],
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
    op.create_index(
        "idx_sessions_expires_at",
        "sessions",
        ["expires_at"],
        postgresql_where=sa.text("revoked_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_table("sessions")
    op.execute("DROP TRIGGER IF EXISTS trg_users_updated_at ON users")
    op.drop_table("users")
    # trg_set_updated_at function diğer tablolarda kullanılacağı için kalır
