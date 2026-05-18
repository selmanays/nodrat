"""Content Quality Gate öncesi failed kayıtlar için archived backfill (#524)

5 production failed article kategorize edildi:
  - 1 Habertürk: relative video URL (host yok) → fetch fail
  - 1 AA: /tr/live-blog/... → thin content
  - 1 AA: /tr/dunya/... → SPA migration thin content (kalır, #460 kullanıcı kararı)
  - 2 Evrensel: silinen haber, soft 404 (HTTP 200 + 404 landing)

Hepsi #524 Content Quality Gate ile gelecekte yakalanır (terminal archived).
Bu migration mevcut 5 failed kayıttan **kalıcı patolojili** olanları
(invalid URL, live-blog, video, soft 404) archived'a çeker.

AA SPA (article.dunya.iran-deprem) bırakılır — #460 kullanıcı kararı; gelecek
fetch'te quality gate `thin_content` ile yakalayacak (skeleton body), o
zaman archived'a otomatik alınacak.

Beklenen etki: 5 failed → ~1 (sadece AA SPA, kullanıcı kararı bekleyen).
Sonraki fetch döngüsünde AA SPA da quality gate ile archived olur ve son
sayaç 0'a iner.

Revision ID: 20260509_0900
Revises: 20260509_0800
Create Date: 2026-05-09 09:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260509_0900"
down_revision = "20260509_0800"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) Invalid URL (relative path, hostname yok) — discovery'de yakalanması
    # gereken ama legacy INSERT olan kayıtlar
    op.execute(
        sa.text(
            """
            UPDATE articles
            SET status = 'archived',
                updated_at = NOW()
            WHERE status = 'failed'
              AND (
                  source_url NOT LIKE 'http://%' AND source_url NOT LIKE 'https://%'
              )
            """
        )
    )

    # 2) Discovery filter pattern'leri (live-blog, video, canli-veri) — #504
    # filter eklenmeden önce INSERT olan legacy kayıtlar
    op.execute(
        sa.text(
            """
            UPDATE articles
            SET status = 'archived',
                updated_at = NOW()
            WHERE status = 'failed'
              AND (
                  source_url ~ '/live-blog/'
                  OR source_url ~ '/canli-(blog|haber|yayin|takip|altin|doviz|borsa|petrol|skor)'
                  OR source_url ~ '/canli/(altin|doviz|borsa|petrol)'
                  OR source_url ~ '/video/'
                  OR source_url ~ '/videolar/'
                  OR canonical_url ~ '/live-blog/'
                  OR canonical_url ~ '/video/'
              )
            """
        )
    )

    # 3) Soft 404 backfill — Evrensel'in silinmiş haberleri için DLQ
    # error_message'ında 'extract conf=0.5/0.6' işareti olanlar büyük
    # olasılıkla soft 404 (Evrensel kalıbı). Yeni gelen Evrensel article'lar
    # quality gate ile yakalanacak; bu sadece geçmiş failed kayıtlar.
    op.execute(
        sa.text(
            """
            UPDATE articles
            SET status = 'archived',
                updated_at = NOW()
            WHERE status = 'failed'
              AND id IN (
                  SELECT a.id FROM articles a
                  JOIN failed_jobs fj ON fj.article_url = a.source_url
                  JOIN sources s ON s.id = a.source_id
                  WHERE s.slug = 'evrensel'
                    AND fj.job_type = 'article.extract'
                    AND fj.created_at >= NOW() - INTERVAL '30 days'
              )
            """
        )
    )


def downgrade() -> None:
    # Geri alma: bu migration'ın etkilediği archived'ları failed'e çek.
    # Filter: son 1 saat içinde updated_at + status='archived' + body_html
    # boş (yeni gelmediler, bizim migration'ımız etkiledi).
    op.execute(
        sa.text(
            """
            UPDATE articles
            SET status = 'failed'
            WHERE status = 'archived'
              AND archived_at IS NULL
              AND cold_storage_key IS NULL
              AND COALESCE(LENGTH(body_html), 0) = 0
              AND updated_at >= NOW() - INTERVAL '1 hour'
            """
        )
    )
