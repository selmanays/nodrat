"""User-facing generation endpoints (#28, #30).

docs/engineering/api-contracts.md §3 (app endpoints)

Endpoints:
    POST   /app/generate                      — Sync MVP-1 generation
    GET    /app/generations                    — Geçmiş listesi
    GET    /app/generations/{id}               — Detay
    POST   /app/generations/{id}/save          — Save (favori)
    DELETE /app/generations/{id}/save          — Unsave
    POST   /app/generations/{id}/flag-halu     — Halüsinasyon raporu
    GET    /app/quota                          — Mevcut kota
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cost_tracker import track_provider_call
from app.core.data_sufficiency import check_sufficiency
from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.quota import (
    QuotaExceeded,
    enforce_quota,
    get_quota_status,
    record_usage,
)
from app.models.generation import Generation, SavedGeneration
from app.models.user import User
from app.prompts.content_generator import (
    PROMPT_VERSION as CONTENT_PROMPT_VERSION,
    ContentGenError,
    GeneratedXContent,
    format_system_prompt,
    parse_x_post_response,
    render_user_payload as render_content_payload,
)
from app.prompts.query_planner import (
    PROMPT_VERSION as PLANNER_PROMPT_VERSION,
    QueryPlanError,
    plan_query,
)
from app.providers.base import Message
from app.providers.registry import bootstrap_default_providers, registry


logger = logging.getLogger(__name__)
router = APIRouter()


# ============================================================================
# Pydantic schemas
# ============================================================================


class GenerateRequest(BaseModel):
    """User generation talebi (PRD §3.6)."""

    request_text: str = Field(min_length=5, max_length=2000)
    output_type: str | None = Field(default=None, max_length=32)
    """LLM planning override; None → planner karar verir."""

    tone: str | None = Field(default=None, max_length=32)
    length: str | None = Field(default=None, max_length=16)
    show_sources: bool = True
    max_posts: int = Field(default=5, ge=1, le=10)


class XPostPublic(BaseModel):
    text: str
    angle: str
    char_count: int
    related_agenda_card_ids: list[str]


class GenerateResponse(BaseModel):
    id: UUID
    status: str
    request_text: str
    mode: str
    output_type: str
    tone: str | None
    posts: list[XPostPublic] = []
    summary: str = ""
    sources: list[dict[str, str]] = []
    warnings: list[str] = []
    suggestions: list[str] = []
    """INSUFFICIENT_DATA durumunda 3 actionable öneri."""

    cost_usd: float | None = None
    created_at: datetime
    completed_at: datetime | None = None


class GenerationSummary(BaseModel):
    id: UUID
    request_text: str
    mode: str
    output_type: str
    status: str
    created_at: datetime
    completed_at: datetime | None
    saved: bool
    posts_count: int
    halu_flagged: bool


class GenerationListResponse(BaseModel):
    data: list[GenerationSummary]
    total: int


class SaveRequest(BaseModel):
    note: str | None = Field(default=None, max_length=500)


class FlagHaluRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class QuotaResponse(BaseModel):
    tier: str
    limit: int
    used: int
    remaining: int
    reset_at: datetime


# ============================================================================
# Generate (sync MVP-1)
# ============================================================================


@router.post(
    "/generate",
    response_model=GenerateResponse,
    summary="Yeni içerik üret (sync, MVP-1)",
)
async def generate(
    payload: GenerateRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> GenerateResponse:
    """End-to-end pipeline:
      1. Quota check (Redis sliding window)
      2. Query Planner → retrieval_plan
      3. Data sufficiency check (agenda_cards)
      4. INSUFFICIENT_DATA → return suggestions, status=insufficient_data
      5. Agenda cards fetch
      6. Content Generator → posts
      7. Persist + record_usage
    """
    bootstrap_default_providers()

    # 1) Quota
    try:
        await enforce_quota(user.id, user.tier)  # type: ignore[arg-type]
    except QuotaExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "QUOTA_EXCEEDED",
                "title": "Kotanız doldu",
                "limit": exc.status.limit,
                "used": exc.status.used,
                "reset_at": exc.status.reset_at.isoformat(),
            },
        )

    now = datetime.now(timezone.utc)

    # 2) Generation row create (status=running)
    gen = Generation(
        user_id=user.id,
        request_text=payload.request_text,
        mode="current",  # planner'dan güncellenecek
        output_type=payload.output_type or "x_post",
        tone=payload.tone,
        length=payload.length,
        show_sources=payload.show_sources,
        status="running",
        started_at=now,
    )
    db.add(gen)
    await db.flush()
    gen_id = gen.id

    # 3) Query planner
    plan_result = await plan_query(
        user_request=payload.request_text,
        current_time=now,
        user_locale=user.locale,
        user_tier=user.tier,
    )

    if isinstance(plan_result, QueryPlanError):
        gen.status = "failed"
        gen.completed_at = datetime.now(timezone.utc)
        gen.warnings = [f"planner_error: {plan_result.error} - {plan_result.reason}"]
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "PLANNER_ERROR",
                "title": "Plan oluşturulamadı",
                "reason": plan_result.reason,
            },
        )

    plan = plan_result
    gen.mode = plan.mode
    gen.output_type = plan.output_type
    gen.tone = plan.tone or gen.tone
    gen.retrieval_plan_json = {
        "intent": plan.intent,
        "topic_query": plan.topic_query,
        "mode": plan.mode,
        "timeframes": [
            {"label": tf.label, "from": tf.from_iso, "to": tf.to_iso}
            for tf in plan.timeframes
        ],
        "output_type": plan.output_type,
        "tone": plan.tone,
        "constraints": plan.constraints,
        "needs_sources": plan.needs_sources,
        "minimum_evidence_per_period": plan.minimum_evidence_per_period,
        "_prompt_version": PLANNER_PROMPT_VERSION,
        "_warnings": plan.warnings,
    }

    # 4) Data sufficiency
    sufficiency = await check_sufficiency(
        db,
        retrieval_plan=gen.retrieval_plan_json,
        min_evidence_per_period=plan.minimum_evidence_per_period,
    )

    if not sufficiency.sufficient:
        gen.status = "insufficient_data"
        gen.completed_at = datetime.now(timezone.utc)
        gen.warnings = [sufficiency.reason or "insufficient_data"]
        await record_usage(
            db,
            user_id=user.id,
            event_type="generation_insufficient",
            metadata={"counts": sufficiency.counts_per_period},
        )
        await db.commit()
        return GenerateResponse(
            id=gen.id,
            status="insufficient_data",
            request_text=payload.request_text,
            mode=plan.mode,
            output_type=plan.output_type,
            tone=plan.tone,
            posts=[],
            summary="",
            sources=[],
            warnings=gen.warnings,
            suggestions=sufficiency.suggestions,
            cost_usd=0.0,
            created_at=gen.created_at,
            completed_at=gen.completed_at,
        )

    # 5) Agenda cards fetch
    agenda_rows = (
        await db.execute(
            __import__("sqlalchemy").text(
                """
                SELECT ac.id, ac.title, ac.summary, ac.key_points,
                       ac.content_angles, ac.source_refs, ac.status,
                       ac.importance_score, ac.freshness_score
                FROM agenda_cards ac
                JOIN event_clusters ec ON ec.id = ac.event_id
                WHERE ec.status IN ('active', 'developing', 'cooling')
                ORDER BY ac.updated_at DESC
                LIMIT 10
                """
            )
        )
    ).mappings().all()
    agenda_cards = [dict(r) for r in agenda_rows]
    used_ids = [c["id"] for c in agenda_cards]

    # 6) Content generator
    try:
        provider = registry.route_for_tier(operation="chat", tier=user.tier)  # type: ignore[arg-type]
    except RuntimeError as exc:
        gen.status = "failed"
        gen.warnings = [f"no_provider: {exc}"]
        gen.completed_at = datetime.now(timezone.utc)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "NO_LLM_PROVIDER", "title": "LLM provider erişilemez"},
        ) from exc

    user_msg = render_content_payload(
        request=payload.request_text,
        retrieval_plan=gen.retrieval_plan_json,
        agenda_cards=agenda_cards,
        output_constraints={
            "output_type": plan.output_type,
            "max_posts": payload.max_posts,
            "tone": plan.tone,
            "length": payload.length or "medium",
            "show_sources": payload.show_sources,
            "language": "tr",
        },
    )

    try:
        async with track_provider_call(
            db=db,
            provider=provider.name,
            operation="chat",
            user_id=user.id,
            generation_id=gen.id,
        ) as tracker:
            generation_call = await provider.generate_text(
                messages=[
                    Message(role="system", content=format_system_prompt(max_posts=payload.max_posts)),
                    Message(role="user", content=user_msg),
                ],
                max_tokens=2000,
                temperature=0.5,
            )
            tracker.record(
                input_tokens=generation_call.input_tokens,
                output_tokens=generation_call.output_tokens,
                model=generation_call.model,
                cost_usd=generation_call.cost_usd,
            )
    except Exception as exc:
        gen.status = "failed"
        gen.warnings = [f"provider_error: {exc}"]
        gen.completed_at = datetime.now(timezone.utc)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "PROVIDER_ERROR", "title": "Üretim başarısız", "reason": str(exc)[:200]},
        ) from exc

    parsed = parse_x_post_response(generation_call.text)

    if isinstance(parsed, ContentGenError):
        if parsed.error == "insufficient_data":
            gen.status = "insufficient_data"
            gen.warnings = [parsed.reason]
        else:
            gen.status = "failed"
            gen.warnings = [f"content_error: {parsed.error} - {parsed.reason}"]
        gen.completed_at = datetime.now(timezone.utc)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": parsed.error.upper(), "title": parsed.reason},
        )

    # 7) Persist
    gen.status = "completed"
    gen.completed_at = datetime.now(timezone.utc)
    gen.used_agenda_card_ids = used_ids
    gen.model_provider = provider.name
    gen.model_name = generation_call.model
    gen.input_tokens = generation_call.input_tokens
    gen.output_tokens = generation_call.output_tokens
    gen.cost_estimate_usd = Decimal(str(generation_call.cost_usd))
    gen.warnings = parsed.warnings
    gen.output_json = {
        "posts": [
            {
                "text": p.text,
                "angle": p.angle,
                "char_count": p.char_count,
                "related_agenda_card_ids": p.related_agenda_card_ids,
            }
            for p in parsed.posts
        ],
        "summary": parsed.summary,
        "sources": parsed.sources,
        "warnings": parsed.warnings,
        "_prompt_version": CONTENT_PROMPT_VERSION,
    }

    # Quota record
    await record_usage(
        db,
        user_id=user.id,
        event_type="generation",
        provider=provider.name,
        model=generation_call.model,
        input_tokens=generation_call.input_tokens,
        output_tokens=generation_call.output_tokens,
        cost_usd=generation_call.cost_usd,
        metadata={"output_type": plan.output_type},
    )

    await db.commit()

    return GenerateResponse(
        id=gen.id,
        status="completed",
        request_text=payload.request_text,
        mode=plan.mode,
        output_type=plan.output_type,
        tone=plan.tone,
        posts=[
            XPostPublic(
                text=p.text,
                angle=p.angle,
                char_count=p.char_count,
                related_agenda_card_ids=p.related_agenda_card_ids,
            )
            for p in parsed.posts
        ],
        summary=parsed.summary,
        sources=parsed.sources,
        warnings=parsed.warnings,
        suggestions=[],
        cost_usd=generation_call.cost_usd,
        created_at=gen.created_at,
        completed_at=gen.completed_at,
    )


# ============================================================================
# History
# ============================================================================


@router.get(
    "/generations",
    response_model=GenerationListResponse,
    summary="Üretim geçmişi (kullanıcı)",
)
async def list_generations(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
    offset: Annotated[int, Query(ge=0)] = 0,
    saved_only: Annotated[bool, Query()] = False,
) -> GenerationListResponse:
    stmt = (
        select(Generation)
        .where(Generation.user_id == user.id)
        .order_by(Generation.created_at.desc())
    )
    if saved_only:
        stmt = stmt.where(Generation.saved_at.is_not(None))

    from sqlalchemy import func as _func

    count_stmt = select(_func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar() or 0

    paged = stmt.limit(limit).offset(offset)
    rows = list((await db.execute(paged)).scalars().all())

    summaries = [
        GenerationSummary(
            id=g.id,
            request_text=g.request_text,
            mode=g.mode,
            output_type=g.output_type,
            status=g.status,
            created_at=g.created_at,
            completed_at=g.completed_at,
            saved=g.saved_at is not None,
            posts_count=(
                len(g.output_json.get("posts", []))
                if g.output_json and isinstance(g.output_json, dict)
                else 0
            ),
            halu_flagged=g.halu_flagged_at is not None,
        )
        for g in rows
    ]

    return GenerationListResponse(data=summaries, total=total)


@router.get(
    "/generations/{generation_id}",
    response_model=GenerateResponse,
    summary="Üretim detay",
)
async def get_generation(
    generation_id: Annotated[UUID, Path()],
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> GenerateResponse:
    gen = await db.get(Generation, generation_id)
    if gen is None or gen.user_id != user.id:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND"})

    output = gen.output_json or {}
    posts = output.get("posts", []) or []

    return GenerateResponse(
        id=gen.id,
        status=gen.status,
        request_text=gen.request_text,
        mode=gen.mode,
        output_type=gen.output_type,
        tone=gen.tone,
        posts=[
            XPostPublic(
                text=p.get("text", ""),
                angle=p.get("angle", ""),
                char_count=p.get("char_count", 0),
                related_agenda_card_ids=p.get("related_agenda_card_ids", []),
            )
            for p in posts
        ],
        summary=output.get("summary", ""),
        sources=output.get("sources", []),
        warnings=gen.warnings or [],
        suggestions=[],
        cost_usd=float(gen.cost_estimate_usd) if gen.cost_estimate_usd else None,
        created_at=gen.created_at,
        completed_at=gen.completed_at,
    )


# ============================================================================
# Save / unsave
# ============================================================================


@router.post(
    "/generations/{generation_id}/save",
    status_code=status.HTTP_201_CREATED,
    summary="Üretimi favorile",
)
async def save_generation(
    generation_id: Annotated[UUID, Path()],
    payload: SaveRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    gen = await db.get(Generation, generation_id)
    if gen is None or gen.user_id != user.id:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND"})
    if gen.status != "completed":
        raise HTTPException(
            status_code=409,
            detail={"code": "NOT_COMPLETED", "title": "Sadece tamamlanmış üretimler kaydedilebilir"},
        )

    saved = SavedGeneration(
        user_id=user.id,
        generation_id=gen.id,
        note=(payload.note or "").strip()[:500] or None,
    )
    db.add(saved)
    gen.saved_at = datetime.now(timezone.utc)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        # Already saved → idempotent
        gen.saved_at = gen.saved_at or datetime.now(timezone.utc)
        return {"status": "already_saved", "generation_id": str(gen.id)}

    return {"status": "saved", "generation_id": str(gen.id)}


@router.delete(
    "/generations/{generation_id}/save",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Üretimi favoriden çıkar",
)
async def unsave_generation(
    generation_id: Annotated[UUID, Path()],
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    gen = await db.get(Generation, generation_id)
    if gen is None or gen.user_id != user.id:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND"})

    result = await db.execute(
        select(SavedGeneration).where(
            SavedGeneration.user_id == user.id,
            SavedGeneration.generation_id == generation_id,
        )
    )
    saved = result.scalar_one_or_none()
    if saved is not None:
        await db.delete(saved)
    gen.saved_at = None
    await db.commit()


# ============================================================================
# Halu flag
# ============================================================================


@router.post(
    "/generations/{generation_id}/flag-halu",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Halüsinasyon raporu (kullanıcı)",
)
async def flag_halu(
    generation_id: Annotated[UUID, Path()],
    payload: FlagHaluRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    gen = await db.get(Generation, generation_id)
    if gen is None or gen.user_id != user.id:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND"})

    gen.halu_flagged_at = datetime.now(timezone.utc)
    gen.halu_flagged_by = user.id

    # Add reason to warnings
    reason = (payload.reason or "user_reported").strip()[:500]
    warnings_list = list(gen.warnings or [])
    warnings_list.append(f"halu_flag: {reason}")
    gen.warnings = warnings_list

    await db.commit()
    return {"status": "flagged", "generation_id": str(gen.id)}


# ============================================================================
# Quota
# ============================================================================


@router.get(
    "/quota",
    response_model=QuotaResponse,
    summary="Mevcut kota durumu",
)
async def my_quota(
    user: Annotated[User, Depends(get_current_user)],
) -> QuotaResponse:
    status_obj = await get_quota_status(user.id, user.tier)  # type: ignore[arg-type]
    return QuotaResponse(
        tier=status_obj.tier,
        limit=status_obj.limit,
        used=status_obj.used,
        remaining=status_obj.remaining,
        reset_at=status_obj.reset_at,
    )
