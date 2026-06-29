"""Integration — #1782 Faz 5.1 otomasyon tetik beat çekirdeği (testcontainers).

`_dispatch_for_session`: aktif kural × breaking küme → 'queued' koşum + idempotency
(rule+küme+gün) + `trigger_config.states` filtresi + enabled/status/soft-delete
filtreleri + per-user cap. `trend_metrics_for_clusters` monkeypatch'lenir (canlı
trend fikstürü ağır; beat uçtan-uca prod canary'de doğrulanır — alerts.py deseni).
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from app.modules.automation.tasks import triggers as trig
from sqlalchemy import text

pytestmark = pytest.mark.integration

NOW = datetime(2026, 6, 27, 12, 0, tzinfo=UTC)
DAY = "2026-06-27"


async def _user(db) -> uuid.UUID:
    uid = uuid.uuid4()
    await db.execute(
        text("INSERT INTO users (id, email, password_hash) VALUES (:i, :e, 'x')"),
        {"i": uid, "e": f"u-{uid.hex[:8]}@x.test"},
    )
    return uid


async def _cluster(db, ckey: str = "org:test-kume") -> tuple[uuid.UUID, str]:
    cid = uuid.uuid4()
    await db.execute(
        text(
            "INSERT INTO research_clusters (id, cluster_key, cluster_type, canonical_name) "
            "VALUES (:i, :k, 'org', 'Test Küme')"
        ),
        {"i": cid, "k": ckey},
    )
    return cid, ckey


async def _subscribe(db, uid: uuid.UUID, cid: uuid.UUID) -> None:
    await db.execute(
        text(
            "INSERT INTO user_cluster_subscriptions (user_id, cluster_id, status, source) "
            "VALUES (:u, :c, 'active', 'test')"
        ),
        {"u": uid, "c": cid},
    )


async def _rule(
    db,
    uid: uuid.UUID,
    cid: uuid.UUID,
    *,
    enabled: bool = True,
    status: str = "active",
    states: list[str] | None = None,
    window_seconds: int | None = None,
    deleted: bool = False,
    subscribed: bool = True,
) -> uuid.UUID:
    rid = uuid.uuid4()
    tc: dict = {"states": states or ["breaking"]}
    if window_seconds is not None:
        tc["window_seconds"] = window_seconds
    await db.execute(
        text(
            """
            INSERT INTO automation_rules
                (id, user_id, cluster_id, trigger_config, action_config,
                 enabled, status, deleted_at)
            VALUES (:i, :u, :c, CAST(:tc AS jsonb), CAST(:ac AS jsonb), :en, :st, :del)
            """
        ),
        {
            "i": rid,
            "u": uid,
            "c": cid,
            "tc": json.dumps(tc),
            "ac": '{"generate_artifact":true}',
            "en": enabled,
            "st": status,
            "del": NOW if deleted else None,
        },
    )
    if subscribed:
        await _subscribe(db, uid, cid)  # abonelik kapısı (beat JOIN'i için)
    return rid


def _fake_metrics(state_by_key: dict[str, str | None]):
    async def _f(db, keys, *, window_seconds, now):
        return {
            k: SimpleNamespace(trend_state=state_by_key.get(k), article_count=5)
            for k in keys
            if state_by_key.get(k) is not None
        }

    return _f


async def _runs(db, rid: uuid.UUID) -> list:
    return (
        await db.execute(
            text("SELECT status, dedupe_key FROM automation_runs WHERE rule_id = :r"),
            {"r": rid},
        )
    ).all()


async def test_enqueues_when_breaking(test_db_session, monkeypatch):
    db = test_db_session
    uid = await _user(db)
    cid, ckey = await _cluster(db)
    rid = await _rule(db, uid, cid)
    monkeypatch.setattr(trig, "trend_metrics_for_clusters", _fake_metrics({ckey: "breaking"}))

    out = await trig._dispatch_for_session(db, NOW)
    assert out == {"rules": 1, "created": 1}
    rows = await _runs(db, rid)
    assert len(rows) == 1
    assert rows[0].status == "queued"  # durum-makinesi: trigger → queued
    assert rows[0].dedupe_key == f"{rid}:{cid}:{DAY}"
    lt = (
        await db.execute(
            text("SELECT last_triggered_at FROM automation_rules WHERE id = :r"), {"r": rid}
        )
    ).scalar()
    assert lt is not None  # koşum üretildi → last_triggered_at güncellendi


async def test_idempotent_same_day(test_db_session, monkeypatch):
    db = test_db_session
    uid = await _user(db)
    cid, ckey = await _cluster(db)
    rid = await _rule(db, uid, cid)
    monkeypatch.setattr(trig, "trend_metrics_for_clusters", _fake_metrics({ckey: "breaking"}))

    first = await trig._dispatch_for_session(db, NOW)
    second = await trig._dispatch_for_session(db, NOW)  # aynı gün → ON CONFLICT
    assert first["created"] == 1
    assert second["created"] == 0
    assert len(await _runs(db, rid)) == 1  # tek koşum (rule+küme+gün)


async def test_no_rule_no_op(test_db_session, monkeypatch):
    db = test_db_session
    await _user(db)
    await _cluster(db)
    monkeypatch.setattr(
        trig, "trend_metrics_for_clusters", _fake_metrics({"org:test-kume": "breaking"})
    )
    out = await trig._dispatch_for_session(db, NOW)
    assert out == {"rules": 0, "created": 0}


async def test_disabled_rule_skipped(test_db_session, monkeypatch):
    db = test_db_session
    uid = await _user(db)
    cid, ckey = await _cluster(db)
    rid = await _rule(db, uid, cid, enabled=False)
    monkeypatch.setattr(trig, "trend_metrics_for_clusters", _fake_metrics({ckey: "breaking"}))
    out = await trig._dispatch_for_session(db, NOW)
    assert out["rules"] == 0  # enabled=false WHERE'de elenir
    assert len(await _runs(db, rid)) == 0


async def test_soft_deleted_rule_skipped(test_db_session, monkeypatch):
    db = test_db_session
    uid = await _user(db)
    cid, ckey = await _cluster(db)
    rid = await _rule(db, uid, cid, deleted=True)
    monkeypatch.setattr(trig, "trend_metrics_for_clusters", _fake_metrics({ckey: "breaking"}))
    out = await trig._dispatch_for_session(db, NOW)
    assert out["rules"] == 0  # deleted_at IS NOT NULL elenir
    assert len(await _runs(db, rid)) == 0


async def test_non_breaking_skipped(test_db_session, monkeypatch):
    db = test_db_session
    uid = await _user(db)
    cid, ckey = await _cluster(db)
    rid = await _rule(db, uid, cid)  # states=['breaking']
    monkeypatch.setattr(trig, "trend_metrics_for_clusters", _fake_metrics({ckey: "stable"}))
    out = await trig._dispatch_for_session(db, NOW)
    assert out == {"rules": 1, "created": 0}  # stable ∉ states → koşum yok
    assert len(await _runs(db, rid)) == 0


async def test_states_data_driven(test_db_session, monkeypatch):
    """Kural states=['developing'] → developing tetikler, breaking tetiklemez (data-driven)."""
    db = test_db_session
    uid = await _user(db)
    cid, ckey = await _cluster(db)
    rid = await _rule(db, uid, cid, states=["developing"])
    monkeypatch.setattr(trig, "trend_metrics_for_clusters", _fake_metrics({ckey: "developing"}))
    out = await trig._dispatch_for_session(db, NOW)
    assert out["created"] == 1
    assert len(await _runs(db, rid)) == 1


async def test_paused_rule_skipped(test_db_session, monkeypatch):
    """status='paused' kural (enabled=true olsa da) WHERE status='active'ta elenir."""
    db = test_db_session
    uid = await _user(db)
    cid, ckey = await _cluster(db)
    rid = await _rule(db, uid, cid, status="paused")
    monkeypatch.setattr(trig, "trend_metrics_for_clusters", _fake_metrics({ckey: "breaking"}))
    out = await trig._dispatch_for_session(db, NOW)
    assert out["rules"] == 0  # status != 'active' → elenir
    assert len(await _runs(db, rid)) == 0


async def test_missing_metric_no_op(test_db_session, monkeypatch):
    """Küme canlı metrikte yok (m is None — ör. canonical drift / sessiz küme) → koşum yok."""
    db = test_db_session
    uid = await _user(db)
    cid, ckey = await _cluster(db)
    rid = await _rule(db, uid, cid)
    # _fake_metrics None değerleri eler → metrics={} → metrics.get(ckey) is None
    monkeypatch.setattr(trig, "trend_metrics_for_clusters", _fake_metrics({ckey: None}))
    out = await trig._dispatch_for_session(db, NOW)
    assert out == {"rules": 1, "created": 0}
    assert len(await _runs(db, rid)) == 0


async def test_multi_rule_multi_window(test_db_session, monkeypatch):
    """İki kural / iki küme / iki pencere → by_window pencere başına metrik + ikisi de enqueue."""
    db = test_db_session
    uid = await _user(db)
    cid_a, _ckey_a = await _cluster(db, "org:kume-a")
    cid_b, _ckey_b = await _cluster(db, "org:kume-b")
    rid_a = await _rule(db, uid, cid_a)  # default 86400
    rid_b = await _rule(db, uid, cid_b, window_seconds=3600)

    windows_seen: list[int] = []

    async def _f(db_, keys, *, window_seconds, now):
        windows_seen.append(window_seconds)
        return {k: SimpleNamespace(trend_state="breaking", article_count=5) for k in keys}

    monkeypatch.setattr(trig, "trend_metrics_for_clusters", _f)
    out = await trig._dispatch_for_session(db, NOW)
    assert out == {"rules": 2, "created": 2}
    assert sorted(windows_seen) == [3600, 86400]  # pencere başına tek sorgu
    assert len(await _runs(db, rid_a)) == 1
    assert len(await _runs(db, rid_b)) == 1


async def test_daily_cap_across_beats(test_db_session, monkeypatch):
    """Günlük tavan beat-başına DEĞİL günlük: cap=1, 2 küme → beat 1'de 1 koşum,
    beat 2 (aynı gün) seed=1 ≥ cap → 0 (toplam 1)."""
    db = test_db_session
    uid = await _user(db)
    cid_a, ckey_a = await _cluster(db, "org:kume-a")
    cid_b, ckey_b = await _cluster(db, "org:kume-b")
    await _rule(db, uid, cid_a)
    await _rule(db, uid, cid_b)
    monkeypatch.setattr(trig, "DAILY_CAP_PER_USER", 1)
    monkeypatch.setattr(
        trig, "trend_metrics_for_clusters", _fake_metrics({ckey_a: "breaking", ckey_b: "breaking"})
    )

    first = await trig._dispatch_for_session(db, NOW)
    assert first["created"] == 1  # cap=1 → tek koşum, ikinci küme atlanır
    second = await trig._dispatch_for_session(db, NOW)  # aynı gün, seed=1 ≥ cap
    assert second["created"] == 0  # günlük tavan beat-arası korunur (seed sayesinde)
    total = (await db.execute(text("SELECT count(*) FROM automation_runs"))).scalar()
    assert total == 1


async def test_unsubscribed_rule_not_dispatched(test_db_session, monkeypatch):
    """Abone OLMAYAN kuralın kümesi breaking olsa da tetiklenmez (#denetim-1/2)."""
    db = test_db_session
    uid = await _user(db)
    cid, ckey = await _cluster(db)
    await _rule(db, uid, cid, subscribed=False)  # kural var, abonelik YOK
    monkeypatch.setattr(trig, "trend_metrics_for_clusters", _fake_metrics({ckey: "breaking"}))
    out = await trig._dispatch_for_session(db, NOW)
    assert out == {"rules": 0, "created": 0}  # abonelik JOIN'i eler


async def test_skipped_runs_dont_consume_daily_cap(test_db_session, monkeypatch):
    """skipped_* koşum DAILY_CAP'i tüketmez (#denetim-3): cap=1, aynı kullanıcının
    BAŞKA kümesinde bugün bir skipped koşum varken yeni breaking kural yine üretmeli."""
    db = test_db_session
    uid = await _user(db)
    cid_a, ckey_a = await _cluster(db, "org:cap-a")
    cid_b, _ckey_b = await _cluster(db, "org:cap-b")
    await _rule(db, uid, cid_a)
    rid_b = await _rule(db, uid, cid_b)
    # cid_b için bugün 'skipped_no_sources' koşum (dedupe_key gün-eki seed pattern'iyle eşleşir)
    await db.execute(
        text(
            "INSERT INTO automation_runs (rule_id, cluster_id, status, dedupe_key) "
            "VALUES (:r, :c, 'skipped_no_sources', :d)"
        ),
        {"r": rid_b, "c": cid_b, "d": f"{rid_b}:{cid_b}:{DAY}"},
    )
    monkeypatch.setattr(trig, "DAILY_CAP_PER_USER", 1)
    # yalnız cid_a breaking (cid_b sakin → yeni koşum yok)
    monkeypatch.setattr(trig, "trend_metrics_for_clusters", _fake_metrics({ckey_a: "breaking"}))
    out = await trig._dispatch_for_session(db, NOW)
    assert out["created"] == 1  # skipped seed cap'i tüketmedi → cid_a üretildi
