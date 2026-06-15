"""Seed gündem kataloğu — 19 Türkçe haber/doğrulama kaynağı (#1524)

Idempotent data migration. Bakınazık seed (#585) kalıbının birebir devamı; her
kaynak `INSERT ... ON CONFLICT (slug) DO NOTHING` ile eklenir, varsa pas geçer.

Bakınazık seed'inden farklar:
  - `type` per-row (bakınazıkta hep 'rss' idi): 15 kaynak 'rss', 4 kaynak
    'category_page' (RSS'i olmayan / Cloudflare-gated kaynaklar).
  - `reliability_score` per-row set edilir (bakınazıkta server default 0.70'e
    düşüyordu). Skorlar 2026-06-15 canlı doğrulama + editoryal güvenilirlik
    bandına göre: fact-check ~0.92-0.95, resmi-otorite 0.98, uluslararası
    kurumsal ~0.84-0.86, kurumsal-ulusal ~0.80-0.82, bağımsız-dijital
    ~0.68-0.78.

Tüm kayıtlar (bakınazık seed ile aynı invariant'lar):
  - language = 'tr', country = 'TR', category = 'Gündem'
  - is_active = FALSE  (admin compliance gate sonrası activate)
  - polling_tier = 'normal' (server default)
  - crawl_interval_minutes = 30 (server default)
  - tos_acknowledged = FALSE  (admin onayı bekliyor)
  - robots_txt_compliant = NULL  (activate adımında set)
  - would_be_tier / tier_metadata = NULL  (#578 Faz 2 ilk fetch sonrası)

Aktivasyon AYRIDIR: `POST /admin/sources/{id}/activate` robots re-check +
5-maddelik compliance checklist çalıştırır (compliance-bypass önleme). Bu
migration yalnız katalog tanımını ekler.

Katman C (type='category_page') kaynakları crawl için ek extraction-config
(SourceConfig.list_selectors) gerektirir — ayrı issue'larda ele alınır; bu
migration yalnız tanımı seed eder:
  - t24            : /rss/* Cloudflare challenge arkasında, HTML site açık
  - diken          : tüm site Cloudflare (robots.txt 403 → aktivasyonda
                     fail-closed reddedilebilir)
  - anka-haber-ajansi : public RSS yok (feed ücretli/şifreli)
  - resmi-gazete   : RSS yok; günlük HTML fihrist + PDF, özel quality-gate

Revision ID: 20260615_1300
Revises: 20260615_1200
Create Date: 2026-06-15 13:00:00 UTC
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "20260615_1300"
down_revision: str | None = "20260615_1200"
branch_labels = None
depends_on = None


# (slug, name, domain, type, base_url, category, reliability_score)
SOURCES: tuple[tuple[str, str, str, str, str, str, float], ...] = (
    # --- Katman A/B: RSS-hazır (feed XML canlı doğrulandı) -------------------
    (
        "cumhuriyet",
        "Cumhuriyet",
        "cumhuriyet.com.tr",
        "rss",
        "https://www.cumhuriyet.com.tr/rss",
        "Gündem",
        0.82,
    ),
    (
        "sozcu",
        "Sözcü",
        "sozcu.com.tr",
        "rss",
        "https://www.sozcu.com.tr/feeds-haberler",
        "Gündem",
        0.80,
    ),
    (
        "birgun",
        "BirGün",
        "birgun.net",
        "rss",
        "https://www.birgun.net/rss/home",
        "Gündem",
        0.72,
    ),
    (
        "medyascope",
        "Medyascope",
        "medyascope.tv",
        "rss",
        "https://medyascope.tv/feed/",
        "Gündem",
        0.74,
    ),
    (
        "kisa-dalga",
        "Kısa Dalga",
        "kisadalga.net",
        "rss",
        "https://kisadalga.net/service/rss.php",
        "Gündem",
        0.75,
    ),
    (
        "dw-turkce",
        "DW Türkçe",
        "dw.com",
        "rss",
        "https://rss.dw.com/rdf/rss-tur-all",
        "Gündem",
        0.86,
    ),
    (
        "euronews-turkce",
        "Euronews Türkçe",
        "euronews.com",
        "rss",
        "https://tr.euronews.com/rss",
        "Gündem",
        0.84,
    ),
    (
        "independent-turkce",
        "Independent Türkçe",
        "indyturk.com",
        "rss",
        "https://www.indyturk.com/rss.xml",
        "Gündem",
        0.78,
    ),
    (
        "teyit",
        "Teyit",
        "teyit.org",
        "rss",
        "https://teyit.org/feed",
        "Gündem",
        0.92,
    ),
    (
        "dogruluk-payi",
        "Doğruluk Payı",
        "dogrulukpayi.com",
        "rss",
        "https://www.dogrulukpayi.com/rss.xml",
        "Gündem",
        0.95,
    ),
    (
        "journo",
        "Journo",
        "journo.com.tr",
        "rss",
        "https://journo.com.tr/feed",
        "Gündem",
        0.82,
    ),
    (
        "gercek-gundem",
        "Gerçek Gündem",
        "gercekgundem.com",
        "rss",
        "https://www.gercekgundem.com/feed",
        "Gündem",
        0.70,
    ),
    (
        "halk-tv",
        "Halk TV",
        "halktv.com.tr",
        "rss",
        "https://halktv.com.tr/rss",
        "Gündem",
        0.76,
    ),
    (
        "dokuz8haber",
        "dokuz8HABER",
        "dokuz8haber.net",
        "rss",
        "https://dokuz8haber.net/rss.xml",
        "Gündem",
        0.68,
    ),
    (
        "yetkin-report",
        "Yetkin Report",
        "yetkinreport.com",
        "rss",
        "https://yetkinreport.com/feed/",
        "Gündem",
        0.83,
    ),
    # --- Katman C: RSS yok / Cloudflare → category_page (config ayrı issue) --
    (
        "t24",
        "T24",
        "t24.com.tr",
        "category_page",
        "https://t24.com.tr/",
        "Gündem",
        0.78,
    ),
    (
        "diken",
        "Diken",
        "diken.com.tr",
        "category_page",
        "https://www.diken.com.tr/",
        "Gündem",
        0.74,
    ),
    (
        "anka-haber-ajansi",
        "ANKA Haber Ajansı",
        "ankahaber.net",
        "category_page",
        "https://ankahaber.net/kategori/gundem",
        "Gündem",
        0.80,
    ),
    (
        "resmi-gazete",
        "Resmî Gazete",
        "resmigazete.gov.tr",
        "category_page",
        "https://www.resmigazete.gov.tr/",
        "Gündem",
        0.98,
    ),
)


INSERT_SQL = sa.text(
    """
    INSERT INTO sources (
        name, slug, domain, type, base_url,
        language, country, category,
        reliability_score, is_active, tos_acknowledged
    ) VALUES (
        :name, :slug, :domain, :type, :base_url,
        'tr', 'TR', :category,
        :reliability_score, FALSE, FALSE
    )
    ON CONFLICT (slug) DO NOTHING
    """
)


def upgrade() -> None:
    bind = op.get_bind()
    for slug, name, domain, type_, base_url, category, reliability_score in SOURCES:
        bind.execute(
            INSERT_SQL,
            {
                "slug": slug,
                "name": name,
                "domain": domain,
                "type": type_,
                "base_url": base_url,
                "category": category,
                "reliability_score": reliability_score,
            },
        )


def downgrade() -> None:
    """Sadece bu migration'ın eklediği slug'ları sil — kullanıcı tarafından
    eklenmiş aynı slug'a sahip kaynak varsa korunur (idempotent down; sadece
    is_active=FALSE olanlar silinir).

    NOT: source_configs / source_health FK ondelete=CASCADE; ilgili
    article'lar source_id NOT NULL → admin tarafında handle edilir.
    """
    slugs = tuple(s[0] for s in SOURCES)
    op.execute(
        sa.text("DELETE FROM sources WHERE slug = ANY(:slugs) AND is_active = FALSE").bindparams(
            sa.bindparam("slugs", value=list(slugs))
        )
    )
