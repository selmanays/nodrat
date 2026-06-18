"""article.entities_extracted_at — NER 'denendi' işareti (#1602)

NER backfill sonsuz döngüsü fix: entity-üretmeyen makaleler (named-entity-yoksun
gürültü içerik — burç/tarif/moda) boş liste dönünce `entities`'e hiçbir şey
yazılmıyordu → `NOT EXISTS(entities)` ile backfill onları her 30dk yeniden
DeepSeek NER'e gönderiyordu (son 7 günde NER çağrılarının %61'i / 17K çağrı israf).
Bu kolon "NER bir kez başarıyla denendi" işaretidir; backfill `IS NULL` ile eler.

**Additive / backward-compatible** — yeni nullable kolon, mevcut data DOKUNULMAZ
(zero-downtime). Eski kod kolonu yok sayar; yeni kod doldurur. `NOT EXISTS(entities)`
guard'ı korunduğu için entity'si olan ~20K makale hiç etkilenmez (data UPDATE yok;
sadece 273 entity-yok makale son 1 kez denenir, kolon dolar, döngü biter).

Revision ID: 20260618_0100
Revises: 20260616_0200
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260618_0100"
down_revision: str | None = "20260616_0200"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "articles",
        sa.Column("entities_extracted_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("articles", "entities_extracted_at")
