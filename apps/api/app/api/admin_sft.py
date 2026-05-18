"""Admin SFT data pipeline dashboard backend (#569).

docs/engineering/api-contracts.md §6 (admin endpoints)
wiki/concepts/sft-data-pipeline.md (pipeline mimarisi)
wiki/decisions/own-slm-strategy.md (locked karar)

5 endpoint:
    GET  /admin/sft/stats              — özet (toplam, daily rate, distribution, quality)
    GET  /admin/sft/recent             — son 50 sample preview
    POST /admin/sft/export             — JSONL streaming response (ChatML)
    POST /admin/sft/recompute-eligibility — admin manuel trigger
    GET  /admin/sft/consent-stats      — opt-in / opt-out / revoke breakdown

Auth: super_admin role only (require_admin dependency).
Audit: her admin action admin_audit_log'a yazılır.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import Float, Integer, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import get_client_ip, require_admin

# S1E (#800): Generation tablosu DROP edildi. Eligibility ve scan
# artık messages tablosundan beslenir.
from app.models.conversation import Conversation, Message
from app.models.job import AdminAuditLog
from app.models.training_sample import TrainingSample
from app.models.user import User
from app.workers.tasks.sft_curator import run_sft_curator

logger = logging.getLogger(__name__)
router = APIRouter()


# =============================================================================
# Schemas
# =============================================================================


class SFTStatsResponse(BaseModel):
    """GET /admin/sft/stats response."""

    total_samples: int
    by_task_type: dict[str, int]
    by_sample_type: dict[str, int]  # S1E (#800): sft|dpo_chosen|dpo_rejected
    by_split: dict[str, int]
    daily_curated: list[dict[str, Any]]  # [{date: 'YYYY-MM-DD', count: N}, ...]
    quality_p50_edit_distance: float | None
    quality_p50_char_count: int | None
    eligible_pending: int  # messages.sft_eligible OR dpo_rejected henüz curated değil
    excluded_breakdown: dict[str, int]
    dpo_pair_complete: int  # S1E (#800): chosen+rejected aynı message için


class SFTRecentSample(BaseModel):
    """GET /admin/sft/recent item — preview (sansürlü)."""

    id: str
    generation_id: str | None  # S1E (#800): legacy nullable
    message_id: str | None  # S1E (#800): chat-derived sample
    sample_type: str  # 'sft' | 'dpo_chosen' | 'dpo_rejected'
    task_type: str
    sft_split: str
    edit_distance: float | None
    char_count: int | None
    curated_at: datetime
    exported_at: datetime | None
    input_preview: str
    output_preview: str


class SFTExportRequest(BaseModel):
    """POST /admin/sft/export body."""

    task_type: str = Field(default="content_generator", max_length=32)
    sft_split: str | None = Field(
        default=None,
        description="Null ise tüm split'ler. 'train'|'val'|'test' filtreler.",
    )
    format: str = Field(default="chatml", description="'chatml' (ileride: 'alpaca')")
    mark_exported: bool = Field(
        default=True,
        description="True ise her sample için exported_at NOW() set edilir.",
    )


class ConsentStatsResponse(BaseModel):
    """GET /admin/sft/consent-stats response."""

    total_users: int
    opted_in: int  # consent_at NOT NULL AND revoked_at NULL
    opted_in_revoked: int  # consent_at NOT NULL AND revoked_at NOT NULL
    never_opted_in: int  # consent_at NULL


class RecomputeEligibilityResponse(BaseModel):
    """POST /admin/sft/recompute-eligibility response."""

    scanned: int
    became_eligible: int
    became_ineligible: int


class TriggerRunResponse(BaseModel):
    """POST /admin/sft/run response — manual ETL tetikleme."""

    task_id: str
    queued: bool
    note: str


# =============================================================================
# GET /admin/sft/stats
# =============================================================================


@router.get(
    "/stats",
    response_model=SFTStatsResponse,
    summary="SFT pipeline özet istatistikler",
)
async def sft_stats(
    user: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    days: Annotated[int, Query(ge=1, le=365)] = 30,
) -> SFTStatsResponse:
    total = (await db.execute(select(func.count()).select_from(TrainingSample))).scalar_one()

    rows_task = (
        await db.execute(
            select(TrainingSample.task_type, func.count()).group_by(TrainingSample.task_type)
        )
    ).all()
    by_task_type = {row[0]: row[1] for row in rows_task}

    # S1E (#800): sample_type breakdown — sft / dpo_chosen / dpo_rejected
    rows_sample_type = (
        await db.execute(
            select(TrainingSample.sample_type, func.count()).group_by(TrainingSample.sample_type)
        )
    ).all()
    by_sample_type = {row[0]: row[1] for row in rows_sample_type}

    rows_split = (
        await db.execute(
            select(TrainingSample.sft_split, func.count()).group_by(TrainingSample.sft_split)
        )
    ).all()
    by_split = {row[0]: row[1] for row in rows_split}

    cutoff = datetime.now(UTC) - timedelta(days=days)
    rows_daily = (
        await db.execute(
            select(
                func.date(TrainingSample.curated_at).label("d"),
                func.count(),
            )
            .where(TrainingSample.curated_at >= cutoff)
            .group_by("d")
            .order_by("d")
        )
    ).all()
    daily_curated = [{"date": row[0].isoformat(), "count": row[1]} for row in rows_daily]

    p50_edit = (
        await db.execute(
            select(
                func.percentile_cont(0.5).within_group(
                    TrainingSample.quality_signals["edit_distance"].astext.cast(Float)
                )
            ).where(TrainingSample.quality_signals["edit_distance"].astext.is_not(None))
        )
    ).scalar()

    p50_char = (
        await db.execute(
            select(
                func.percentile_cont(0.5).within_group(
                    TrainingSample.quality_signals["char_count"].astext.cast(Integer)
                )
            )
        )
    ).scalar()

    # S1E (#800): eligible pending — messages.sft_eligible=true henüz curated edilmemiş
    eligible_pending_q = (
        select(func.count())
        .select_from(Message)
        .where(
            Message.role == "assistant",
            (Message.sft_eligible.is_(True)) | (Message.dpo_rejected.is_(True)),
            ~Message.id.in_(
                select(TrainingSample.message_id).where(
                    TrainingSample.message_id.is_not(None),
                )
            ),
        )
    )
    eligible_pending = (await db.execute(eligible_pending_q)).scalar_one()

    rows_excluded = (
        await db.execute(
            select(Message.sft_excluded_reason, func.count())
            .where(
                Message.role == "assistant",
                Message.sft_excluded_reason.is_not(None),
            )
            .group_by(Message.sft_excluded_reason)
        )
    ).all()
    excluded_breakdown = {row[0]: row[1] for row in rows_excluded}

    # S1E (#800): DPO pair completeness — message için hem chosen hem rejected var
    dpo_pair_complete_q = select(func.count(func.distinct(TrainingSample.message_id))).where(
        TrainingSample.message_id.is_not(None),
        TrainingSample.sample_type == "dpo_rejected",
        TrainingSample.message_id.in_(
            select(TrainingSample.message_id).where(
                TrainingSample.sample_type == "dpo_chosen",
            )
        ),
    )
    dpo_pair_complete = (await db.execute(dpo_pair_complete_q)).scalar_one()

    return SFTStatsResponse(
        total_samples=total,
        by_task_type=by_task_type,
        by_sample_type=by_sample_type,
        by_split=by_split,
        daily_curated=daily_curated,
        quality_p50_edit_distance=(float(p50_edit) if p50_edit is not None else None),
        quality_p50_char_count=(int(p50_char) if p50_char is not None else None),
        eligible_pending=eligible_pending,
        excluded_breakdown=excluded_breakdown,
        dpo_pair_complete=dpo_pair_complete,
    )


# =============================================================================
# GET /admin/sft/recent
# =============================================================================


@router.get(
    "/recent",
    response_model=list[SFTRecentSample],
    summary="Son curated sample'lar (preview)",
)
async def sft_recent(
    user: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[SFTRecentSample]:
    rows = (
        (
            await db.execute(
                select(TrainingSample).order_by(TrainingSample.curated_at.desc()).limit(limit)
            )
        )
        .scalars()
        .all()
    )

    return [_to_recent(s) for s in rows]


def _to_recent(sample: TrainingSample) -> SFTRecentSample:
    """ORM → preview shape (kullanıcı içeriği kısaltılır)."""
    inp = sample.input_payload or {}
    out = sample.output_payload or {}
    qs = sample.quality_signals or {}

    user_msg = ""
    for m in inp.get("messages", []):
        if isinstance(m, dict) and m.get("role") == "user":
            user_msg = str(m.get("content", ""))[:240]
            break

    assistant_msg = ""
    for m in out.get("messages", []):
        if isinstance(m, dict) and m.get("role") == "assistant":
            assistant_msg = str(m.get("content", ""))[:240]
            break

    edit_dist = qs.get("edit_distance")
    return SFTRecentSample(
        id=str(sample.id),
        generation_id=(str(sample.generation_id) if sample.generation_id else None),
        message_id=(str(sample.message_id) if sample.message_id else None),
        sample_type=sample.sample_type,
        task_type=sample.task_type,
        sft_split=sample.sft_split,
        edit_distance=(float(edit_dist) if edit_dist is not None else None),
        char_count=qs.get("char_count"),
        curated_at=sample.curated_at,
        exported_at=sample.exported_at,
        input_preview=user_msg,
        output_preview=assistant_msg,
    )


# =============================================================================
# POST /admin/sft/export — JSONL streaming
# =============================================================================


async def _export_jsonl_stream(
    db: AsyncSession,
    payload: SFTExportRequest,
    actor_id: UUID,
):
    """Async generator — chunked JSONL streaming (memory safe)."""
    stmt = select(TrainingSample).where(TrainingSample.task_type == payload.task_type)
    if payload.sft_split is not None:
        stmt = stmt.where(TrainingSample.sft_split == payload.sft_split)
    stmt = stmt.order_by(TrainingSample.curated_at.asc())

    exported_ids: list[UUID] = []
    chunk_count = 0

    result = await db.execute(stmt)
    for row in result.scalars():
        record = {
            "messages": (row.input_payload or {}).get("messages", [])
            + (row.output_payload or {}).get("messages", []),
            "metadata": {
                "training_sample_id": str(row.id),
                "generation_id": (str(row.generation_id) if row.generation_id else None),
                "message_id": (str(row.message_id) if row.message_id else None),
                "sample_type": row.sample_type,
                "task_type": row.task_type,
                "prompt_version": row.prompt_version,
                "sft_split": row.sft_split,
                "quality_signals": row.quality_signals,
                "curated_at": row.curated_at.isoformat(),
            },
        }
        if row.edited_output:
            record["metadata"]["edited_output_present"] = True

        yield (json.dumps(record, ensure_ascii=False) + "\n").encode("utf-8")
        chunk_count += 1
        exported_ids.append(row.id)

    # Mark exported_at after stream
    if payload.mark_exported and exported_ids:
        now = datetime.now(UTC)
        # Chunk update'ler — single UPDATE de yapılabilir, batch güvenli
        await db.execute(
            update(TrainingSample)
            .where(TrainingSample.id.in_(exported_ids))
            .values(exported_at=now)
        )
        # Audit
        db.add(
            AdminAuditLog(
                actor_id=actor_id,
                action="sft.export",
                target_type="training_samples",
                event_metadata={
                    "task_type": payload.task_type,
                    "sft_split": payload.sft_split,
                    "format": payload.format,
                    "exported_count": chunk_count,
                },
            )
        )
        await db.commit()


@router.post(
    "/export",
    summary="JSONL dataset export (ChatML format, HF datasets uyumlu)",
)
async def sft_export(
    payload: SFTExportRequest,
    user: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> StreamingResponse:
    if payload.format != "chatml":
        raise HTTPException(
            status_code=400,
            detail={
                "code": "UNSUPPORTED_FORMAT",
                "message": f"Format '{payload.format}' desteklenmiyor. Şu an sadece 'chatml'.",
            },
        )

    filename_split = payload.sft_split or "all"
    filename = f"nodrat-sft-{payload.task_type}-{filename_split}.jsonl"

    return StreamingResponse(
        _export_jsonl_stream(db, payload, user.id),
        media_type="application/x-ndjson",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


# =============================================================================
# POST /admin/sft/recompute-eligibility
# =============================================================================


@router.post(
    "/recompute-eligibility",
    response_model=RecomputeEligibilityResponse,
    summary="Tüm messages (assistant) için sft_eligible kuralını yeniden hesapla",
)
async def sft_recompute_eligibility(
    request: Request,
    user: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    days: Annotated[int, Query(ge=1, le=365)] = 30,
) -> RecomputeEligibilityResponse:
    """Eligibility kuralı değiştiğinde admin manuel tetikler.

    S1E (#800) rewrite: messages tablosundan beslenir (chat-only mimari).
    Son `days` gün içindeki assistant mesajlarını rescan eder.
    Kural: `apps/api/app/core/sft_eligibility.recompute_sft_eligibility`.
    """
    from app.core.sft_eligibility import recompute_sft_eligibility

    cutoff = datetime.now(UTC) - timedelta(days=days)

    # Message + User'i Conversation üzerinden join'le
    rows = (
        await db.execute(
            select(Message, User)
            .join(Conversation, Conversation.id == Message.conversation_id)
            .join(User, User.id == Conversation.user_id)
            .where(
                Message.role == "assistant",
                Message.created_at >= cutoff,
            )
        )
    ).all()

    became_eligible = 0
    became_ineligible = 0

    for msg, msg_user in rows:
        was_eligible = bool(msg.sft_eligible)
        eligible, reason = recompute_sft_eligibility(
            msg,
            msg_user,
            require_completed_status=False,
        )
        msg.sft_eligible = eligible
        msg.sft_excluded_reason = reason
        msg.sft_recomputed_at = datetime.now(UTC)
        if eligible and not was_eligible:
            became_eligible += 1
        elif was_eligible and not eligible:
            became_ineligible += 1

    db.add(
        AdminAuditLog(
            actor_id=user.id,
            action="sft.recompute_eligibility",
            target_type="messages",
            event_metadata={
                "days": days,
                "scanned": len(rows),
                "became_eligible": became_eligible,
                "became_ineligible": became_ineligible,
            },
            ip_address=get_client_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
    )
    await db.commit()

    return RecomputeEligibilityResponse(
        scanned=len(rows),
        became_eligible=became_eligible,
        became_ineligible=became_ineligible,
    )


# =============================================================================
# POST /admin/sft/run — Manual ETL trigger
# =============================================================================


@router.post(
    "/run",
    response_model=TriggerRunResponse,
    summary="ETL worker'ı şimdi çalıştır (manual trigger)",
)
async def sft_run_now(
    request: Request,
    user: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    batch: Annotated[int | None, Query(ge=1, le=10000)] = None,
) -> TriggerRunResponse:
    """02:45 UTC nightly schedule'ı beklemeden ETL'i şimdi tetikle.

    Celery `apply_async()` ile worker_embedding queue'ya dispatch eder.
    Kill switch (`sft.curator.enabled`) hâlâ kapalıysa task no-op döner
    (`{"status": "disabled"}`) — manuel trigger admin override DEĞİL.
    """
    kwargs = {} if batch is None else {"batch": batch}
    result = run_sft_curator.apply_async(kwargs=kwargs, queue="embedding_queue")

    db.add(
        AdminAuditLog(
            actor_id=user.id,
            action="sft.run_now",
            target_type="celery_task",
            event_metadata={
                "task_id": result.id,
                "batch_override": batch,
            },
            ip_address=get_client_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
    )
    await db.commit()

    return TriggerRunResponse(
        task_id=str(result.id),
        queued=True,
        note=(
            "ETL worker queue'ya dispatch edildi. Kill switch kapalıysa "
            "task no-op döner. Sonuçları görmek için sayfayı yenileyin."
        ),
    )


# =============================================================================
# GET /admin/sft/consent-stats
# =============================================================================


@router.get(
    "/consent-stats",
    response_model=ConsentStatsResponse,
    summary="Model improvement consent breakdown",
)
async def sft_consent_stats(
    user: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ConsentStatsResponse:
    total = (await db.execute(select(func.count()).select_from(User))).scalar_one()

    opted_in = (
        await db.execute(
            select(func.count())
            .select_from(User)
            .where(User.model_improvement_consent_at.is_not(None))
            .where(User.model_improvement_consent_revoked_at.is_(None))
        )
    ).scalar_one()

    opted_in_revoked = (
        await db.execute(
            select(func.count())
            .select_from(User)
            .where(User.model_improvement_consent_at.is_not(None))
            .where(User.model_improvement_consent_revoked_at.is_not(None))
        )
    ).scalar_one()

    never_opted_in = (
        await db.execute(
            select(func.count())
            .select_from(User)
            .where(User.model_improvement_consent_at.is_(None))
        )
    ).scalar_one()

    return ConsentStatsResponse(
        total_users=total,
        opted_in=opted_in,
        opted_in_revoked=opted_in_revoked,
        never_opted_in=never_opted_in,
    )
