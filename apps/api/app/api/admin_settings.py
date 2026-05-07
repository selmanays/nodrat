"""Admin runtime settings endpoint'leri (#262/#265 Epic, MVP-1.2).

docs/engineering/api-contracts.md (admin/settings)
docs/engineering/data-model.md (app_settings tablosu)

Endpoints:
    GET    /admin/settings                  — Tüm settings (default + override)
    GET    /admin/settings/{key}            — Tek setting detay
    PUT    /admin/settings/{key}            — Değer güncelle
    DELETE /admin/settings/{key}            — Default'a dön

Default registry: SETTING_REGISTRY (kod tarafında tanımlı).
Override değerler: app_settings tablosu (DB).

require_admin tüm endpoint'lerde. Her değişiklik admin_audit_log'a yazılır.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import get_client_ip, require_admin
from app.core.settings_store import settings_store
from app.models.job import AdminAuditLog
from app.models.user import User


logger = logging.getLogger(__name__)
router = APIRouter()


# =============================================================================
# SETTING_REGISTRY — known settings (default değerler + meta)
# =============================================================================
# Yeni setting eklenirken:
#  1) Buraya ekle (default + meta)
#  2) İlgili kodda settings_store.get(...) ile çek
#  3) Migration script gerekirse seed yap


SETTING_REGISTRY: dict[str, dict[str, Any]] = {
    # ---- RAG / Reranker ------------------------------------------------
    "rerank.enabled": {
        "default": True,
        "type": "bool",
        "group": "rag",
        "description": (
            "Cross-encoder reranker aktif mi. False → RRF sırası kullanılır "
            "(acil rollback)."
        ),
        "requires_restart": False,
    },
    "rerank.candidate_pool": {
        "default": 50,
        "type": "int",
        "group": "rag",
        "description": "Reranker'a gönderilen aday sayısı (RRF top-N).",
        "min_value": 10,
        "max_value": 200,
        "requires_restart": False,
    },
    "rerank.min_combined_score": {
        "default": 0.15,
        "type": "float",
        "group": "rag",
        "description": (
            "combined_score < eşik → kart drop. 0.10 permisif, 0.20 sıkı, "
            "0.30 agresif. (#251/#253/#259)"
        ),
        "min_value": 0.0,
        "max_value": 1.0,
        "requires_restart": False,
    },
    "rerank.min_query_words": {
        "default": 3,
        "type": "int",
        "group": "rag",
        "description": (
            "Bu kelime sayısının altındaki query'lerde rerank bypass "
            "(NIM cross-encoder kısa query'lerde başarısız). #253"
        ),
        "min_value": 1,
        "max_value": 10,
        "requires_restart": False,
    },
    # ---- Retrieval / Hybrid search -------------------------------------
    "retrieval.min_semantic_score": {
        "default": 0.55,
        "type": "float",
        "group": "retrieval",
        "description": (
            "Cosine sim < eşik → query ile alakasız demek (dense filter). "
            "0.45 permisif, 0.55 varsayılan, 0.65 sıkı."
        ),
        "min_value": 0.0,
        "max_value": 1.0,
        "requires_restart": False,
    },
    "retrieval.min_text_score": {
        "default": 0.15,
        "type": "float",
        "group": "retrieval",
        "description": (
            "Trigram similarity eşiği (sparse layer). Title+summary trigram "
            "match'i bu eşiğin altıysa sparse adayda yer almaz."
        ),
        "min_value": 0.0,
        "max_value": 1.0,
        "requires_restart": False,
    },
    "retrieval.candidate_pool": {
        "default": 30,
        "type": "int",
        "group": "retrieval",
        "description": "Hybrid search her layer'dan çekilen aday sayısı (RRF input).",
        "min_value": 10,
        "max_value": 200,
        "requires_restart": False,
    },
    # ---- Clustering ----------------------------------------------------
    "clustering.semantic_threshold": {
        "default": 0.85,
        "type": "float",
        "group": "clustering",
        "description": (
            "Cosine sim eşiği — yeni article'ı mevcut cluster'a ekleme "
            "kararı (#247: 0.78 → 0.85, farklı maçlar karışmasın)."
        ),
        "min_value": 0.5,
        "max_value": 1.0,
        "requires_restart": False,
    },
    "clustering.title_trigram_threshold": {
        "default": 0.40,
        "type": "float",
        "group": "clustering",
        "description": (
            "pg_trgm.similarity eşiği — semantic match'e ek title benzerlik "
            "şartı (#247: 0.30 → 0.40)."
        ),
        "min_value": 0.0,
        "max_value": 1.0,
        "requires_restart": False,
    },
    "clustering.window_hours": {
        "default": 72,
        "type": "int",
        "group": "clustering",
        "description": (
            "Aktif cluster matching penceresi (saat). Bu süre içinde "
            "last_seen olan cluster'lar arasında match aranır."
        ),
        "min_value": 6,
        "max_value": 168,
        "requires_restart": False,
    },
    # ---- Quota ---------------------------------------------------------
    "quota.window_seconds": {
        "default": 86400,
        "type": "int",
        "group": "quota",
        "description": "Sliding window süresi (saniye). 86400=24h varsayılan.",
        "min_value": 3600,
        "max_value": 604800,
        "requires_restart": False,
    },
    "quota.tier_trial": {
        "default": 10,
        "type": "int",
        "group": "quota",
        "description": "Trial kullanıcısı 24h limiti (kayıtsız anonim).",
        "min_value": 0,
        "max_value": 1000,
        "requires_restart": False,
    },
    "quota.tier_free": {
        "default": 5,
        "type": "int",
        "group": "quota",
        "description": "Free tier 24h limiti.",
        "min_value": 0,
        "max_value": 1000,
        "requires_restart": False,
    },
    "quota.tier_starter": {
        "default": 30,
        "type": "int",
        "group": "quota",
        "description": "Starter tier 24h limiti.",
        "min_value": 0,
        "max_value": 5000,
        "requires_restart": False,
    },
    "quota.tier_pro": {
        "default": 150,
        "type": "int",
        "group": "quota",
        "description": "Pro tier 24h limiti.",
        "min_value": 0,
        "max_value": 10000,
        "requires_restart": False,
    },
    "quota.tier_agency_seat": {
        "default": 500,
        "type": "int",
        "group": "quota",
        "description": "Agency seat tier 24h limiti.",
        "min_value": 0,
        "max_value": 50000,
        "requires_restart": False,
    },
    # ---- Scraping ------------------------------------------------------
    "scraping.fetch_timeout": {
        "default": 15.0,
        "type": "float",
        "group": "scraping",
        "description": (
            "RSS feed + listing fetch timeout (saniye). Büyük feed'ler için "
            "20+ tavsiye (Anadolu Ajansı gibi)."
        ),
        "min_value": 5.0,
        "max_value": 120.0,
        "requires_restart": False,
    },
    "scraping.article_detail_timeout": {
        "default": 20.0,
        "type": "float",
        "group": "scraping",
        "description": "Article detail fetch timeout. AA için 30+ önerilir (#250).",
        "min_value": 5.0,
        "max_value": 120.0,
        "requires_restart": False,
    },
    "scraping.max_attempts": {
        "default": 3,
        "type": "int",
        "group": "scraping",
        "description": "Crawler job retry limiti (DLQ'ya gitmeden önce).",
        "min_value": 1,
        "max_value": 10,
        "requires_restart": False,
    },
    # ---- LLM -----------------------------------------------------------
    "llm.deepseek_chat_model": {
        "default": "deepseek-v4-flash",
        "type": "string",
        "group": "llm",
        "description": (
            "DeepSeek chat model adı. Eski 'deepseek-chat' adı kullanımdan "
            "kalktı, redirect ediyor — explicit yeni adı kullan (#361). "
            "Alternatifler: deepseek-reasoner (R1), deepseek-coder."
        ),
        "requires_restart": True,
    },
    "llm.nim_rerank_model": {
        "default": "nvidia/rerank-qa-mistral-4b",
        "type": "string",
        "group": "llm",
        "description": (
            "NIM rerank model adı (yedek/fallback). Local bge-reranker-v2-m3 "
            "primary olduğunda kullanılmaz (#224 MVP-1.5 PR-9)."
        ),
        "requires_restart": True,
    },
    # ---- Local model primary flag'leri (#345 / #347 MVP-1.5) ----
    "llm.use_local_embedding": {
        "default": False,
        "type": "bool",
        "group": "llm",
        "description": (
            "Local bge-m3 (sentence-transformers, CPU) embedding primary mi? "
            "True ise NIM nim_bge_m3 fallback'e iner. Türkçe topic-relevance "
            "için tercih edilir; latency ~106ms warm, batch 19ms/text. "
            "Flip öncesi DB chunks + agenda_cards re-embed migration "
            "(tasks.maintenance.reembed_chunks/agenda) zorunlu — yoksa "
            "retrieval cosine ≈ 0 (#345). Container restart gerekir."
        ),
        "requires_restart": True,
    },
    "llm.use_local_rerank": {
        "default": False,
        "type": "bool",
        "group": "llm",
        "description": (
            "Local bge-reranker-v2-m3 (CrossEncoder, CPU) rerank primary mi? "
            "True ise NIM rerank-qa-mistral-4b fallback'e iner. Tour 5 "
            "reranker kalite sorunlarının (#251, #252, #254, #259, #260) "
            "kalıcı çözüm yolu. Flip öncesi eval gate (#347 — NDCG@10 ≥ "
            "0.90 hedef) zorunlu. Container restart gerekir."
        ),
        "requires_restart": True,
    },
    "llm.deepseek_campaign_discount": {
        "default": 0.25,
        "type": "float",
        "group": "llm",
        "description": (
            "DeepSeek kampanya indirim multiplier'ı (input/output cost × bu). "
            "Kampanya 2026-05-31 23:59 UTC'a kadar AKTİF (-%75 indirim, 0.25). "
            "Kampanya bittiğinde 1.0'a çek."
        ),
        "min_value": 0.0,
        "max_value": 1.0,
        "requires_restart": False,
    },
    "llm.content_temperature": {
        "default": 0.5,
        "type": "float",
        "group": "llm",
        "description": (
            "Content generator chat temperature. Yüksek=yaratıcı, düşük=tutarlı."
        ),
        "min_value": 0.0,
        "max_value": 2.0,
        "requires_restart": False,
    },
    # ---- Citation validator (#271) -------------------------------------
    "citation.cosine_threshold": {
        "default": 0.55,
        "type": "float",
        "group": "rag",
        "description": (
            "Citation validator cosine similarity eşiği. LLM çıktısındaki "
            "cümle ↔ source chunk benzerliği bu eşik altıysa halüsinasyon "
            "flag edilir."
        ),
        "min_value": 0.0,
        "max_value": 1.0,
        "requires_restart": False,
    },
    # ---- Chunker (#271) ------------------------------------------------
    "chunker.target_tokens": {
        "default": 500,
        "type": "int",
        "group": "chunker",
        "description": "Hedef chunk boyutu (token). Retrieval kalite/cost dengesi.",
        "min_value": 100,
        "max_value": 2000,
        "requires_restart": False,
    },
    "chunker.max_tokens": {
        "default": 900,
        "type": "int",
        "group": "chunker",
        "description": "Üst sınır chunk boyutu (token).",
        "min_value": 200,
        "max_value": 4000,
        "requires_restart": False,
    },
    "chunker.min_tokens": {
        "default": 200,
        "type": "int",
        "group": "chunker",
        "description": "Alt sınır chunk boyutu (token). Bu altı standalone chunk olmaz.",
        "min_value": 50,
        "max_value": 500,
        "requires_restart": False,
    },
    "chunker.overlap_tokens": {
        "default": 80,
        "type": "int",
        "group": "chunker",
        "description": "Bitişik chunk'lar arası overlap (token). 10-20% target.",
        "min_value": 0,
        "max_value": 500,
        "requires_restart": False,
    },
    # ---- Media — Görsel İşleme (process & discard, #300 MVP-1.4) -------
    "media.processing_enabled": {
        "default": False,
        "type": "bool",
        "group": "media",
        "description": (
            "Görsel işleme pipeline aktif mi. True → scraper haber detayından "
            "DOM görsellerini keşfeder, NIM VLM ile caption+OCR+depicts metadata "
            "çıkarır, image bytes discard edilir. Sadece original_url + metadata "
            "DB'de kalır."
        ),
        "requires_restart": False,
    },
    "media.max_image_bytes": {
        "default": 5242880,
        "type": "int",
        "group": "media",
        "description": (
            "VLM'ye gönderilecek görsel için RAM'e geçici download max boyutu "
            "(byte). 5 MB varsayılan (NIM upload limit). Bytes sadece NIM çağrısı "
            "süresince RAM'de tutulur, sonra discard."
        ),
        "min_value": 1048576,
        "max_value": 20971520,
        "requires_restart": False,
    },
    "media.download_timeout": {
        "default": 10.0,
        "type": "float",
        "group": "media",
        "description": "Görsel geçici download timeout (saniye).",
        "min_value": 5.0,
        "max_value": 60.0,
        "requires_restart": False,
    },
    "media.max_redirects": {
        "default": 5,
        "type": "int",
        "group": "media",
        "description": "Görsel URL redirect zinciri limiti.",
        "min_value": 0,
        "max_value": 20,
        "requires_restart": False,
    },
    # #305 MVP-1.4 PR-5 — generation'a görsel önerisi
    "media.suggestion_enabled": {
        "default": False,
        "type": "bool",
        "group": "media",
        "description": (
            "Generation response'unda 'suggested_image' field'ını döndür. "
            "Process & discard mimarisi: bytes saklanmaz, URL + VLM metadata."
        ),
        "requires_restart": False,
    },
    "media.suggestion_min_confidence": {
        "default": 0.15,
        "type": "float",
        "group": "media",
        "description": (
            "Görsel önerisi için minimum lexical (Jaccard) skor. "
            "Altındaki match'ler reddedilir."
        ),
        "min_value": 0.0,
        "max_value": 1.0,
        "requires_restart": False,
    },
    # #219 MVP-1.5 PR-4 — cold tier retention
    "cold_tier.enabled": {
        "default": False,
        "type": "bool",
        "group": "storage",
        "description": (
            "30+ gün eski raw_html'leri MinIO'dan Contabo Object Storage'a "
            "(cold tier) taşı. Hot tier disk'i koru. Beat task günlük 03:30 "
            "UTC çalışır. Manuel enable — production'da disk dolmaya başlayınca."
        ),
        "requires_restart": False,
    },
    "cold_tier.max_age_days": {
        "default": 30,
        "type": "int",
        "group": "storage",
        "description": (
            "Cold tier'a taşınma yaş eşiği (gün). 30+ gün eski article'ların "
            "raw_html'i taşınır. Daha agresif (7) hot disk daha temiz; daha "
            "muhafazakar (90) hot tier'da daha uzun erişim."
        ),
        "min_value": 1,
        "max_value": 365,
        "requires_restart": False,
    },
    "cold_tier.batch_size": {
        "default": 100,
        "type": "int",
        "group": "storage",
        "description": (
            "Cold tier archive task batch boyutu (article/run). NIM/Postgres "
            "yükünü dengelemek için ihtiyatlı."
        ),
        "min_value": 10,
        "max_value": 1000,
        "requires_restart": False,
    },
    # #220 MVP-1.5 PR-5 — body_html drop policy
    "body_html_drop.enabled": {
        "default": False,
        "type": "bool",
        "group": "storage",
        "description": (
            "24+ saat eski cleaned article'ların body_html'ini NULL'a çek. "
            "clean_text + chunks korunur (RAG çalışır), body_html sadece "
            "reprocess için gerek (raw_html'den re-extract). DB row size "
            "azalır → backup boyutu küçülür → restore süresi kısalır. "
            "Beat task günlük 03:00 UTC çalışır."
        ),
        "requires_restart": False,
    },
    "body_html_drop.max_age_hours": {
        "default": 24,
        "type": "int",
        "group": "storage",
        "description": (
            "body_html drop için yaş eşiği (saat). 24 (gün öncesi cleaned), "
            "agresif 6 (yeni içerik UI'ında body_html görünmez); muhafazakar "
            "168 (1 hafta) reprocess olası süresince saklı tut."
        ),
        "min_value": 1,
        "max_value": 720,
        "requires_restart": False,
    },
    "body_html_drop.batch_size": {
        "default": 500,
        "type": "int",
        "group": "storage",
        "description": (
            "body_html drop task batch boyutu. UPDATE WHERE IN tek transaction; "
            "Postgres rev rotation buffer'ını zorlamamak için 500 ihtiyatlı."
        ),
        "min_value": 50,
        "max_value": 5000,
        "requires_restart": False,
    },
    # ---- Vector quantization (#221 MVP-1.5 PR-6) ----
    "vector_quantization.enabled": {
        "default": False,
        "type": "bool",
        "group": "storage",
        "description": (
            "Hibrit retrieval'da pgvector binary quantization kullan. "
            "embedding_binary BIT(1024) kolonu HNSW Hamming index üzerinden "
            "daha hızlı + 32x küçük; NDCG@10 ≤ %3 düşer (pgvector docs). "
            "False iken float32 cosine kullanılır (default — eval gate öncesi). "
            "Scaffold sadece — search routing entegrasyonu sonraki PR."
        ),
        "requires_restart": False,
    },
    "vector_quantization.backfill_batch": {
        "default": 500,
        "type": "int",
        "group": "storage",
        "description": (
            "quantize_chunks task batch boyutu. UPDATE ... WHERE id IN (SELECT) "
            "ile tek SQL'de doldurur. Postgres lock pressure için 500 makul."
        ),
        "min_value": 50,
        "max_value": 10000,
        "requires_restart": False,
    },
    # ---- Vision LLM (NIM VLM, #304 MVP-1.4 — 'llm' grubuna eklendi) ----
    "media.vlm_provider": {
        "default": "nim",
        "type": "string",
        "group": "llm",
        "description": (
            "Vision LLM sağlayıcısı (haber görsellerinden caption + OCR + "
            "depicts çıkarır). Şu an sadece NIM (NVIDIA) — free tier."
        ),
        "allowed_values": ["nim"],
        "requires_restart": False,
    },
    "media.vlm_model": {
        "default": "meta/llama-4-maverick-17b-128e-instruct",
        "type": "string",
        "group": "llm",
        "description": (
            "NIM VLM modeli. Varsayılan: Llama 4 Maverick (multilingual + free, "
            "Türkçe destekli). Alternatif: google/paligemma (OCR-specialized)."
        ),
        "requires_restart": False,
    },
    "media.vlm_rate_limit_rpm": {
        "default": 35,
        "type": "int",
        "group": "llm",
        "description": (
            "NIM VLM rate limit (request per minute). Free tier 40 RPM, "
            "35 conservative margin (worker concurrency 2 ile uyumlu)."
        ),
        "min_value": 1,
        "max_value": 100,
        "requires_restart": False,
    },
    # NOT: extractor.min_text_length module-level sabit ve birden fazla
    # call site'tan geçiyor. Runtime override için extractor refactor
    # gerekiyor — MVP-1.5'te yapılacak.
    #
    # ---- Auth / JWT (#271) ---------------------------------------------
    "auth.jwt_access_expire_minutes": {
        "default": 15,
        "type": "int",
        "group": "auth",
        "description": "JWT access token TTL (dakika).",
        "min_value": 1,
        "max_value": 1440,
        "requires_restart": False,
    },
    "auth.jwt_refresh_expire_days": {
        "default": 30,
        "type": "int",
        "group": "auth",
        "description": "JWT refresh token TTL (gün).",
        "min_value": 1,
        "max_value": 365,
        "requires_restart": False,
    },
    "auth.email_verify_token_ttl_hours": {
        "default": 24,
        "type": "int",
        "group": "auth",
        "description": "Email doğrulama token TTL (saat).",
        "min_value": 1,
        "max_value": 168,
        "requires_restart": False,
    },
    "auth.password_reset_token_ttl_hours": {
        "default": 1,
        "type": "int",
        "group": "auth",
        "description": "Şifre sıfırlama token TTL (saat). Güvenlik için kısa tutulur.",
        "min_value": 1,
        "max_value": 24,
        "requires_restart": False,
    },
    # ---- LLM task-specific parameters (#272 PR-D) ----------------------
    "llm.query_planner_max_tokens": {
        "default": 512,
        "type": "int",
        "group": "llm",
        "description": "Query planner LLM output max_tokens.",
        "min_value": 64,
        "max_value": 4096,
        "requires_restart": False,
    },
    "llm.query_planner_temperature": {
        "default": 0.1,
        "type": "float",
        "group": "llm",
        "description": "Query planner LLM temperature. Düşük = deterministic plan.",
        "min_value": 0.0,
        "max_value": 2.0,
        "requires_restart": False,
    },
    "llm.agenda_max_tokens": {
        "default": 2800,
        "type": "int",
        "group": "llm",
        "description": (
            "Agenda card LLM max_tokens. #175 — 1500'de bazı 3+ article "
            "cluster'larında JSON truncate oluyordu, 2800 emniyetli."
        ),
        "min_value": 500,
        "max_value": 8000,
        "requires_restart": False,
    },
    "llm.agenda_temperature": {
        "default": 0.3,
        "type": "float",
        "group": "llm",
        "description": "Agenda card LLM temperature. Düşük = halüsinasyon az.",
        "min_value": 0.0,
        "max_value": 2.0,
        "requires_restart": False,
    },
    "llm.country_backfill_max_tokens": {
        "default": 10,
        "type": "int",
        "group": "llm",
        "description": "Country backfill — sadece 2-char ISO kodu döner.",
        "min_value": 5,
        "max_value": 100,
        "requires_restart": False,
    },
    "llm.raptor_max_tokens": {
        "default": 1800,
        "type": "int",
        "group": "llm",
        "description": "RAPTOR weekly cluster LLM max_tokens.",
        "min_value": 500,
        "max_value": 4000,
        "requires_restart": False,
    },
    "llm.raptor_temperature": {
        "default": 0.3,
        "type": "float",
        "group": "llm",
        "description": "RAPTOR LLM temperature.",
        "min_value": 0.0,
        "max_value": 2.0,
        "requires_restart": False,
    },
    "llm.content_max_tokens": {
        "default": 2000,
        "type": "int",
        "group": "llm",
        "description": "İçerik üretici LLM max_tokens (X post + summary).",
        "min_value": 500,
        "max_value": 4000,
        "requires_restart": False,
    },
    # NOT: Provider HTTP timeouts (deepseek=60s, nim_rerank=15s, nim_chat=120s)
    # provider __init__ zamanı set ediliyor. Runtime tunable yapmak için
    # provider registry refactor gerek. → MVP-1.5 (#273).
    #
    # NOT: cost.cap_*_monthly_usd config'te tanımlı ama henüz hiçbir kod
    # tarafından enforce edilmiyor (ölü config). Gerçek cost guard
    # implementasyonu MVP-2'de eklenecek.
    #
    # NOT: Beat schedule (cron) ayarları MVP-1.5'te DB-backed scheduler
    # ile gelecek (#271).
}


# =============================================================================
# Pydantic schemas
# =============================================================================


class SettingDTO(BaseModel):
    """Admin GET response item."""

    key: str
    value: Any
    default: Any
    type: str
    group: str
    description: str | None
    min_value: float | None = None
    max_value: float | None = None
    allowed_values: list | None = None
    requires_restart: bool
    is_overridden: bool
    updated_at: str | None = None
    updated_by: str | None = None


class SettingListResponse(BaseModel):
    data: list[SettingDTO]
    groups: list[str]


class SettingUpdate(BaseModel):
    value: Any = Field(..., description="Yeni değer (type'a uygun)")


# =============================================================================
# Helpers
# =============================================================================


def _coerce_value(value: Any, type_: str) -> Any:
    """Cast incoming JSON value to declared type."""
    try:
        if type_ == "int":
            return int(value)
        if type_ == "float":
            return float(value)
        if type_ == "bool":
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                return value.lower() in ("true", "1", "yes", "on")
            return bool(value)
        if type_ == "string":
            return str(value)
        return value  # json
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "INVALID_TYPE",
                "title": "Geçersiz tip",
                "message": f"'{value}' değeri {type_} tipine cast edilemedi: {exc}",
            },
        )


def _validate_range(
    value: Any, *, min_v: float | None, max_v: float | None
) -> None:
    if min_v is not None and isinstance(value, (int, float)):
        if value < min_v:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "OUT_OF_RANGE",
                    "title": "Aralık dışı",
                    "message": f"Minimum {min_v} olmalı",
                },
            )
    if max_v is not None and isinstance(value, (int, float)):
        if value > max_v:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "OUT_OF_RANGE",
                    "title": "Aralık dışı",
                    "message": f"Maksimum {max_v} olmalı",
                },
            )


async def _audit(
    db: AsyncSession,
    *,
    actor_id: UUID,
    ip: str | None,
    action: str,
    key: str,
    old_value: Any,
    new_value: Any,
) -> None:
    db.add(
        AdminAuditLog(
            actor_id=actor_id,
            action=action,
            target_type="app_setting",
            target_id=None,
            ip_address=ip,
            event_metadata={
                "key": key,
                "old_value": old_value,
                "new_value": new_value,
            },
        )
    )


# =============================================================================
# Endpoints
# =============================================================================


@router.get(
    "",
    response_model=SettingListResponse,
    summary="Tüm runtime settings (default + override)",
)
async def list_settings(
    user: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    group: str | None = None,
) -> SettingListResponse:
    overrides = await settings_store.list(db, group=group)
    overrides_by_key = {o.key: o for o in overrides}

    items: list[SettingDTO] = []
    groups: set[str] = set()

    for key, meta in SETTING_REGISTRY.items():
        if group and meta["group"] != group:
            continue
        groups.add(meta["group"])
        ovr = overrides_by_key.get(key)
        current_value = ovr.value if ovr else meta["default"]
        items.append(
            SettingDTO(
                key=key,
                value=current_value,
                default=meta["default"],
                type=meta["type"],
                group=meta["group"],
                description=meta.get("description"),
                min_value=meta.get("min_value"),
                max_value=meta.get("max_value"),
                allowed_values=meta.get("allowed_values"),
                requires_restart=meta.get("requires_restart", False),
                is_overridden=ovr is not None,
                updated_at=ovr.updated_at if ovr else None,
                updated_by=ovr.updated_by if ovr else None,
            )
        )

    items.sort(key=lambda x: (x.group, x.key))
    return SettingListResponse(data=items, groups=sorted(groups))


@router.get(
    "/{key}",
    response_model=SettingDTO,
    summary="Tek setting detayı",
)
async def get_setting(
    user: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    key: str = Path(..., description="Setting key (örn. rerank.min_combined_score)"),
) -> SettingDTO:
    if key not in SETTING_REGISTRY:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "title": "Setting bulunamadı", "key": key},
        )
    meta = SETTING_REGISTRY[key]
    overrides = await settings_store.list(db)
    ovr = next((o for o in overrides if o.key == key), None)
    return SettingDTO(
        key=key,
        value=ovr.value if ovr else meta["default"],
        default=meta["default"],
        type=meta["type"],
        group=meta["group"],
        description=meta.get("description"),
        min_value=meta.get("min_value"),
        max_value=meta.get("max_value"),
        allowed_values=meta.get("allowed_values"),
        requires_restart=meta.get("requires_restart", False),
        is_overridden=ovr is not None,
        updated_at=ovr.updated_at if ovr else None,
        updated_by=ovr.updated_by if ovr else None,
    )


@router.put(
    "/{key}",
    response_model=SettingDTO,
    summary="Setting değer güncelle",
)
async def update_setting(
    request: Request,
    payload: SettingUpdate,
    user: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    key: str = Path(...),
) -> SettingDTO:
    if key not in SETTING_REGISTRY:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "title": "Setting bulunamadı", "key": key},
        )
    meta = SETTING_REGISTRY[key]
    new_value = _coerce_value(payload.value, meta["type"])
    _validate_range(
        new_value, min_v=meta.get("min_value"), max_v=meta.get("max_value")
    )

    # Old value snapshot (audit için)
    old_value = await settings_store.get(db, key, meta["default"])

    await settings_store.set(
        db,
        key=key,
        value=new_value,
        type_=meta["type"],
        group_name=meta["group"],
        user_id=user.id,
    )
    await _audit(
        db,
        actor_id=user.id,
        ip=get_client_ip(request),
        action="settings.update",
        key=key,
        old_value=old_value,
        new_value=new_value,
    )
    await db.commit()

    return SettingDTO(
        key=key,
        value=new_value,
        default=meta["default"],
        type=meta["type"],
        group=meta["group"],
        description=meta.get("description"),
        min_value=meta.get("min_value"),
        max_value=meta.get("max_value"),
        allowed_values=meta.get("allowed_values"),
        requires_restart=meta.get("requires_restart", False),
        is_overridden=True,
        updated_at=datetime.now(UTC).isoformat(),
        updated_by=str(user.id),
    )


@router.delete(
    "/{key}",
    response_model=SettingDTO,
    summary="Default değere dön",
)
async def reset_setting(
    request: Request,
    user: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    key: str = Path(...),
) -> SettingDTO:
    if key not in SETTING_REGISTRY:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "title": "Setting bulunamadı", "key": key},
        )
    meta = SETTING_REGISTRY[key]
    old_value = await settings_store.get(db, key, meta["default"])
    await settings_store.reset(db, key, user_id=user.id)
    await _audit(
        db,
        actor_id=user.id,
        ip=get_client_ip(request),
        action="settings.reset",
        key=key,
        old_value=old_value,
        new_value=meta["default"],
    )
    await db.commit()
    return SettingDTO(
        key=key,
        value=meta["default"],
        default=meta["default"],
        type=meta["type"],
        group=meta["group"],
        description=meta.get("description"),
        min_value=meta.get("min_value"),
        max_value=meta.get("max_value"),
        allowed_values=meta.get("allowed_values"),
        requires_restart=meta.get("requires_restart", False),
        is_overridden=False,
        updated_at=None,
        updated_by=None,
    )
