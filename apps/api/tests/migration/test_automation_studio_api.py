"""Integration — #1791 Faz 5.3a otomasyon stüdyo API (testcontainers).

Kural CRUD + onay kuyruğu (approve/reject) + çift flag-gate 403 + feed gizleme
(onaylanmamış otomasyon artefaktı küme feed'inde görünmez). Route fonksiyonları
DOĞRUDAN çağrılır (test_notifications.py deseni); settings_store.get_bool monkeypatch.
"""

from __future__ import annotations

import json
import uuid
from types import SimpleNamespace

import app.api.app_automation as api
import pytest
from fastapi import HTTPException
from sqlalchemy import text

pytestmark = pytest.mark.integration


def _enable(monkeypatch, *, on: bool = True):
    from app.shared.runtime_config.settings_store import settings_store

    async def _flag(db, key, default=False):
        return on

    monkeypatch.setattr(settings_store, "get_bool", _flag)


async def _user(db) -> uuid.UUID:
    uid = uuid.uuid4()
    await db.execute(
        text("INSERT INTO users (id, email, password_hash) VALUES (:i, :e, 'x')"),
        {"i": uid, "e": f"u-{uid.hex[:8]}@x.test"},
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


def _u(uid):
    return SimpleNamespace(id=uid)


async def test_create_and_list_rule(test_db_session, monkeypatch):
    db = test_db_session
    _enable(monkeypatch)
    uid = await _user(db)
    cid = await _cluster(db)
    created = await api.create_rule(api.RuleCreate(cluster_id=cid), user=_u(uid), db=db)
    assert created.enabled is True
    assert created.states == ["breaking"]
    lst = await api.list_rules(user=_u(uid), db=db)
    assert lst.total == 1
    assert lst.rules[0].cluster_name == "Asgari Ücret"
    assert lst.rules[0].status == "active"


async def test_create_duplicate_409(test_db_session, monkeypatch):
    db = test_db_session
    _enable(monkeypatch)
    uid = await _user(db)
    cid = await _cluster(db)
    await api.create_rule(api.RuleCreate(cluster_id=cid), user=_u(uid), db=db)
    with pytest.raises(HTTPException) as exc:
        await api.create_rule(api.RuleCreate(cluster_id=cid), user=_u(uid), db=db)
    assert exc.value.status_code == 409  # küme başına tek canlı kural


async def test_create_invalid_states_and_missing_cluster(test_db_session, monkeypatch):
    db = test_db_session
    _enable(monkeypatch)
    uid = await _user(db)
    cid = await _cluster(db)
    with pytest.raises(HTTPException) as e1:
        await api.create_rule(api.RuleCreate(cluster_id=cid, states=["bogus"]), user=_u(uid), db=db)
    assert e1.value.status_code == 422
    with pytest.raises(HTTPException) as e2:
        await api.create_rule(api.RuleCreate(cluster_id=uuid.uuid4()), user=_u(uid), db=db)
    assert e2.value.status_code == 404


async def test_update_pause_and_delete(test_db_session, monkeypatch):
    db = test_db_session
    _enable(monkeypatch)
    uid = await _user(db)
    cid = await _cluster(db)
    rule = await api.create_rule(api.RuleCreate(cluster_id=cid), user=_u(uid), db=db)
    rid = uuid.UUID(rule.rule_id)
    await api.update_rule(rid, api.RuleUpdate(status="paused", enabled=False), user=_u(uid), db=db)
    lst = await api.list_rules(user=_u(uid), db=db)
    assert lst.rules[0].status == "paused"
    assert lst.rules[0].enabled is False
    await api.delete_rule(rid, user=_u(uid), db=db)
    assert (await api.list_rules(user=_u(uid), db=db)).total == 0  # soft-delete → listede yok


async def test_cross_user_rule_404(test_db_session, monkeypatch):
    db = test_db_session
    _enable(monkeypatch)
    owner = await _user(db)
    other = await _user(db)
    cid = await _cluster(db)
    rule = await api.create_rule(api.RuleCreate(cluster_id=cid), user=_u(owner), db=db)
    with pytest.raises(HTTPException) as exc:
        await api.delete_rule(uuid.UUID(rule.rule_id), user=_u(other), db=db)
    assert exc.value.status_code == 404  # başkasının kuralı


async def _seed_pending_run(db, uid, cid):
    from app.modules.generations.artifacts import create_artifact_with_revision

    art_id = await create_artifact_with_revision(
        db,
        user_id=uid,
        cluster_id=cid,
        content="Otomasyon özeti [1].",
        sources_used=[{"title": "A"}],
        origin="automation",
    )
    rid = uuid.uuid4()
    await db.execute(
        text(
            "INSERT INTO automation_rules (id, user_id, cluster_id, trigger_config, "
            "action_config, enabled) VALUES (:i,:u,:c, CAST(:tc AS jsonb), CAST(:ac AS jsonb), true)"
        ),
        {
            "i": rid,
            "u": uid,
            "c": cid,
            "tc": json.dumps({"states": ["breaking"]}),
            "ac": json.dumps({}),
        },
    )
    run_id = uuid.uuid4()
    await db.execute(
        text(
            "INSERT INTO automation_runs (id, rule_id, cluster_id, status, dedupe_key, artifact_id) "
            "VALUES (:i, :r, :c, 'pending', :d, :a)"
        ),
        {"i": run_id, "r": rid, "c": cid, "d": f"{rid}:{cid}:x", "a": art_id},
    )
    return art_id, run_id


async def test_approval_queue_approve(test_db_session, monkeypatch):
    db = test_db_session
    _enable(monkeypatch)
    uid = await _user(db)
    cid = await _cluster(db)
    _art, run_id = await _seed_pending_run(db, uid, cid)
    queue = await api.list_runs(user=_u(uid), db=db)
    assert queue.total == 1
    assert queue.runs[0].artifact_preview and "Otomasyon" in queue.runs[0].artifact_preview
    out = await api.approve_run(run_id, user=_u(uid), db=db)
    assert out["status"] == "posted"
    assert (await api.list_runs(user=_u(uid), db=db)).total == 0  # artık pending değil


async def test_reject_run(test_db_session, monkeypatch):
    db = test_db_session
    _enable(monkeypatch)
    uid = await _user(db)
    cid = await _cluster(db)
    _art, run_id = await _seed_pending_run(db, uid, cid)
    out = await api.reject_run(run_id, user=_u(uid), db=db)
    assert out["status"] == "rejected"
    st = (
        await db.execute(text("SELECT status FROM automation_runs WHERE id = :r"), {"r": run_id})
    ).scalar()
    assert st == "rejected"


async def test_cross_user_approve_reject_404(test_db_session, monkeypatch):
    """Başkasının pending koşumunu onaylayamaz/reddedemez (404, yan-etkisiz)."""
    db = test_db_session
    _enable(monkeypatch)
    owner = await _user(db)
    other = await _user(db)
    cid = await _cluster(db)
    _art, run_id = await _seed_pending_run(db, owner, cid)
    with pytest.raises(HTTPException) as e1:
        await api.approve_run(run_id, user=_u(other), db=db)
    assert e1.value.status_code == 404
    with pytest.raises(HTTPException) as e2:
        await api.reject_run(run_id, user=_u(other), db=db)
    assert e2.value.status_code == 404
    # owner'ın koşumu hâlâ pending (other çağrıları yan-etkisiz)
    st = (
        await db.execute(text("SELECT status FROM automation_runs WHERE id = :r"), {"r": run_id})
    ).scalar()
    assert st == "pending"


async def test_flag_off_403(test_db_session, monkeypatch):
    db = test_db_session
    _enable(monkeypatch, on=False)  # master/studio OFF
    uid = await _user(db)
    with pytest.raises(HTTPException) as exc:
        await api.list_rules(user=_u(uid), db=db)
    assert exc.value.status_code == 403


async def test_feed_hides_pending_automation_artifact(test_db_session, monkeypatch):
    """Onaylanmamış otomasyon artefaktı küme feed'inde GÖRÜNMEZ; onaylanınca görünür."""
    from app.api.app_me import cluster_artifacts

    db = test_db_session
    _enable(monkeypatch)
    uid = await _user(db)
    cid = await _cluster(db)
    _art, run_id = await _seed_pending_run(db, uid, cid)

    feed = await cluster_artifacts(cluster_id=cid, user=_u(uid), db=db)
    assert feed.total == 0  # pending oto-artefakt feed'de gizli

    await api.approve_run(run_id, user=_u(uid), db=db)  # → 'posted'
    feed2 = await cluster_artifacts(cluster_id=cid, user=_u(uid), db=db)
    assert feed2.total == 1  # onaylanınca görünür
