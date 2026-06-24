"""Küme birleştirme + canonical-demirleme reconcile (#1742, PR-2).

`merge_clusters`: iki research_cluster'ı tek düğümde birleştirir — bağımlı kayıtları
(artifacts · message_clusters · user_cluster_subscriptions · parent_cluster_id) hedefe
REPARENT eder, kaynağı SOFT-DEPRECATE eder (RESTRICT FK korunur → kaynak SİLİNMEZ).
Tek transaction (commit caller'da), idempotent (deprecated kaynak → no-op).

`find_drift_candidates`: aktif kümeleri canonical_id'ye çözüp >=2 olan grupları döndürür
(salt-okuma; #1740 cluster_key drift'inin tespiti).

`reconcile_canonical_anchors`: NULL canonical_id backfill + drift gruplarını tek hedefe
merge. dry_run=True → yalnız rapor (mutation YOK).

Tasarım: training_samples.cluster_id IMMUTABLE (history-safety) → DOKUNULMAZ. Çakışmalar:
message_clusters UNIQUE(message_id,cluster_id) → çakışmayanı taşı/çakışanı düşür;
user_cluster_subscriptions partial-unique(user_id,cluster_id WHERE unsubscribed_at IS NULL)
→ live'ı taşı (hedefte live yoksa)/kalan live'ı soft-unsub (opt-out izi korunur).
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.research_clustering import canonical_cluster_key


async def merge_clusters(db: AsyncSession, source_id: str, target_id: str) -> dict:
    """source kümesini target'a birleştir. Dönüş: özet dict (status: ok|noop|error).

    commit ETMEZ (caller commit'ler). Idempotent: source zaten deprecated → noop.
    """
    s, t = str(source_id), str(target_id)
    if s == t:
        return {"status": "noop", "reason": "source==target"}

    src = (
        await db.execute(
            text("SELECT cluster_key, deprecated_at FROM research_clusters WHERE id = :s"),
            {"s": s},
        )
    ).first()
    tgt = (
        await db.execute(
            text("SELECT id FROM research_clusters WHERE id = :t AND deprecated_at IS NULL"),
            {"t": t},
        )
    ).first()
    if src is None:
        return {"status": "error", "reason": "source yok"}
    if tgt is None:
        return {"status": "error", "reason": "target yok ya da deprecated"}
    if src.deprecated_at is not None:
        return {"status": "noop", "reason": "source zaten deprecated"}

    summary: dict = {"status": "ok", "source": s, "target": t}

    # 1) artifacts — unique kısıt yok, düz reparent
    r = await db.execute(
        text("UPDATE artifacts SET cluster_id = :t WHERE cluster_id = :s"), {"t": t, "s": s}
    )
    summary["artifacts"] = r.rowcount or 0

    # 2) message_clusters — UNIQUE(message_id, cluster_id): çakışmayanı taşı, çakışanı sil
    r = await db.execute(
        text(
            "UPDATE message_clusters SET cluster_id = :t WHERE cluster_id = :s "
            "AND NOT EXISTS (SELECT 1 FROM message_clusters m2 "
            "WHERE m2.message_id = message_clusters.message_id AND m2.cluster_id = :t)"
        ),
        {"t": t, "s": s},
    )
    summary["messages_moved"] = r.rowcount or 0
    r = await db.execute(text("DELETE FROM message_clusters WHERE cluster_id = :s"), {"s": s})
    summary["messages_dropped_dup"] = r.rowcount or 0

    # 3) user_cluster_subscriptions — partial-unique(user_id,cluster_id WHERE unsubscribed_at
    #    IS NULL): live'ı taşı (hedefte live yoksa); kalan live'ı soft-unsub (opt-out izi).
    r = await db.execute(
        text(
            "UPDATE user_cluster_subscriptions SET cluster_id = :t, updated_at = NOW() "
            "WHERE cluster_id = :s AND unsubscribed_at IS NULL "
            "AND NOT EXISTS (SELECT 1 FROM user_cluster_subscriptions s2 "
            "WHERE s2.user_id = user_cluster_subscriptions.user_id "
            "AND s2.cluster_id = :t AND s2.unsubscribed_at IS NULL)"
        ),
        {"t": t, "s": s},
    )
    summary["subs_moved"] = r.rowcount or 0
    r = await db.execute(
        text(
            "UPDATE user_cluster_subscriptions SET status = 'unsubscribed', "
            "unsubscribed_at = NOW(), updated_at = NOW() "
            "WHERE cluster_id = :s AND unsubscribed_at IS NULL"
        ),
        {"s": s},
    )
    summary["subs_closed_dup"] = r.rowcount or 0

    # 4) parent_cluster_id — alt kümeleri hedefe reparent
    r = await db.execute(
        text("UPDATE research_clusters SET parent_cluster_id = :t WHERE parent_cluster_id = :s"),
        {"t": t, "s": s},
    )
    summary["children_reparented"] = r.rowcount or 0

    # 4b) artifact_clusters (#1762) — UNIQUE(artifact_id,cluster_id): çakışmayanı taşı,
    #     çakışanı sil (message_clusters deseni; artefakt zaten hedefte üye → dup düşer).
    r = await db.execute(
        text(
            "UPDATE artifact_clusters SET cluster_id = :t WHERE cluster_id = :s "
            "AND NOT EXISTS (SELECT 1 FROM artifact_clusters a2 "
            "WHERE a2.artifact_id = artifact_clusters.artifact_id AND a2.cluster_id = :t)"
        ),
        {"t": t, "s": s},
    )
    summary["artifact_memberships_moved"] = r.rowcount or 0
    r = await db.execute(text("DELETE FROM artifact_clusters WHERE cluster_id = :s"), {"s": s})
    summary["artifact_memberships_dropped_dup"] = r.rowcount or 0

    # 4c) role INVARIANT'ını koru (#1762): junction role = 'primary' ⇔ cluster_id ==
    #     artifacts.cluster_id. Adım-1 birincil pointer'ı S→T taşıdı; eğer artefakt
    #     hedefe zaten 'secondary' üyeyse adım-4b primary satırı (S) dedup'la düşürdü →
    #     hayatta kalan (T) satır 'secondary' kalırdı (bayat role). Bunu 'primary'ye
    #     yükselt → role her okuyucu için (feed CASE + history) kanonik kalır.
    r = await db.execute(
        text(
            "UPDATE artifact_clusters ac SET role = 'primary' FROM artifacts a "
            "WHERE ac.artifact_id = a.id AND ac.cluster_id = :t AND a.cluster_id = :t "
            "AND ac.role <> 'primary'"
        ),
        {"t": t},
    )
    summary["artifact_roles_promoted"] = r.rowcount or 0

    # 5) training_samples.cluster_id IMMUTABLE (history-safety) → DOKUNULMAZ.

    # 6) source key'i hedef aliases'e iz + source soft-deprecate
    await db.execute(
        text(
            "UPDATE research_clusters SET aliases = "
            "COALESCE(aliases, '[]'::jsonb) || jsonb_build_array(CAST(:k AS text)), "
            "updated_at = NOW() WHERE id = :t"
        ),
        {"t": t, "k": src.cluster_key},
    )
    await db.execute(
        text("UPDATE research_clusters SET deprecated_at = NOW() WHERE id = :s"), {"s": s}
    )
    summary["source_deprecated"] = True
    return summary


async def _cluster_key_to_canonical(db: AsyncSession) -> dict[str, str]:
    """{cluster_key → canonical_id}: her canonical + alias yüzey-formunun key'ini eşle.
    Canonical-key, alias-key'i geçer (setdefault canonical önce)."""
    key2cid: dict[str, str] = {}
    canon = (
        await db.execute(
            text("SELECT id, entity_type, canonical_normalized FROM canonical_entities")
        )
    ).all()
    for c in canon:
        try:
            key2cid.setdefault(
                canonical_cluster_key(c.entity_type, c.canonical_normalized), str(c.id)
            )
        except ValueError:  # pragma: no cover
            continue
    aliases = (
        await db.execute(
            text("SELECT alias_normalized, entity_type, canonical_id FROM entity_aliases")
        )
    ).all()
    for a in aliases:
        try:
            key2cid.setdefault(
                canonical_cluster_key(a.entity_type, a.alias_normalized), str(a.canonical_id)
            )
        except ValueError:  # pragma: no cover
            continue
    return key2cid


async def _active_clusters_by_canonical(db: AsyncSession):
    """Aktif kümeleri canonical_id'ye grupla (canonical_entity_id varsa onu, yoksa
    key→canonical eşlemesini kullan). Dönüş: {cid: [row,...]} + null-cid backfill listesi."""
    key2cid = await _cluster_key_to_canonical(db)
    rows = (
        await db.execute(
            text(
                "SELECT id, cluster_key, canonical_entity_id, created_at, "
                "(SELECT count(*) FROM user_cluster_subscriptions s "
                " WHERE s.cluster_id = rc.id AND s.unsubscribed_at IS NULL) AS subs, "
                "(SELECT count(*) FROM artifacts a WHERE a.cluster_id = rc.id) AS arts "
                "FROM research_clusters rc WHERE deprecated_at IS NULL"
            )
        )
    ).all()
    groups: dict[str, list] = {}
    for r in rows:
        cid = str(r.canonical_entity_id) if r.canonical_entity_id else key2cid.get(r.cluster_key)
        if cid:
            groups.setdefault(cid, []).append(r)
    return groups


async def find_drift_candidates(db: AsyncSession) -> list[dict]:
    """Aynı canonical'a düşen >=2 aktif küme grupları (salt-okuma)."""
    groups = await _active_clusters_by_canonical(db)
    out: list[dict] = []
    for cid, members in groups.items():
        if len(members) < 2:
            continue
        out.append(
            {
                "canonical_id": cid,
                "clusters": [
                    {
                        "id": str(m.id),
                        "cluster_key": m.cluster_key,
                        "subs": int(m.subs),
                        "arts": int(m.arts),
                        "created_at": m.created_at.isoformat(),
                    }
                    for m in sorted(members, key=lambda x: x.created_at)
                ],
            }
        )
    return out


def _pick_target(members: list):
    """Birleştirme hedefi: en çok kullanılan (subs+arts), eşitlikte en eski."""
    return sorted(members, key=lambda m: (-(int(m.subs) + int(m.arts)), m.created_at))[0]


async def reconcile_canonical_anchors(
    db: AsyncSession, *, dry_run: bool = True, limit: int = 1000
) -> dict:
    """NULL canonical_id backfill + drift gruplarını tek hedefe merge.

    dry_run=True → mutation YOK, yalnız plan. False → uygular + commit.
    """
    groups = await _active_clusters_by_canonical(db)
    merges: list[tuple[str, str]] = []  # (source, target)
    survivors: dict[str, str] = {}  # target_id → cid (merge sonrası backfill için)
    backfill: list[tuple[str, str]] = []  # (cluster_id, cid) — tekil/zaten-tek kümeler

    for cid, members in groups.items():
        if len(members) >= 2:
            target = _pick_target(members)
            survivors[str(target.id)] = cid
            for m in members:
                if str(m.id) != str(target.id):
                    merges.append((str(m.id), str(target.id)))
        else:
            m = members[0]
            if m.canonical_entity_id is None:
                backfill.append((str(m.id), cid))

    summary = {
        "dry_run": dry_run,
        "drift_groups": sum(1 for v in groups.values() if len(v) >= 2),
        "merge_count": len(merges),
        "backfill_count": len(backfill) + len(survivors),
    }
    if dry_run:
        summary["merges"] = merges[:limit]
        summary["backfill_singletons"] = backfill[:limit]
        return summary

    for source, target in merges:
        await merge_clusters(db, source, target)
    # merge sonrası hayatta kalan hedefler + tekil kümeler → canonical_id backfill
    for cluster_id, cid in [*backfill, *survivors.items()]:
        await db.execute(
            text(
                "UPDATE research_clusters SET canonical_entity_id = :c, updated_at = NOW() "
                "WHERE id = :i AND canonical_entity_id IS NULL AND deprecated_at IS NULL"
            ),
            {"c": cid, "i": cluster_id},
        )
    await db.commit()
    return summary
