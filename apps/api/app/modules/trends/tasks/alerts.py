"""Trend-alert bildirim üretici (#1581 C) — kullanıcı ilgi kümeleri × breaking trend.

Kullanıcının araştırma kümesindeki (talep) bir entity haberde "Patlıyor" olunca
(arz) `user_notifications`'a bildirim yazar. İki flag-gate: `trends.enabled` +
`notifications.trend_alerts.enabled` (default OFF → canary). İdempotent: dedupe_key
`<user>:<cluster_key>:<gün>` UNIQUE → kullanıcı+küme+gün başına tek bildirim
(ON CONFLICT DO NOTHING). Cross-domain okuma (message_clusters/research_clusters)
RAW SQL → import-linter-safe. user-scoped (her kullanıcı yalnız kendi kümeleri).
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import text

from app.modules.trends.cluster_link import trend_metrics_for_clusters
from app.shared.runtime_config.settings_store import settings_store
from app.shared.workers.db_session import _get_session_factory, _run_async
from app.workers.celery_app import celery_app

# #1585: "breaking" (Patlıyor) + "developing" (Gelişiyor) — ilgi alanı belirgin
# hareketlenince bildir (korpus-üstü büyüme veya pencere-içi yükseliş). Günde-bir
# deduped (dedupe_key) → spam değil; "quiet/stable/fading" bildirmez.
ALERT_STATES = frozenset({"breaking", "developing"})
DAILY_CAP_PER_USER = 20  # güvenlik üst sınırı (dedupe zaten küme+gün başına tekler)
ALERT_WINDOW_SECONDS = 86_400  # 24s pencere


async def _detect_for_session(db, now: datetime) -> dict:
    """Çekirdek: aktif kümeler × kullanıcı → breaking olanlara bildirim (commit'siz).

    Flag kontrolü ÇAĞIRANDA (_detect_async). Test bunu doğrudan çağırır (test_db_session).
    """
    day = now.date().isoformat()

    # aktif kümeler × ilgilenen kullanıcı (RAW SQL cross-domain read)
    pairs = (
        await db.execute(
            text(
                """
                SELECT mc.user_id::text AS uid, rc.cluster_key AS ckey,
                       rc.canonical_name AS name
                FROM message_clusters mc
                JOIN research_clusters rc ON rc.id = mc.cluster_id
                WHERE rc.deprecated_at IS NULL
                GROUP BY mc.user_id, rc.cluster_key, rc.canonical_name
                """
            )
        )
    ).all()
    if not pairs:
        return {"pairs": 0, "created": 0, "users_notified": 0}

    keys = sorted({p.ckey for p in pairs})
    metrics = await trend_metrics_for_clusters(
        db, keys, window_seconds=ALERT_WINDOW_SECONDS, now=now
    )

    created = 0
    per_user: dict[str, int] = {}
    for p in pairs:
        m = metrics.get(p.ckey)
        if m is None or m.trend_state not in ALERT_STATES:
            continue
        if per_user.get(p.uid, 0) >= DAILY_CAP_PER_USER:
            continue
        res = await db.execute(
            text(
                """
                INSERT INTO user_notifications
                    (user_id, type, cluster_key, title, trend_state, article_count, dedupe_key)
                VALUES (CAST(:uid AS uuid), 'trend_alert', :ckey, :title, :state, :ac, :dk)
                ON CONFLICT (dedupe_key) DO NOTHING
                """
            ),
            {
                "uid": p.uid,
                "ckey": p.ckey,
                "title": f"{p.name} gündemde — ilgi alanın şu an öne çıkıyor",
                "state": m.trend_state,
                "ac": m.article_count,
                "dk": f"{p.uid}:{p.ckey}:{day}",
            },
        )
        if res.rowcount:
            created += 1
            per_user[p.uid] = per_user.get(p.uid, 0) + 1
    return {"pairs": len(pairs), "created": created, "users_notified": len(per_user)}


async def _detect_async() -> dict:
    factory = _get_session_factory()
    async with factory() as db:
        if not await settings_store.get_bool(db, "trends.enabled", False):
            return {"skipped": "trends_disabled"}
        if not await settings_store.get_bool(db, "notifications.trend_alerts.enabled", False):
            return {"skipped": "alerts_disabled"}
        result = await _detect_for_session(db, datetime.now(UTC))
        await db.commit()
        return result


@celery_app.task(name="tasks.trends.detect_trend_alerts", bind=True)
def detect_trend_alerts(self) -> dict:  # type: ignore[no-untyped-def]
    """Beat — kullanıcının breaking ilgi kümeleri için bildirim (flag-gated, idempotent)."""
    return _run_async(_detect_async())
