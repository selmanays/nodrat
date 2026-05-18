"""Admin LLM prompts endpoint'leri (#270 PR-B, MVP-1.2).

docs/engineering/api-contracts.md (admin/prompts)
docs/engineering/data-model.md (app_prompts + app_prompt_history)

Endpoints:
    GET    /admin/prompts                    — Bilinen prompts list
    GET    /admin/prompts/{name}             — Detay (current + meta)
    GET    /admin/prompts/{name}/history     — Version history
    PUT    /admin/prompts/{name}             — Yeni versiyon
    DELETE /admin/prompts/{name}             — Default'a dön (history korunur)
    POST   /admin/prompts/{name}/restore     — Geçmiş bir version'ı current yap

require_admin tüm endpoint'lerde. Audit log her değişiklikte.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import get_client_ip, require_admin
from app.core.prompts_store import prompts_store
from app.models.job import AdminAuditLog
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter()


# =============================================================================
# PROMPT_REGISTRY — known prompts + default fallback
# =============================================================================
# Yeni prompt eklenirken:
#  1) Buraya ekle (default kod modülünden import edilir)
#  2) İlgili kodda prompts_store.get(...) ile çek
#
# pipeline metadata (#720): UI sekmelendirmesi için
#   "ingestion" → Haber işleme (scraper → clean → embed → cluster → agenda)
#   "generate"  → Generate (user query → plan → retrieve → content)


def _default_query_planner() -> str:
    from app.prompts.query_planner import SYSTEM_PROMPT

    return SYSTEM_PROMPT


def _default_agenda_card() -> str:
    from app.prompts.agenda_card import SYSTEM_PROMPT

    return SYSTEM_PROMPT


def _default_content_generator_x_post() -> str:
    from app.prompts.content_generator import SYSTEM_PROMPT_X_POST

    return SYSTEM_PROMPT_X_POST


def _default_content_generator_summary() -> str:
    from app.prompts.content_generator import SYSTEM_PROMPT_SUMMARY

    return SYSTEM_PROMPT_SUMMARY


def _default_content_generator_thread() -> str:
    from app.prompts.content_generator import SYSTEM_PROMPT_THREAD

    return SYSTEM_PROMPT_THREAD


def _default_content_generator_headline() -> str:
    from app.prompts.content_generator import SYSTEM_PROMPT_HEADLINE

    return SYSTEM_PROMPT_HEADLINE


def _default_ner_extraction() -> str:
    from app.prompts.ner import SYSTEM_PROMPT

    return SYSTEM_PROMPT


def _default_weekly_summary() -> str:
    from app.prompts.weekly_summary import SYSTEM_PROMPT

    return SYSTEM_PROMPT


def _default_country_backfill() -> str:
    from app.prompts.country_backfill import SYSTEM_PROMPT

    return SYSTEM_PROMPT


def _default_style_analyzer() -> str:
    from app.prompts.style_analyzer import SYSTEM_PROMPT

    return SYSTEM_PROMPT


def _default_hyde() -> str:
    from app.prompts.hyde import SYSTEM_PROMPT

    return SYSTEM_PROMPT


def _default_chat_nodrat_agent() -> str:
    from app.prompts.chat_answer import SYSTEM_PROMPT_NODRAT_AGENT

    return SYSTEM_PROMPT_NODRAT_AGENT


def _default_chat_query_rewrite() -> str:
    from app.prompts.query_rewrite import REWRITE_SYSTEM_PROMPT

    return REWRITE_SYSTEM_PROMPT


PROMPT_REGISTRY: dict[str, dict[str, Any]] = {
    # === HABER İŞLEME (ingestion pipeline, scraper → agenda) ============
    "ner_extraction": {
        "default_factory": _default_ner_extraction,
        "description": (
            "Article cleaned_text + title'dan özel ad + sayısal niş entity "
            "çıkarımı. JSON array output (person/place/org/event/money/number). "
            "Faz 6.1 NER pipeline; niş entity recall sıçraması için kritik."
        ),
        "model_hint": "deepseek-v4-flash",
        "pipeline": "ingestion",
        "order": 10,
    },
    "agenda_card": {
        "default_factory": _default_agenda_card,
        "description": (
            "Cluster + article'lardan agenda card (özet + key_points + "
            "importance + country) üretim prompt'u."
        ),
        "model_hint": "deepseek-v4-flash",
        "pipeline": "ingestion",
        "order": 20,
    },
    "agenda_country_backfill": {
        "default_factory": _default_country_backfill,
        "description": (
            "Agenda card NULL country alanını ISO 3166-1 alpha-2 kodu olarak "
            "doldurma. Tek harf cevap (örn. 'TR', 'US', 'null')."
        ),
        "model_hint": "deepseek-v4-flash",
        "pipeline": "ingestion",
        "order": 30,
    },
    "weekly_summary": {
        "default_factory": _default_weekly_summary,
        "description": (
            "RAPTOR weekly cluster özetleyici — 8-12 daily card'dan haftalık "
            "tema synthesize eder. JSON output."
        ),
        "model_hint": "deepseek-v4-flash",
        "pipeline": "ingestion",
        "order": 40,
    },
    "style_analyzer": {
        "default_factory": _default_style_analyzer,
        "description": (
            "Style profile worker — kullanıcı örnek metinlerinden yazım stili "
            "(ton, kelime hazinesi, cümle yapısı) JSON profili çıkarır."
        ),
        "model_hint": "deepseek-v4-flash",
        "pipeline": "ingestion",
        "order": 50,
    },
    # === CHAT (agentic generate — #845/#848/#851/#854) =================
    "chat_nodrat_agent": {
        "default_factory": _default_chat_nodrat_agent,
        "description": (
            "GÜNCEL chat ana sistem prompt'u (Nodrat agentic). LLM "
            "search_news + search_wikipedia tool'larını çok-turlu "
            "orkestre eder; kimlik/güncel-tarih/C1/öz-düzeltme/yorum-"
            "yasağı kuralları. `{current_date}` placeholder runtime'da "
            "gerçek tarihle doldurulur (silinmemeli)."
        ),
        "model_hint": "deepseek-v4-flash",
        "pipeline": "generate",
        "order": 5,
    },
    "chat_query_rewrite": {
        "default_factory": _default_chat_query_rewrite,
        "description": (
            "Multi-turn condense — follow-up mesajı standalone arama "
            "sorgusuna çevirir (#833). Asistan/kimlik/meta soruları "
            "topic-follow-up DEĞİL (#851); talimat-odaklı follow-up "
            "önceki soruyu taşır (#854). Yardımcı adım (timeout'lu)."
        ),
        "model_hint": "deepseek-v4-flash",
        "pipeline": "generate",
        "order": 8,
    },
    # === GENERATE (legacy /app/generate X-post + retrieval makinesi) ====
    "query_planner": {
        "default_factory": _default_query_planner,
        "description": (
            "Kullanıcı isteğini intent + topic + timeframe + output_type'a "
            "ayrıştıran planner prompt. JSON output. (Chat'te search_news "
            "tool'unun İÇİNDE retrieval makinesi olarak kullanılır — #845.)"
        ),
        "model_hint": "deepseek-v4-flash",
        "pipeline": "generate",
        "order": 10,
    },
    "hyde_doc": {
        "default_factory": _default_hyde,
        "description": (
            "HyDE (Hypothetical Document Embeddings) — query'den 1-2 cümlelik "
            "hipotetik haber paragrafı üretir, semantic uzayda recall yardımcısı. "
            "{query} placeholder zorunlu (silinirse default'a düşer)."
        ),
        "model_hint": "deepseek-v4-flash",
        "pipeline": "generate",
        "order": 20,
    },
    "content_generator_x_post": {
        "default_factory": _default_content_generator_x_post,
        "description": (
            "X post (kısa, tweet-tarzı) üretim prompt'u. Citation + 25 kelime "
            "quote cap. Static prefix (DeepSeek implicit cache hit için)."
        ),
        "model_hint": "deepseek-v4-flash",
        "pipeline": "generate",
        "order": 30,
    },
    "content_generator_summary": {
        "default_factory": _default_content_generator_summary,
        "description": (
            "Summary modu üretim prompt'u — multi-event briefing (tarih + "
            "olay + kaynak yapısında array)."
        ),
        "model_hint": "deepseek-v4-flash",
        "pipeline": "generate",
        "order": 40,
    },
    "content_generator_thread": {
        "default_factory": _default_content_generator_thread,
        "description": ("Thread modu üretim prompt'u — bağlantılı 3-7 post zinciri."),
        "model_hint": "deepseek-v4-flash",
        "pipeline": "generate",
        "order": 50,
    },
    "content_generator_headline": {
        "default_factory": _default_content_generator_headline,
        "description": ("Headline modu üretim prompt'u — manşet-tarzı tek satır + alt başlık."),
        "model_hint": "deepseek-v4-flash",
        "pipeline": "generate",
        "order": 60,
    },
}


# =============================================================================
# Pydantic schemas
# =============================================================================


class PromptDTO(BaseModel):
    name: str
    version: int
    content: str
    default: str
    description: str | None
    model_hint: str | None
    is_overridden: bool
    updated_at: str | None
    updated_by: str | None
    pipeline: str | None = None  # #720: "ingestion" | "generate"
    order: int | None = None  # #720: sort within pipeline


class PromptListResponse(BaseModel):
    data: list[PromptDTO]
    pipelines: list[str] = Field(default_factory=list)  # #720: UI tab listesi


class PromptHistoryItem(BaseModel):
    id: str
    name: str
    version: int
    content: str
    updated_by: str | None
    created_at: str


class PromptHistoryResponse(BaseModel):
    data: list[PromptHistoryItem]


class PromptUpdate(BaseModel):
    content: str = Field(..., min_length=10, max_length=20000)
    description: str | None = None
    model_hint: str | None = None


# =============================================================================
# Helpers
# =============================================================================


def _resolve_default(name: str) -> str:
    if name not in PROMPT_REGISTRY:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "NOT_FOUND",
                "title": "Prompt bulunamadı",
                "name": name,
            },
        )
    factory = PROMPT_REGISTRY[name]["default_factory"]
    try:
        return factory()
    except Exception as exc:  # pragma: no cover
        logger.error("prompt default load fail name=%s err=%s", name, exc)
        return ""


async def _audit(
    db: AsyncSession,
    *,
    actor_id: UUID,
    ip: str | None,
    action: str,
    name: str,
    old_version: int | None,
    new_version: int | None,
) -> None:
    db.add(
        AdminAuditLog(
            actor_id=actor_id,
            action=action,
            target_type="app_prompt",
            target_id=None,
            ip_address=ip,
            event_metadata={
                "prompt_name": name,
                "old_version": old_version,
                "new_version": new_version,
            },
        )
    )


# =============================================================================
# Endpoints
# =============================================================================


@router.get(
    "",
    response_model=PromptListResponse,
    summary="Tüm bilinen LLM prompts",
)
async def list_prompts(
    user: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PromptListResponse:
    overrides = await prompts_store.list(db)
    overrides_by_name = {o.name: o for o in overrides}
    items: list[PromptDTO] = []
    pipelines: set[str] = set()
    for name, meta in PROMPT_REGISTRY.items():
        ovr = overrides_by_name.get(name)
        default_content = _resolve_default(name)
        pipeline = meta.get("pipeline")
        if pipeline:
            pipelines.add(pipeline)
        items.append(
            PromptDTO(
                name=name,
                version=ovr.version if ovr else 0,
                content=ovr.content if ovr else default_content,
                default=default_content,
                description=ovr.description if ovr and ovr.description else meta.get("description"),
                model_hint=ovr.model_hint if ovr and ovr.model_hint else meta.get("model_hint"),
                is_overridden=ovr is not None,
                updated_at=ovr.updated_at if ovr else None,
                updated_by=ovr.updated_by if ovr else None,
                pipeline=pipeline,
                order=meta.get("order"),
            )
        )
    # Pipeline → order ile sırala (UI sekme + tablo sıralaması için)
    items.sort(
        key=lambda x: (
            0 if x.pipeline == "ingestion" else (1 if x.pipeline == "generate" else 99),
            x.order if x.order is not None else 999,
            x.name,
        )
    )
    return PromptListResponse(
        data=items,
        pipelines=sorted(pipelines, key=lambda p: (0 if p == "ingestion" else 1, p)),
    )


@router.get(
    "/{name}",
    response_model=PromptDTO,
    summary="Tek prompt detayı",
)
async def get_prompt(
    user: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    name: str = Path(...),
) -> PromptDTO:
    if name not in PROMPT_REGISTRY:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "title": "Prompt bulunamadı", "name": name},
        )
    meta = PROMPT_REGISTRY[name]
    overrides = await prompts_store.list(db)
    ovr = next((o for o in overrides if o.name == name), None)
    default_content = _resolve_default(name)
    return PromptDTO(
        name=name,
        version=ovr.version if ovr else 0,
        content=ovr.content if ovr else default_content,
        default=default_content,
        description=ovr.description if ovr and ovr.description else meta.get("description"),
        model_hint=ovr.model_hint if ovr and ovr.model_hint else meta.get("model_hint"),
        is_overridden=ovr is not None,
        updated_at=ovr.updated_at if ovr else None,
        updated_by=ovr.updated_by if ovr else None,
        pipeline=meta.get("pipeline"),
        order=meta.get("order"),
    )


@router.get(
    "/{name}/history",
    response_model=PromptHistoryResponse,
    summary="Prompt version history",
)
async def get_prompt_history(
    user: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    name: str = Path(...),
    limit: int = 20,
) -> PromptHistoryResponse:
    if name not in PROMPT_REGISTRY:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "title": "Prompt bulunamadı", "name": name},
        )
    rows = await prompts_store.history(db, name, limit=min(limit, 100))
    return PromptHistoryResponse(
        data=[
            PromptHistoryItem(
                id=r.id,
                name=r.name,
                version=r.version,
                content=r.content,
                updated_by=r.updated_by,
                created_at=r.created_at,
            )
            for r in rows
        ]
    )


@router.put(
    "/{name}",
    response_model=PromptDTO,
    summary="Prompt güncelle (yeni versiyon)",
)
async def update_prompt(
    request: Request,
    payload: PromptUpdate,
    user: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    name: str = Path(...),
) -> PromptDTO:
    if name not in PROMPT_REGISTRY:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "title": "Prompt bulunamadı", "name": name},
        )

    # Old version snapshot (audit için)
    old_overrides = await prompts_store.list(db)
    old_ovr = next((o for o in old_overrides if o.name == name), None)
    old_version = old_ovr.version if old_ovr else 0

    new_version = await prompts_store.set(
        db,
        name=name,
        content=payload.content,
        description=payload.description,
        model_hint=payload.model_hint,
        user_id=user.id,
    )
    await _audit(
        db,
        actor_id=user.id,
        ip=get_client_ip(request),
        action="prompts.update",
        name=name,
        old_version=old_version,
        new_version=new_version,
    )
    await db.commit()

    meta = PROMPT_REGISTRY[name]
    return PromptDTO(
        name=name,
        version=new_version,
        content=payload.content,
        default=_resolve_default(name),
        description=payload.description or meta.get("description"),
        model_hint=payload.model_hint or meta.get("model_hint"),
        is_overridden=True,
        updated_at=datetime.now(UTC).isoformat(),
        updated_by=str(user.id),
        pipeline=meta.get("pipeline"),
        order=meta.get("order"),
    )


@router.delete(
    "/{name}",
    response_model=PromptDTO,
    summary="Default'a dön (history korunur)",
)
async def reset_prompt(
    request: Request,
    user: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    name: str = Path(...),
) -> PromptDTO:
    if name not in PROMPT_REGISTRY:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "title": "Prompt bulunamadı", "name": name},
        )

    old_overrides = await prompts_store.list(db)
    old_ovr = next((o for o in old_overrides if o.name == name), None)
    old_version = old_ovr.version if old_ovr else 0

    await prompts_store.reset(db, name)
    await _audit(
        db,
        actor_id=user.id,
        ip=get_client_ip(request),
        action="prompts.reset",
        name=name,
        old_version=old_version,
        new_version=None,
    )
    await db.commit()

    meta = PROMPT_REGISTRY[name]
    default_content = _resolve_default(name)
    return PromptDTO(
        name=name,
        version=0,
        content=default_content,
        default=default_content,
        description=meta.get("description"),
        model_hint=meta.get("model_hint"),
        is_overridden=False,
        updated_at=None,
        updated_by=None,
        pipeline=meta.get("pipeline"),
        order=meta.get("order"),
    )


@router.post(
    "/{name}/restore/{version}",
    response_model=PromptDTO,
    summary="Geçmiş bir versiyonu current yap (yeni version üretir)",
)
async def restore_prompt(
    request: Request,
    user: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    name: str = Path(...),
    version: int = Path(..., ge=1),
) -> PromptDTO:
    if name not in PROMPT_REGISTRY:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "title": "Prompt bulunamadı", "name": name},
        )

    # History'den fetch
    row = (
        await db.execute(
            sa_text(
                """
                SELECT content FROM app_prompt_history
                WHERE name = :n AND version = :v
                """
            ),
            {"n": name, "v": version},
        )
    ).first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "NOT_FOUND",
                "title": "Version bulunamadı",
                "version": version,
            },
        )

    new_version = await prompts_store.set(
        db,
        name=name,
        content=row[0],
        user_id=user.id,
    )
    await _audit(
        db,
        actor_id=user.id,
        ip=get_client_ip(request),
        action="prompts.restore",
        name=name,
        old_version=version,
        new_version=new_version,
    )
    await db.commit()

    meta = PROMPT_REGISTRY[name]
    return PromptDTO(
        name=name,
        version=new_version,
        content=row[0],
        default=_resolve_default(name),
        description=meta.get("description"),
        model_hint=meta.get("model_hint"),
        is_overridden=True,
        updated_at=datetime.now(UTC).isoformat(),
        updated_by=str(user.id),
        pipeline=meta.get("pipeline"),
        order=meta.get("order"),
    )
