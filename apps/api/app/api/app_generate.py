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

from app.config import get_settings
from app.core.citation import (
    SourceFragment,
    cited_only_sources,
    validate_citations,
)
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


class SummaryItemPublic(BaseModel):
    """#173 PR-F — summary mode item."""

    event: str
    source: str
    date: str
    agenda_card_id: str | None = None


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

    # #173 PR-F — summary mode (multi-item bullet doc)
    summary_doc_title: str = ""
    summary_doc_items: list[SummaryItemPublic] = []

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
        "keywords": plan.keywords,
        "requested_count": plan.requested_count,
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

    # 5) Hybrid retrieval (#171 PR-E) — dense + sparse RRF
    # PR-D: dense-only agenda. PR-E: hybrid agenda + chunks supplementary fallback
    from app.core.retrieval import (
        hybrid_search_agenda_cards,
        hybrid_search_chunks,
    )

    # Query enrichment — keywords planner çıktısından
    enriched_query = plan.topic_query
    if hasattr(plan, "keywords") and plan.keywords:
        enriched_query = f"{plan.topic_query} {' '.join(plan.keywords[:5])}"

    # Query embedding
    query_vec = None
    emb_cost = 0.0
    try:
        emb_provider = registry.route_for_tier(operation="embedding", tier="free")
        emb_result = await emb_provider.create_embedding([enriched_query])
        query_vec = emb_result.vectors[0] if emb_result.vectors else None
        emb_cost = float(emb_result.cost_usd)
    except Exception as exc:
        logger.warning("query embedding failed: %s — sparse-only retrieval", exc)

    # Hybrid agenda card retrieval (#181 — rerank pool 50)
    settings = get_settings()

    # #182 RAPTOR-Lite — timeframe range geniş ise weekly card'ları da dahil et
    # #205 — timeframe range parser (planner'dan from/to ISO ile geliyor)
    levels: tuple[str, ...] = ("daily",)
    timeframe_from = None
    timeframe_to = None
    try:
        if plan.timeframes:
            from datetime import datetime as _dt

            spans_days: list[float] = []
            parsed_ranges: list[tuple[Any, Any]] = []
            for tf in plan.timeframes:
                try:
                    a = _dt.fromisoformat(tf.from_iso.replace("Z", "+00:00"))
                    b = _dt.fromisoformat(tf.to_iso.replace("Z", "+00:00"))
                    spans_days.append(abs((b - a).total_seconds()) / 86400.0)
                    parsed_ranges.append((a, b))
                except Exception:
                    continue
            max_span = max(spans_days) if spans_days else 0.0
            if max_span >= 30:
                levels = ("daily", "weekly", "monthly")
            elif max_span >= 6:
                levels = ("daily", "weekly")

            # #205 — En geniş timeframe'i retrieval filter olarak uygula
            # (multiple timeframe varsa: from = en eski, to = en yeni)
            if parsed_ranges:
                timeframe_from = min(r[0] for r in parsed_ranges)
                timeframe_to = max(r[1] for r in parsed_ranges)
                logger.info(
                    "retrieval timeframe: %s → %s (span %.1fd)",
                    timeframe_from.isoformat(),
                    timeframe_to.isoformat(),
                    max_span,
                )
    except Exception:  # pragma: no cover
        pass

    agenda_cards = await hybrid_search_agenda_cards(
        db,
        query_text=enriched_query,
        query_vector=query_vec,
        top_k=10,
        candidate_pool=settings.reranker_candidate_pool,
        levels=levels,
        timeframe_from=timeframe_from,
        timeframe_to=timeframe_to,
    )
    used_ids = [c["id"] for c in agenda_cards]

    # Chunks supplementary — agenda 0 ise (singleton cluster article'ları için)
    supplementary_chunks: list[dict] = []
    if not agenda_cards:
        supplementary_chunks = await hybrid_search_chunks(
            db,
            query_text=enriched_query,
            query_vector=query_vec,
            top_k=8,
            candidate_pool=settings.reranker_candidate_pool,
            since_hours=168,  # son 7 gün
        )
        logger.info(
            "agenda_empty fallback_chunks=%d topic=%s",
            len(supplementary_chunks),
            plan.topic_query[:80],
        )

    logger.info(
        "retrieval cards=%d chunks=%d topic=%s",
        len(agenda_cards),
        len(supplementary_chunks),
        plan.topic_query[:80],
    )

    # Hem agenda hem chunks boş → insufficient_data
    if not agenda_cards and not supplementary_chunks:
        gen.status = "insufficient_data"
        gen.warnings = [
            f"'{plan.topic_query}' konusuyla ilgili kaynak bulunamadı "
            "(hybrid search dense+sparse fail)"
        ]
        gen.completed_at = datetime.now(timezone.utc)
        await record_usage(
            db,
            user_id=user.id,
            event_type="generation_insufficient",
            metadata={"path": "hybrid_retrieval", "topic": plan.topic_query[:120]},
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
            suggestions=[
                {"type": "broaden_query", "text": f"'{plan.topic_query}' konusunu daha geniş anahtar kelimelerle tekrar deneyin"},
                {"type": "different_topic", "text": "Farklı bir konu deneyin (gündemde yer alan başka bir başlık)"},
            ],
            cost_usd=emb_cost,
            created_at=gen.created_at,
            completed_at=gen.completed_at,
        )

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

    # #173 PR-F — effective_max_posts: planner suggested vs payload override
    # Frontend default = 1; planner kullanıcı sayısını yakaladıysa onu kullan
    PAYLOAD_DEFAULT_MAX_POSTS = 1
    effective_max_posts = payload.max_posts
    if (
        payload.max_posts == PAYLOAD_DEFAULT_MAX_POSTS
        and getattr(plan, "requested_count", 1) > 1
    ):
        effective_max_posts = plan.requested_count
        logger.info(
            "max_posts override: payload=%d plan=%d topic=%s",
            payload.max_posts,
            plan.requested_count,
            plan.topic_query[:60],
        )

    user_msg = render_content_payload(
        request=payload.request_text,
        retrieval_plan=gen.retrieval_plan_json,
        agenda_cards=agenda_cards,
        supplementary_chunks=supplementary_chunks,
        output_constraints={
            "output_type": plan.output_type,
            "max_posts": effective_max_posts,
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
                    Message(role="system", content=format_system_prompt(max_posts=effective_max_posts, output_type=plan.output_type)),
                    Message(role="user", content=user_msg),
                ],
                max_tokens=2000,
                temperature=0.5,
                json_mode=True,  # #171 PR-E — DeepSeek deterministic JSON
            )
            tracker.record(
                input_tokens=generation_call.input_tokens,
                output_tokens=generation_call.output_tokens,
                cached_tokens=getattr(generation_call, "cached_input_tokens", 0),
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
        # #159: insufficient_data / irrelevant_sources için 200 OK +
        # GenerationResponse (planner sufficiency path ile tutarlı)
        if parsed.error == "insufficient_data":
            gen.status = "insufficient_data"
            gen.warnings = [parsed.reason]
            gen.completed_at = datetime.now(timezone.utc)
            await record_usage(
                db,
                user_id=user.id,
                event_type="generation_insufficient",
                metadata={"path": "generator", "reason": parsed.reason[:200]},
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
                suggestions=[],
                cost_usd=0.0,
                created_at=gen.created_at,
                completed_at=gen.completed_at,
            )

        # Diğer parse_error'lar gerçekten internal error (LLM JSON bozuk vb.)
        gen.status = "failed"
        gen.warnings = [f"content_error: {parsed.error} - {parsed.reason}"]
        gen.completed_at = datetime.now(timezone.utc)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": parsed.error.upper(), "title": parsed.reason},
        )

    # 6.5) Citation validation (#180) — repair format + embedding-based evidence check
    citation_warnings: list[str] = []
    citation_meta: dict[str, Any] = {}
    try:
        source_fragments = [
            SourceFragment(
                id=i + 1,
                title=str(card.get("title", ""))[:200],
                summary=str(card.get("summary", ""))[:600],
            )
            for i, card in enumerate(agenda_cards)
        ]

        async def _embed_batch(texts: list[str]) -> list[list[float]] | None:
            try:
                emb_provider = registry.route_for_tier(
                    operation="embedding", tier="free"
                )
                result = await emb_provider.create_embedding(texts)
                if not result.vectors or any(
                    len(v) != 1024 for v in result.vectors
                ):
                    return None
                return [list(v) for v in result.vectors]
            except Exception as exc:  # pragma: no cover
                logger.warning("citation embed batch failed: %s", exc)
                return None

        # Her post için ve summary için citation report
        for post in parsed.posts:
            report = await validate_citations(
                post.text,
                sources=source_fragments,
                embed_fn=_embed_batch,
                cosine_threshold=0.55,
            )
            if report.repair_count:
                post.text = report.cleaned_text
                citation_meta.setdefault("repairs", 0)
                citation_meta["repairs"] += report.repair_count
            if report.unsupported_count:
                citation_warnings.append(
                    f"post_unsupported_claims={report.unsupported_count}"
                )

        if parsed.summary:
            sum_report = await validate_citations(
                parsed.summary,
                sources=source_fragments,
                embed_fn=_embed_batch,
                cosine_threshold=0.55,
            )
            if sum_report.repair_count:
                parsed.summary = sum_report.cleaned_text
                citation_meta["repairs"] = (
                    citation_meta.get("repairs", 0) + sum_report.repair_count
                )
            if sum_report.unsupported_count:
                citation_warnings.append(
                    f"summary_unsupported_claims={sum_report.unsupported_count}"
                )
    except Exception as cit_exc:  # pragma: no cover
        logger.warning("citation validation skipped: %s", cit_exc)

    # 7) Persist
    gen.status = "completed"
    gen.completed_at = datetime.now(timezone.utc)
    gen.used_agenda_card_ids = used_ids
    gen.model_provider = provider.name
    gen.model_name = generation_call.model
    gen.input_tokens = generation_call.input_tokens
    gen.output_tokens = generation_call.output_tokens
    gen.cost_estimate_usd = Decimal(str(generation_call.cost_usd))
    gen.warnings = list(parsed.warnings) + citation_warnings
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
        # #173 PR-F — summary mode (multi-item bullet doc)
        "summary_doc_title": parsed.summary_doc_title,
        "summary_doc_items": [
            {
                "event": it.event,
                "source": it.source,
                "date": it.date,
                "agenda_card_id": it.agenda_card_id,
            }
            for it in parsed.summary_doc_items
        ],
        "_prompt_version": CONTENT_PROMPT_VERSION,
        "_citation": citation_meta,  # #180 repair + supported claim metadata
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
        # #173 PR-F — summary mode (multi-item bullet)
        summary_doc_title=parsed.summary_doc_title,
        summary_doc_items=[
            SummaryItemPublic(
                event=it.event,
                source=it.source,
                date=it.date,
                agenda_card_id=it.agenda_card_id,
            )
            for it in parsed.summary_doc_items
        ],
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
    summary_items_raw = output.get("summary_doc_items", []) or []

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
        # #173 PR-F
        summary_doc_title=output.get("summary_doc_title", ""),
        summary_doc_items=[
            SummaryItemPublic(
                event=it.get("event", ""),
                source=it.get("source", ""),
                date=it.get("date", ""),
                agenda_card_id=it.get("agenda_card_id"),
            )
            for it in summary_items_raw
        ],
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
