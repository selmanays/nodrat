"""entities tablosu — NER pipeline (#667 Faz 6)

Article metinlerinden çıkarılan özel ad entity'leri:
  - Kişi (Emine Aydınbelge, Fatih Tutak, Erdoğan)
  - Yer (Rodos, Salt Galata, Karşıyaka, İstanbul)
  - Kurum (Karşıyaka SK, Bursaspor, Cengiz Holding)
  - Etkinlik (Şehit Anneler Programı, 15 Temmuz, SAHA 2026)
  - Sayı/rakam (488 milyon dolar, %42, 21 ülke)

bge-m3 embedding niş entity disambiguation'da zayıf. NER ile direct exact
match yapıyoruz → embedding bypass → retrieval recall sıçraması.

Index: (entity_normalized, entity_type) — fast LIKE lookup için.
GIN trigram index — fuzzy match için.

Backward-compat: nullable foreign key (article silinince entity'ler de
silinsin diye CASCADE).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers
revision = "20260511_0200"
down_revision = "20260511_0100"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "entities",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "article_id",
            UUID(as_uuid=True),
            sa.ForeignKey("articles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("entity_text", sa.String(200), nullable=False),
        sa.Column("entity_normalized", sa.String(200), nullable=False),
        sa.Column("entity_type", sa.String(20), nullable=False),
        sa.Column("mention_count", sa.Integer, nullable=False, server_default="1"),
        sa.Column(
            "first_position",
            sa.String(20),
            nullable=False,
            server_default="body",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "idx_entities_normalized",
        "entities",
        ["entity_normalized", "entity_type"],
    )
    op.create_index("idx_entities_article", "entities", ["article_id"])
    op.execute(
        "CREATE INDEX idx_entities_normalized_trgm ON entities "
        "USING gin (entity_normalized gin_trgm_ops)"
    )
    # Unique constraint: aynı article'da aynı entity bir kez (mention_count
    # ile aggregate edilir)
    op.create_unique_constraint(
        "uq_entities_article_normalized_type",
        "entities",
        ["article_id", "entity_normalized", "entity_type"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_entities_article_normalized_type", "entities")
    op.execute("DROP INDEX IF EXISTS idx_entities_normalized_trgm")
    op.drop_index("idx_entities_article", table_name="entities")
    op.drop_index("idx_entities_normalized", table_name="entities")
    op.drop_table("entities")
