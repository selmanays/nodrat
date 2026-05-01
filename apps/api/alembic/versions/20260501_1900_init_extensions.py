"""Init PostgreSQL extensions

PostgreSQL extension'larını yükler. Tüm Nodrat tablolarının önkoşulu.

docs/engineering/data-model.md §1.3

Revision ID: 20260501_1900
Revises: None
Create Date: 2026-05-01 19:00:00 UTC

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers
revision: str = "20260501_1900"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Required extensions:

    - pgcrypto  : gen_random_uuid(), encryption helpers
    - vector    : pgvector for embeddings (article_chunks, agenda_cards, image_embeddings)
    - pg_trgm   : full-text search + similarity (titles, clean_text)
    - citext    : case-insensitive text (email)
    """
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "vector"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "pg_trgm"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "citext"')


def downgrade() -> None:
    """Extensions kaldırılmaz — tüm tablolar bunlara bağlı.

    Geri alma yalnızca DB'yi tamamen sıfırlama senaryosunda mantıklı.
    Bu yüzden no-op (intentional).
    """
    pass
