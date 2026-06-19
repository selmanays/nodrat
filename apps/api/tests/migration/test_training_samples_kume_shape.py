"""Integration — Faz 1a training_samples küme/artefakt şekli (testcontainers).

Additive kolonlar + artifact_id SET NULL (snapshot korunur) + artefakt-yolu
idempotency (ON CONFLICT partial unique). Curator artefakt-yolu Faz 3'te; burada
yalnız şema/constraint katmanı doğrulanır.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.integration


async def _user(db) -> uuid.UUID:
    uid = uuid.uuid4()
    await db.execute(
        text("INSERT INTO users (id, email, password_hash) VALUES (:id, :e, 'x')"),
        {"id": uid, "e": f"u-{uid.hex[:8]}@test.local"},
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


async def _artifact(db, cid: uuid.UUID, uid: uuid.UUID) -> uuid.UUID:
    aid = uuid.uuid4()
    await db.execute(
        text(
            "INSERT INTO artifacts (id, cluster_id, user_id, artifact_type) "
            "VALUES (:id, :c, :u, 'thread')"
        ),
        {"id": aid, "c": cid, "u": uid},
    )
    return aid


async def _insert_sample(db, uid, aid, cid, seq=1) -> int:
    """Faz 3 curator artefakt-yolu deseni: idempotent upsert."""
    res = await db.execute(
        text(
            """
            INSERT INTO training_samples
                (user_id, task_type, sample_type, prompt_version,
                 input_payload, output_payload, sft_split,
                 artifact_id, artifact_revision_seq, cluster_id)
            VALUES (:u, 'research_answer', 'sft', '2.0.0',
                    '{}'::jsonb, '{}'::jsonb, 'train',
                    :art, :seq, :c)
            ON CONFLICT (artifact_id, artifact_revision_seq, task_type, sample_type)
                WHERE artifact_id IS NOT NULL
            DO NOTHING
            """
        ),
        {"u": uid, "art": aid, "seq": seq, "c": cid},
    )
    return res.rowcount


async def test_artifact_path_idempotent(test_db_session):
    """Aynı (artefakt, revizyon, task, sample) 2. kez → ON CONFLICT DO NOTHING."""
    db = test_db_session
    uid = await _user(db)
    cid = await _cluster(db)
    aid = await _artifact(db, cid, uid)

    assert await _insert_sample(db, uid, aid, cid) == 1
    assert await _insert_sample(db, uid, aid, cid) == 0  # duplicate → skip

    n = (
        await db.execute(
            text("SELECT count(*) FROM training_samples WHERE artifact_id = :a"),
            {"a": aid},
        )
    ).scalar()
    assert n == 1


async def test_artifact_delete_sets_null_snapshot_survives(test_db_session):
    """Artefakt silinince training snapshot KORUNUR (artifact_id → NULL)."""
    db = test_db_session
    uid = await _user(db)
    cid = await _cluster(db)
    aid = await _artifact(db, cid, uid)
    await _insert_sample(db, uid, aid, cid)

    await db.execute(text("DELETE FROM artifacts WHERE id = :a"), {"a": aid})

    # snapshot satırı yaşıyor, artifact_id NULL'a düştü; cluster_id (soft ref) kalır
    row = (
        await db.execute(
            text("SELECT artifact_id, cluster_id FROM training_samples WHERE user_id = :u"),
            {"u": uid},
        )
    ).one()
    assert row.artifact_id is None
    assert row.cluster_id == cid


async def test_user_delete_cascades_sample(test_db_session):
    """Kullanıcı silinince sample gider (KVKK CASCADE — message yolu ile aynı)."""
    db = test_db_session
    uid = await _user(db)
    cid = await _cluster(db)
    aid = await _artifact(db, cid, uid)
    await _insert_sample(db, uid, aid, cid)

    await db.execute(text("DELETE FROM users WHERE id = :u"), {"u": uid})
    n = (
        await db.execute(
            text("SELECT count(*) FROM training_samples WHERE user_id = :u"),
            {"u": uid},
        )
    ).scalar()
    assert n == 0
