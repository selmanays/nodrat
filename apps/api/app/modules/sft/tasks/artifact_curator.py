"""SFT/DPO artefakt-yolu curator — artifacts/artifact_revisions → training_samples (Faz 3c/1b).

Küme-bağlı artefaktların HEAD (en güncel/kabul edilen final) içeriğini cluster-anchored
SFT örneği olarak yazar: input = effective_query (initial revizyon, seq=1) + kaynaklar,
output = head içeriği. Mevcut message-yolu curator (sft_curator.py) deseni; aynı nightly
run'a entegre, sub-flag `sft.curator.artifacts.enabled` ile BAĞIMSIZ açılır/kapanır.

DPO (Faz 3c, founder kararı 2026-06-20 — KONSERVATİF): yalnız MANUEL-EDIT revizyonlarından
(`freetext`/`edit` = kullanıcı LLM çıktısını elle düzeltti) + ANLAMLI değişim (difflib
similarity < 0.95) tercih çifti üretir: chosen = head (düzeltilmiş), rejected = parent
(düzeltmeden önce). Quick-action reshape'leri (shorter/longer/rewrite/multi_share) tercih
sinyali DEĞİL → DPO ÜRETMEZ (yalnız SFT). Mevcut halu-flag DPO'nun "user-correction=tercih"
semantiğini izler (wiki/decisions/artifact-edit-dpo).

Invariant'lar (wiki/concepts/sft-data-pipeline.md):
  - `model_improvement_consent` ZORUNLU (KVKK md.5/11). consent yok/revoke → ELE.
  - review buffer (created_at < NOW - 7g) — takedown/geri-çekme penceresi.
  - PII secondary scan (defense-in-depth) → hit varsa skip (head + parent ayrı taranır).
  - `task_type='research_answer'` REUSE — artefakt içeriği research türevi; yeni task_type
    = CHECK-constraint mutation = HARD-STOP (CLAUDE.md §0), kaçınıldı. Provenance
    artifact_id/cluster_id kolonlarında ayrışır.
  - Idempotent: `uq_training_samples_artifact (artifact_id, artifact_revision_seq,
    task_type, sample_type)` partial — INSERT ... ON CONFLICT DO NOTHING (atomik, race-safe).
  - `query_embedding`'e DOKUNMAZ (embedding HARD-STOP) — yalnız content okunur.
  - Self-distillation YASAK: yalnız premium (DeepSeek/Haiku) output'u. Nodrat-SLM henüz
    yok → tüm artefaktlar premium-türevi (provenance filtresi Nodrat-SLM gelince eklenir).
"""

from __future__ import annotations

import hashlib
import logging
from difflib import SequenceMatcher
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

# DPO yalnız MANUEL-EDIT revizyonlarından (kullanıcı içeriği elle düzeltti = güçlü tercih).
# Quick-action reshape'leri (shorter/longer/...) tercih sinyali DEĞİL → SFT-only.
MANUAL_EDIT_INTENTS = frozenset({"freetext", "edit"})
# DPO için parent→head arasında en az %5 içerik değişimi (difflib). Küçük tweak
# (typo fix) parent'ı "rejected" yapmaz (SFT edit_distance<0.05 eşiğinin ayna karşılığı).
_DPO_MIN_CHANGE = 0.05

# Aday sorgu: eligible artefakt + head revizyonu + parent (DPO) + initial(effective_query)
# + consent + review-buffer + NOT EXISTS(head için sft örneği). Head soft-pointer
# (head_revision_id) ile join; initial seq=1 effective_query'yi taşır.
_CANDIDATES_SQL = text(
    """
    SELECT a.id AS artifact_id, a.cluster_id, a.user_id, a.artifact_type, a.created_at,
           hr.content AS head_content, hr.sources_used AS head_sources,
           hr.revision_seq AS head_seq, hr.revision_intent AS head_intent,
           hr.accepted_at AS head_accepted_at,
           pr.content AS parent_content, pr.revision_seq AS parent_seq,
           ir.effective_query,
           (SELECT count(*) FROM artifact_revisions WHERE artifact_id = a.id) AS revision_count
    FROM artifacts a
    JOIN artifact_revisions hr ON hr.id = a.head_revision_id
    LEFT JOIN artifact_revisions pr ON pr.id = hr.parent_revision_id
    JOIN artifact_revisions ir ON ir.artifact_id = a.id AND ir.revision_seq = 1
    JOIN users u ON u.id = a.user_id
    WHERE u.model_improvement_consent_at IS NOT NULL
      AND u.model_improvement_consent_revoked_at IS NULL
      AND a.created_at < (NOW() - (:buffer_days * INTERVAL '1 day'))
      AND (
          -- SFT henüz yoksa işle
          NOT EXISTS (
              SELECT 1 FROM training_samples ts
              WHERE ts.artifact_id = a.id AND ts.artifact_revision_seq = hr.revision_seq
                AND ts.task_type = 'research_answer' AND ts.sample_type = 'sft'
          )
          -- VEYA: manuel-edit head'de SFT var ama dpo_chosen yoksa yeniden dahil et
          -- (SFT yazılıp DPO transient fail ettiyse pair kalıcı kaybolmasın; SFT
          --  re-insert'i ON CONFLICT ile no-op). Quick-action head'de DPO beklenmez.
          OR (
              hr.revision_intent IN ('freetext', 'edit')
              AND NOT EXISTS (
                  SELECT 1 FROM training_samples ts2
                  WHERE ts2.artifact_id = a.id AND ts2.artifact_revision_seq = hr.revision_seq
                    AND ts2.task_type = 'research_answer' AND ts2.sample_type = 'dpo_chosen'
              )
          )
      )
    ORDER BY a.created_at ASC
    LIMIT :daily_max
    """
)


def _assign_split(artifact_id: Any) -> str:
    """Deterministik split (hash(artifact_id) % 100) — train/val/test idempotent.

    Bir artefaktın TÜM örnekleri (sft + dpo_chosen + dpo_rejected) aynı split'e düşer."""
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
    """ChatML input: cluster-anchored sorgu + kaynak bağlamı (message-yolu deseni).

    DPO çiftinde chosen ve rejected AYNI input'u paylaşır (yalnız output farklı)."""
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


async def _upsert_sample(db: AsyncSession, values: dict[str, Any]) -> bool:
    """INSERT ... ON CONFLICT DO NOTHING — atomik + race-safe (begin_nested DEĞİL;
    SQLAlchemy 2.0'da savepoint'ten önce flush eder → race IntegrityError tüm
    transaction'ı zehirlerdi). Dönüş: True=insert, False=duplicate."""
    stmt = (
        pg_insert(TrainingSample)
        .values(**values)
        .on_conflict_do_nothing(
            index_elements=["artifact_id", "artifact_revision_seq", "task_type", "sample_type"],
            index_where=text("artifact_id IS NOT NULL"),
        )
    )
    return bool((await db.execute(stmt)).rowcount)


async def curate_artifacts(
    db: AsyncSession, *, daily_max: int, prompt_version: str
) -> dict[str, Any]:
    """Eligible artefakt head'lerini SFT (+ manuel-edit DPO çifti) olarak yaz.

    commit ETMEZ (caller commit'ler). Her insert ON CONFLICT DO NOTHING (race-safe).
    """
    summary: dict[str, Any] = {
        "status": "ok",
        "scanned": 0,
        "ingested_sft": 0,
        "ingested_dpo_chosen": 0,
        "ingested_dpo_rejected": 0,
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

            # PII secondary scan (defense-in-depth) — hit → ele (SFT + DPO ikisi de).
            if redact(eq + "\n" + head_content).has_pii:
                summary["skipped_pii"] += 1
                continue

            aid = r["artifact_id"]
            split = _assign_split(aid)
            input_payload = _build_input_payload(eq, r["head_sources"], aid, r["cluster_id"])
            base = {
                "artifact_id": aid,
                "cluster_id": r["cluster_id"],
                "user_id": r["user_id"],
                "task_type": ARTIFACT_TASK_TYPE,
                "prompt_version": prompt_version,
                "input_payload": input_payload,
                "sft_split": split,
            }
            head_qs = {
                "char_count": len(head_content),
                "source_count": len(r["head_sources"]) if r["head_sources"] else 0,
                "artifact_type": r["artifact_type"],
                "head_intent": r["head_intent"],
                "revision_count": int(r["revision_count"]),
                "accepted": r["head_accepted_at"] is not None,
                "source": "artifact",
            }

            # 1) SFT — head = kabul edilen final çıktı (her zaman).
            if await _upsert_sample(
                db,
                {
                    **base,
                    "artifact_revision_seq": r["head_seq"],
                    "sample_type": "sft",
                    "output_payload": {"content": head_content},
                    "quality_signals": head_qs,
                },
            ):
                summary["ingested_sft"] += 1
            else:
                summary["skipped_duplicate"] += 1

            # 2) DPO çifti — YALNIZ manuel-edit (freetext/edit) + anlamlı değişim.
            parent_content = r["parent_content"]
            if (
                r["head_intent"] in MANUAL_EDIT_INTENTS
                and parent_content
                and r["parent_seq"] is not None
            ):
                similarity = SequenceMatcher(None, parent_content, head_content).ratio()
                # Küçük tweak parent'ı "rejected" yapmaz; parent PII'liyse çift atlanır.
                # (eq + head zaten yukarıda PII-tarandı; burada yalnız parent gövdesi.)
                if (1.0 - similarity) >= _DPO_MIN_CHANGE and not redact(parent_content).has_pii:
                    pair_qs = {"dpo_pair_with": str(aid), "edit_similarity": round(similarity, 3)}
                    # chosen = head (kullanıcının elle düzelttiği = tercih edilen)
                    if await _upsert_sample(
                        db,
                        {
                            **base,
                            "artifact_revision_seq": r["head_seq"],
                            "sample_type": "dpo_chosen",
                            "output_payload": {"content": head_content},
                            "quality_signals": {**head_qs, **pair_qs},
                        },
                    ):
                        summary["ingested_dpo_chosen"] += 1
                    # rejected = parent (düzeltmeden önceki = reddedilen)
                    if await _upsert_sample(
                        db,
                        {
                            **base,
                            "artifact_revision_seq": r["parent_seq"],
                            "sample_type": "dpo_rejected",
                            "output_payload": {"content": parent_content},
                            "quality_signals": {
                                "char_count": len(parent_content),
                                "source": "artifact",
                                **pair_qs,
                            },
                        },
                    ):
                        summary["ingested_dpo_rejected"] += 1
        except Exception as exc:  # tek satır hatası tüm run'ı düşürmesin
            logger.exception(
                "artifact_curator row failed: artifact=%s err=%s", r["artifact_id"], exc
            )
            summary["errors"] += 1

    logger.info("artifact_curator summary: %s", summary)
    return summary
