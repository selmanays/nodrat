"""canonical_entities + entity_aliases — entity variant canonicalization (Faz 1 PR-A, #1540)

Aynı varlığın farklı yüzey biçimlerini (CHP↔Cumhuriyet Halk Partisi · Cumhurbaşkanı
Erdoğan↔Recep Tayyip Erdoğan) tek canonical kimlikte gruplamak için **additive** şema.
`entities` tablosu DOKUNULMAZ — orijinal yüzey biçimleri korunur. İki tablo da
**raw-SQL-only** (env.py RAW_SQL_ONLY_TABLES) → ORM/alembic-check parity yükü yok
(`entities` deseni). Builder + trend read entegrasyonu PR-B (#1540 takip).

Revision ID: 20260616_0100
Revises: 20260615_1300
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "20260616_0100"
down_revision: str | None = "20260615_1300"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # ---- canonical_entities — kalıcı birleşik kimlik --------------------------
    op.create_table(
        "canonical_entities",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("canonical_name", sa.String(300), nullable=False),
        sa.Column("entity_type", sa.String(20), nullable=False),
        sa.Column("canonical_normalized", sa.String(200), nullable=False),
        # active | merged | rejected (admin lifecycle)
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        # rule | seed | llm | admin (nasıl oluştu)
        sa.Column("source", sa.String(16), nullable=False, server_default="rule"),
        sa.Column("alias_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("article_count_total", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "canonical_normalized",
            "entity_type",
            name="uq_canonical_entities_norm_type",
        ),
    )
    op.create_index(
        "idx_canonical_entities_type_status",
        "canonical_entities",
        ["entity_type", "status"],
    )

    # ---- entity_aliases — yüzey biçimi (entity_normalized) → canonical --------
    op.create_table(
        "entity_aliases",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("alias_normalized", sa.String(200), nullable=False),
        sa.Column("entity_type", sa.String(20), nullable=False),
        sa.Column(
            "canonical_id",
            UUID(as_uuid=True),
            sa.ForeignKey("canonical_entities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=False, server_default="1.000"),
        sa.Column("source", sa.String(16), nullable=False, server_default="rule"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        # bir yüzey biçimi (tip başına) tek canonical'a bağlanır
        sa.UniqueConstraint("alias_normalized", "entity_type", name="uq_entity_aliases_alias_type"),
    )
    op.create_index("idx_entity_aliases_canonical", "entity_aliases", ["canonical_id"])
    op.create_index(
        "idx_entity_aliases_lookup",
        "entity_aliases",
        ["alias_normalized", "entity_type"],
    )


def downgrade() -> None:
    op.drop_table("entity_aliases")
    op.drop_table("canonical_entities")
