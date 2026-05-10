"""SSE streaming generation endpoint (issue #527).

`/app/generate-stream` — `POST` returns `text/event-stream`. Eski blocking
`/app/generate` korunur (backward-compat); yeni endpoint TTFT'yi ~5s'ten
<1s'e indirir.

Event akışı:
    event: meta         {generation_id, mode, output_type, tone, plan}
    event: progress     {stage: "planning"|"retrieving"|"generating"|"validating"}
    event: chunk        {delta}                         # raw LLM token delta
    event: post         {index, text, angle, char_count, related_agenda_card_ids}
    event: parsed       {posts, summary, sources, summary_doc_*, warnings}
    event: citation     {repairs, unsupported_warnings}
    event: image        {image_id, original_url, ...}
    event: done         {generation_id, status, cost_usd, completed_at}
    event: error        {code, title, reason}

Mimari kararlar:
- Speculative retrieval: planner ile paralel `embed(raw_query)` (issue #527).
- Planner cache: `app.core.planner_cache` (24h Redis, gün granülasyonu).
- Citation + image: stream sonrası paralel; `chunk`/`post` event'lerini
  bloklamaz.
- DB persist: stream generator içinde commit; row başlangıçta `running`,
  sonunda `completed`/`failed`.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.app_generate import (
    GenerateRequest,
    SuggestedImagePublic,
    _resolve_style_profile,
)
from app.config import get_settings
from app.core.citation import SourceFragment, validate_citations_batch
from app.core.cost_tracker import track_provider_call
from app.core.data_sufficiency import check_sufficiency
from app.core.db import get_db
from app.core.deps import require_foreign_transfer_consent
from app.core.media_suggest import (
    SuggestedImage,
    article_ids_from_urls,
    suggest_image_for_post,
)
from app.core.quota import (
    QuotaExceeded,
    enforce_quota,
    record_usage,
)
from app.core.settings_store import settings_store
from app.core.streaming_json import StreamingPostExtractor
from app.models.generation import Generation
from app.models.user import User
from app.prompts.content_generator import (
    PROMPT_VERSION as CONTENT_PROMPT_VERSION,
)
from app.prompts.content_generator import (
    ContentGenError,
    format_system_prompt,
    parse_x_post_response,
)
from app.prompts.content_generator import (
    render_user_payload as render_content_payload,
)
from app.prompts.query_planner import (
    PROMPT_VERSION as PLANNER_PROMPT_VERSION,
)
from app.prompts.query_planner import (
    QueryPlanError,
    plan_query,
)
from app.providers.base import Message
from app.providers.registry import bootstrap_default_providers, registry

logger = logging.getLogger(__name__)
router = APIRouter()


def _sse(event: str, data: dict | None = None) -> str:
    """SSE event'i format et."""
    payload = json.dumps(data or {}, ensure_ascii=False, default=str)
    return f"event: {event}\ndata: {payload}\n\n"


@router.post(
    "/generate-stream",
    summary="Yeni içerik üret (SSE streaming, issue #527)",
)
async def generate_stream(
    payload: GenerateRequest,
    user: Annotated[User, Depends(require_foreign_transfer_consent)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Streaming variant of /app/generate (issue #527).

    Authentication, quota ve style profile resolve sync olarak çalışır;
    hata varsa stream başlamadan HTTP error döner. Sonra StreamingResponse
    ile event stream başlar.
    """
    bootstrap_default_providers()

    # 1) Quota — pre-stream (HTTP 429 stream'e dahil edilmez)
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
        ) from exc

    now = datetime.now(UTC)

    # 2) Style profile (Pro paywall pre-stream)
    style_profile_rules: dict[str, Any] | None = None
    style_profile_used_id: UUID | None = None
    if payload.style_profile_id is not None:
        style_profile_rules, style_profile_used_id = await _resolve_style_profile(
            db, user, payload.style_profile_id
        )

    # 3) Generation row (status=running, persist hemen)
    gen = Generation(
        user_id=user.id,
        request_text=payload.request_text,
        mode="current",
        output_type=payload.output_type or "x_post",
        tone=payload.tone,
        length=payload.length,
        show_sources=payload.show_sources,
        style_profile_id=style_profile_used_id,
        status="running",
        started_at=now,
    )
    db.add(gen)
    await db.flush()
    await db.commit()
    gen_id = gen.id

    return StreamingResponse(
        _stream_body(
            db=db,
            user=user,
            payload=payload,
            gen_id=gen_id,
            now=now,
            style_profile_rules=style_profile_rules,
        ),
        media_type="text/event-stream",
        headers={
            # #531 — proxy/CDN buffer'larını agresif şekilde disable et:
            # - no-transform: Cloudflare/Caddy compression bypass (en kritik)
            # - no-cache: browser caching disable
            # - X-Accel-Buffering: nginx-style proxy buffer disable (defense)
            # - Content-Encoding: identity → response sıkıştırılmasın
            # Caddy tarafında ayrıca encode middleware'inden bu path bypass'lı
            # ve `flush_interval -1` ile chunk-anında-forward (infra/Caddyfile).
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Content-Encoding": "identity",
        },
    )


# ============================================================================
# Stream body — async generator
# ============================================================================


async def _stream_body(
    *,
    db: AsyncSession,
    user: User,
    payload: GenerateRequest,
    gen_id: UUID,
    now: datetime,
    style_profile_rules: dict[str, Any] | None,
) -> AsyncIterator[str]:
    """Ana streaming akışı — SSE event'leri üretir."""

    stream_start = time.perf_counter()
    settings = get_settings()

    # Helpers
    async def _finalize_failed(code: str, title: str, reason: str) -> AsyncIterator[str]:
        """Hata durumunda gen row'u failed yap + done emit."""
        try:
            gen = await db.get(Generation, gen_id)
            if gen is not None:
                gen.status = "failed"
                gen.warnings = [f"{code}: {reason}"][:5]
                gen.completed_at = datetime.now(UTC)
                await db.commit()
        except Exception:  # pragma: no cover
            await db.rollback()
        yield _sse("error", {"code": code, "title": title, "reason": reason})
        yield _sse("done", {"generation_id": str(gen_id), "status": "failed"})

    yield _sse("progress", {"stage": "planning", "detail": "Plan hazırlanıyor"})

    # 4) Speculative retrieval — embed(raw_query) paralel olarak başlar
    enriched_query_initial = payload.request_text  # planner gelene kadar fallback

    async def _embed_async(text: str) -> tuple[list[float] | None, float]:
        try:
            emb_provider = registry.route_for_tier(operation="embedding", tier="free")
            res = await emb_provider.create_embedding([text])
            vec = res.vectors[0] if res.vectors else None
            return vec, float(res.cost_usd)
        except Exception as exc:  # pragma: no cover
            logger.warning("speculative embed failed: %s", exc)
            return None, 0.0

    speculative_emb_task = asyncio.create_task(_embed_async(enriched_query_initial))

    # 5) Plan query (cache'li) — paralel olarak embedding çalışıyor
    try:
        plan_result = await plan_query(
            user_request=payload.request_text,
            current_time=now,
            user_locale=user.locale,
            user_tier=user.tier,
        )
    except Exception as exc:  # pragma: no cover
        speculative_emb_task.cancel()
        async for ev in _finalize_failed("PLANNER_ERROR", "Plan oluşturulamadı", str(exc)[:200]):
            yield ev
        return

    if isinstance(plan_result, QueryPlanError):
        speculative_emb_task.cancel()
        async for ev in _finalize_failed(
            "PLANNER_ERROR", "Plan oluşturulamadı", plan_result.reason
        ):
            yield ev
        return

    plan = plan_result

    # Comparison feature flag (sync with /generate)
    if plan.mode == "comparison":
        try:
            comparison_enabled = await settings_store.get(
                db, "comparison.enabled", default=False
            )
        except Exception:  # pragma: no cover
            comparison_enabled = False
        if not comparison_enabled:
            plan.mode = "current"  # type: ignore[attr-defined]

    # Persist plan to gen row
    retrieval_plan_json = {
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
        "geographic_focus": getattr(plan, "geographic_focus", None),
        "constraints": plan.constraints,
        "needs_sources": plan.needs_sources,
        "minimum_evidence_per_period": plan.minimum_evidence_per_period,
        "_prompt_version": PLANNER_PROMPT_VERSION,
        "_warnings": plan.warnings,
    }
    try:
        gen_row = await db.get(Generation, gen_id)
        if gen_row is not None:
            gen_row.mode = plan.mode
            gen_row.output_type = plan.output_type
            gen_row.tone = plan.tone or gen_row.tone
            gen_row.retrieval_plan_json = retrieval_plan_json
            await db.commit()
    except Exception:  # pragma: no cover
        await db.rollback()

    yield _sse(
        "meta",
        {
            "generation_id": str(gen_id),
            "mode": plan.mode,
            "output_type": plan.output_type,
            "tone": plan.tone,
            "plan": {
                "intent": plan.intent,
                "topic_query": plan.topic_query,
                "keywords": plan.keywords,
                "requested_count": plan.requested_count,
            },
        },
    )

    # 6) Data sufficiency
    sufficiency = await check_sufficiency(
        db,
        retrieval_plan=retrieval_plan_json,
        min_evidence_per_period=plan.minimum_evidence_per_period,
    )

    if not sufficiency.sufficient:
        speculative_emb_task.cancel()
        try:
            gen_row = await db.get(Generation, gen_id)
            if gen_row is not None:
                gen_row.status = "insufficient_data"
                gen_row.completed_at = datetime.now(UTC)
                gen_row.warnings = [sufficiency.reason or "insufficient_data"]
                await record_usage(
                    db,
                    user_id=user.id,
                    event_type="generation_insufficient",
                    metadata={"counts": sufficiency.counts_per_period},
                )
                await db.commit()
        except Exception:  # pragma: no cover
            await db.rollback()
        yield _sse(
            "error",
            {
                "code": "INSUFFICIENT_DATA",
                "title": "Yeterli kaynak yok",
                "reason": sufficiency.reason or "insufficient_data",
                "suggestions": sufficiency.suggestions,
            },
        )
        yield _sse(
            "done", {"generation_id": str(gen_id), "status": "insufficient_data"}
        )
        return

    # 7) Hybrid retrieval — speculative embedding'i bekleyip kullan
    yield _sse("progress", {"stage": "retrieving", "detail": "Kaynaklar getiriliyor"})

    from app.core.retrieval import (
        hybrid_search_agenda_cards,
        hybrid_search_chunks,
        normalize_tr_query,
    )

    # MVP-1.8 PR-B (#618) — Multi-query rewrite: planner çıktısından 2 varyant
    # üret (orijinal + keywords-enriched). RRF füzyon farklı yazımları yakalar.
    # #647 streaming parity: app_generate.py ile aynı multi-query mantığı.
    query_variants: list[str] = [plan.topic_query]
    if plan.keywords:
        kw_top = plan.keywords[:3]
        query_variants.append(f"{plan.topic_query} {' '.join(kw_top)}")
    enriched_query = query_variants[-1]

    norm_query = normalize_tr_query(enriched_query)

    # Speculative emb. ham sorgu için yapıldı; planner enriched_query üretti.
    # Eğer enriched_query ham sorguya çok yakınsa (örn. plan = sorgu kelimeleri),
    # speculative emb'i kullan; aksi halde yeni embedding üret.
    speculative_vec, speculative_cost = await speculative_emb_task

    raw_lower = payload.request_text.strip().lower()
    enriched_lower = enriched_query.strip().lower()
    use_speculative = (
        speculative_vec is not None
        and len(speculative_vec) == 1024
        and (
            enriched_lower == raw_lower
            or enriched_lower.startswith(raw_lower)
            or raw_lower.startswith(enriched_lower)
        )
    )

    query_vec: list[float] | None = None
    emb_cost = 0.0
    if use_speculative:
        query_vec = speculative_vec
        emb_cost = speculative_cost
        logger.info("speculative emb reused (raw≈enriched)")
    else:
        try:
            emb_provider = registry.route_for_tier(operation="embedding", tier="free")
            emb_result = await emb_provider.create_embedding([enriched_query])
            query_vec = emb_result.vectors[0] if emb_result.vectors else None
            emb_cost = float(emb_result.cost_usd)
        except Exception as exc:  # pragma: no cover
            logger.warning("query embedding failed: %s — sparse-only", exc)

    # Timeframe parse (existing logic)
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
                except Exception:  # pragma: no cover
                    continue
            max_span = max(spans_days) if spans_days else 0.0
            if max_span >= 30:
                levels = ("daily", "weekly", "monthly")
            elif max_span >= 6:
                levels = ("daily", "weekly")
            if parsed_ranges:
                timeframe_from = min(r[0] for r in parsed_ranges)
                timeframe_to = max(r[1] for r in parsed_ranges)
    except Exception:  # pragma: no cover
        pass

    # Settings parallel load
    (
        candidate_pool,
        content_temp,
        content_max_tokens,
        citation_thr,
        suggest_enabled,
        content_top_k,
    ) = await asyncio.gather(
        settings_store.get_int(
            db, "rerank.candidate_pool", settings.reranker_candidate_pool
        ),
        settings_store.get_float(db, "llm.content_temperature", 0.5),
        settings_store.get_int(db, "llm.content_max_tokens", 2000),
        settings_store.get_float(db, "citation.cosine_threshold", 0.55),
        settings_store.get_bool(db, "media.suggestion_enabled", False),
        settings_store.get_int(db, "retrieval.content_top_k", 5),
    )
    # MVP-1.8 PR-A: range 3-15 (Perplexity-style geniş kapsam — non-streaming
    # endpoint ile parity, #647 streaming sync).
    content_top_k = max(3, min(15, content_top_k))

    effective_candidate_pool = candidate_pool
    if getattr(plan, "is_short_query", False):
        effective_candidate_pool = min(candidate_pool, 10)

    # MVP-1.8 PR-B (#618) streaming parity (#647): multi-query rewrite + RRF.
    async def _search_variant(qt: str, qvec: list[float] | None) -> list[dict]:
        return await hybrid_search_agenda_cards(
            db,
            query_text=qt,
            query_vector=qvec,
            top_k=content_top_k * 2,
            candidate_pool=effective_candidate_pool,
            levels=levels,
            timeframe_from=timeframe_from,
            timeframe_to=timeframe_to,
            geographic_focus=getattr(plan, "geographic_focus", None),
            pre_normalized=normalize_tr_query(qt),
        )

    if len(query_variants) > 1 and query_vec is not None:
        variant_results = await asyncio.gather(
            *(_search_variant(qt, query_vec) for qt in query_variants),
            return_exceptions=False,
        )
        # RRF füzyon (k=60 standart)
        rrf_scores: dict[str, float] = {}
        card_by_id: dict[str, dict] = {}
        for results in variant_results:
            for rank, card in enumerate(results):
                cid = str(card.get("id", ""))
                if not cid:
                    continue
                rrf_scores[cid] = rrf_scores.get(cid, 0.0) + 1.0 / (60 + rank)
                if cid not in card_by_id:
                    card_by_id[cid] = card
        sorted_ids = sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True)
        agenda_cards_raw = [card_by_id[cid] for cid in sorted_ids[: content_top_k * 2]]
        logger.info(
            "stream multi_query variants=%d total=%d rrf_unique=%d topic=%s",
            len(query_variants),
            sum(len(r) for r in variant_results),
            len(agenda_cards_raw),
            plan.topic_query[:60],
        )
    else:
        agenda_cards_raw = await _search_variant(enriched_query, query_vec)

    # MVP-1.8 PR-A (#616) streaming parity (#647) — Source diversity cap (max
    # 2/domain). Tek-kaynak halüsinasyon koruması + kaynak çeşitliliği.
    domain_counts: dict[str, int] = {}
    agenda_cards: list[dict] = []
    for card in agenda_cards_raw:
        domain = (card.get("source_domain") or card.get("domain") or "").lower()
        if not domain:
            agenda_cards.append(card)
            continue
        if domain_counts.get(domain, 0) < 2:
            agenda_cards.append(card)
            domain_counts[domain] = domain_counts.get(domain, 0) + 1
        if len(agenda_cards) >= content_top_k:
            break
    used_ids = [c["id"] for c in agenda_cards]
    if len(agenda_cards_raw) > len(agenda_cards):
        logger.info(
            "stream source_diversity raw=%d kept=%d (max 2/domain)",
            len(agenda_cards_raw), len(agenda_cards),
        )

    # MVP-1.8 PR-H (#637) streaming parity (#647) — Chunks ALWAYS-ON (90 gün
    # corpus), top_k 15+. Singleton/eski article'lar (kendi agenda'sı yok)
    # ve subtitle-only entity'ler (Bianet "Toprakaltı") chunks üzerinden
    # yakalanır. Önceden: chunks sadece agenda boş ise + 7 gün → körlük.
    supplementary_chunks: list[dict] = []
    try:
        supplementary_chunks = await hybrid_search_chunks(
            db,
            query_text=enriched_query,
            query_vector=query_vec,
            top_k=max(15, content_top_k * 2),
            candidate_pool=candidate_pool,
            since_hours=24 * 90,
            pre_normalized=norm_query,
        )
        logger.info(
            "stream chunks_primary agenda=%d chunks=%d topic=%s (90d)",
            len(agenda_cards), len(supplementary_chunks),
            plan.topic_query[:80],
        )
    except Exception as exc:
        logger.warning("stream chunks_primary failed: %s", exc)
        supplementary_chunks = []

    if not agenda_cards and not supplementary_chunks:
        try:
            gen_row = await db.get(Generation, gen_id)
            if gen_row is not None:
                gen_row.status = "insufficient_data"
                gen_row.warnings = [
                    f"'{plan.topic_query}' konusuyla ilgili kaynak bulunamadı"
                ]
                gen_row.completed_at = datetime.now(UTC)
                await record_usage(
                    db,
                    user_id=user.id,
                    event_type="generation_insufficient",
                    metadata={
                        "path": "hybrid_retrieval",
                        "topic": plan.topic_query[:120],
                    },
                )
                await db.commit()
        except Exception:  # pragma: no cover
            await db.rollback()
        yield _sse(
            "error",
            {
                "code": "INSUFFICIENT_DATA",
                "title": "Kaynak bulunamadı",
                "reason": f"'{plan.topic_query}' için sonuç yok",
                "suggestions": [
                    f"'{plan.topic_query}' konusunu daha geniş anahtar kelimelerle deneyin",
                    "Farklı bir konu deneyin",
                ],
            },
        )
        yield _sse(
            "done", {"generation_id": str(gen_id), "status": "insufficient_data"}
        )
        return

    # 8) Content Generator — STREAMING
    yield _sse(
        "progress",
        {"stage": "generating", "detail": "İçerik üretiliyor", "agenda_count": len(agenda_cards)},
    )

    try:
        provider = registry.route_for_tier(operation="chat", tier=user.tier)  # type: ignore[arg-type]
    except RuntimeError as exc:
        async for ev in _finalize_failed("NO_LLM_PROVIDER", "LLM provider erişilemez", str(exc)):
            yield ev
        return

    # #548 — payload.max_posts:
    #   None  → "Otomatik" — planner.requested_count karar verir
    #   sayı  → kullanıcı bilinçli seçti, planner override etmez
    if payload.max_posts is None:
        effective_max_posts = max(1, getattr(plan, "requested_count", 1) or 1)
    else:
        effective_max_posts = payload.max_posts

    if payload.length:
        from app.prompts.content_generator import resolve_count

        length_count = resolve_count(
            output_type=plan.output_type or "x_post", length=payload.length
        )
        effective_max_posts = length_count

    user_msg = render_content_payload(
        request=payload.request_text,
        retrieval_plan=retrieval_plan_json,
        agenda_cards=agenda_cards,
        supplementary_chunks=supplementary_chunks,
        style_profile=style_profile_rules,
        output_constraints={
            "output_type": plan.output_type,
            "max_posts": effective_max_posts,
            "tone": plan.tone,
            "length": payload.length or "medium",
            "show_sources": payload.show_sources,
            "language": "tr",
        },
    )

    default_system = format_system_prompt(
        max_posts=effective_max_posts,
        output_type=plan.output_type,
        tone=plan.tone,
    )
    content_system = default_system
    try:
        from app.core.prompts_store import prompts_store

        content_system = await prompts_store.get(
            db, "content_generator", default_system
        )
    except Exception:  # pragma: no cover
        pass

    # Provider streaming desteği yoksa fallback yok — önce gözle (current
    # implementation: DeepSeekProvider). Provider stream desteklemiyorsa
    # NotImplementedError yükselir; caller hatayı stream'e error event olarak
    # yansıtır.
    if not hasattr(provider, "generate_text_stream"):
        async for ev in _finalize_failed(
            "STREAM_UNSUPPORTED",
            "Provider streaming desteklemiyor",
            f"provider={provider.name}",
        ):
            yield ev
        return

    raw_buffer: list[str] = []
    extractor = StreamingPostExtractor()
    final_input_tokens = 0
    final_output_tokens = 0
    final_cached_tokens = 0
    final_cost = 0.0
    final_model = ""
    ttfb_emitted = False
    finalizing_emitted = False  # #542 — posts array kapandığında erken sinyal

    try:
        async with track_provider_call(
            db=db,
            provider=provider.name,
            operation="chat",
            user_id=user.id,
            generation_id=gen_id,
        ) as tracker:
            stream_iter = provider.generate_text_stream(
                messages=[
                    Message(role="system", content=content_system),
                    Message(role="user", content=user_msg),
                ],
                max_tokens=content_max_tokens,
                temperature=content_temp,
                json_mode=True,
            )

            async for sc in stream_iter:
                if sc.is_final:
                    final_input_tokens = sc.input_tokens
                    final_output_tokens = sc.output_tokens
                    final_cached_tokens = sc.cached_input_tokens
                    final_cost = sc.cost_usd
                    final_model = sc.model
                    continue

                if sc.delta_text:
                    raw_buffer.append(sc.delta_text)
                    if not ttfb_emitted:
                        ttfb_ms = int((time.perf_counter() - stream_start) * 1000)
                        logger.info(
                            "stream first byte after %dms (gen=%s)",
                            ttfb_ms,
                            gen_id,
                        )
                        ttfb_emitted = True

                    yield _sse("chunk", {"delta": sc.delta_text})

                    new_posts = extractor.feed(sc.delta_text)
                    for idx, post_obj in new_posts:
                        # Validate post shape; emit defensively
                        if not isinstance(post_obj, dict):
                            continue
                        text_field = post_obj.get("text")
                        if not isinstance(text_field, str):
                            continue
                        yield _sse(
                            "post",
                            {
                                "index": idx,
                                "text": text_field,
                                "angle": str(post_obj.get("angle", "")),
                                "char_count": int(post_obj.get("char_count", 0)),
                                "related_agenda_card_ids": list(
                                    post_obj.get("related_agenda_card_ids") or []
                                ),
                            },
                        )

                    # #542 — Posts array `]` ile kapandığında erken sinyal.
                    # DeepSeek hâlâ summary/sources/warnings yazıyor olabilir
                    # (görsel olarak fark edilmez); kullanıcı için post'lar
                    # tamamlandı. Stage'i "finalizing"e çek ki "Yazıyor…"
                    # yerine "Tamamlanıyor…" görsün.
                    if extractor.posts_array_closed and not finalizing_emitted:
                        finalizing_emitted = True
                        yield _sse(
                            "progress",
                            {
                                "stage": "finalizing",
                                "detail": "Tamamlanıyor",
                            },
                        )

            tracker.record(
                input_tokens=final_input_tokens,
                output_tokens=final_output_tokens,
                cached_tokens=final_cached_tokens,
                model=final_model,
                cost_usd=final_cost,
            )
    except Exception as exc:
        async for ev in _finalize_failed(
            "PROVIDER_ERROR", "Üretim başarısız", str(exc)[:200]
        ):
            yield ev
        return

    # 9) Tüm response'u parse et — final yapısal output
    full_response = "".join(raw_buffer)
    parsed = parse_x_post_response(full_response)

    if isinstance(parsed, ContentGenError):
        if parsed.error == "insufficient_data":
            try:
                gen_row = await db.get(Generation, gen_id)
                if gen_row is not None:
                    gen_row.status = "insufficient_data"
                    gen_row.warnings = [parsed.reason]
                    gen_row.completed_at = datetime.now(UTC)
                    await record_usage(
                        db,
                        user_id=user.id,
                        event_type="generation_insufficient",
                        metadata={
                            "path": "generator",
                            "reason": parsed.reason[:200],
                        },
                    )
                    await db.commit()
            except Exception:  # pragma: no cover
                await db.rollback()
            yield _sse(
                "error",
                {
                    "code": "INSUFFICIENT_DATA",
                    "title": "Yetersiz kaynak",
                    "reason": parsed.reason,
                },
            )
            yield _sse(
                "done", {"generation_id": str(gen_id), "status": "insufficient_data"}
            )
            return
        async for ev in _finalize_failed(
            parsed.error.upper(), parsed.reason, parsed.reason
        ):
            yield ev
        return

    yield _sse(
        "parsed",
        {
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
        },
    )

    # 10) Citation + image — paralel post-stream
    yield _sse("progress", {"stage": "validating", "detail": "Doğrulama"})

    citation_warnings: list[str] = []
    citation_meta: dict[str, Any] = {}

    async def _validate_citations() -> None:
        nonlocal citation_warnings, citation_meta
        try:
            source_fragments = [
                SourceFragment(
                    id=i + 1,
                    title=str(card.get("title", ""))[:200],
                    summary=str(card.get("summary", ""))[:600],
                    embedding=card.get("embedding"),
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

            post_texts = [p.text for p in parsed.posts]
            has_summary = bool(parsed.summary)
            all_texts = list(post_texts) + ([parsed.summary] if has_summary else [])

            if all_texts:
                reports = await validate_citations_batch(
                    all_texts,
                    sources=source_fragments,
                    embed_fn=_embed_batch,
                    cosine_threshold=citation_thr,
                )
                for post, report in zip(
                    parsed.posts, reports[: len(post_texts)], strict=False
                ):
                    if report.repair_count:
                        post.text = report.cleaned_text
                        citation_meta.setdefault("repairs", 0)
                        citation_meta["repairs"] += report.repair_count
                    if report.unsupported_count:
                        citation_warnings.append(
                            f"post_unsupported_claims={report.unsupported_count}"
                        )
                if has_summary:
                    sum_report = reports[-1]
                    if sum_report.repair_count:
                        parsed.summary = sum_report.cleaned_text
                        citation_meta["repairs"] = (
                            citation_meta.get("repairs", 0) + sum_report.repair_count
                        )
                    if sum_report.unsupported_count:
                        citation_warnings.append(
                            f"summary_unsupported_claims={sum_report.unsupported_count}"
                        )
        except Exception as exc:  # pragma: no cover
            logger.warning("citation validation failed: %s", exc)

    suggested_dto: SuggestedImagePublic | None = None

    async def _maybe_suggest_image() -> None:
        nonlocal suggested_dto
        try:
            if not suggest_enabled or not parsed.posts:
                return
            min_conf = await settings_store.get_float(
                db, "media.suggestion_min_confidence", 0.15
            )
            source_urls = [
                s.get("url", "") for s in parsed.sources if isinstance(s, dict)
            ]
            article_ids = await article_ids_from_urls(db, urls=source_urls)
            sg: SuggestedImage | None = await suggest_image_for_post(
                db,
                post_text=parsed.posts[0].text,
                article_ids=article_ids,
                min_confidence=min_conf,
            )
            if sg is not None:
                suggested_dto = SuggestedImagePublic(
                    image_id=sg.image_id,
                    article_id=sg.article_id,
                    original_url=sg.original_url,
                    vlm_caption=sg.vlm_caption,
                    depicts=sg.depicts,
                    alt_text=sg.alt_text,
                    score=sg.score,
                    reason=sg.reason,
                )
        except Exception as exc:  # pragma: no cover
            logger.warning("suggest image failed: %s", exc)

    await asyncio.gather(_validate_citations(), _maybe_suggest_image())

    # Citation event'i — citation tamamlandıktan sonra (post text repair'ları dahil)
    yield _sse(
        "citation",
        {
            "repairs": citation_meta.get("repairs", 0),
            "unsupported_warnings": citation_warnings,
            "posts_after_repair": [
                {"index": i, "text": p.text, "char_count": p.char_count}
                for i, p in enumerate(parsed.posts)
            ],
        },
    )

    if suggested_dto is not None:
        yield _sse(
            "image",
            {
                "image_id": str(suggested_dto.image_id),
                "article_id": str(suggested_dto.article_id),
                "original_url": suggested_dto.original_url,
                "vlm_caption": suggested_dto.vlm_caption,
                "depicts": suggested_dto.depicts,
                "alt_text": suggested_dto.alt_text,
                "score": suggested_dto.score,
                "reason": suggested_dto.reason,
            },
        )

    # 11) Persist final state
    try:
        gen_row = await db.get(Generation, gen_id)
        if gen_row is not None:
            gen_row.status = "completed"
            gen_row.completed_at = datetime.now(UTC)
            gen_row.used_agenda_card_ids = used_ids
            gen_row.model_provider = provider.name
            gen_row.model_name = final_model
            gen_row.input_tokens = final_input_tokens
            gen_row.output_tokens = final_output_tokens
            gen_row.cost_estimate_usd = Decimal(str(final_cost))
            gen_row.warnings = list(parsed.warnings) + citation_warnings
            gen_row.output_json = {
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
                "suggested_image": (
                    suggested_dto.model_dump(mode="json") if suggested_dto else None
                ),
                "_prompt_version": CONTENT_PROMPT_VERSION,
                "_citation": citation_meta,
                "_streamed": True,
            }
            await record_usage(
                db,
                user_id=user.id,
                event_type="generation",
                provider=provider.name,
                model=final_model,
                input_tokens=final_input_tokens,
                output_tokens=final_output_tokens,
                cost_usd=final_cost,
                metadata={"output_type": plan.output_type, "stream": True},
            )
            await db.commit()
    except Exception as exc:  # pragma: no cover
        logger.exception("stream finalize failed: %s", exc)
        await db.rollback()

    yield _sse(
        "done",
        {
            "generation_id": str(gen_id),
            "status": "completed",
            "cost_usd": final_cost + emb_cost,
            "completed_at": datetime.now(UTC).isoformat(),
            "ttfb_ms": int((time.perf_counter() - stream_start) * 1000),
        },
    )
