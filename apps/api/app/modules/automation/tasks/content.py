"""Otomasyon içerik işlemcisi (Faz 5.2b, #1785) — queued koşum → kaynaklı artefakt.

`queued` automation_runs'ı işler:
  1. consent kapısı (KVKK yurt-dışı LLM) — yok/iptal → 'skipped_no_consent'
  2. kota kapısı — dolu → 'skipped_quota'
  3. research_runner ile kaynaklı içerik üret (canlı SSE yolu DEĞİŞMEZ, aynı yapı-taşları)
  4. kaynaksız → 'skipped_no_sources' (#1754 artefakt YOK)
  5. artefakt (origin='automation') + kota tüket (record_usage) → koşum 'pending' (onay kuyruğu)
  hata → 'failed' (+ error).

Çift flag-gate: `automation.enabled` (master) + `automation.content.enabled`
(davranış-canary, default OFF → no-op). Kural-kurma UI'ı (5.3) henüz yok → 0 queued
koşum → zaten no-op.

automation ÜST orkestratör → generations (research_runner/artifacts) + billing (quota)
OKUR (import-linter 17. contract: automation→generations/billing izinli). Per-koşum
commit (bir koşum hatası diğerlerinin artefaktını geri almaz). Lazy import'lar.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

from sqlalchemy import text

from app.shared.runtime_config.settings_store import settings_store
from app.shared.workers.db_session import _get_session_factory, _run_async
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

CONTENT_BATCH_LIMIT = 10  # beat başına işlenecek queued koşum (LLM ağır → küçük tut)
DEFAULT_QUERY_TEMPLATE = "{cluster} son gelişmeler neden gündemde"

_BATCH_SQL = """
    SELECT r.id::text AS run_id, r.cluster_id::text AS cluster_id,
           ar.user_id::text AS user_id, ar.action_config AS action_config,
           rc.canonical_name AS cluster_name,
           u.tier AS tier, u.locale AS locale,
           u.foreign_transfer_consent_at AS consent_at,
           u.foreign_transfer_consent_revoked_at AS consent_revoked_at
    FROM automation_runs r
    JOIN automation_rules ar ON ar.id = r.rule_id
    JOIN research_clusters rc ON rc.id = r.cluster_id
    JOIN users u ON u.id = ar.user_id
    WHERE r.status = 'queued'
    ORDER BY r.created_at ASC
    LIMIT :lim
"""


def _build_query(action_config: dict | None, cluster_name: str) -> str:
    """Küme adından research sorgusu türet (kural şablonu varsa onu kullan)."""
    name = (cluster_name or "").strip()
    tmpl = (action_config or {}).get("query_template") or DEFAULT_QUERY_TEMPLATE
    try:
        q = tmpl.format(cluster=name).strip()
    except (KeyError, IndexError, ValueError):
        q = DEFAULT_QUERY_TEMPLATE.format(cluster=name)
    return q or name


async def _set_status(db, run_id: str, status: str, *, artifact_id=None, error=None) -> None:
    await db.execute(
        text(
            "UPDATE automation_runs SET status = :s, "
            "artifact_id = CAST(:a AS uuid), error = :e "
            "WHERE id = CAST(:r AS uuid)"
        ),
        {
            "s": status,
            "a": str(artifact_id) if artifact_id else None,
            "e": (error[:500] if error else None),
            "r": run_id,
        },
    )


async def _process_for_session(db, now: datetime, *, limit: int = CONTENT_BATCH_LIMIT) -> dict:
    """Çekirdek: queued koşumları işle (per-koşum commit). Flag kontrolü ÇAĞIRANDA."""
    from app.modules.billing.services.quota import get_quota_status, record_usage
    from app.modules.generations.artifacts import create_artifact_with_revision
    from app.modules.generations.research_runner import run_cluster_research

    rows = (await db.execute(text(_BATCH_SQL), {"lim": limit})).all()
    counts = {"queued": len(rows), "pending": 0, "skipped": 0, "failed": 0}
    if not rows:
        return counts

    for row in rows:
        run_id = row.run_id
        uid = uuid.UUID(row.user_id)
        # 1) consent kapısı (KVKK — yurt-dışı LLM; require_foreign_transfer_consent eşleniği)
        if row.consent_at is None or row.consent_revoked_at is not None:
            await _set_status(db, run_id, "skipped_no_consent")
            counts["skipped"] += 1
            await db.commit()
            continue
        # 2) kota kapısı (founder: kotaya tabi)
        try:
            qs = await get_quota_status(uid, row.tier or "free")
        except Exception as exc:
            # kota okunamadı (ör. Redis) → bu turda atla (geçici; 'failed' DEĞİL)
            logger.warning("automation content kota okunamadı run=%s: %s", run_id, exc)
            continue
        if qs.exceeded:
            await _set_status(db, run_id, "skipped_quota")
            counts["skipped"] += 1
            await db.commit()
            continue
        # 3) research (canlı yolla aynı yapı-taşları)
        user_obj = SimpleNamespace(id=uid, tier=row.tier or "free", locale=row.locale or "tr-TR")
        query = _build_query(row.action_config, row.cluster_name)
        try:
            result = await run_cluster_research(db, user=user_obj, query=query, now=now)
        except Exception as exc:
            logger.warning("automation content research hata run=%s: %s", run_id, exc)
            await db.rollback()
            await _set_status(db, run_id, "failed", error=str(exc))
            await db.commit()
            counts["failed"] += 1
            continue
        # 4) kaynaksız → artefakt YOK (#1754)
        if result.status != "ok" or not result.sources_used:
            await _set_status(db, run_id, "skipped_no_sources")
            counts["skipped"] += 1
            await db.commit()
            continue
        # 5) artefakt (origin='automation') + kota tüket + 'pending' (onay kuyruğu)
        try:
            art_id = await create_artifact_with_revision(
                db,
                user_id=uid,
                cluster_id=uuid.UUID(row.cluster_id),
                content=result.content,
                sources_used=result.sources_used,
                effective_query=query,
                origin="automation",
            )
            u = result.usage or {}
            await record_usage(
                db,
                user_id=uid,
                event_type="generation",
                provider=u.get("provider"),
                model=u.get("model"),
                input_tokens=u.get("input_tokens"),
                output_tokens=u.get("output_tokens"),
                cost_usd=u.get("cost_usd"),
                metadata={"source": "automation", "automation_run_id": run_id},
            )
            await _set_status(db, run_id, "pending", artifact_id=art_id)
            await db.commit()
            counts["pending"] += 1
        except Exception as exc:
            logger.warning("automation content artefakt hata run=%s: %s", run_id, exc)
            await db.rollback()
            await _set_status(db, run_id, "failed", error=str(exc))
            await db.commit()
            counts["failed"] += 1
    return counts


async def _process_async() -> dict:
    factory = _get_session_factory()
    async with factory() as db:
        if not await settings_store.get_bool(db, "automation.enabled", False):
            return {"skipped": "automation_disabled"}
        if not await settings_store.get_bool(db, "automation.content.enabled", False):
            return {"skipped": "content_disabled"}
        return await _process_for_session(db, datetime.now(UTC))


@celery_app.task(name="tasks.automation.process_content", bind=True)
def process_automation_content(self) -> dict:  # type: ignore[no-untyped-def]
    """Beat — queued koşumları kaynaklı artefakta dönüştür (flag-gated, per-koşum commit)."""
    return _run_async(_process_async())
