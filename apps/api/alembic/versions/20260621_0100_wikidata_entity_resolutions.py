"""wikidata_entity_resolutions — Wikidata canonical-etiket zenginleştirme guard/cache (#1710)

Yüzey form (entity_normalized, entity_type) → Wikidata çözüm denemesi sonucu. İki amaç:
(1) "denendi" GUARD — entity-üretmeyen/çözülemeyen yüzey formların her beat'te yeniden
    Wikidata'ya gitmesini önler (#1602 NER backfill sonsuz-döngü dersi).
(2) CACHE — çözülen QID + canonical başlık (idempotent re-enrichment).

**ADDITIVE** (yeni tablo, zero-downtime). raw-SQL-only (env.py RAW_SQL_ONLY_TABLES) →
ORM/alembic-check parity yükü yok (canonical_entities/entity_aliases deseni). `entities`,
`canonical_entities`, `entity_aliases` DOKUNULMAZ (bu tablo yalnız çözüm-denemesi izi).

Revision ID: 20260621_0100
Revises: 20260619_1500
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260621_0100"
down_revision: str | None = "20260619_1500"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "wikidata_entity_resolutions",
        sa.Column("entity_normalized", sa.String(200), nullable=False),
        sa.Column("entity_type", sa.String(20), nullable=False),
        # resolved | no_match | type_mismatch | error
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("wikidata_qid", sa.String(24), nullable=True),
        sa.Column("canonical_title", sa.String(300), nullable=True),
        # P31 (instance-of) QID'leri — gözlem/eşik-genişletme için (virgül-ayrık)
        sa.Column("p31", sa.String(200), nullable=True),
        sa.Column(
            "attempted_at",
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
        # bir yüzey biçimi (tip başına) tek çözüm-denemesi izi tutar
        sa.PrimaryKeyConstraint(
            "entity_normalized", "entity_type", name="pk_wikidata_entity_resolutions"
        ),
    )
    # re-eligibility taraması: status + attempted_at (eski/no_match'leri yeniden dene)
    op.create_index(
        "idx_wikidata_resolutions_status_attempted",
        "wikidata_entity_resolutions",
        ["status", "attempted_at"],
    )


def downgrade() -> None:
    op.drop_table("wikidata_entity_resolutions")
