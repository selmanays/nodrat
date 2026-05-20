"""Unit tests for cold tier helpers (#219 MVP-1.5 PR-4).

Pure-Python tests — bucket key generation + import surface.
DB integration test ayrıca yapılır (live Contabo OS gerek).
"""

from __future__ import annotations

from app.core.storage import build_cold_storage_key


def test_cold_storage_key_format():
    """Format: cold/raw-html/YYYY/MM/<article-id>.html.gz"""
    key = build_cold_storage_key(
        article_id="abc123-def456-ghi789",
        year=2026,
        month=5,
    )
    assert key == "cold/raw-html/2026/05/abc123-def456-ghi789.html.gz"


def test_cold_storage_key_pads_month():
    """Aylar 2 haneli zero-pad."""
    key = build_cold_storage_key(article_id="x", year=2026, month=1)
    assert "/2026/01/" in key


def test_cold_storage_key_includes_year():
    """Yıl 4 haneli."""
    key = build_cold_storage_key(article_id="x", year=2026, month=12)
    assert key.startswith("cold/raw-html/2026/")


def test_cold_storage_key_gz_suffix():
    """.html.gz suffix sabit."""
    key = build_cold_storage_key(article_id="x", year=2026, month=5)
    assert key.endswith(".html.gz")


def test_cold_tier_archive_task_exported():
    """Celery task export."""
    from app.modules.ops.tasks.maintenance import cold_tier_archive

    assert cold_tier_archive.name == "tasks.maintenance.cold_tier_archive"


def test_cold_tier_restore_task_exported():
    """Restore task export (admin manuel kullanım için)."""
    from app.modules.ops.tasks.maintenance import cold_tier_restore

    assert cold_tier_restore.name == "tasks.maintenance.cold_tier_restore"


def test_beat_has_cold_tier_archive_schedule():
    """Beat schedule'da cold-tier-archive var (günlük 03:30 UTC)."""
    from app.workers.celery_app import celery_app

    schedule = celery_app.conf.beat_schedule
    assert "cold-tier-archive" in schedule
    entry = schedule["cold-tier-archive"]
    assert entry["task"] == "tasks.maintenance.cold_tier_archive"
    assert entry["kwargs"]["max_age_days"] == 30


def test_get_cold_storage_client_uses_s3_settings():
    """get_cold_storage_client S3_ settings kullanır."""
    from app.core.storage import get_cold_storage_client

    # Çağrı kendisi import zincirini doğrular; gerçek client bağlantı yapmaz
    # boto3 client'ı erken validation yapmaz, lazy connect.
    client = get_cold_storage_client()
    assert client is not None
    # boto3 endpoint URL config'ten alınmış mı (basit attribute check)
    assert hasattr(client, "get_object")
    assert hasattr(client, "put_object")


# ============================================================================
# Body HTML drop (#220 MVP-1.5 PR-5)
# ============================================================================


def test_body_html_drop_task_exported():
    """body_html_drop Celery task export edilmiş olmalı."""
    from app.modules.ops.tasks.maintenance import body_html_drop

    assert body_html_drop.name == "tasks.maintenance.body_html_drop"


def test_beat_has_body_html_drop_schedule():
    """Beat schedule'da body-html-drop var, cold-tier'dan ÖNCE."""
    from app.workers.celery_app import celery_app

    schedule = celery_app.conf.beat_schedule
    assert "body-html-drop" in schedule
    entry = schedule["body-html-drop"]
    assert entry["task"] == "tasks.maintenance.body_html_drop"
    assert entry["kwargs"]["max_age_hours"] == 24
    # Sıra: body_html_drop (03:00) < cold_tier (03:30) < backup (04:00)
    cold_entry = schedule["cold-tier-archive"]
    # celery crontab .hour/.minute = SET (int değil) → tuple<set karşılaştırma
    # subset semantiği verir, zaman sırası DEĞİL. min() ile gerçek saat (#1033).
    body_hour_min = (min(entry["schedule"].hour), min(entry["schedule"].minute))
    cold_hour_min = (min(cold_entry["schedule"].hour), min(cold_entry["schedule"].minute))
    assert body_hour_min < cold_hour_min, (
        "body_html_drop beat task cold_tier_archive'dan önce çalışmalı"
    )
