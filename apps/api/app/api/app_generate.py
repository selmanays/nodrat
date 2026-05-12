"""User-facing generation endpoints (#28, #30, #566).

docs/engineering/api-contracts.md §3 (app endpoints)

Endpoints:
    POST   /app/generate                      — Sync MVP-1 generation
    GET    /app/generations                    — Geçmiş listesi
    GET    /app/generations/{id}               — Detay
    POST   /app/generations/{id}/save          — Save (favori)
    DELETE /app/generations/{id}/save          — Unsave
    POST   /app/generations/{id}/flag-halu     — Halüsinasyon raporu
    POST   /app/generations/{id}/copied        — User action: copy (#566)
    POST   /app/generations/{id}/posted        — User action: posted (#566)
    POST   /app/generations/{id}/edited        — User action: edited (#566)
    POST   /app/generations/{id}/regenerated   — User action: regenerated (#566)
    DELETE /app/generations/{id}               — User action: deleted (#566)
    GET    /app/quota                          — Mevcut kota
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings

# #394 MVP-2.1 — batch interface kullanılır; validate_citations citation.py'de korunur
from app.core.citation import (
    SourceFragment,
    validate_citations_batch,
)
from app.core.cost_tracker import track_provider_call
from app.core.data_sufficiency import check_sufficiency
from app.core.db import get_db
from app.core.deps import get_current_user, require_foreign_transfer_consent
from app.core.media_suggest import (
    SuggestedImage,
    article_ids_from_urls,
    suggest_image_for_post,
)
from app.core.quota import (
    QuotaExceeded,
    enforce_quota,
    get_quota_status,
    record_usage,
)
from app.core.settings_store import settings_store
from app.core.text_metrics import normalized_levenshtein_distance
from app.models.generation import Generation, SavedGeneration
from app.models.style_profile import StyleProfile
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
    max_posts: int | None = Field(default=None, ge=1, le=10)
    """#548 — None ise planner.requested_count karar verir; explicit sayı ise
    kullanıcı bilinçli seçti, planner override etmez. Eski davranış
    (sentinel=1 → planner override) kaldırıldı çünkü kullanıcı bilinçli "1"
    seçtiğinde de override oluyordu (CHP özet vakası)."""
    style_profile_id: UUID | None = Field(default=None)
    """#52 Faz 5 — Pro+ tier'da style profile uygulama. Profil status=='ready'
    olmalı; sahibi current user olmalı. Pro tier altında sessizce yok sayılır."""


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


class SuggestedImagePublic(BaseModel):
    """#305 MVP-1.4 PR-5 — generation'a uygun görsel önerisi.

    process & discard: bytes saklanmaz, sadece original_url + VLM metadata.
    Frontend bu URL'i kullanıcıya gösterir; kullanıcı kendisi seçer.
    Telif/atıf: alt+vlm_caption ile birlikte kaynak makale linki gösterilir.
    """

    image_id: UUID
    article_id: UUID
    original_url: str
    vlm_caption: str | None = None
    depicts: list[str] | None = None
    alt_text: str | None = None
    score: float
    reason: str


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

    # #305 MVP-1.4 PR-5 — suggested image (process & discard)
    suggested_image: SuggestedImagePublic | None = None

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
    # #470 — KVKK m.9 server-side gate. LLM provider çağrısı yurt dışına
    # gittiği için açık rıza zorunlu (avukat şartlı onayı, Epic #448).
    user: Annotated[User, Depends(require_foreign_transfer_consent)],
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

    now = datetime.now(UTC)

    # 2) Generation row create (status=running)
    # #52 Faz 5 — Stil profili çözümleme + ownership/Pro paywall server-side
    style_profile_rules: dict[str, Any] | None = None
    style_profile_used_id: UUID | None = None
    if payload.style_profile_id is not None:
        style_profile_rules, style_profile_used_id = await _resolve_style_profile(
            db, user, payload.style_profile_id
        )

    gen = Generation(
        user_id=user.id,
        request_text=payload.request_text,
        mode="current",  # planner'dan güncellenecek
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
        gen.completed_at = datetime.now(UTC)
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

    # #51 — Comparison mode feature flag (Dalga 4 telemetry gate)
    if plan.mode == "comparison":
        try:
            comparison_enabled = await settings_store.get(
                db, "comparison.enabled", default=False
            )
        except Exception:
            comparison_enabled = False
        if not comparison_enabled:
            logger.info(
                "comparison mode downgraded to current (flag off) topic=%s",
                plan.topic_query[:60],
            )
            plan.mode = "current"  # type: ignore[attr-defined]
        else:
            # Telemetry counter — daily comparison usage
            try:
                import time as _t

                from app.api.public_search import _get_redis as _redis

                await _redis().incr(
                    f"comparison.usage:{int(_t.time() // 86400)}"
                )
            except Exception:
                pass

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
        "geographic_focus": getattr(plan, "geographic_focus", None),
        "constraints": plan.constraints,
        "needs_sources": plan.needs_sources,
        "minimum_evidence_per_period": plan.minimum_evidence_per_period,
        "_prompt_version": PLANNER_PROMPT_VERSION,
        "_warnings": plan.warnings,
    }

    # 4) Data sufficiency — #675 + #726 SOFT-GATE
    # check_sufficiency SADECE agenda_cards count'a bakıyor (event_clusters).
    # Chunks-first retrieval (#637) + NER (#667) + summary_emb (#661) sonrası
    # agenda boş olsa BİLE chunks'tan retrieve edebiliriz. Önceki davranış:
    # mode='current' + sufficient=False → erken çıkış → chunks fallback bypass.
    #
    # #726 (2026-05-12): Erken çıkış KALDIRILDI. Sufficiency yalnız TELEMETRİ
    # olarak çalışır; gerçek "kaynak yok" kararı retrieval sonucundan
    # verilir (line ~672: agenda + chunks her ikisi de boşsa insufficient_data).
    # Sebep: "afyon belediye başkanı olayı nedir" planner timeframe='bugün'
    # seçince agenda=0 ama chunks-first 90 gün penceresinde 11 May/8 May
    # cards bulurdu — early exit bunu engelliyordu (#725 tespitten).
    sufficiency = await check_sufficiency(
        db,
        retrieval_plan=gen.retrieval_plan_json,
        min_evidence_per_period=plan.minimum_evidence_per_period,
    )
    _mode_for_sufficiency = (gen.retrieval_plan_json.get("mode") or "current").lower()
    _sufficiency_softfail = (
        _mode_for_sufficiency == "current" and not sufficiency.sufficient
    )
    if _sufficiency_softfail:
        logger.info(
            "sufficiency soft-fail: mode=current agenda yetersiz, chunks-first "
            "fallback'e güveniyor — counts=%s reason=%s",
            sufficiency.counts_per_period,
            sufficiency.reason,
        )

    # 5) Hybrid retrieval (#171 PR-E) — dense + sparse RRF
    # PR-D: dense-only agenda. PR-E: hybrid agenda + chunks supplementary fallback
    from app.core.retrieval import (
        hybrid_search_agenda_cards,
        hybrid_search_chunks,
        normalize_tr_query,
    )

    # MVP-1.8 PR-B + PR-E.1 (#618) — Multi-query rewrite (Perplexity-style).
    # Sıkılaştırıldı: 3. varyant (keywords-only) kaldırıldı çünkü too broad —
    # "Toprakaltı sergisi" sorgusu için planner keywords ['sergi','tünel','kültürel']
    # çıkarınca "tünel sergi" varyantı Slovenya Nova Gorica tünelini çekiyordu.
    # Topic_query her zaman sabit (kullanıcı niyeti); enriched ek context için.
    #   v1: topic_query (orijinal — kullanıcı sorgusu, sıkı match)
    #   v2: topic_query + keywords[:3] (sınırlı genişleme, sıkı kalsın)
    query_variants: list[str] = [plan.topic_query]
    if hasattr(plan, "keywords") and plan.keywords:
        kw_top = plan.keywords[:3]  # 5 → 3 (daha sıkı genişletme)
        query_variants.append(f"{plan.topic_query} {' '.join(kw_top)}")
    enriched_query = query_variants[-1]

    # MVP-1.8 PR-C (#621) — HyDE (Hypothetical Document Embeddings).
    # DeepSeek'a topic_query için 1-2 cümlelik "imagined news headline+lead"
    # üret → bu cevabı embed et → RRF'e ek varyant. Sorgu-cevap asimetrisini
    # azaltır: "Azıcık radyasyon kemiklere yararlıdır" tam başlık olunca,
    # planner topic_query "radyasyon kemikler etkisi" gibi soyut çıkar; HyDE
    # tahmini cevap "Bilim insanları küçük dozda radyasyonun kemik..." gibi
    # daha somut → article başlık embedding'lerine semantic yakın.
    # Feature flag arkasında (default OFF) — A/B rollout için.
    hyde_doc: str | None = None
    try:
        # #652 Faz 3 — default flag OFF→ON. Meta-sorgu ("var mı / ne dedi /
        # nedir") + dolaylı sorgular için kritik recall kazanımı.
        hyde_enabled = await settings_store.get_bool(
            db, "retrieval.hyde_enabled", True
        )
    except Exception:
        hyde_enabled = True
    if hyde_enabled:
        try:
            chat_provider = registry.route_for_tier(operation="chat", tier="free")
            # #720: prompts_store override (admin /prompts editable, {query} zorunlu)
            from app.core.prompts_store import prompts_store
            from app.prompts.hyde import (
                SYSTEM_PROMPT as _HYDE_DEFAULT,
                render_hyde_prompt,
            )
            hyde_template = await prompts_store.get(db, "hyde_doc", _HYDE_DEFAULT)
            hyde_prompt = render_hyde_prompt(plan.topic_query, template=hyde_template)
            hyde_resp = await chat_provider.generate_text(
                messages=[Message(role="user", content=hyde_prompt)],
                max_tokens=120,
                temperature=0.7,
                json_mode=False,
            )
            hyde_doc = (hyde_resp.text or "").strip()
            if hyde_doc:
                query_variants.append(hyde_doc)
                logger.info(
                    "hyde_dispatched len=%d topic=%s",
                    len(hyde_doc), plan.topic_query[:60],
                )
        except Exception as exc:
            logger.warning("hyde generation failed: %s — skip variant", exc)
            hyde_doc = None

    # #397 MVP-2.1 — Türkçe normalize bir kez handler düzeyinde, hybrid_search_*
    # fonksiyonlarına `pre_normalized` ile geç (her function'da tekrar yapılmasın).
    norm_query = normalize_tr_query(enriched_query)

    # Query embedding — tek call, en kapsamlı varyant (enriched_query) için
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

    # #266 — runtime-tunable candidate_pool (DB override → config fallback)
    # #395 MVP-2.1 — request başında ihtiyacımız olan tüm settings'leri paralel yükle.
    # #393 MVP-2.1 — retrieval.content_top_k (default 5, range 3-10) eklendi.
    # L1 cache (process-local 30s TTL) varsa anında, yoksa DB'ye paralel git.
    (
        candidate_pool,
        content_temp,
        content_max_tokens,
        citation_thr,
        suggest_enabled,
        content_top_k,
    ) = await asyncio.gather(
        settings_store.get_int(db, "rerank.candidate_pool", settings.reranker_candidate_pool),
        settings_store.get_float(db, "llm.content_temperature", 0.5),
        settings_store.get_int(db, "llm.content_max_tokens", 1500),  # #684 PR-D
        settings_store.get_float(db, "citation.cosine_threshold", 0.55),
        settings_store.get_bool(db, "media.suggestion_enabled", False),
        settings_store.get_int(db, "retrieval.content_top_k", 5),
    )
    # MVP-1.8 PR-A: range 3-15 (önceden 3-10). Perplexity-style daha geniş kapsam.
    content_top_k = max(3, min(15, content_top_k))

    # #396 MVP-2.1 — Kısa sorgu (≤2 kelime topic_query) için candidate_pool
    # küçült. Cross-encoder rerank zaten skip ediyor; dense+sparse pool
    # 30→10'a inerek embedding+SQL latency düşer (~300ms).
    effective_candidate_pool = candidate_pool
    if getattr(plan, "is_short_query", False):
        effective_candidate_pool = min(candidate_pool, 10)
        logger.info(
            "short_query candidate_pool reduced %d → %d (topic=%s)",
            candidate_pool,
            effective_candidate_pool,
            plan.topic_query[:60],
        )

    # MVP-1.8 PR-B (#618) — Multi-query rewrite paralel arama + RRF füzyon.
    # Her varyant için search → RRF (reciprocal rank fusion, k=60 standart).
    # Bu, dolaylı sorguları yakalar: "Azıcık radyasyon kemiklere yararlıdır"
    # tam başlık variant_1'de match etmese bile, keywords variant_3 yakalar.
    # MVP-1.8 PR-C: HyDE varyantı (varsa) kendi embedding'i ile dense+sparse
    # tam katmanlı arama yapar (ek paralel embedding call).
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
        # MVP-1.8 PR-C — HyDE doc için ayrı embedding (hipotetik cevap-tabanlı arama)
        variant_vecs: list[list[float] | None] = [query_vec] * len(query_variants)
        if hyde_doc and query_variants[-1] == hyde_doc:
            try:
                hyde_emb = await emb_provider.create_embedding([hyde_doc])
                hyde_vec = hyde_emb.vectors[0] if hyde_emb.vectors else None
                if hyde_vec:
                    variant_vecs[-1] = hyde_vec
                    emb_cost += float(hyde_emb.cost_usd)
            except Exception as exc:
                logger.warning("hyde embedding failed: %s", exc)
        variant_results = await asyncio.gather(
            *(_search_variant(qt, variant_vecs[i]) for i, qt in enumerate(query_variants)),
            return_exceptions=False,
        )
        # RRF füzyon
        rrf_scores: dict[str, float] = {}
        card_by_id: dict[str, dict] = {}
        for variant_idx, results in enumerate(variant_results):
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
            "multi_query variants=%d total_cards=%d rrf_unique=%d topic=%s",
            len(query_variants),
            sum(len(r) for r in variant_results),
            len(agenda_cards_raw),
            plan.topic_query[:60],
        )
    else:
        agenda_cards_raw = await _search_variant(enriched_query, query_vec)

    # MVP-1.8 PR-A (#616) — Source diversity: aynı domain'den max 2 kart.
    # Tek-kaynak halüsinasyon riskini azaltır + kaynak çeşitliliği sağlar.
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
            "source_diversity raw=%d kept=%d (max 2/domain) topic=%s",
            len(agenda_cards_raw), len(agenda_cards), plan.topic_query[:60],
        )

    # MVP-1.8 PR-H (#637) — Chunks-first retrieval (Plan A — kök çözüm).
    # Önceden: chunks fallback (agenda<3 ise, 7 gün penceresi). Sonuç:
    # singleton article'lar (kendi agenda_card'ı olmayan, örn. Northrop F-16)
    # ve eski article'lar (>7 gün) RAG'da görünmüyordu.
    # Yeni: chunks ALWAYS-ON, 90 gün penceresi, geniş top_k. agenda_cards
    # secondary kalır (event/kategori özeti). 3800+ cleaned article hazinesi
    # arama uzayında.
    supplementary_chunks: list[dict] = []
    try:
        # #652 Faz 2 — self-query date filter: planner spesifik tarih
        # çıkardıysa BETWEEN filter, yoksa 90 gün since window.
        supplementary_chunks = await hybrid_search_chunks(
            db,
            query_text=enriched_query,
            query_vector=query_vec,
            top_k=max(10, content_top_k * 2),  # #684 PR-D: 15→10 (parent-doc ile context genişler)
            candidate_pool=candidate_pool,
            since_hours=24 * 90,  # 7 gün → 90 gün (3 ay corpus)
            timeframe_from=timeframe_from,
            timeframe_to=timeframe_to,
            pre_normalized=norm_query,
        )
        logger.info(
            "chunks_primary agenda=%d chunks=%d topic=%s (tf=%s..%s)",
            len(agenda_cards), len(supplementary_chunks),
            plan.topic_query[:80],
            timeframe_from.isoformat() if timeframe_from else "90d",
            timeframe_to.isoformat() if timeframe_to else "now",
        )
    except Exception as exc:
        logger.warning("chunks_primary failed: %s", exc)
        supplementary_chunks = []

    logger.info(
        "retrieval cards=%d chunks=%d topic=%s",
        len(agenda_cards),
        len(supplementary_chunks),
        plan.topic_query[:80],
    )

    # Hem agenda hem chunks boş → insufficient_data
    # #726: Eğer sufficiency soft-fail tetiklendiyse retrieval yine de denedi;
    # buraya geldiysek sufficiency önerilerini kullanıcıya gösterelim.
    if not agenda_cards and not supplementary_chunks:
        gen.status = "insufficient_data"
        gen.warnings = [
            f"'{plan.topic_query}' konusuyla ilgili kaynak bulunamadı "
            "(hybrid search dense+sparse fail)"
        ]
        gen.completed_at = datetime.now(UTC)
        await record_usage(
            db,
            user_id=user.id,
            event_type="generation_insufficient",
            metadata={
                "path": "hybrid_retrieval",
                "topic": plan.topic_query[:120],
                "sufficiency_softfail": _sufficiency_softfail,
            },
        )
        await db.commit()
        _suggestions = (
            sufficiency.suggestions
            if _sufficiency_softfail and sufficiency.suggestions
            else [
                f"'{plan.topic_query}' konusunu daha geniş anahtar kelimelerle tekrar deneyin",
                "Farklı bir konu deneyin (gündemde yer alan başka bir başlık)",
            ]
        )
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
            suggestions=_suggestions,
            cost_usd=emb_cost,
            created_at=gen.created_at,
            completed_at=gen.completed_at,
        )
    # #726: Soft-fail durumunda chunks-first retrieval kurtardı → warning ekle.
    # SQLAlchemy JSONB column'da in-place append() ORM "modified" sinyalini
    # tetiklemez; reassignment ile yeni liste yarat ki commit persist olsun.
    if _sufficiency_softfail:
        gen.warnings = list(gen.warnings or []) + [
            "Planner timeframe penceresinde agenda card yetersizdi; "
            "geniş retrieval (chunks 90 gün) ile cevap üretildi."
        ]

    # 6) Content generator
    try:
        provider = registry.route_for_tier(operation="chat", tier=user.tier)  # type: ignore[arg-type]
    except RuntimeError as exc:
        gen.status = "failed"
        gen.warnings = [f"no_provider: {exc}"]
        gen.completed_at = datetime.now(UTC)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "NO_LLM_PROVIDER", "title": "LLM provider erişilemez"},
        ) from exc

    # #548 — payload.max_posts:
    #   None  → "Otomatik" — planner.requested_count karar verir
    #   sayı  → kullanıcı bilinçli seçti, planner override etmez
    if payload.max_posts is None:
        effective_max_posts = max(1, getattr(plan, "requested_count", 1) or 1)
        logger.info(
            "max_posts auto: planner=%d topic=%s",
            effective_max_posts,
            plan.topic_query[:60],
        )
    else:
        effective_max_posts = payload.max_posts

    # #74 — length parametresi varsa output_type'a göre count override
    if payload.length:
        from app.prompts.content_generator import resolve_count

        length_count = resolve_count(
            output_type=plan.output_type or "x_post", length=payload.length
        )
        # Length kullanıcı tarafı net ifade — planner'ı override et
        effective_max_posts = length_count
        logger.info(
            "length override: length=%s output_type=%s count=%d",
            payload.length, plan.output_type, length_count,
        )

    user_msg = render_content_payload(
        request=payload.request_text,
        retrieval_plan=gen.retrieval_plan_json,
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

    try:
        async with track_provider_call(
            db=db,
            provider=provider.name,
            operation="chat",
            user_id=user.id,
            generation_id=gen.id,
        ) as tracker:
            # #270 — runtime temperature override (önceden yüklendi #395)
            # content_temp ve content_max_tokens üst handler scope'unda paralel
            # yüklendi; burada sadece kullan, tekrar settings_store çağırma.

            # #270 PR-B — runtime prompt override (varsayılan: format_system_prompt)
            # #392 MVP-2.1 — system prompt artık STATIC: max_posts/tone user
            # payload'undaki output_constraints'a eklendi.
            # #720 — content_generator output_type başına ayrı prompt:
            #   x_post / summary / thread / headline (admin /prompts'tan editable)
            default_system = format_system_prompt(
                max_posts=effective_max_posts,
                output_type=plan.output_type,
                tone=plan.tone,
            )
            content_system = default_system
            try:
                from app.core.prompts_store import prompts_store

                _content_prompt_name = {
                    "summary": "content_generator_summary",
                    "thread": "content_generator_thread",
                    "headline": "content_generator_headline",
                }.get(plan.output_type, "content_generator_x_post")

                content_system = await prompts_store.get(
                    db, _content_prompt_name, default_system
                )
            except Exception:  # pragma: no cover
                pass

            generation_call = await provider.generate_text(
                messages=[
                    Message(role="system", content=content_system),
                    Message(role="user", content=user_msg),
                ],
                max_tokens=content_max_tokens,
                temperature=content_temp,
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
        gen.completed_at = datetime.now(UTC)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "PROVIDER_ERROR", "title": "Üretim başarısız", "reason": str(exc)[:200]},
        ) from exc

    parsed = parse_x_post_response(generation_call.text)

    # MVP-1.8 PR-I — Empty-posts guard KALDIRILDI.
    # PR-G başta agresif (posts=[]+summary dolu→insufficient), PR-H gevşek
    # (>150 char), PR-I tamamen KALDIRILDI çünkü:
    # - F-16 vakası (alakalı tek kaynak) hâlâ eleniyordu
    # - Toprakaltı koruması zaten content_generator prompt #13'te
    #   "irrelevant_sources" warning ile çalışıyor (Test 2 başarılı)
    # - LLM kararsız davranışı için failsafe: summary varsa posts'a fallback
    #
    # YENİ FAILSAFE — auto-post fallback:
    # LLM summary üretti ama posts=[] döndü → summary'i 1 post olarak kullan
    # (kullanıcı içeriği görür, "yetersiz veri" yerine cevap)
    if (
        not isinstance(parsed, ContentGenError)
        and not parsed.posts
        and parsed.summary
        and "irrelevant_sources" not in (parsed.warnings or [])
    ):
        # MVP-1.8 PR-M — PR-L kaldırıldı (Türkçe weak — F-16 false negative,
        # Toprakaltı false positive). Toprakaltı koruması artık prompt #13
        # alaka kontrolünde ağırlaştırılmış konkret örneklerle yapılıyor.
        # Auto-post fallback (LLM kararsız → summary'i 1 post wrap):
        from app.prompts.content_generator import XPost

        post_text = parsed.summary[:1000].strip()
        # PR-I2: parsed.sources dict listesi, .id yok — agenda_cards.id kullan
        related_ids = [str(c.get("id", "")) for c in agenda_cards[:5] if c.get("id")]
        parsed.posts = [
            XPost(
                text=post_text,
                angle="auto-fallback",
                char_count=len(post_text),
                related_agenda_card_ids=related_ids,
            )
        ]
        logger.info(
            "auto_post_fallback: posts=0 → wrapped summary (%d char) topic=%s",
            len(post_text), plan.topic_query[:60],
        )

    if isinstance(parsed, ContentGenError):
        # #159: insufficient_data / irrelevant_sources için 200 OK +
        # GenerationResponse (planner sufficiency path ile tutarlı)
        if parsed.error == "insufficient_data":
            gen.status = "insufficient_data"
            gen.warnings = [parsed.reason]
            gen.completed_at = datetime.now(UTC)
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
        gen.completed_at = datetime.now(UTC)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": parsed.error.upper(), "title": parsed.reason},
        )

    # 6.5) Citation validation (#180) — repair format + embedding-based evidence check
    # #398 MVP-2.1 — agenda_cards.embedding (DB) → SourceFragment.embedding,
    # citation validation re-embed yapmaz; sadece post text'leri embed edilir.
    citation_warnings: list[str] = []
    citation_meta: dict[str, Any] = {}
    try:
        source_fragments = [
            SourceFragment(
                id=i + 1,
                title=str(card.get("title", ""))[:200],
                summary=str(card.get("summary", ""))[:600],
                embedding=card.get("embedding"),  # list[float]|None — retrieval.py:_parse_pgvector_text
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

        # #271 — runtime citation threshold override
        # citation_thr üst handler scope'unda paralel yüklendi (#395 MVP-2.1)

        # #394 MVP-2.1 — TÜM post.text + summary tek mega-batch'te embed edilir.
        # Önceden N post için N ayrı validate_citations + N ayrı embedding API call;
        # şimdi tek batch içinde.
        post_texts: list[str] = [p.text for p in parsed.posts]
        has_summary = bool(parsed.summary)
        all_texts = list(post_texts) + ([parsed.summary] if has_summary else [])

        if all_texts:
            reports = await validate_citations_batch(
                all_texts,
                sources=source_fragments,
                embed_fn=_embed_batch,
                cosine_threshold=citation_thr,
            )
            # Post raporları
            for post, report in zip(parsed.posts, reports[: len(post_texts)]):
                if report.repair_count:
                    post.text = report.cleaned_text
                    citation_meta.setdefault("repairs", 0)
                    citation_meta["repairs"] += report.repair_count
                if report.unsupported_count:
                    citation_warnings.append(
                        f"post_unsupported_claims={report.unsupported_count}"
                    )
            # Summary raporu (varsa son)
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
    except Exception as cit_exc:  # pragma: no cover
        logger.warning("citation validation skipped: %s", cit_exc)

    # 6.5) #305 MVP-1.4 PR-5 — suggested image (process & discard)
    # Settings flag ile koşullu, X post için 1. post text'i kullanılır.
    # suggest_enabled üst handler scope'unda paralel yüklendi (#395 MVP-2.1)
    suggested_dto: SuggestedImagePublic | None = None
    try:
        if suggest_enabled and parsed.posts:
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
    except Exception as suggest_exc:  # pragma: no cover — never break generate
        logger.warning("media suggest skipped: %s", suggest_exc)

    # 7) Persist
    gen.status = "completed"
    gen.completed_at = datetime.now(UTC)
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
        # #305 — suggested image meta persistance (history'de görünsün)
        "suggested_image": (
            suggested_dto.model_dump(mode="json") if suggested_dto else None
        ),
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
        # #305 — suggested image (process & discard)
        suggested_image=suggested_dto,
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

    # #305 — suggested_image history'den geri okunur
    suggested_raw = output.get("suggested_image")
    suggested_dto: SuggestedImagePublic | None = None
    if isinstance(suggested_raw, dict):
        try:
            suggested_dto = SuggestedImagePublic.model_validate(suggested_raw)
        except Exception:  # pragma: no cover — backward compat
            suggested_dto = None

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
        # #305 — suggested image
        suggested_image=suggested_dto,
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
    gen.saved_at = datetime.now(UTC)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        # Already saved → idempotent
        gen.saved_at = gen.saved_at or datetime.now(UTC)
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

    gen.halu_flagged_at = datetime.now(UTC)
    gen.halu_flagged_by = user.id

    # Add reason to warnings
    reason = (payload.reason or "user_reported").strip()[:500]
    warnings_list = list(gen.warnings or [])
    warnings_list.append(f"halu_flag: {reason}")
    gen.warnings = warnings_list

    await db.commit()
    return {"status": "flagged", "generation_id": str(gen.id)}


# ============================================================================
# User actions (SFT telemetry, #566)
# ============================================================================
#
# Trendyol-LLM-7B-chat-v4.1.0 üzerine domain-spesifik fine-tune için
# altın etiketleme sinyalleri. Her action sonrası generations.user_action +
# action_at + time_to_action_sec + (varsa) edited_text + edit_distance
# güncellenir; ardından _recompute_sft_eligibility yeniden hesaplar.
#
# Bağlı: wiki/concepts/sft-data-pipeline.md, wiki/decisions/own-slm-strategy.md


SFT_REVIEW_BUFFER_DAYS = 7
SFT_EDIT_DISTANCE_THRESHOLD = Decimal("0.05")
SFT_ELIGIBLE_ACTIONS: frozenset[str] = frozenset({"copied", "posted"})
SFT_USER_ACTION_VALUES: frozenset[str] = frozenset(
    {"copied", "posted", "edited", "regenerated", "kept", "deleted"}
)


class EditedRequest(BaseModel):
    edited_text: str = Field(min_length=1, max_length=20000)


@router.post(
    "/generations/{generation_id}/copied",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="User action: copy-to-clipboard (SFT telemetry)",
)
async def action_copied(
    generation_id: Annotated[UUID, Path()],
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    gen = await db.get(Generation, generation_id)
    if gen is None or gen.user_id != user.id:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND"})
    _apply_user_action(gen, user, "copied")
    await db.commit()


@router.post(
    "/generations/{generation_id}/posted",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="User action: paylaşıldı (X / başka platform)",
)
async def action_posted(
    generation_id: Annotated[UUID, Path()],
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    gen = await db.get(Generation, generation_id)
    if gen is None or gen.user_id != user.id:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND"})
    _apply_user_action(gen, user, "posted")
    await db.commit()


@router.post(
    "/generations/{generation_id}/edited",
    status_code=status.HTTP_200_OK,
    summary="User action: kullanıcı düzenledi (DPO için)",
)
async def action_edited(
    generation_id: Annotated[UUID, Path()],
    payload: EditedRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    gen = await db.get(Generation, generation_id)
    if gen is None or gen.user_id != user.id:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND"})
    _apply_user_action(gen, user, "edited", edited_text=payload.edited_text)
    await db.commit()
    return {
        "status": "edited",
        "edit_distance": (
            float(gen.edit_distance) if gen.edit_distance is not None else None
        ),
        "sft_eligible": gen.sft_eligible,
        "sft_excluded_reason": gen.sft_excluded_reason,
    }


@router.post(
    "/generations/{generation_id}/regenerated",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="User action: yeniden üret (negatif sinyal)",
)
async def action_regenerated(
    generation_id: Annotated[UUID, Path()],
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    gen = await db.get(Generation, generation_id)
    if gen is None or gen.user_id != user.id:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND"})
    _apply_user_action(gen, user, "regenerated")
    await db.commit()


@router.delete(
    "/generations/{generation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="User action: sil (negatif sinyal)",
)
async def action_delete_generation(
    generation_id: Annotated[UUID, Path()],
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Soft delete sinyali — generations.user_action='deleted'.

    Generation row silinmez; SFT pipeline'da `wrong_action` ile
    excluded edilir. Hard delete KVKK self-service `DELETE /app/me`
    üzerinden tüm generations.user_id=X cascade ile yapılır.
    """
    gen = await db.get(Generation, generation_id)
    if gen is None or gen.user_id != user.id:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND"})
    _apply_user_action(gen, user, "deleted")
    await db.commit()


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


# ============================================================================
# #52 — Style profile helpers (Faz 5)
# ============================================================================


async def _resolve_style_profile(
    db: AsyncSession, user: User, profile_id: UUID
) -> tuple[dict[str, Any] | None, UUID | None]:
    """Style profile'ı doğrula + Pro paywall + status check.

    Returns (rules_json, profile_id_to_persist). Pro tier'da değilse veya
    profil bulunamazsa 402/404 atar. status != 'ready' ise warning ile
    None döner — generation profilsiz devam eder.
    """
    # Pro tier paywall — server-side enforcement (#52, #522)
    # User.tier authoritative; subscription yoksa tier→plan_code fallback (#522)
    from app.core.plan_features import resolve_user_plan_features

    plan_features, plan_code = await resolve_user_plan_features(db, user)

    if not plan_features.get("style_profiles", False):
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "code": "STYLE_PROFILES_REQUIRES_PRO",
                "message": (
                    "Stil profili kullanımı Pro tier'da kullanıma açıktır. "
                    "Planınızı yükselterek bu özelliği kullanabilirsiniz."
                ),
                "current_plan": plan_code,
            },
        )

    profile = await db.get(StyleProfile, profile_id)
    if profile is None or profile.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "STYLE_PROFILE_NOT_FOUND",
                "message": "Stil profili bulunamadı.",
            },
        )

    if profile.status != "ready":
        # Hazır değil → profil yokmuş gibi devam et, warning log
        logger.info(
            "style_profile not ready user=%s pid=%s status=%s",
            user.id,
            profile.id,
            profile.status,
        )
        return None, None

    return profile.rules_json or None, profile.id


# ============================================================================
# SFT eligibility helpers (#566)
# ============================================================================


def _extract_original_text(gen: Generation) -> str:
    """output_json'dan kullanıcıya gösterilen orijinal metni çıkar.

    Edit distance hesabı için kullanılır — kullanıcının nihai metni
    (edited_text) ile bu orijinal arasında Levenshtein normalize.

    Output şemaları (parse_x_post_response):
      - posts:     list of {text|post: str, ...}
      - summary_doc: {title, items[]: {event, ...}}
      - summary:   düz string
    """
    output = gen.output_json or {}

    posts = output.get("posts")
    if isinstance(posts, list):
        texts: list[str] = []
        for p in posts:
            if isinstance(p, dict):
                t = p.get("text") or p.get("post") or ""
                if isinstance(t, str) and t:
                    texts.append(t)
        if texts:
            return "\n\n".join(texts)

    summary_doc = output.get("summary_doc")
    if isinstance(summary_doc, dict):
        parts: list[str] = []
        title = summary_doc.get("title")
        if isinstance(title, str) and title:
            parts.append(title)
        items = summary_doc.get("items", [])
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict):
                    event = item.get("event")
                    if isinstance(event, str) and event:
                        parts.append(event)
        if parts:
            return "\n".join(parts)

    summary_text = output.get("summary")
    if isinstance(summary_text, str):
        return summary_text

    return ""


def _recompute_sft_eligibility(
    gen: Generation, user: User
) -> tuple[bool, str | None]:
    """SFT eligibility kuralı — 7 koşul.

    `wiki/concepts/sft-data-pipeline.md`'deki kanonik kural seti.

    Returns: (eligible, excluded_reason)
        eligible=True ise excluded_reason=None.
        eligible=False ise excluded_reason ∈ {
            'wrong_status', 'no_consent', 'consent_revoked',
            'wrong_action', 'edit_too_large', 'halu_flagged',
            'review_buffer'
        }
    """
    if gen.status != "completed":
        return (False, "wrong_status")
    if user.model_improvement_consent_at is None:
        return (False, "no_consent")
    if user.model_improvement_consent_revoked_at is not None:
        return (False, "consent_revoked")
    if gen.user_action not in SFT_ELIGIBLE_ACTIONS:
        return (False, "wrong_action")
    if (
        gen.edit_distance is not None
        and gen.edit_distance >= SFT_EDIT_DISTANCE_THRESHOLD
    ):
        return (False, "edit_too_large")
    if gen.halu_flagged_at is not None:
        return (False, "halu_flagged")

    review_cutoff = datetime.now(UTC) - timedelta(days=SFT_REVIEW_BUFFER_DAYS)
    if gen.created_at >= review_cutoff:
        return (False, "review_buffer")

    return (True, None)


def _apply_user_action(
    gen: Generation,
    user: User,
    action: str,
    *,
    edited_text: str | None = None,
) -> None:
    """User action'ı generation kaydına işle + SFT eligibility recompute.

    - user_action overwrite (en son action kazanır)
    - action_at + time_to_action_sec yeniden hesapla
    - 'edited' ise edited_text + edit_distance set et
    - sft_eligible + sft_excluded_reason yeniden hesapla
    """
    if action not in SFT_USER_ACTION_VALUES:
        raise ValueError(f"invalid user_action: {action}")

    now = datetime.now(UTC)
    gen.user_action = action
    gen.action_at = now

    if gen.completed_at is not None:
        delta = now - gen.completed_at
        gen.time_to_action_sec = max(0, int(delta.total_seconds()))

    if action == "edited" and edited_text is not None:
        gen.edited_text = edited_text
        original = _extract_original_text(gen)
        if original:
            distance = normalized_levenshtein_distance(original, edited_text)
            gen.edit_distance = round(Decimal(str(distance)), 3)

    eligible, reason = _recompute_sft_eligibility(gen, user)
    gen.sft_eligible = eligible
    gen.sft_excluded_reason = reason
