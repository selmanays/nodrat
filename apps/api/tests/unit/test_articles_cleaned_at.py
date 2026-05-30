"""articles.cleaned_at field — pipeline state-machine timestamp testi (#513).

Chart yığılma sorunu: 'Temizlenen içerikler' tek saatte 2620 article
gösteriyordu. Sebep: chart `updated_at` üzerinden grupluyor, migration
toplu UPDATE'leri tüm cleaned'leri tek saate yığıyordu.

Çözüm: yeni cleaned_at field, sadece status='cleaned' geçişinde set.
"""

from __future__ import annotations

from pathlib import Path

_REPO_API = Path(__file__).resolve().parents[2]


def test_dashboard_jobs_query_uses_cleaned_at():
    """admin_dashboard.py 'jobs' SQL query'si cleaned_at üzerinden grupluyor."""
    src = (_REPO_API / "app/modules/ops/admin/dashboard.py").read_text()
    # jobs query bölümü
    jobs_block_start = src.index('"jobs"')
    jobs_block = src[jobs_block_start : jobs_block_start + 800]
    assert "date_trunc('hour', cleaned_at)" in jobs_block, (
        "jobs query cleaned_at üzerinden grupluyor olmalı (#513)"
    )
    assert "cleaned_at >= :since" in jobs_block
    # WHERE clause hala status='cleaned' filter taşıyor
    assert "status = 'cleaned'" in jobs_block


def test_dashboard_jobs_query_does_not_use_updated_at():
    """jobs query updated_at KULLANMAMALI — yığılma sebebi."""
    src = (_REPO_API / "app/modules/ops/admin/dashboard.py").read_text()
    jobs_block_start = src.index('"jobs"')
    jobs_block_end = src.index('"generations"')
    jobs_block = src[jobs_block_start:jobs_block_end]
    assert "updated_at" not in jobs_block, (
        "jobs query updated_at kullanmamalı (#513 — chart yığılma kök neden)"
    )


def test_articles_query_unchanged():
    """articles chart hala fetched_at — RSS discovery zamanı."""
    src = (_REPO_API / "app/modules/ops/admin/dashboard.py").read_text()
    articles_start = src.index('"articles"')
    articles_block = src[articles_start : articles_start + 400]
    assert "fetched_at" in articles_block


def test_article_model_cleaned_at_defined():
    """Article model dosyasında cleaned_at column tanımlı."""
    src = (_REPO_API / "app/modules/articles/models.py").read_text()  # T8-12b: taşındı
    assert "cleaned_at: Mapped[datetime | None]" in src
    # Yorum #513 referansı olmalı (kalıcılık için)
    assert "#513" in src


def test_fetch_detail_sets_cleaned_at():
    """_article_fetch_detail_async cleaning sırasında cleaned_at set ediyor."""
    src = (_REPO_API / "app/modules/articles/tasks/articles.py").read_text()
    # status=CLEANED set bölgesinin yakınında cleaned_at de set edilmeli
    cleaned_idx = src.index("article.status = STATUS_CLEANED")
    nearby = src[cleaned_idx : cleaned_idx + 600]
    assert "article.cleaned_at" in nearby, "cleaning sırasında cleaned_at set edilmeli"
