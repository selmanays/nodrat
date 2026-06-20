"""Küme abonelik servisi — Faz 2 (küme-merkezli abonelik vizyonu).

Kullanıcı↔küme AÇIK abonelik yazma. Auto-subscribe `cluster_assigner` gece
batch'inden (yalnız `via='entity'` — yüksek-güven, haber-korpusu entity çapası;
noise zaten `_ENTITY_DF_SQL` person/org/place/event filtresiyle elenir) ve
`subscriptions.auto.enabled` flag ardından tetiklenir. Sıcak üretim akışına
(app_research_stream) DOKUNMAZ → latency yok.

Okuma yolu (/app/me) + unsubscribe endpoint + alert subscription-gate = Faz 2b.

Karar: birim = ResearchCluster (Faz 0). Sahiplik = generations modülü.
"""

from __future__ import annotations

import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def auto_subscribe(
    db: AsyncSession,
    user_id: uuid.UUID,
    cluster_id: uuid.UUID,
    *,
    source: str = "auto_query",
) -> bool:
    """Kullanıcıyı kümeye otomatik abone et — yeni satır oluştuysa True.

    Önceki "abonelikten çık"a SAYGI: kullanıcının o küme için HERHANGİ bir
    abonelik satırı (canlı VEYA unsubscribed) varsa eklemez → opt-out kalıcıdır,
    tekrar sorgulamak yeniden abone yapmaz. Idempotent (NOT EXISTS).

    NOT: commit ETMEZ — INSERT'i execute eder, transaction yönetimi caller'da
    (cluster_assigner başarıda commit eder; test fixture per-test rollback).

    NOT EXISTS opt-out semantiğini KORUR (canlı/unsubscribed herhangi satır →
    eklemez); ON CONFLICT ... DO NOTHING ise eşzamanlı iki istek arası yarışı
    güvenli kapatır (NOT EXISTS partial-unique `uq_user_cluster_sub_live`'a
    karşı atomik değil — sıcak yol + gece batch çakışabilir). Çakışmada hata
    yerine rowcount=0 → False.
    """
    res = await db.execute(
        text(
            """
            INSERT INTO user_cluster_subscriptions (user_id, cluster_id, status, source)
            SELECT :u, :c, 'active', :src
            WHERE NOT EXISTS (
                SELECT 1 FROM user_cluster_subscriptions
                WHERE user_id = :u AND cluster_id = :c
            )
            ON CONFLICT (user_id, cluster_id) WHERE unsubscribed_at IS NULL
            DO NOTHING
            """
        ),
        {"u": user_id, "c": cluster_id, "src": source},
    )
    return res.rowcount > 0


async def unsubscribe(
    db: AsyncSession,
    user_id: uuid.UUID,
    cluster_id: uuid.UUID,
) -> bool:
    """Canlı aboneliği soft-kapat — satır SİLİNMEZ (opt-out kalıcı + KVKK iz).

    `status='unsubscribed'` + `unsubscribed_at=NOW()`. Canlı abonelik yoksa
    no-op (zaten çıkılmış/hiç abone değil). Kapanan satır varsa True.
    NOT: commit ETMEZ — transaction yönetimi caller'da.
    """
    res = await db.execute(
        text(
            """
            UPDATE user_cluster_subscriptions
            SET status = 'unsubscribed', unsubscribed_at = NOW(), updated_at = NOW()
            WHERE user_id = :u AND cluster_id = :c AND unsubscribed_at IS NULL
            """
        ),
        {"u": user_id, "c": cluster_id},
    )
    return res.rowcount > 0
