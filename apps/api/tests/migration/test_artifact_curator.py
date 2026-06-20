"""Integration — Faz 3c/1b SFT artefakt-curator (testcontainers).

curate_artifacts eligible artefakt HEAD'lerini SFT örneği olarak yazar. Eligibility:
model_improvement_consent + review-buffer + effective_query + PII-temiz. Idempotent
(uq_training_samples_artifact). Head ≠ initial → head içeriği örneklenir.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.modules.sft.tasks.artifact_curator import curate_artifacts
from sqlalchemy import text

pytestmark = pytest.mark.integration


async def _user(db, *, consent: bool = True, revoked: bool = False) -> uuid.UUID:
    uid = uuid.uuid4()
    await db.execute(
        text("INSERT INTO users (id, email, password_hash) VALUES (:id, :e, 'x')"),
        {"id": uid, "e": f"u-{uid.hex[:8]}@test.local"},
    )
    if consent:
        await db.execute(
            text(
                "UPDATE users SET model_improvement_consent_at = NOW(), "
                "model_improvement_consent_revoked_at = :rev WHERE id = :id"
            ),
            {"id": uid, "rev": datetime.now(UTC) if revoked else None},
        )
    return uid


async def _cluster(db) -> uuid.UUID:
    cid = uuid.uuid4()
    await db.execute(
        text(
            "INSERT INTO research_clusters (id, cluster_key, cluster_type, canonical_name) "
            "VALUES (:id, :k, 'topic', 'Asgari Ücret')"
        ),
        {"id": cid, "k": f"topic:{cid.hex[:10]}"},
    )
    return cid


async def _seed_artifact(
    db,
    cid: uuid.UUID,
    uid: uuid.UUID,
    *,
    effective_query: str | None = "asgari ücret 2026 ne olacak",
    initial_content: str = "İlk taslak içerik [1].",
    sources: list | None = None,
    days_ago: int = 10,
    head_content: str | None = None,
    head_intent: str = "quick_shorter",
) -> tuple[uuid.UUID, int]:
    """Artefakt + initial revizyon (+ opsiyonel head revizyon). Dönüş: (artifact_id, head_seq)."""
    if sources is None:
        sources = [{"title": "Komisyon takvimi", "source_name": "ANKA"}]
    aid = uuid.uuid4()
    rev1 = uuid.uuid4()
    head_seq = 1
    created = datetime.now(UTC) - timedelta(days=days_ago)
    await db.execute(
        text(
            "INSERT INTO artifacts (id, cluster_id, user_id, artifact_type, head_revision_id, created_at) "
            "VALUES (:id, :c, :u, 'post', :head, :created)"
        ),
        {"id": aid, "c": cid, "u": uid, "head": rev1, "created": created},
    )
    await db.execute(
        text(
            "INSERT INTO artifact_revisions "
            "(id, artifact_id, revision_seq, revision_intent, content, sources_used, effective_query) "
            "VALUES (:id, :a, 1, 'initial', :content, :src, :eq)"
        ),
        {
            "id": rev1,
            "a": aid,
            "content": initial_content,
            "src": json.dumps(sources),
            "eq": effective_query,
        },
    )
    if head_content is not None:
        rev2 = uuid.uuid4()
        await db.execute(
            text(
                "INSERT INTO artifact_revisions "
                "(id, artifact_id, revision_seq, parent_revision_id, revision_intent, content, sources_used) "
                "VALUES (:id, :a, 2, :parent, :intent, :content, :src)"
            ),
            {
                "id": rev2,
                "a": aid,
                "parent": rev1,
                "intent": head_intent,
                "content": head_content,
                "src": json.dumps(sources),
            },
        )
        await db.execute(
            text("UPDATE artifacts SET head_revision_id = :h WHERE id = :a"), {"h": rev2, "a": aid}
        )
        head_seq = 2
    return aid, head_seq


async def _samples(db, aid):
    return (
        (
            await db.execute(
                text(
                    "SELECT artifact_revision_seq, task_type, sample_type, cluster_id, user_id, "
                    "input_payload, output_payload, quality_signals, sft_split "
                    "FROM training_samples WHERE artifact_id = :a ORDER BY artifact_revision_seq"
                ),
                {"a": aid},
            )
        )
        .mappings()
        .all()
    )


async def test_curate_creates_sft_sample(test_db_session):
    db = test_db_session
    uid = await _user(db)
    cid = await _cluster(db)
    aid, head_seq = await _seed_artifact(db, cid, uid, head_content="Kısa içerik [1].")

    summary = await curate_artifacts(db, daily_max=100, prompt_version="2.0.0")
    assert summary["ingested_sft"] == 1
    assert summary["scanned"] == 1

    rows = await _samples(db, aid)
    assert len(rows) == 1
    s = rows[0]
    assert s["artifact_revision_seq"] == head_seq == 2  # HEAD örneklenir, initial değil
    assert s["task_type"] == "research_answer"  # REUSE
    assert s["sample_type"] == "sft"
    assert str(s["cluster_id"]) == str(cid)
    assert str(s["user_id"]) == str(uid)
    assert s["output_payload"]["content"] == "Kısa içerik [1]."  # head içeriği
    assert "asgari ücret" in s["input_payload"]["messages"][0]["content"]  # effective_query
    assert s["quality_signals"]["source"] == "artifact"
    assert s["quality_signals"]["head_intent"] == "quick_shorter"
    assert s["sft_split"] in {"train", "val", "test"}


async def test_idempotent(test_db_session):
    db = test_db_session
    uid = await _user(db)
    cid = await _cluster(db)
    aid, _ = await _seed_artifact(db, cid, uid)

    s1 = await curate_artifacts(db, daily_max=100, prompt_version="2.0.0")
    assert s1["ingested_sft"] == 1
    s2 = await curate_artifacts(db, daily_max=100, prompt_version="2.0.0")
    assert s2["ingested_sft"] == 0  # NOT EXISTS → 2. run boş
    assert s2["scanned"] == 0
    assert len(await _samples(db, aid)) == 1


async def test_no_consent_skipped(test_db_session):
    db = test_db_session
    uid = await _user(db, consent=False)
    cid = await _cluster(db)
    aid, _ = await _seed_artifact(db, cid, uid)

    summary = await curate_artifacts(db, daily_max=100, prompt_version="2.0.0")
    assert summary["scanned"] == 0  # consent yok → aday değil
    assert len(await _samples(db, aid)) == 0


async def test_revoked_consent_skipped(test_db_session):
    db = test_db_session
    uid = await _user(db, consent=True, revoked=True)
    cid = await _cluster(db)
    aid, _ = await _seed_artifact(db, cid, uid)

    summary = await curate_artifacts(db, daily_max=100, prompt_version="2.0.0")
    assert summary["scanned"] == 0
    assert len(await _samples(db, aid)) == 0


async def test_review_buffer_skipped(test_db_session):
    db = test_db_session
    uid = await _user(db)
    cid = await _cluster(db)
    # 1 gün önce oluşturulmuş → 7-gün buffer içinde → aday değil
    aid, _ = await _seed_artifact(db, cid, uid, days_ago=1)

    summary = await curate_artifacts(db, daily_max=100, prompt_version="2.0.0")
    assert summary["scanned"] == 0
    assert len(await _samples(db, aid)) == 0


async def test_no_effective_query_skipped(test_db_session):
    db = test_db_session
    uid = await _user(db)
    cid = await _cluster(db)
    aid, _ = await _seed_artifact(db, cid, uid, effective_query=None)

    summary = await curate_artifacts(db, daily_max=100, prompt_version="2.0.0")
    assert summary["scanned"] == 1
    assert summary["skipped_no_query"] == 1
    assert summary["ingested_sft"] == 0
    assert len(await _samples(db, aid)) == 0


async def test_pii_skipped(test_db_session):
    db = test_db_session
    uid = await _user(db)
    cid = await _cluster(db)
    # head içeriğinde email → PII secondary scan hit
    aid, _ = await _seed_artifact(
        db, cid, uid, head_content="İletişim: gizli@example.com üzerinden [1]."
    )

    summary = await curate_artifacts(db, daily_max=100, prompt_version="2.0.0")
    assert summary["scanned"] == 1
    assert summary["skipped_pii"] == 1
    assert summary["ingested_sft"] == 0
    assert len(await _samples(db, aid)) == 0


async def test_multiple_artifacts_one_run(test_db_session):
    """Tek run'da birden çok eligible artefakt → hepsi ingest (ON CONFLICT atomik;
    bir satır diğerlerini zehirlemez — begin_nested-poison regresyon guard'ı)."""
    db = test_db_session
    uid = await _user(db)
    cid = await _cluster(db)
    aids = []
    for i in range(3):
        aid, _ = await _seed_artifact(db, cid, uid, effective_query=f"sorgu {i} ne olacak")
        aids.append(aid)

    summary = await curate_artifacts(db, daily_max=100, prompt_version="2.0.0")
    assert summary["ingested_sft"] == 3
    assert summary["errors"] == 0
    total = (
        await db.execute(
            text("SELECT count(*) FROM training_samples WHERE artifact_id = ANY(:ids)"),
            {"ids": aids},
        )
    ).scalar()
    assert total == 3


async def test_single_revision_artifact_curated(test_db_session):
    """Tek revizyonlu artefakt (head=initial, seq=1) de örneklenir."""
    db = test_db_session
    uid = await _user(db)
    cid = await _cluster(db)
    aid, _ = await _seed_artifact(db, cid, uid, head_content=None)  # yalnız initial

    summary = await curate_artifacts(db, daily_max=100, prompt_version="2.0.0")
    assert summary["ingested_sft"] == 1
    rows = await _samples(db, aid)
    assert rows[0]["artifact_revision_seq"] == 1
    assert rows[0]["output_payload"]["content"] == "İlk taslak içerik [1]."
