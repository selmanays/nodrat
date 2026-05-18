"""Conversations + messages — Perplexity-style chat UX (#793 S1).

İki yeni tablo:
- conversations: bir sohbet birimi (user-bound, title + summary + archived flag)
- messages: user query + assistant response pairs (sources_used, query_embedding
  for follow-up relatedness)

Mevcut `generations` tablosu KORUNUR (backward compat — admin/billing/observability).
messages.generation_id ile lineage.

Revision: 20260514_1500
Revises: 20260514_1200
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260514_1500"
down_revision: str | None = "20260514_1200"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1) conversations
    op.create_table(
        "conversations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column(
            "summary",
            sa.String(length=500),
            nullable=True,
            comment="Son N mesaj özeti — context budget korumak için.",
        ),
        sa.Column(
            "archived",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "idx_conversations_user_updated",
        "conversations",
        ["user_id", sa.text("updated_at DESC")],
    )

    # 2) messages
    op.create_table(
        "messages",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "role",
            sa.String(length=16),
            nullable=False,
            comment="'user' | 'assistant'",
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "generation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("generations.id", ondelete="SET NULL"),
            nullable=True,
            comment="Assistant mesajları için — generations tablosu bağı.",
        ),
        sa.Column(
            "sources_used",
            postgresql.JSONB(),
            nullable=True,
            comment="[{article_id, chunk_id, url, title, relevance}, ...] — generator tarafından kullanılan",
        ),
        sa.Column(
            "sources_considered",
            postgresql.JSONB(),
            nullable=True,
            comment="LLM'in gördüğü ama kullanmadığı kaynaklar — follow-up reuse için",
        ),
        sa.Column(
            "query_embedding",
            postgresql.BYTEA(),
            nullable=True,
            comment="User query bge-m3 embedding (raw bytes) — follow-up relatedness için",
        ),
        sa.Column(
            "thinking_steps",
            postgresql.JSONB(),
            nullable=True,
            comment="SSE thinking event log — ['planner: ...', 'hyde: ...', ...]",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "role IN ('user', 'assistant')",
            name="messages_role_check",
        ),
    )
    op.create_index(
        "idx_messages_conv_created",
        "messages",
        ["conversation_id", "created_at"],
    )
    op.create_index(
        "idx_messages_generation",
        "messages",
        ["generation_id"],
        postgresql_where=sa.text("generation_id IS NOT NULL"),
    )

    # 3) updated_at trigger on conversations (auto-touch on UPDATE)
    op.execute(
        sa.text("""
        CREATE OR REPLACE FUNCTION fn_conversation_touch_updated_at()
        RETURNS trigger AS $$
        BEGIN
            NEW.updated_at := NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    )
    op.execute(
        sa.text("""
        CREATE TRIGGER trg_conversation_touch_updated_at
        BEFORE UPDATE ON conversations
        FOR EACH ROW
        EXECUTE FUNCTION fn_conversation_touch_updated_at();
    """)
    )

    # 4) Auto-update conversation.updated_at on new message
    op.execute(
        sa.text("""
        CREATE OR REPLACE FUNCTION fn_message_touch_conversation()
        RETURNS trigger AS $$
        BEGIN
            UPDATE conversations SET updated_at = NOW()
            WHERE id = NEW.conversation_id;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    )
    op.execute(
        sa.text("""
        CREATE TRIGGER trg_message_touch_conversation
        AFTER INSERT ON messages
        FOR EACH ROW
        EXECUTE FUNCTION fn_message_touch_conversation();
    """)
    )


def downgrade() -> None:
    op.execute(sa.text("DROP TRIGGER IF EXISTS trg_message_touch_conversation ON messages"))
    op.execute(sa.text("DROP FUNCTION IF EXISTS fn_message_touch_conversation()"))
    op.execute(sa.text("DROP TRIGGER IF EXISTS trg_conversation_touch_updated_at ON conversations"))
    op.execute(sa.text("DROP FUNCTION IF EXISTS fn_conversation_touch_updated_at()"))
    op.drop_index("idx_messages_generation", table_name="messages")
    op.drop_index("idx_messages_conv_created", table_name="messages")
    op.drop_table("messages")
    op.drop_index("idx_conversations_user_updated", table_name="conversations")
    op.drop_table("conversations")
