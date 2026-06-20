"""Integration — Faz 3b artefakt geçmişi + revizyon (testcontainers).

add_revision zinciri (seq++, parent, head güncelle) + cluster_artifacts/
artifact_detail endpoint'leri (user-scoped, ownership). Endpoint fonksiyonları
doğrudan çağrılır; commit'siz yollar → fixture per-test rollback uyumlu.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from app.api.app_me import artifact_detail, cluster_artifacts
from app.modules.generations.artifacts import add_revision, create_artifact_with_revision
from fastapi import HTTPException
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


async def test_add_revision_chain(test_db_session):
    db = test_db_session
    uid = await _user(db)
    cid = await _cluster(db)
    aid = await create_artifact_with_revision(db, user_id=uid, cluster_id=cid, content="v1 içerik")

    seq = await add_revision(
        db, artifact_id=aid, content="v2 daha kısa", revision_intent="quick_shorter"
    )
    assert seq == 2

    # head v2'ye işaret eder
    head = (
        await db.execute(text("SELECT head_revision_id FROM artifacts WHERE id=:a"), {"a": aid})
    ).scalar()
    revs = (
        await db.execute(
            text(
                "SELECT id, revision_seq, parent_revision_id, revision_intent "
                "FROM artifact_revisions WHERE artifact_id=:a ORDER BY revision_seq"
            ),
            {"a": aid},
        )
    ).all()
    assert [r.revision_seq for r in revs] == [1, 2]
    assert revs[1].parent_revision_id == revs[0].id  # zincir
    assert revs[1].revision_intent == "quick_shorter"
    assert head == revs[1].id  # head = en güncel


async def test_cluster_artifacts_endpoint(test_db_session):
    db = test_db_session
    uid = await _user(db)
    cid = await _cluster(db)
    await create_artifact_with_revision(db, user_id=uid, cluster_id=cid, content="bir")
    a2 = await create_artifact_with_revision(db, user_id=uid, cluster_id=cid, content="iki")
    await add_revision(db, artifact_id=a2, content="iki-v2", revision_intent="edit")

    resp = await cluster_artifacts(cluster_id=cid, user=SimpleNamespace(id=uid), db=db)  # type: ignore[arg-type]
    assert resp.total == 2
    by_count = sorted(a.revision_count for a in resp.artifacts)
    assert by_count == [1, 2]  # biri 1 revizyon, diğeri 2
    assert all(a.head_preview for a in resp.artifacts)


async def test_cluster_artifacts_user_scoped(test_db_session):
    db = test_db_session
    uid = await _user(db)
    other = await _user(db)
    cid = await _cluster(db)
    await create_artifact_with_revision(db, user_id=other, cluster_id=cid, content="başkası")

    resp = await cluster_artifacts(cluster_id=cid, user=SimpleNamespace(id=uid), db=db)  # type: ignore[arg-type]
    assert resp.total == 0  # başkasının artefaktı sızmaz


async def test_artifact_detail_and_ownership(test_db_session):
    db = test_db_session
    uid = await _user(db)
    other = await _user(db)
    cid = await _cluster(db)
    aid = await create_artifact_with_revision(
        db, user_id=uid, cluster_id=cid, content="v1", artifact_type="thread"
    )
    await add_revision(db, artifact_id=aid, content="v2", revision_intent="quick_longer")

    detail = await artifact_detail(artifact_id=aid, user=SimpleNamespace(id=uid), db=db)  # type: ignore[arg-type]
    assert detail.artifact_type == "thread"
    assert detail.cluster_id == str(cid)
    assert [r.revision_seq for r in detail.revisions] == [1, 2]
    assert detail.head_revision_seq == 2

    # başka kullanıcı → 404
    with pytest.raises(HTTPException) as exc:
        await artifact_detail(artifact_id=aid, user=SimpleNamespace(id=other), db=db)  # type: ignore[arg-type]
    assert exc.value.status_code == 404
