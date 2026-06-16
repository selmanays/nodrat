"""user_notifications — kullanıcı bildirimleri (trend-alert) (#1581 C)

Kullanıcının ilgi kümesindeki bir entity "Patlıyor" olunca bildirim. **Additive**
şema — mevcut tablolar DOKUNULMAZ (zero-downtime). **raw-SQL-only** (env.py
RAW_SQL_ONLY_TABLES) → ORM/alembic-check parity yükü yok (canonical_entities deseni).
`dedupe_key` UNIQUE → beat task idempotent (kullanıcı+küme+gün başına tek bildirim).
FK user_id → users CASCADE (KVKK: hesap silinince bildirimleri de silinir).

Revision ID: 20260616_0200
Revises: 20260616_0100
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "20260616_0200"
down_revision: str | None = "20260616_0100"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_notifications",
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
        # şu an yalnız 'trend_alert'; ileride genişleyebilir
        sa.Column("type", sa.String(40), nullable=False, server_default="trend_alert"),
        sa.Column("cluster_key", sa.String(320)),  # ilgili entity (<type>:<kebab>)
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("body", sa.Text),
        sa.Column("trend_state", sa.String(20)),
        sa.Column("article_count", sa.Integer),
        # idempotency: '<user_id>:<cluster_key>:<YYYY-MM-DD>' → gün+küme başına tek
        sa.Column("dedupe_key", sa.String(400), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("read_at", sa.DateTime(timezone=True)),  # NULL = okunmadı
        sa.UniqueConstraint("dedupe_key", name="uq_user_notifications_dedupe"),
    )
    # okunmamış sayımı + listeleme (en yeni önce)
    op.create_index(
        "idx_user_notifications_user_created",
        "user_notifications",
        ["user_id", sa.text("created_at DESC")],
    )
    op.create_index(
        "idx_user_notifications_user_unread",
        "user_notifications",
        ["user_id"],
        postgresql_where=sa.text("read_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("idx_user_notifications_user_unread", table_name="user_notifications")
    op.drop_index("idx_user_notifications_user_created", table_name="user_notifications")
    op.drop_table("user_notifications")
