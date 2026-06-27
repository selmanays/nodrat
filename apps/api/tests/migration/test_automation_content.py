"""Integration — #1785 Faz 5.2b otomasyon içerik işlemcisi (testcontainers).

`_process_for_session`: consent + kota kapıları → research_runner → artefakt
(origin='automation') → koşum 'pending'; kaynaksız/consent-yok/kota-dolu/hata için
skip+status geçişleri. `run_cluster_research` + `get_quota_status` KAYNAK modülde
monkeypatch (LLM/Redis gerektirmez); `create_artifact_with_revision` + `record_usage`
GERÇEK (artefakt origin + UsageEvent yazımı + CHECK constraint doğrulanır).
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from app.modules.automation.tasks import content as mod
from sqlalchemy import text

pytestmark = pytest.mark.integration

NOW = datetime(2026, 6, 27, 12, 0, tzinfo=UTC)


async def _user(db, *, consent: bool = True, revoked: bool = False) -> uuid.UUID:
    uid = uuid.uuid4()
    await db.execute(
        text(
            "INSERT INTO users (id, email, password_hash, tier, "
            "foreign_transfer_consent_at, foreign_transfer_consent_revoked_at) "
            "VALUES (:i, :e, 'x', 'free', :c, :r)"
        ),
        {
            "i": uid,
            "e": f"u-{uid.hex[:8]}@x.test",
            "c": NOW if consent else None,
            "r": NOW if revoked else None,
        },
    )
    return uid


async def _cluster(db, name: str = "Asgari Ücret") -> uuid.UUID:
    cid = uuid.uuid4()
    await db.execute(
        text(
            "INSERT INTO research_clusters (id, cluster_key, cluster_type, canonical_name) "
            "VALUES (:i, :k, 'org', :n)"
        ),
        {"i": cid, "k": f"org:{cid.hex[:10]}", "n": name},
    )
    return cid


async def _rule(db, uid: uuid.UUID, cid: uuid.UUID) -> uuid.UUID:
    rid = uuid.uuid4()
    await db.execute(
        text(
            "INSERT INTO automation_rules (id, user_id, cluster_id, trigger_config, action_config) "
            "VALUES (:i, :u, :c, CAST(:tc AS jsonb), CAST(:ac AS jsonb))"
        ),
        {
            "i": rid,
            "u": uid,
            "c": cid,
            "tc": json.dumps({"states": ["breaking"]}),
            "ac": json.dumps({"generate_artifact": True}),
        },
    )
    return rid


async def _queued(db, rid: uuid.UUID, cid: uuid.UUID) -> uuid.UUID:
    run_id = uuid.uuid4()
    await db.execute(
        text(
            "INSERT INTO automation_runs (id, rule_id, cluster_id, status, dedupe_key) "
            "VALUES (:i, :r, :c, 'queued', :d)"
        ),
        {"i": run_id, "r": rid, "c": cid, "d": f"{rid}:{cid}:{run_id.hex[:8]}"},
    )
    return run_id


def _fake_research(*, status: str = "ok", sources: list | None = None, content: str = "Özet [1]."):
    async def _f(db, *, user, query, now, max_rounds=2):
        return SimpleNamespace(
            status=status,
            content=content,
            sources_used=sources if sources is not None else [{"title": "A", "article_id": "a1"}],
            all_sources=[],
            usage={
                "provider": "deepseek",
                "model": "v4-flash",
                "input_tokens": 120,
                "output_tokens": 60,
                "cost_usd": 0.0001,
            },
        )

    return _f


def _fake_quota(*, exceeded: bool = False):
    async def _f(user_id, tier):
        return SimpleNamespace(exceeded=exceeded)

    return _f


def _patch(monkeypatch, *, research, quota):
    monkeypatch.setattr("app.modules.billing.services.quota.get_quota_status", quota)
    monkeypatch.setattr("app.modules.generations.research_runner.run_cluster_research", research)


async def _run_status(db, run_id: uuid.UUID):
    return (
        await db.execute(
            text("SELECT status, artifact_id FROM automation_runs WHERE id = :r"), {"r": run_id}
        )
    ).first()


async def test_ok_creates_automation_artifact_and_pending(test_db_session, monkeypatch):
    db = test_db_session
    uid = await _user(db)
    cid = await _cluster(db)
    rid = await _rule(db, uid, cid)
    run = await _queued(db, rid, cid)
    _patch(monkeypatch, research=_fake_research(), quota=_fake_quota())

    out = await mod._process_for_session(db, NOW)
    assert out["pending"] == 1
    row = await _run_status(db, run)
    assert row.status == "pending"
    assert row.artifact_id is not None
    art = (
        await db.execute(
            text("SELECT origin, cluster_id FROM artifacts WHERE id = :a"), {"a": row.artifact_id}
        )
    ).first()
    assert art.origin == "automation"  # interactive değil
    assert str(art.cluster_id) == str(cid)
    # kota tüketildi (UsageEvent ledger)
    n = (
        await db.execute(text("SELECT count(*) FROM usage_events WHERE user_id = :u"), {"u": uid})
    ).scalar()
    assert n == 1


async def test_no_consent_skipped(test_db_session, monkeypatch):
    db = test_db_session
    uid = await _user(db, consent=False)
    cid = await _cluster(db)
    rid = await _rule(db, uid, cid)
    run = await _queued(db, rid, cid)
    _patch(monkeypatch, research=_fake_research(), quota=_fake_quota())

    out = await mod._process_for_session(db, NOW)
    assert out["skipped"] == 1
    row = await _run_status(db, run)
    assert row.status == "skipped_no_consent"
    assert row.artifact_id is None


async def test_revoked_consent_skipped(test_db_session, monkeypatch):
    db = test_db_session
    uid = await _user(db, consent=True, revoked=True)
    cid = await _cluster(db)
    rid = await _rule(db, uid, cid)
    run = await _queued(db, rid, cid)
    _patch(monkeypatch, research=_fake_research(), quota=_fake_quota())

    out = await mod._process_for_session(db, NOW)
    assert out["skipped"] == 1
    assert (await _run_status(db, run)).status == "skipped_no_consent"


async def test_quota_exceeded_skipped(test_db_session, monkeypatch):
    db = test_db_session
    uid = await _user(db)
    cid = await _cluster(db)
    rid = await _rule(db, uid, cid)
    run = await _queued(db, rid, cid)
    _patch(monkeypatch, research=_fake_research(), quota=_fake_quota(exceeded=True))

    out = await mod._process_for_session(db, NOW)
    assert out["skipped"] == 1
    assert (await _run_status(db, run)).status == "skipped_quota"
    assert (await _run_status(db, run)).artifact_id is None


async def test_no_sources_skipped(test_db_session, monkeypatch):
    db = test_db_session
    uid = await _user(db)
    cid = await _cluster(db)
    rid = await _rule(db, uid, cid)
    run = await _queued(db, rid, cid)
    _patch(
        monkeypatch,
        research=_fake_research(status="skipped_no_sources", sources=[]),
        quota=_fake_quota(),
    )

    out = await mod._process_for_session(db, NOW)
    assert out["skipped"] == 1
    assert (await _run_status(db, run)).status == "skipped_no_sources"
    # artefakt üretilmedi (#1754)
    n = (
        await db.execute(text("SELECT count(*) FROM artifacts WHERE cluster_id = :c"), {"c": cid})
    ).scalar()
    assert n == 0


async def test_research_error_failed(test_db_session, monkeypatch):
    db = test_db_session
    uid = await _user(db)
    cid = await _cluster(db)
    rid = await _rule(db, uid, cid)
    run = await _queued(db, rid, cid)

    async def _boom(db_, *, user, query, now, max_rounds=2):
        raise RuntimeError("research patladı")

    _patch(monkeypatch, research=_boom, quota=_fake_quota())
    out = await mod._process_for_session(db, NOW)
    assert out["failed"] == 1
    row = await _run_status(db, run)
    assert row.status == "failed"
    err = (
        await db.execute(text("SELECT error FROM automation_runs WHERE id = :r"), {"r": run})
    ).scalar()
    assert err and "patladı" in err
