"""Seed bakinazik kataloğu — 10 kategori × 2 = 20 RSS kaynağı (#585)

Idempotent data migration. Her kaynak `INSERT ... ON CONFLICT (slug) DO NOTHING`
ile eklenir; varsa pas geçer. Tüm kayıtlar:

  - type = 'rss'
  - language = 'tr', country = 'TR'
  - is_active = FALSE  (admin compliance gate sonrası activate)
  - polling_tier = 'normal' (server default)
  - crawl_interval_minutes = 30 (server default)
  - reliability_score = 0.70 (server default)
  - tos_acknowledged = FALSE  (admin onayı bekliyor)
  - robots_txt_compliant = NULL  (activate adımında set)
  - would_be_tier / tier_metadata = NULL  (#578 Faz 2 ilk fetch sonrası)

Kategori etiketi (`category` kolonu) bakinazik kataloğundan birebir alınır:
Bilim, Teknoloji, Eğlence, Kültür ve Sanat, Spor, Gündem,
Savunma ve Sanayi, Ekonomi ve Finans, İş Dünyası, Yaşam.

Faz 2 (#578) shadow mode bozulmaz: yeni kaynaklar default polling_tier='normal'
ile insert edilir; activate sonrası worker fetch sırasında `compute_tier`
çağrılınca `would_be_tier` + `tier_metadata` JSONB telemetri yazılır,
`polling_tier` shadow_mode=true olduğu sürece dokunulmaz.

Revision ID: 20260510_0500
Revises: 20260510_0400
Create Date: 2026-05-10 05:00:00 UTC
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# #661 fix: dosya adı ve revision tutarlı olsun (DB head check için).
# Eskiden revision="20260510_0500" idi ama training_samples.py ile çakışıyordu.
# Yeni: revision="20260510_0600", down_revision="20260510_0500" (training_samples).
revision = "20260510_0600"
down_revision = "20260510_0500"
branch_labels = None
depends_on = None


# (slug, name, domain, base_url, category)
SOURCES: tuple[tuple[str, str, str, str, str], ...] = (
    # --- Bilim ---------------------------------------------------------------
    (
        "evrim-agaci",
        "Evrim Ağacı",
        "evrimagaci.org",
        "https://evrimagaci.org/rss.xml",
        "Bilim",
    ),
    (
        "sarkac",
        "Sarkaç",
        "sarkac.org",
        "https://sarkac.org/feed/",
        "Bilim",
    ),
    # --- Teknoloji -----------------------------------------------------------
    (
        "webtekno",
        "Webtekno",
        "webtekno.com",
        "https://www.webtekno.com/rss.xml",
        "Teknoloji",
    ),
    (
        "donanim-haber",
        "Donanım Haber",
        "donanimhaber.com",
        "https://www.donanimhaber.com/rss/tum/",
        "Teknoloji",
    ),
    # --- Eğlence -------------------------------------------------------------
    (
        "beyaz-perde",
        "Beyaz Perde",
        "beyazperde.com",
        "https://www.beyazperde.com/rss/haberler.xml",
        "Eğlence",
    ),
    (
        "ign-turkiye",
        "IGN Türkiye",
        "tr.ign.com",
        "https://tr.ign.com/feed.xml",
        "Eğlence",
    ),
    # --- Kültür ve Sanat -----------------------------------------------------
    (
        "arkitera",
        "Arkitera",
        "arkitera.com",
        "https://www.arkitera.com/feed/",
        "Kültür ve Sanat",
    ),
    (
        "bant-mag",
        "Bant Mag",
        "bantmag.com",
        "https://bantmag.com/feed/",
        "Kültür ve Sanat",
    ),
    # --- Spor ----------------------------------------------------------------
    (
        "ntv-spor",
        "NTV Spor",
        "ntvspor.net",
        "https://www.ntvspor.net/rss/anasayfa",
        "Spor",
    ),
    (
        "fotomac",
        "Fotomaç",
        "fotomac.com.tr",
        "https://www.fotomac.com.tr/rss/anasayfa.xml",
        "Spor",
    ),
    # --- Gündem --------------------------------------------------------------
    (
        "bianet",
        "Bianet",
        "bianet.org",
        "https://bianet.org/biamag.rss",
        "Gündem",
    ),
    (
        "hurriyet",
        "Hürriyet",
        "hurriyet.com.tr",
        "https://www.hurriyet.com.tr/rss/anasayfa",
        "Gündem",
    ),
    # --- Savunma ve Sanayi ---------------------------------------------------
    (
        "c4-defence",
        "C4 Defence",
        "c4defence.com",
        "https://www.c4defence.com/tr/feed/",
        "Savunma ve Sanayi",
    ),
    (
        "savunma-sanayi-st",
        "SavunmaSanayiST",
        "savunmasanayist.com",
        "https://www.savunmasanayist.com/feed/",
        "Savunma ve Sanayi",
    ),
    # --- Ekonomi ve Finans ---------------------------------------------------
    (
        "bloomberg-ht",
        "Bloomberg HT",
        "bloomberght.com",
        "https://www.bloomberght.com/rss",
        "Ekonomi ve Finans",
    ),
    (
        "forbes-turkiye",
        "Forbes Türkiye",
        "forbes.com.tr",
        "https://www.forbes.com.tr/rss",
        "Ekonomi ve Finans",
    ),
    # --- İş Dünyası ----------------------------------------------------------
    (
        "midas",
        "Midas",
        "getmidas.com",
        "https://www.getmidas.com/feed/",
        "İş Dünyası",
    ),
    (
        "isin-detayi-is-dunyasi",
        "İşin Detayı — İş Dünyası",
        "isindetayi.com",
        "https://www.isindetayi.com/rss/is-dunyasi",
        "İş Dünyası",
    ),
    # --- Yaşam ---------------------------------------------------------------
    (
        "elle-turkiye",
        "Elle Türkiye",
        "elle.com.tr",
        "https://www.elle.com.tr/rss",
        "Yaşam",
    ),
    (
        "marie-claire",
        "Marie Claire Türkiye",
        "marieclaire.com.tr",
        "https://www.marieclaire.com.tr/feed/",
        "Yaşam",
    ),
)


INSERT_SQL = sa.text(
    """
    INSERT INTO sources (
        name, slug, domain, type, base_url,
        language, country, category,
        is_active, tos_acknowledged
    ) VALUES (
        :name, :slug, :domain, 'rss', :base_url,
        'tr', 'TR', :category,
        FALSE, FALSE
    )
    ON CONFLICT (slug) DO NOTHING
    """
)


def upgrade() -> None:
    bind = op.get_bind()
    for slug, name, domain, base_url, category in SOURCES:
        bind.execute(
            INSERT_SQL,
            {
                "slug": slug,
                "name": name,
                "domain": domain,
                "base_url": base_url,
                "category": category,
            },
        )


def downgrade() -> None:
    """Sadece bu migration'ın eklediği slug'ları sil — kullanıcı tarafından
    eklenmiş aynı slug'a sahip kaynak varsa korunur (idempotent down).

    NOT: source_configs / source_health FK ondelete=CASCADE; ilgili
    article'lar source_id NOT NULL → admin tarafında handle edilir.
    """
    slugs = tuple(s[0] for s in SOURCES)
    op.execute(
        sa.text(
            "DELETE FROM sources WHERE slug = ANY(:slugs) AND is_active = FALSE"
        ).bindparams(sa.bindparam("slugs", value=list(slugs)))
    )
