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
    # #758: rerank.* settings kaldırıldı (cross-encoder rerank tamamen silindi).
    # Eski keys: rerank.enabled, rerank.candidate_pool, rerank.min_combined_score,
    # rerank.min_query_words — eval ile baseline'dan kötü, kalıcı disabled.
    # LLM rerank bağımsız: retrieval.llm_rerank_enabled hala mevcut.
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
    "retrieval.content_top_k": {
        "default": 5,
        "type": "int",
        "group": "retrieval",
        "description": (
            "Generate akışında LLM'e gönderilecek nihai içerik top-K. Hem "
            "agenda cards hem chunks fallback tarafına yansır. 3 dar/keskin, "
            "5 varsayılan, 10 geniş context (cost ↑, TTFT ↑). app_generate.py:533 "
            "+ app_generate_stream.py:537 callsite."
        ),
        "min_value": 3,
        "max_value": 15,
        "requires_restart": False,
    },
    # ---- #696 B7+C8 — NER scoring (Faz 6.1 IDF + multi-entity AND) ----
    "retrieval.ner_df_threshold": {
        "default": 30,
        "type": "int",
        "group": "retrieval",
        "description": (
            "NER entity 'nadir' eşiği (article frequency). Bu sayıdan az "
            "article'da geçen entity rare sayılır → RRF boost'a aday. "
            "Corpus büyüdükçe artırılabilir (~%0.7 of total)."
        ),
        "min_value": 5,
        "max_value": 200,
        "requires_restart": False,
    },
    "retrieval.ner_k_multi": {
        "default": 20,
        "type": "int",
        "group": "retrieval",
        "description": (
            "NER multi-entity AND match RRF K (en güçlü stream). Düşük K = "
            "daha güçlü boost (1/(K+rank))."
        ),
        "min_value": 5,
        "max_value": 100,
        "requires_restart": False,
    },
    "retrieval.ner_k_single_rare": {
        "default": 30,
        "type": "int",
        "group": "retrieval",
        "description": (
            "NER tek nadir entity RRF K (Faz 6 eski seviye). Sparse/dense "
            "K=60'tan 2x güçlü boost."
        ),
        "min_value": 10,
        "max_value": 100,
        "requires_restart": False,
    },
    "retrieval.ner_fetch_per_entity_limit": {
        "default": 100,
        "type": "int",
        "group": "retrieval",
        "description": (
            "Her query entity için DB'den çekilen max article (df sayım + "
            "filtre için). Yüksek değer doğruluk, düşük değer latency."
        ),
        "min_value": 20,
        "max_value": 500,
        "requires_restart": False,
    },
    "retrieval.ner_final_aids_cap": {
        "default": 30,
        "type": "int",
        "group": "retrieval",
        "description": (
            "NER stream'inde RRF'e giden max article. Yüksek değer recall, "
            "düşük değer precision."
        ),
        "min_value": 5,
        "max_value": 100,
        "requires_restart": False,
    },
    "retrieval.rrf_k": {
        "default": 60.0,
        "type": "float",
        "group": "retrieval",
        "description": (
            "RRF base K (sparse + dense streams). Standart literatür değeri 60."
        ),
        "min_value": 10.0,
        "max_value": 200.0,
        "requires_restart": False,
    },
    "retrieval.rrf_k_summary": {
        "default": 80.0,
        "type": "float",
        "group": "retrieval",
        "description": (
            "Summary stream RRF K (#661 Faz 5.2). Daha yüksek K = daha zayıf "
            "boost (sparse/dense dominantlığı korunsun)."
        ),
        "min_value": 20.0,
        "max_value": 200.0,
        "requires_restart": False,
    },
    "retrieval.rrf_phrase_boost": {
        "default": 0.05,
        "type": "float",
        "group": "retrieval",
        "description": (
            "Exact phrase match +bonus (#198). Trigram score'a ek olarak "
            "RRF stream'e eklenir."
        ),
        "min_value": 0.0,
        "max_value": 0.5,
        "requires_restart": False,
    },
    "retrieval.rrf_phrase_boost_ner_mode": {
        "default": 0.03,
        "type": "float",
        "group": "retrieval",
        "description": (
            "#718 mode-aware: NER multi_and tetiklendiğinde sparse phrase boost "
            "(düşük versiyon). Niş entity sorgularında yaygın bigram match'i "
            "(örn. 'kaç bitti' → Şampiyonlar Ligi cards) niş cards'ı bastırmasın diye."
        ),
        "min_value": 0.0,
        "max_value": 0.5,
        "requires_restart": False,
    },
    "retrieval.rrf_gram_boost": {
        "default": 0.025,
        "type": "float",
        "group": "retrieval",
        "description": (
            "Her n-gram match için +bonus (#200), max +0.10 cap'li."
        ),
        "min_value": 0.0,
        "max_value": 0.2,
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
    # #353: scraping.fetch_timeout + scraping.max_attempts kaldırıldı
    # (registry'de var ama hiçbir yerde okunmuyordu — stale).
    # Sadece article_detail_timeout aktif kullanımda.
    "scraping.article_detail_timeout": {
        "default": 20.0,
        "type": "float",
        "group": "scraping",
        "description": "Article detail fetch timeout. AA için 30+ önerilir (#250).",
        "min_value": 5.0,
        "max_value": 120.0,
        "requires_restart": False,
    },
    # ---- LLM -----------------------------------------------------------
    # #720: llm.deepseek_chat_model kaldırıldı — kod app.config.settings
    # (env var DEEPSEEK_CHAT_MODEL) üzerinden okuyor; admin UI override
    # etkisiz oluyordu. Model adı env var ile kontrol edilir.
    # #758: llm.nim_rerank_model + llm.use_local_rerank kaldırıldı (cross-encoder
    # rerank tamamen silindi, provider modülleri yok).
    # #720: llm.deepseek_campaign_discount kaldırıldı — kod
    # providers/deepseek.py settings.deepseek_campaign_discount (env var) ile
    # okuyor; admin UI override etkisiz. Kampanya bitiminde DEEPSEEK_CAMPAIGN_DISCOUNT
    # env var ile 1.0'a çekilir.
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
    # #353: media.max_redirects kaldırıldı (constant MAX_REDIRECTS kullanılıyor,
    # registry key okunmuyor — stale).
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
    # ---- Vector quantization (#221 MVP-1.5 PR-6 — SCAFFOLD) ----
    "vector_quantization.enabled": {
        "default": False,
        "type": "bool",
        "group": "storage",
        "description": (
            "[SCAFFOLD] pgvector binary quantization kullan (1024-dim BIT(1024), "
            "HNSW Hamming index, 32x sıkışma). DB schema + backfill task hazır "
            "ama hibrit retrieval routing henüz entegre değil — sonraki PR'da "
            "search routing flag'le aktive edilecek. Şu an UI değişimi etkisiz."
        ),
        "requires_restart": False,
    },
    "vector_quantization.backfill_batch": {
        "default": 500,
        "type": "int",
        "group": "storage",
        "description": (
            "[SCAFFOLD] quantize_chunks task batch boyutu. Manuel one-shot "
            "(reembed task ile zaten dual-write yapılır). UI değişimi etkisiz."
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
    # #720: media.vlm_rate_limit_rpm kaldırıldı — registry'de tanımlıydı ama
    # hiçbir kod path'i okumuyor. Worker concurrency .env üzerinden kontrol
    # ediliyor; rate limit ayrıca enforce edilmiyor.
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
    # #720: auth.email_verify_token_ttl_hours + auth.password_reset_token_ttl_hours
    # kaldırıldı — kod email/service.py settings.* (env var) üzerinden okuyor;
    # admin UI override etkisiz. Token TTL'leri EMAIL_VERIFY_TOKEN_TTL_HOURS +
    # PASSWORD_RESET_TOKEN_TTL_HOURS env var ile kontrol edilir.
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
    # ---- PMF Survey (#55 — Dalga 5, default OFF) -----------------------
    "pmf_survey.enabled": {
        "default": False,
        "type": "bool",
        "group": "growth",
        "description": (
            "Sean Ellis PMF survey aktif mi. False ise frontend popup "
            "gösterilmez, eligibility endpoint reason='enabled_off' döner. "
            "30g+ aktif user'a 'Nodrat olmasaydı nasıl hissederdin?' sorusu. "
            "Hedef ≥%40 'very_disappointed'."
        ),
        "requires_restart": False,
    },
    # ---- Comparison mode (#51 — Dalga 4 telemetry gate) ----------------
    "comparison.enabled": {
        "default": False,
        "type": "bool",
        "group": "rag",
        "description": (
            "Comparison mode (zaman karşılaştırması) feature flag. False ise "
            "comparison query'leri current mode'a downgrade edilir. MVP-2 "
            "Dalga 4'te beta açık, telemetry sonra kill/keep kararı (R-PRD-03)."
        ),
        "requires_restart": False,
    },
    # ---- Provider HTTP timeouts (#273 MVP-2 Wave 0) --------------------
    "llm.deepseek_timeout": {
        "default": 60.0,
        "type": "float",
        "group": "llm",
        "description": (
            "DeepSeek API HTTP timeout (saniye). Uzun promptlarda artırın. "
            "Değişiklik için API container restart gerek."
        ),
        "min_value": 10.0,
        "max_value": 600.0,
        "requires_restart": True,
    },
    # #720: llm.nim_chat_timeout kaldırıldı — NIM chat fallback artık register
    # olmuyor, timeout okunmuyor.
    # #758: llm.nim_rerank_timeout kaldırıldı — cross-encoder rerank kaldırıldı.
    # NOT (#420): llm.nim_embedding_timeout kaldırıldı — embedding artık tek
    # provider (local CPU, HTTP timeout yok).
    "llm.nim_vlm_timeout": {
        "default": 30.0,
        "type": "float",
        "group": "llm",
        "description": (
            "NIM VLM (Llama 4 Maverick) HTTP timeout — image caption + OCR."
        ),
        "min_value": 10.0,
        "max_value": 180.0,
        "requires_restart": True,
    },
    # ---- SFT Foundation (#567 MVP-1.7 — own SLM training data ETL) -----
    "sft.curator.enabled": {
        "default": False,
        "type": "bool",
        "group": "sft",
        "description": (
            "SFT curator nightly worker (kill switch). False → ETL hiç çalışmaz, "
            "True → 02:45 UTC her gece generations.sft_eligible=true → "
            "training_samples ETL. Mevcut user verisi her zaman birikir; bu flag "
            "sadece training_samples'a curate-INSERT'i kontrol eder."
        ),
        "requires_restart": False,
    },
    "sft.curator.review_buffer_days": {
        "default": 7,
        "type": "int",
        "group": "sft",
        "description": (
            "Generation oluştuktan kaç gün sonra ETL'e dahil. Kullanıcının "
            "consent geri çekme şansı için buffer (KVKK md.11). 0 → buffer yok "
            "(test için)."
        ),
        "min_value": 0,
        "max_value": 90,
        "requires_restart": False,
    },
    "sft.curator.daily_max_samples": {
        "default": 1000,
        "type": "int",
        "group": "sft",
        "description": (
            "Bir koşumda max sample sayısı (overflow protection). NOT EXISTS "
            "filter ile birlikte kademeli catch-up sağlar (geriye dönük data)."
        ),
        "min_value": 10,
        "max_value": 100000,
        "requires_restart": False,
    },
    "sft.curator.min_quality_score": {
        "default": 0.7,
        "type": "float",
        "group": "sft",
        "description": (
            "Quality signals composite threshold (0-1). edit_distance düşük + "
            "char_count makul + source_count yeterli = yüksek skor. Şu an "
            "compute edilse de filter henüz aktif değil — Faz 2'de eklenecek."
        ),
        "min_value": 0.0,
        "max_value": 1.0,
        "requires_restart": False,
    },
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
