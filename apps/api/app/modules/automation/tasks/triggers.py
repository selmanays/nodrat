"""Otomasyon tetik beat'i (Faz 5.1, #1782) — abone küme breaking → koşum kuyruğu.

Automation ÜST orkestratör (import-linter 17. contract: `trends → automation` YASAK).
Bu yüzden trend-alert beat'ine HOOK DEĞİL, AYRI bir beat: automation trends'i OKUR.

Aktif kuralları (enabled + status='active' + canlı küme) tarar; kuralın kümesi
`trigger_config.states` (default {breaking} — founder breaking-only) trend-state'indeyse
`automation_runs`'a 'queued' koşum ekler. İdempotent: dedupe_key
`<rule>:<cluster>:<gün-UTC>` UNIQUE (ON CONFLICT DO NOTHING) → rule+küme+gün başına
tek koşum. İki flag-gate: `automation.enabled` (master) + `automation.triggers.enabled`
(default OFF → no-op). Kural yokken VEYA flag OFF → no-op (deploy davranış değiştirmez).

Cross-domain okuma RAW SQL (research_clusters) → automation kendi tablolarını yazar.
trend-state CANLI okunur (`trend_metrics_for_clusters` — alerts.py ile aynı yol;
snapshot worker flag'inden bağımsız).

Koşum durum-makinesi: queued (bu beat) → [5.2 oto-içerik] → pending (onay kuyruğu)
→ [5.3 onay] → posted | rejected | skipped_* | failed.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime

from sqlalchemy import text

from app.modules.trends.cluster_link import trend_metrics_for_clusters
from app.shared.runtime_config.settings_store import settings_store
from app.shared.workers.db_session import _get_session_factory, _run_async
from app.workers.celery_app import celery_app

DEFAULT_STATES = frozenset({"breaking"})  # founder: breaking-only ('developing' sonra)
DEFAULT_WINDOW_SECONDS = 86_400  # 24s
# GÜNLÜK maliyet/abuse tavanı (kullanıcı başına gün içinde üretilebilecek koşum).
# Beat saatlik koşar → `per_user` bugün ZATEN üretilmiş koşumlardan tohumlanır,
# yoksa cap beat-başına olur (her saat 50 yeni) → günlük tavan tutmaz.
DAILY_CAP_PER_USER = 50


async def _dispatch_for_session(db, now: datetime) -> dict:
    """Çekirdek: aktif kurallar × breaking küme → 'queued' koşum (commit'siz).

    Flag kontrolü ÇAĞIRANDA (`_dispatch_async`). Test bunu doğrudan çağırır.
    """
    day = now.date().isoformat()
    rules = (
        await db.execute(
            text(
                """
                SELECT ar.id::text AS rule_id, ar.user_id::text AS uid,
                       ar.cluster_id::text AS cid, rc.cluster_key AS ckey,
                       ar.trigger_config AS tc
                FROM automation_rules ar
                JOIN research_clusters rc ON rc.id = ar.cluster_id
                -- abonelik kapısı: kullanıcı kümeye HÂLÂ abone olmalı (unsubscribe
                -- → üretim durur; vizyon + KVKK opt-out paritesi, alerts.py deseni)
                JOIN user_cluster_subscriptions ucs
                  ON ucs.user_id = ar.user_id AND ucs.cluster_id = ar.cluster_id
                  AND ucs.unsubscribed_at IS NULL
                WHERE ar.enabled = true AND ar.status = 'active'
                  AND ar.deleted_at IS NULL AND rc.deprecated_at IS NULL
                """
            )
        )
    ).all()
    if not rules:
        return {"rules": 0, "created": 0}

    # Kuralları pencereye göre grupla (çoğu default 86400; nadiren override) →
    # pencere başına tek canlı metrik sorgusu.
    by_window: dict[int, list] = defaultdict(list)
    for r in rules:
        w = int((r.tc or {}).get("window_seconds") or DEFAULT_WINDOW_SECONDS)
        by_window[w].append(r)

    # Günlük tavanı GERÇEKTEN günlük yap: bugün (dedupe_key son segmenti = gün) bu
    # kullanıcı için üretilmiş koşumları say → per_user beat-yerel sıfırlanmaz.
    # dedupe_key formatı <rule>:<cluster>:<gün> ile tutarlı (clock-bağımsız).
    seed = (
        await db.execute(
            text(
                """
                SELECT ar.user_id::text AS uid, count(*) AS n
                FROM automation_runs r
                JOIN automation_rules ar ON ar.id = r.rule_id
                -- yalnız MALİYET/artefakt doğuran koşumlar tavanı tüketir; sıfır-maliyetli
                -- elemeler (consent/kota/kaynaksız) + failed cap'i tüketmez (#denetim-3)
                WHERE r.dedupe_key LIKE '%:' || :day
                  AND r.status NOT IN ('skipped_no_sources', 'skipped_quota',
                                       'skipped_no_consent', 'failed')
                GROUP BY ar.user_id
                """
            ),
            {"day": day},
        )
    ).all()
    created = 0
    per_user: dict[str, int] = {s.uid: int(s.n) for s in seed}
    for window, group in by_window.items():
        keys = sorted({r.ckey for r in group})
        metrics = await trend_metrics_for_clusters(db, keys, window_seconds=window, now=now)
        for r in group:
            m = metrics.get(r.ckey)
            states = set((r.tc or {}).get("states") or DEFAULT_STATES)
            if m is None or m.trend_state not in states:
                continue
            if per_user.get(r.uid, 0) >= DAILY_CAP_PER_USER:
                continue
            res = await db.execute(
                text(
                    """
                    INSERT INTO automation_runs (rule_id, cluster_id, status, dedupe_key)
                    VALUES (CAST(:rid AS uuid), CAST(:cid AS uuid), 'queued', :dk)
                    ON CONFLICT (dedupe_key) DO NOTHING
                    """
                ),
                {"rid": r.rule_id, "cid": r.cid, "dk": f"{r.rule_id}:{r.cid}:{day}"},
            )
            if res.rowcount:
                created += 1
                per_user[r.uid] = per_user.get(r.uid, 0) + 1
                await db.execute(
                    text(
                        "UPDATE automation_rules SET last_triggered_at = :now "
                        "WHERE id = CAST(:rid AS uuid)"
                    ),
                    {"now": now, "rid": r.rule_id},
                )
    return {"rules": len(rules), "created": created}


async def _dispatch_async() -> dict:
    factory = _get_session_factory()
    async with factory() as db:
        if not await settings_store.get_bool(db, "automation.enabled", False):
            return {"skipped": "automation_disabled"}
        if not await settings_store.get_bool(db, "automation.triggers.enabled", False):
            return {"skipped": "triggers_disabled"}
        result = await _dispatch_for_session(db, datetime.now(UTC))
        await db.commit()
        return result


@celery_app.task(name="tasks.automation.dispatch_triggers", bind=True)
def dispatch_automation_triggers(self) -> dict:  # type: ignore[no-untyped-def]
    """Beat — aktif kuralların breaking kümelerine 'queued' koşum (flag-gated, idempotent)."""
    return _run_async(_dispatch_async())
