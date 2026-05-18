"""#539 — _record_failure davranış testleri.

1. Sibling DLQ auto-resolve when article terminal
2. fetch_detail invalid URL → archived + permanent_info
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from app.core.cleaning import STATUS_ARCHIVED, STATUS_FAILED
from app.models.article import Article
from app.models.job import FailedJob
from app.models.source import Source
from app.workers.tasks.articles import _record_failure
from sqlalchemy import select

pytestmark = pytest.mark.integration


async def _make_source(db) -> Source:
    """Test source — minimum alanlarla."""
    src = Source(
        slug=f"test-source-{uuid.uuid4().hex[:8]}",
        name="Test Source",
        feed_url="https://example.com/rss",
        is_active=True,
    )
    db.add(src)
    await db.flush()
    return src


async def _make_article(db, source: Source, *, url: str, status: str = "discovered") -> Article:
    art = Article(
        source_id=source.id,
        canonical_url=url,
        source_url=url,
        title=f"Test {uuid.uuid4().hex[:6]}",
        content_hash="0" * 64,
        title_hash="0" * 64,
        language="tr",
        status=status,
    )
    db.add(art)
    await db.flush()
    return art


@pytest.mark.asyncio
async def test_record_failure_resolves_sibling_dlq_when_article_archived(test_db_session) -> None:
    """#539: Article archived'a alınırken aynı URL'in eski DLQ rows'ları resolve olur."""
    db = test_db_session
    src = await _make_source(db)
    url = "https://example.com/news/123"
    art = await _make_article(db, src, url=url, status="failed")

    # Pre-existing stale DLQ rows
    for i in range(3):
        db.add(
            FailedJob(
                job_type="article.fetch_detail",
                payload_json={"source_url": url},
                source_id=src.id,
                article_url=url,
                error_message=f"old fail {i}",
                last_attempt_at=datetime.now(UTC),
                severity="error",
            )
        )
    await db.flush()

    # Now archive the article via _record_failure
    await _record_failure(
        db,
        article=art,
        job_type="article.invalid_url",
        error="invalid url at fetch: relative_path",
        payload={"source_url": url},
        severity="permanent_info",
        article_status_override=STATUS_ARCHIVED,
    )
    await db.flush()

    # All 3 stale + new permanent_info = 4 rows; ALL should be resolved
    rows = (
        await db.execute(
            select(FailedJob).where(FailedJob.article_url == url)
        )
    ).scalars().all()
    assert len(rows) == 4, f"Expected 4 DLQ rows, got {len(rows)}"
    unresolved = [r for r in rows if r.resolved_at is None]
    assert unresolved == [], f"Sibling auto-resolve failed: {len(unresolved)} unresolved"

    # Article is archived
    assert art.status == STATUS_ARCHIVED


@pytest.mark.asyncio
async def test_record_failure_does_not_resolve_when_article_failed(test_db_session) -> None:
    """#539: severity='error' default → article 'failed', sibling resolve OLMAMALI."""
    db = test_db_session
    src = await _make_source(db)
    url = "https://example.com/news/456"
    art = await _make_article(db, src, url=url, status="discovered")

    # Pre-existing unresolved DLQ row
    db.add(
        FailedJob(
            job_type="article.fetch_detail",
            payload_json={"source_url": url},
            source_id=src.id,
            article_url=url,
            error_message="old fail",
            last_attempt_at=datetime.now(UTC),
            severity="error",
        )
    )
    await db.flush()

    # severity='error' default → article 'failed' (NOT terminal)
    await _record_failure(
        db,
        article=art,
        job_type="article.fetch_detail",
        error="fetch failed status=500",
        payload={"source_url": url},
    )
    await db.flush()

    # 2 rows total, both UNRESOLVED (article still 'failed', not terminal)
    rows = (
        await db.execute(
            select(FailedJob).where(FailedJob.article_url == url)
        )
    ).scalars().all()
    assert len(rows) == 2
    unresolved = [r for r in rows if r.resolved_at is None]
    assert len(unresolved) == 2, "non-terminal article should NOT trigger sibling resolve"
    assert art.status == STATUS_FAILED


@pytest.mark.asyncio
async def test_record_failure_resolves_sibling_when_article_already_cleaned(test_db_session) -> None:
    """#539: Article zaten cleaned ise (race condition'da gecikmiş retry),
    sibling DLQ rows'ları resolve olur."""
    db = test_db_session
    src = await _make_source(db)
    url = "https://example.com/news/789"
    art = await _make_article(db, src, url=url, status="cleaned")

    # Stale DLQ rows from earlier failures
    for i in range(2):
        db.add(
            FailedJob(
                job_type="article.fetch_detail",
                payload_json={"source_url": url},
                source_id=src.id,
                article_url=url,
                error_message=f"transient fail {i}",
                last_attempt_at=datetime.now(UTC),
                severity="error",
            )
        )
    await db.flush()

    # Permanent_info call (no override) — caller knows article is cleaned
    await _record_failure(
        db,
        article=art,
        job_type="article.duplicate_content",
        error="content_hash already exists",
        payload={"source_url": url},
        severity="permanent_info",
    )
    await db.flush()

    rows = (
        await db.execute(
            select(FailedJob).where(FailedJob.article_url == url)
        )
    ).scalars().all()
    unresolved = [r for r in rows if r.resolved_at is None]
    assert unresolved == [], f"Sibling resolve failed for cleaned article: {len(unresolved)}"
