"""AA (anadolu-ajansi) extract failure 187 satır warning auto-resolve (#460)

Production tanı (2026-05-08 20:45 UTC):
  failed_jobs.article.extract unresolved = 189
  └─ anadolu-ajansi: 187 (%99)
  └─ evrensel: 2

AA HTML incelendi: artık Tailwind + JS-rendered SPA. Statik HTML'de sadece
skeleton placeholder'lar var; gerçek içerik client-side hydrate ediliyor.
Trafilatura ve mevcut site_profiles selector'ları (article, .detay, .haber-detay)
boş wrapper'lara denk geliyor. JSON-LD `articleBody` sadece 83 char özet —
MIN_TEXT_LENGTH=200 altı, fail.

Gerçek çözüm Playwright JS-render entegrasyonu (MVP-2 #71 cut-list LATER) veya
AA için API endpoint discovery — bu PR sınırı dışı.

Bu migration sadece **alarm yorgunluğunu giderir**:
  - 187 mevcut AA extract failure → severity='warning'
  - resolved_at=NOW() ile auto-close (alarm sayımından çıkar)
  - resolution_note: SPA tracking + #460 referans

Yeni AA extract failure'ları durdurma kapsam dışı — bu source-level karar
(sources.is_active=false veya Playwright). #460 issue'da kullanıcıya bırakıldı.

Beklenen etki:
  failed_jobs unresolved 217 -> ~30 (-187, %86)

Revision ID: 20260508_2100
Revises: 20260508_2030
Create Date: 2026-05-08 21:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260508_2100"
down_revision = "20260508_2030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE failed_jobs
            SET severity = 'warning',
                resolved_at = NOW(),
                resolution_note = COALESCE(
                    resolution_note,
                    'AA (aa.com.tr) SPA migration — Playwright/source-disable kararı için #460. Auto-resolved alarm temizliği.'
                )
            WHERE job_type = 'article.extract'
              AND article_url LIKE '%aa.com.tr%'
              AND resolved_at IS NULL
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE failed_jobs
            SET severity = 'error',
                resolved_at = NULL
            WHERE job_type = 'article.extract'
              AND article_url LIKE '%aa.com.tr%'
              AND severity = 'warning'
              AND resolution_note LIKE '%AA (aa.com.tr) SPA migration%'
            """
        )
    )
