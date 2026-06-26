"""Integration — #1779 Faz 5.0 otomasyon şema iskelesi (testcontainers pgvector).

3 tablo (social_accounts/automation_rules/automation_runs) + server_default + CHECK +
partial-unique + FK ondelete. Faz 5.0 saf şema; bu test şemanın doğru kurulduğunu +
invariantları (küme-başına-tek-canlı-kural, mode/status CHECK, cluster RESTRICT /
user CASCADE, run dedupe UNIQUE) doğrular. Constraint-ihlali savepoint (begin_nested)
ile izole edilir → dış transaction zehirlenmez.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

pytestmark = pytest.mark.integration


async def _user(db) -> str:
    uid = uuid.uuid4()
    await db.execute(
        text("INSERT INTO users (id, email, password_hash) VALUES (:i, :e, 'x')"),
        {"i": uid, "e": f"u-{uid.hex[:8]}@x.test"},
    )
    return str(uid)


async def _cluster(db) -> str:
    cid = uuid.uuid4()
    await db.execute(
        text(
            "INSERT INTO research_clusters (id, cluster_key, cluster_type, canonical_name) "
            "VALUES (:i, :k, 'org', 'X')"
        ),
        {"i": cid, "k": f"org:{cid.hex[:10]}"},
    )
    return str(cid)


async def _rule(db, uid: str, cid: str, *, mode: str = "approval_queue") -> str:
    rid = uuid.uuid4()
    await db.execute(
        text(
            "INSERT INTO automation_rules "
            "(id, user_id, cluster_id, trigger_config, action_config, mode) VALUES "
            '(:i, :u, :c, \'{"states":["breaking"]}\'::jsonb, '
            "'{\"generate_artifact\":true}'::jsonb, :m)"
        ),
        {"i": rid, "u": uid, "c": cid, "m": mode},
    )
    return str(rid)


async def test_schema_tables_exist(test_db_session):
    db = test_db_session
    for t in ("social_accounts", "automation_rules", "automation_runs"):
        reg = (await db.execute(text("SELECT to_regclass(:t)"), {"t": f"public.{t}"})).scalar()
        assert reg == t


async def test_rule_defaults(test_db_session):
    db = test_db_session
    uid, cid = await _user(db), await _cluster(db)
    rid = await _rule(db, uid, cid)
    r = (
        await db.execute(
            text("SELECT mode, status, enabled FROM automation_rules WHERE id=:i"), {"i": rid}
        )
    ).first()
    assert r.mode == "approval_queue"  # founder ilkesi: onay-kuyruğu varsayılan
    assert r.status == "active"
    assert r.enabled is False  # default OFF


async def test_mode_check_rejects_invalid(test_db_session):
    db = test_db_session
    uid, cid = await _user(db), await _cluster(db)
    with pytest.raises(IntegrityError):
        async with db.begin_nested():
            await _rule(db, uid, cid, mode="bogus")


async def test_one_live_rule_per_cluster(test_db_session):
    db = test_db_session
    uid, cid = await _user(db), await _cluster(db)
    await _rule(db, uid, cid)
    # ikinci CANLI kural aynı user+cluster → partial-unique ihlali
    with pytest.raises(IntegrityError):
        async with db.begin_nested():
            await _rule(db, uid, cid)
    # birinciyi soft-delete → ikinci serbest (partial WHERE deleted_at IS NULL)
    await db.execute(
        text("UPDATE automation_rules SET deleted_at=NOW() WHERE user_id=:u AND cluster_id=:c"),
        {"u": uid, "c": cid},
    )
    rid2 = await _rule(db, uid, cid)
    assert rid2


async def test_cluster_restrict_user_cascade(test_db_session):
    db = test_db_session
    uid, cid = await _user(db), await _cluster(db)
    await _rule(db, uid, cid)
    # cluster_id RESTRICT: kuralı olan küme silinemez (paylaşımlı düğüm korunur)
    with pytest.raises(IntegrityError):
        async with db.begin_nested():
            await db.execute(text("DELETE FROM research_clusters WHERE id=:c"), {"c": cid})
    # user_id CASCADE: hesap silinince kural gider (KVKK)
    await db.execute(text("DELETE FROM users WHERE id=:u"), {"u": uid})
    n = (
        await db.execute(text("SELECT count(*) FROM automation_rules WHERE user_id=:u"), {"u": uid})
    ).scalar()
    assert n == 0


async def test_run_dedupe_unique(test_db_session):
    db = test_db_session
    uid, cid = await _user(db), await _cluster(db)
    rid = await _rule(db, uid, cid)
    key = "rule:cluster:2026-06-26"
    await db.execute(
        text("INSERT INTO automation_runs (rule_id, cluster_id, dedupe_key) VALUES (:r,:c,:k)"),
        {"r": rid, "c": cid, "k": key},
    )
    # aynı dedupe_key → UNIQUE ihlali (idempotency: rule+küme+gün tek koşum)
    with pytest.raises(IntegrityError):
        async with db.begin_nested():
            await db.execute(
                text(
                    "INSERT INTO automation_runs (rule_id, cluster_id, dedupe_key) "
                    "VALUES (:r,:c,:k)"
                ),
                {"r": rid, "c": cid, "k": key},
            )


async def test_social_account_one_live_per_provider(test_db_session):
    db = test_db_session
    uid = await _user(db)

    async def _sa():
        await db.execute(
            text("INSERT INTO social_accounts (user_id, provider) VALUES (:u, 'x')"),
            {"u": uid},
        )

    await _sa()
    with pytest.raises(IntegrityError):
        async with db.begin_nested():
            await _sa()  # ikinci canlı 'x' hesabı → partial-unique ihlali
    # revoke → yeni bağlanabilir
    await db.execute(
        text("UPDATE social_accounts SET revoked_at=NOW() WHERE user_id=:u"), {"u": uid}
    )
    await _sa()
