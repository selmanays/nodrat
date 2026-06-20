"""SFT artefakt-yolu curator — artifacts/artifact_revisions → training_samples (Faz 3c/1b).

Küme-bağlı artefaktların HEAD (en güncel/kabul edilen final) içeriğini cluster-anchored
SFT örneği olarak yazar: input = effective_query (initial revizyon, seq=1) + kaynaklar,
output = head içeriği. Mevcut message-yolu curator (sft_curator.py) deseni; aynı nightly
run'a entegre, sub-flag `sft.curator.artifacts.enabled` ile BAĞIMSIZ açılır/kapanır.

KAPSAM = YALNIZ SFT. Artefakt-DPO'nun (revizyon zinciri → chosen/rejected) locked kararı
YOK (wiki/decisions/dpo-rejected-samples: tek tanımlı kaynak = user halu-flag feedback) →
bu modül DPO ÜRETMEZ; açık karar (founder).

Invariant'lar (wiki/concepts/sft-data-pipeline.md):
  - `model_improvement_consent` ZORUNLU (KVKK md.5/11). consent yok/revoke → ELE.
  - review buffer (created_at < NOW - 7g) — takedown/geri-çekme penceresi.
  - PII secondary scan (defense-in-depth) → hit varsa skip.
  - `task_type='research_answer'` REUSE — artefakt içeriği research türevi; yeni task_type
    = CHECK-constraint mutation = HARD-STOP (CLAUDE.md §0), kaçınıldı. Provenance
    artifact_id/cluster_id kolonlarında ayrışır.
  - Idempotent: `uq_training_samples_artifact (artifact_id, artifact_revision_seq,
    task_type, sample_type)` partial WHERE artifact_id IS NOT NULL — INSERT ... ON
    CONFLICT DO NOTHING (atomik, race-safe; begin_nested savepoint DEĞİL).
  - `query_embedding`'e DOKUNMAZ (embedding HARD-STOP) — yalnız content okunur.
  - Self-distillation YASAK: yalnız premium (DeepSeek/Haiku) output'u. Nodrat-SLM henüz
    yok → tüm artefaktlar premium-türevi (provenance filtresi Nodrat-SLM gelince eklenir).
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pii import redact
from app.modules.sft.eligibility import SFT_REVIEW_BUFFER_DAYS
from app.modules.sft.models import TrainingSample

logger = logging.getLogger(__name__)

# REUSE — artefakt içeriği research_answer türevi; yeni task_type = HARD-STOP.
ARTIFACT_TASK_TYPE = "research_answer"
SPLIT_TRAIN_BUCKET = 80
SPLIT_VAL_BUCKET = 90

# Aday sorgu: eligible artefakt + head revizyonu + initial(effective_query) + consent +
# review-buffer + NOT EXISTS(head için sft örneği). Head soft-pointer (head_revision_id)
# ile join; initial seq=1 effective_query'yi taşır (add_revision effective_query yazmaz).
_CANDIDATES_SQL = text(
    """
    SELECT a.id AS artifact_id, a.cluster_id, a.user_id, a.artifact_type, a.created_at,
           hr.content AS head_content, hr.sources_used AS head_sources,
           hr.revision_seq AS head_seq, hr.revision_intent AS head_intent,
           hr.accepted_at AS head_accepted_at,
           ir.effective_query,
           (SELECT count(*) FROM artifact_revisions WHERE artifact_id = a.id) AS revision_count
    FROM artifacts a
    JOIN artifact_revisions hr ON hr.id = a.head_revision_id
    JOIN artifact_revisions ir ON ir.artifact_id = a.id AND ir.revision_seq = 1
    JOIN users u ON u.id = a.user_id
    WHERE u.model_improvement_consent_at IS NOT NULL
      AND u.model_improvement_consent_revoked_at IS NULL
      AND a.created_at < (NOW() - (:buffer_days * INTERVAL '1 day'))
      AND NOT EXISTS (
          SELECT 1 FROM training_samples ts
          WHERE ts.artifact_id = a.id
            AND ts.artifact_revision_seq = hr.revision_seq
            AND ts.task_type = 'research_answer'
            AND ts.sample_type = 'sft'
      )
    ORDER BY a.created_at ASC
    LIMIT :daily_max
    """
)


def _assign_split(artifact_id: Any) -> str:
    """Deterministik split (hash(artifact_id) % 100) — train/val/test idempotent."""
    h = hashlib.sha256(str(artifact_id).encode()).hexdigest()[:8]
    bucket = int(h, 16) % 100
    if bucket < SPLIT_TRAIN_BUCKET:
        return "train"
    if bucket < SPLIT_VAL_BUCKET:
        return "val"
    return "test"


def _build_input_payload(
    effective_query: str, sources_used: list | None, artifact_id: Any, cluster_id: Any
) -> dict[str, Any]:
    """ChatML input: cluster-anchored sorgu + kaynak bağlamı (message-yolu deseni)."""
    sources_block = ""
    if sources_used:
        lines: list[str] = []
        for i, s in enumerate(sources_used[:10], start=1):
            if isinstance(s, dict):
                title = s.get("title") or ""
                source = s.get("source_name") or s.get("source") or ""
                label = " — ".join(p for p in (source, title) if p)
                lines.append(f"[{i}] {label}" if label else f"[{i}]")
        if lines:
            sources_block = "\n\nKaynaklar:\n" + "\n".join(lines)
    return {
        "messages": [{"role": "user", "content": effective_query + sources_block}],
        "input_schema_version": "v3-cluster_artifact",
        "effective_query": effective_query,
        "cluster_id": str(cluster_id),
        "artifact_id": str(artifact_id),
    }


async def curate_artifacts(
    db: AsyncSession, *, daily_max: int, prompt_version: str
) -> dict[str, Any]:
    """Eligible artefakt head'lerini SFT örneği olarak yaz. commit ETMEZ (caller commit'ler).

    Her insert INSERT ... ON CONFLICT DO NOTHING ile atomik yazılır → race-duplicate
    exception fırlatmaz (tüm-transaction zehirleme riski yok). rowcount=1 ingest, 0 skip.
    """
    summary: dict[str, Any] = {
        "status": "ok",
        "scanned": 0,
        "ingested_sft": 0,
        "skipped_no_query": 0,
        "skipped_pii": 0,
        "skipped_duplicate": 0,
        "errors": 0,
    }
    rows = (
        (
            await db.execute(
                _CANDIDATES_SQL, {"buffer_days": SFT_REVIEW_BUFFER_DAYS, "daily_max": daily_max}
            )
        )
        .mappings()
        .all()
    )
    summary["scanned"] = len(rows)

    for r in rows:
        try:
            eq = (r["effective_query"] or "").strip()
            if not eq:
                # effective_query yok → temiz cluster-anchored input kurulamaz, ele.
                summary["skipped_no_query"] += 1
                continue
            head_content = r["head_content"] or ""

            # PII secondary scan (defense-in-depth) — hit → ele.
            if redact(eq + "\n" + head_content).has_pii:
                summary["skipped_pii"] += 1
                continue

            # INSERT ... ON CONFLICT DO NOTHING — atomik + race-safe. begin_nested
            # savepoint deseni kullanmadık: SQLAlchemy 2.0'da begin_nested() snapshot
            # alırken SAVEPOINT'ten ÖNCE flush eder → race-duplicate IntegrityError'ı
            # savepoint DIŞINDA patlatıp tüm transaction'ı zehirlerdi (run sıfır commit).
            # ON CONFLICT hiç exception fırlatmaz; rowcount=1 insert, 0 duplicate.
            stmt = (
                pg_insert(TrainingSample)
                .values(
                    artifact_id=r["artifact_id"],
                    artifact_revision_seq=r["head_seq"],
                    cluster_id=r["cluster_id"],
                    user_id=r["user_id"],
                    task_type=ARTIFACT_TASK_TYPE,
                    sample_type="sft",
                    prompt_version=prompt_version,
                    input_payload=_build_input_payload(
                        eq, r["head_sources"], r["artifact_id"], r["cluster_id"]
                    ),
                    output_payload={"content": head_content},
                    quality_signals={
                        "char_count": len(head_content),
                        "source_count": len(r["head_sources"]) if r["head_sources"] else 0,
                        "artifact_type": r["artifact_type"],
                        "head_intent": r["head_intent"],
                        "revision_count": int(r["revision_count"]),
                        "accepted": r["head_accepted_at"] is not None,
                        "source": "artifact",
                    },
                    sft_split=_assign_split(r["artifact_id"]),
                )
                .on_conflict_do_nothing(
                    index_elements=[
                        "artifact_id",
                        "artifact_revision_seq",
                        "task_type",
                        "sample_type",
                    ],
                    index_where=text("artifact_id IS NOT NULL"),
                )
            )
            if (await db.execute(stmt)).rowcount:
                summary["ingested_sft"] += 1
            else:
                summary["skipped_duplicate"] += 1
        except Exception as exc:
            logger.exception(
                "artifact_curator row failed: artifact=%s err=%s", r["artifact_id"], exc
            )
            summary["errors"] += 1

    logger.info("artifact_curator summary: %s", summary)
    return summary
