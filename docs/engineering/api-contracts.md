# Nodrat — API Sözleşmeleri (OpenAPI Spec)

**Doküman türü:** REST API Contracts
**Sürüm:** v0.1
**Bağımlılık:** PRD §10, IA §8, Architecture §3, Data Model (tüm tablolar), Risk Register §4 (MVP-1 kapsam)
**Hedef:** Tüm endpoint'lerin request/response gövdeleri, hata kodları, auth gereksinimleri ve rate limit politikaları.

⚠️ **Konvansiyon:**
- Base URL: `https://nodrat.com/api`
- Content-Type: `application/json`
- Auth: Bearer token (JWT) `Authorization: Bearer <token>`
- Pagination: `?limit=20&cursor=<opaque>` (cursor-based, klasik offset değil)
- Tarih: ISO 8601 (`2026-05-01T12:00:00Z`)
- Hata format: RFC 7807 Problem Details (`application/problem+json`)

---

## 0. Yönetici Özeti

```text
API segmentleri (IA §8.1):
  /public/*       — Auth gerektirmez, rate limit'li
  /auth/*         — Login, register, password reset, 2FA
  /app/*          — Kullanıcı (registered, JWT)
  /admin/*        — Super admin (JWT + role + 2FA)
  /internal/*     — Worker'lar arası (mTLS / token)
  /webhooks/*     — Provider callback'leri
  /health, /readiness, /metrics

Toplam endpoint:  ~50 (MVP-1: ~22)
MVP-1 dahil:      Auth + Sources + Articles + Queue + Generate

Versioning:       URL path versioning yok (MVP)
                  Breaking change'de header X-API-Version
                  Faz 7+ /v2/ prefix gerekirse
```

---

## 1. Genel Konvansiyonlar

### 1.1 Standart hata yanıtı (RFC 7807)

```json
{
  "type": "https://nodrat.com/errors/insufficient-data",
  "title": "Veri yetersiz",
  "status": 422,
  "detail": "Bu konu için seçilen dönemde yeterli güvenilir haber verisi bulunamadı.",
  "instance": "/app/generate/abc123",
  "code": "INSUFFICIENT_DATA",
  "trace_id": "0e6f4..."
}
```

### 1.2 Standart hata kodları

```text
HTTP   Code                       Anlam
─────────────────────────────────────────────────────────────────
400    VALIDATION_ERROR           Pydantic validation başarısız
401    UNAUTHENTICATED            Token yok / geçersiz / expire
403    FORBIDDEN                  Token var ama yetki yok
403    EMAIL_NOT_VERIFIED         Email doğrulanmamış
403    QUOTA_EXCEEDED             Aylık üretim hakkı doldu
403    RATE_LIMITED               Saatlik rate limit
404    NOT_FOUND                  Resource yok
409    CONFLICT                   Duplicate / state çakışması
409    SELECTOR_MISMATCH          Source config + HTML uyumsuzluk
422    INSUFFICIENT_DATA          Veri yetersizliği (PRD §2.10)
422    UNSAFE_OUTPUT              Halüsinasyon kontrolü flag
429    TOO_MANY_REQUESTS          Rate limit
500    INTERNAL_ERROR             Beklenmeyen hata
502    PROVIDER_ERROR             LLM/embedding provider failure
503    SERVICE_UNAVAILABLE        Maintenance / partial outage
504    GATEWAY_TIMEOUT            Upstream timeout
```

### 1.3 Pagination

```http
GET /admin/articles?limit=20&cursor=eyJpZCI6IjEyMyIsImNyZWF0ZWRfYXQiOiIyMDI2In0=
```

Response:
```json
{
  "data": [ ... ],
  "pagination": {
    "next_cursor": "eyJpZCI6IjI0MyIs...",
    "has_more": true,
    "total_estimate": 1452
  }
}
```

### 1.4 Rate limit header'ları

```http
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 47
X-RateLimit-Reset: 1717260000
```

### 1.5 Auth flow

```text
1. POST /auth/login → access_token (15 dk) + refresh_token (30 gün)
2. Authorization: Bearer <access_token>
3. 401 alınca → POST /auth/refresh ile yenile
4. Logout → POST /auth/logout (refresh_token revoke)

JWT claims:
  sub: user_id
  role: 'super_admin' | 'user'
  tier: 'free' | 'starter' | 'pro' | 'agency_seat'
  exp, iat, jti
```

### 1.6 Idempotency

```http
Idempotency-Key: 7b8e0d4c-...

Sadece kritik mutation endpoint'lerinde:
  POST /app/generate
  POST /app/billing/checkout
```

---

## 2. Public Endpoints

### 2.1 `GET /health`

Tüm bağımlılıkların durumu.

**Auth:** Yok
**Rate limit:** 60/dk

```json
// 200 OK
{
  "status": "ok",
  "version": "0.1.0",
  "checks": {
    "database": "ok",
    "redis": "ok",
    "minio": "ok",
    "providers": {
      "deepseek_v3": "ok",
      "nim_bge_m3": "ok"
    }
  },
  "uptime_seconds": 84512
}
```

### 2.2 `GET /readiness`

Migration tamamlandı mı, provider'lar reachable mı.

**Auth:** Yok

```json
// 200 OK | 503 SERVICE_UNAVAILABLE
{
  "ready": true,
  "migration_version": "20260512_2310",
  "providers_healthy": 4,
  "providers_total": 4
}
```

### 2.3 `POST /public/trial/generate`

Kayıtsız trial üretimi (Pricing §2.1).

**Auth:** Yok
**Rate limit:** 1/gün IP+fingerprint
**Headers:**
  - `X-Browser-Fingerprint: <opaque>` (client'tan)

```json
// Request
{
  "request_text": "Bugünkü ekonomi gündemiyle 3 X paylaşımı üret",
  "fingerprint": "abc123..."
}

// 200 OK
{
  "trial_token": "tr_abc...",
  "expires_at": "2026-05-08T12:00:00Z",
  "result": {
    "content_type": "x_post",
    "topic": "ekonomi gündemi",
    "data_coverage": {
      "mode": "current",
      "from": "2026-05-01T00:00:00Z",
      "to": "2026-05-01T23:59:59Z",
      "source_count": 3,
      "agenda_card_count": 2
    },
    "posts": [
      {
        "text": "...",
        "angle": "ekonomi eleştirisi",
        "related_agenda_card_ids": ["..."]
      }
    ],
    "sources": [
      {"title": "...", "source": "...", "url": "..."}
    ],
    "warnings": []
  },
  "cta": {
    "register_url": "/register?from=trial",
    "remaining_today": 0
  }
}

// 429 RATE_LIMITED
{
  "title": "Günlük trial sınırı",
  "code": "RATE_LIMITED",
  "detail": "Bugün için trial hakkın doldu. Üye ol → 10 üretim/ay."
}
```

---

## 3. Auth Endpoints

### 3.1 `POST /auth/register`

```json
// Request
{
  "email": "user@example.com",
  "password": "secure-pwd-12+chars",
  "full_name": "Ad Soyad",
  "kvkk_consent": true,
  "foreign_transfer_consent": true,
  "marketing_consent": false
}

// 201 Created
{
  "user_id": "uuid",
  "email": "user@example.com",
  "verification_email_sent": true
}

// 409 CONFLICT
// 400 VALIDATION_ERROR (kvkk_consent zorunlu)
```

### 3.2 `POST /auth/login`

```json
// Request
{ "email": "user@example.com", "password": "..." }

// 200 OK
{
  "access_token": "eyJ...",
  "refresh_token": "rf_...",
  "token_type": "Bearer",
  "expires_in": 900,
  "user": {
    "id": "uuid",
    "email": "...",
    "role": "user",
    "tier": "free",
    "email_verified": true
  }
}

// 401 UNAUTHENTICATED — credential hatalı
// 403 EMAIL_NOT_VERIFIED
```

### 3.3 `POST /auth/refresh`

```json
// Request
{ "refresh_token": "rf_..." }

// 200 OK
{ "access_token": "eyJ...", "expires_in": 900 }
```

### 3.4 `POST /auth/logout`

**Auth:** Bearer
```json
// 204 No Content
```

### 3.5 `POST /auth/forgot-password`

```json
// Request
{ "email": "user@example.com" }
// 202 Accepted (her durumda, enumeration koruması)
```

### 3.6 `POST /auth/reset-password`

```json
// Request
{ "token": "rst_...", "new_password": "..." }
// 200 OK
```

### 3.7 `POST /auth/verify-email`

```json
// Request
{ "token": "ev_..." }
// 200 OK { "verified": true }
```

### 3.8 `POST /auth/2fa/setup` (Faz 6)

**Auth:** Bearer
```json
// 200 OK
{
  "secret": "JBSWY3DPEHPK3PXP",
  "qr_url": "otpauth://totp/Nodrat:user@example.com?secret=...",
  "backup_codes": ["...", "..."]
}
```

### 3.9 `POST /auth/2fa/verify`

```json
// Request
{ "code": "123456" }
// 200 OK { "enabled": true }
```

---

## 4. Admin: Source Management

### 4.1 `POST /admin/sources`

**Auth:** Bearer (super_admin)
**Audit log:** Evet

```json
// Request — RSS source
{
  "name": "BBC Türkçe",
  "slug": "bbc-tr",
  "domain": "bbc.com",
  "type": "rss",
  "base_url": "https://www.bbc.com/turkce",
  "language": "tr",
  "country": "TR",
  "category": "haber",
  "reliability_score": 0.85,
  "crawl_interval_minutes": 30,
  "tos_acknowledged": true,
  "config": {
    "rss_url": "https://feeds.bbci.co.uk/turkce/rss.xml",
    "field_map": {
      "link": "link",
      "title": "title",
      "published_at": "pubDate",
      "image": "media:thumbnail"
    },
    "detail_extraction": {
      "method": "readability",
      "fallback": "trafilatura"
    }
  }
}

// 201 Created
{
  "id": "uuid",
  "name": "BBC Türkçe",
  "slug": "bbc-tr",
  "is_active": false,
  "created_at": "...",
  "active_config_id": "uuid"
}

// 409 CONFLICT — slug taken
// 422 — robots.txt non-compliant (admin override gerek)
```

### 4.2 `GET /admin/sources`

```http
GET /admin/sources?type=rss&is_active=true&limit=50&cursor=...
```

```json
// 200 OK
{
  "data": [
    {
      "id": "uuid",
      "name": "BBC Türkçe",
      "type": "rss",
      "is_active": true,
      "language": "tr",
      "reliability_score": 0.85,
      "last_crawled_at": "...",
      "health": {
        "status": "green",
        "last_success_at": "...",
        "failure_count_24h": 0,
        "avg_extract_confidence": 0.91
      }
    }
  ],
  "pagination": { ... }
}
```

### 4.3 `GET /admin/sources/{id}`

```json
// 200 OK
{
  "id": "uuid",
  "name": "...",
  "type": "rss",
  "active_config": { ... },
  "configs_history": [
    { "version": 2, "is_active": true, "created_at": "...", "created_by": "..." },
    { "version": 1, "is_active": false, "created_at": "..." }
  ],
  "health": { ... },
  "stats": {
    "articles_total": 1452,
    "articles_last_24h": 47,
    "duplicate_rate": 0.12,
    "avg_extraction_confidence": 0.89
  }
}
```

### 4.4 `PATCH /admin/sources/{id}`

```json
// Request — yalnızca config update (yeni version oluşturur)
{
  "config": {
    "list_selectors": {
      "card": ".news-card",
      "title": ".news-card h2",
      ...
    }
  },
  "is_active": true,
  "crawl_interval_minutes": 60
}

// 200 OK
// Yeni source_configs satırı oluşur, eskisi pasifleşir
```

### 4.5 `POST /admin/sources/{id}/test-listing`

Liste sayfası selector test (PRD §1.4).

**Auth:** Bearer (super_admin)
**Side effect:** Yok (sadece test, kayıt yok)

```json
// Request
{
  "selectors": {
    "card": ".news-card",
    "title": ".news-card h2",
    "link": ".news-card a",
    "image": ".news-card img",
    "date": ".news-date"
  }
}

// 200 OK
{
  "url": "https://example.com/category",
  "fetch_status": 200,
  "card_count": 12,
  "preview": [
    {
      "title": "...",
      "link": "...",
      "image_url": "...",
      "date": "..."
    }
  ],
  "warnings": ["3 cards without image"],
  "errors": []
}
```

### 4.6 `POST /admin/sources/{id}/test-detail`

Detay sayfası extractor test.

```json
// Request
{
  "url": "https://example.com/news/123",
  "method": "readability"
}

// 200 OK
{
  "url": "...",
  "http_status": 200,
  "final_canonical_url": "...",
  "extracted": {
    "title": "...",
    "subtitle": "...",
    "author": "...",
    "published_at": "...",
    "clean_text": "...",
    "main_image_url": "...",
    "gallery_image_urls": ["..."],
    "language": "tr"
  },
  "metrics": {
    "extraction_confidence": 0.92,
    "html_cleanup_score": 0.88,
    "text_length": 4521,
    "paragraph_count": 18,
    "boilerplate_ratio": 0.08
  },
  "fallback_chain_used": ["readability"]
}
```

### 4.7 `POST /admin/sources/{id}/crawl-now`

Manuel tetikleme.

```json
// 202 Accepted
{
  "job_id": "uuid",
  "status": "queued",
  "scheduled_at": "..."
}
```

### 4.8 `GET /admin/sources/{id}/health`

```json
// 200 OK
{
  "status": "green",
  "last_success_at": "...",
  "last_failure_at": "...",
  "failure_count_24h": 0,
  "avg_fetch_ms": 412,
  "avg_extract_confidence": 0.91,
  "last_error": null,
  "trend_7d": [
    { "date": "2026-04-25", "success_rate": 0.98 },
    ...
  ]
}
```

---

## 5. Admin: Article Management

### 5.1 `GET /admin/articles`

```http
GET /admin/articles?source_id=...&status=cleaned&from=2026-05-01&limit=50&cursor=...
```

```json
// 200 OK
{
  "data": [
    {
      "id": "uuid",
      "source_name": "BBC Türkçe",
      "title": "...",
      "canonical_url": "...",
      "published_at": "...",
      "status": "cleaned",
      "extraction_confidence": 0.91,
      "image_count": 3,
      "language": "tr"
    }
  ],
  "pagination": { ... }
}
```

### 5.2 `GET /admin/articles/{id}`

```json
// 200 OK
{
  "id": "uuid",
  "source": { "id": "...", "name": "..." },
  "canonical_url": "...",
  "title": "...",
  "subtitle": "...",
  "author": "...",
  "published_at": "...",
  "clean_text": "...",
  "language": "tr",
  "status": "cleaned",
  "extraction_confidence": 0.91,
  "content_hash": "...",
  "images": [
    { "id": "...", "storage_url": "...", "caption": "..." }
  ],
  "chunks_count": 4,
  "in_event_clusters": ["..."]
}
```

### 5.3 `POST /admin/articles/{id}/reprocess`

```json
// Request
{ "steps": ["extract", "clean", "embed"] }

// 202 Accepted
{ "job_ids": ["uuid", ...] }
```

### 5.4 `GET /admin/articles/{id}/raw`

Orijinal HTML snapshot (Faz 2+'da MinIO'dan).

```http
// 200 OK — text/html veya redirect to MinIO presigned URL
```

### 5.5 `GET /admin/articles/{id}/images`

```json
// 200 OK
{
  "data": [
    {
      "id": "...",
      "original_url": "...",
      "storage_url": "...",
      "mime_type": "image/jpeg",
      "width": 800,
      "height": 600,
      "discovered_from": "detail",
      "status": "downloaded"
    }
  ]
}
```

---

## 6. Admin: Queue Management

### 6.1 `GET /admin/queue/overview`

```json
// 200 OK
{
  "queues": [
    {
      "name": "crawl_queue",
      "active_count": 3,
      "queued_count": 47,
      "scheduled_count": 12,
      "failed_count_24h": 2
    },
    {
      "name": "embedding_queue",
      "active_count": 1,
      "queued_count": 21,
      ...
    }
  ],
  "workers": [
    { "name": "worker_scraper", "status": "online", "concurrency": 2 }
  ]
}
```

### 6.2 `GET /admin/queue/jobs/{type}`

```http
GET /admin/queue/jobs/article.fetch_detail?status=running&limit=50
```

```json
// 200 OK
{
  "data": [
    {
      "id": "uuid",
      "job_type": "article.fetch_detail",
      "status": "running",
      "priority": 50,
      "attempt_count": 1,
      "scheduled_at": "...",
      "started_at": "...",
      "payload": { "url": "...", "source_id": "..." }
    }
  ]
}
```

### 6.3 `GET /admin/queue/failed`

```json
// 200 OK
{
  "data": [
    {
      "id": "uuid",
      "job_type": "article.fetch_detail",
      "source_id": "...",
      "article_url": "...",
      "error_message": "HTTP 429",
      "retry_count": 3,
      "last_attempt_at": "...",
      "stack_trace": "..."
    }
  ]
}
```

### 6.4 `POST /admin/queue/jobs/{id}/retry`

```json
// 202 Accepted
{ "new_job_id": "uuid", "scheduled_at": "..." }
```

### 6.5 `DELETE /admin/queue/failed/{id}`

```json
// 204 No Content
// failed_jobs.resolved_at set edilir
```

---

## 7. Admin: Provider Config

### 7.1 `GET /admin/providers`

```json
// 200 OK
{
  "data": [
    {
      "id": "...",
      "name": "deepseek_v3",
      "type": "llm",
      "is_active": true,
      "priority": 100,
      "cost_per_1m_input": 0.27,
      "cost_per_1m_output": 1.10,
      "monthly_cost_cap_usd": 200.00,
      "current_month_spend_usd": 12.40,
      "supports_chat": true
    }
  ]
}
```

### 7.2 `PATCH /admin/providers/{id}`

```json
// Request
{ "is_active": false, "priority": 50, "monthly_cost_cap_usd": 250.00 }
// 200 OK — audit log
```

### 7.3 `POST /admin/providers/{id}/test`

```json
// Request
{ "operation": "chat" | "embedding" | "rerank" }

// 200 OK
{
  "success": true,
  "latency_ms": 421,
  "sample_output_excerpt": "..."
}
// 502 PROVIDER_ERROR
```

---

## 8. Admin: Image & Entity (Faz 4)

### 8.1 `GET /admin/images`

```http
GET /admin/images?status=downloaded&has_labels=false&limit=50
```

```json
// 200 OK — list
```

### 8.2 `GET /admin/images/{id}`

```json
// 200 OK
{
  "id": "...",
  "article": { "id": "...", "title": "..." },
  "storage_url": "...",
  "analysis": {
    "vlm_caption": "...",
    "ocr_text": "...",
    "auto_label_candidates": [
      { "entity_id": "...", "confidence": 0.84 }
    ]
  },
  "labels": [
    { "id": "...", "entity": { "name": "Özgür Özel", "type": "person" },
      "status": "verified", "verified_by": "..." }
  ],
  "similar_images": [
    { "id": "...", "similarity": 0.92, "storage_url": "..." }
  ]
}
```

### 8.3 `POST /admin/images/{id}/analyze`

```json
// 202 Accepted — VLM + OCR + embedding kuyruğa
```

### 8.4 `POST /admin/images/{id}/labels`

```json
// Request
{ "entity_id": "...", "label_type": "person", "status": "verified" }
// 201 Created
```

### 8.5 `PATCH /admin/image-labels/{id}`

```json
// Request
{ "status": "rejected" }  // veya 'verified', 'uncertain'
// 200 OK
```

### 8.6 `GET /admin/entities`

```json
// 200 OK
{
  "data": [
    {
      "id": "...",
      "type": "person",
      "name": "Özgür Özel",
      "aliases": ["CHP Genel Başkanı"],
      "is_public_figure": true,
      "label_count": 47
    }
  ]
}
```

### 8.7 `POST /admin/entities`

```json
// Request
{
  "type": "person",
  "name": "...",
  "aliases": ["..."],
  "description": "...",
  "is_public_figure": true
}
// 201 Created
```

---

## 9. Admin: User & Plan Management

### 9.1 `GET /admin/users`

```http
GET /admin/users?tier=pro&limit=50&cursor=...
```

### 9.2 `GET /admin/users/{id}`

```json
// 200 OK
{
  "id": "...",
  "email": "...",
  "full_name": "...",
  "tier": "pro",
  "subscription": { "plan_code": "pro", "status": "active", ... },
  "stats": {
    "generations_total": 248,
    "generations_30d": 45,
    "saved_count": 67,
    "last_login_at": "..."
  }
}
```

### 9.3 `GET /admin/users/{id}/usage`

```json
// 200 OK
{
  "current_period": {
    "from": "2026-05-01",
    "to": "2026-05-31",
    "generation_count": 45,
    "limit": 500,
    "cost_usd": 0.92
  },
  "history_12m": [ ... ]
}
```

### 9.4 `GET /admin/plans`

```json
// 200 OK — Data Model §10.3 seed
```

### 9.5 `GET /admin/subscriptions`

```http
GET /admin/subscriptions?status=active&plan_code=pro
```

---

## 10. Admin: Observability

### 10.1 `GET /admin/observability/metrics`

```json
// 200 OK
{
  "north_star": { "wsgau": 2.7, "delta_7d": 0.12 },
  "summary": {
    "wau": 145,
    "mau": 380,
    "mrr_usd": 2340,
    "active_paid_users": 67
  },
  "operational": {
    "queue_lag_seconds": { "embedding": 12, "crawl": 3 },
    "source_health_green": 47,
    "source_health_total": 50,
    "daily_cost_usd": 4.12
  }
}
```

### 10.2 `GET /admin/observability/audit-log`

```http
GET /admin/observability/audit-log?actor_id=...&action=source.create
```

### 10.3 `GET /admin/observability/storage`

```json
// 200 OK
{
  "postgres_size_gb": 2.1,
  "minio_size_gb": 5.4,
  "redis_size_mb": 142,
  "vps_disk_used_pct": 18.4
}
```

### 10.4 `GET /admin/rag/pipeline-comparison` (#440)

**Auth:** Bearer (admin)
**Amaç:** İki tarih aralığında LLM pipeline metriklerini yan yana karşılaştır. Optimizasyon dalgalarının (örn. prompt cache tuning, top_k tuning, model değişikliği) etkisini retrospektif ölçmek için. UI: `/admin/rag` sayfası "Performans" sekmesi.

**Query parametreleri (hepsi opsiyonel — default: son 7 gün vs önceki 7 gün):**
- `from_a: datetime` — Dönem A başlangıcı (default: now − 14d)
- `to_a: datetime` — Dönem A bitişi (default: now − 7d)
- `from_b: datetime` — Dönem B başlangıcı (default: now − 7d)
- `to_b: datetime` — Dönem B bitişi (default: now)

**Veri kapsamı:**
- `provider_call_logs` — sadece `operation = 'chat'` ve `success = TRUE` (LLM çağrıları; embedding/rerank hariç).
- `generations` — sadece `output_type IN ('x_post', 'x_thread', 'summary', 'headline')` (Content Generator çıktıları).

```json
// 200 OK
{
  "period_a": {
    "period_start": "2026-05-01T00:00:00Z",
    "period_end":   "2026-05-08T00:00:00Z",
    "sample_count": 247,
    "avg_input_tokens": 5800.0,
    "avg_output_tokens": 1800.0,
    "cache_hit_ratio": 0.05,
    "avg_cost_usd_per_req": 0.0036,
    "p50_latency_ms": 4000,
    "p95_latency_ms": 7500,
    "halu_flag_rate": 0.018,
    "insufficient_data_rate": 0.04,
    "completed_generation_count": 192
  },
  "period_b": {
    "period_start": "2026-05-08T00:00:00Z",
    "period_end":   "2026-05-15T00:00:00Z",
    "sample_count": 268,
    "avg_input_tokens": 3200.0,
    "avg_output_tokens": 1700.0,
    "cache_hit_ratio": 0.42,
    "avg_cost_usd_per_req": 0.0027,
    "p50_latency_ms": 3700,
    "p95_latency_ms": 6800,
    "halu_flag_rate": 0.015,
    "insufficient_data_rate": 0.03,
    "completed_generation_count": 211
  },
  "delta_pct": {
    "avg_input_tokens": -44.83,
    "avg_output_tokens": -5.56,
    "cache_hit_ratio": 740.0,
    "avg_cost_usd_per_req": -25.0,
    "p50_latency_ms": -7.5,
    "p95_latency_ms": -9.33,
    "halu_flag_rate": -16.67
  }
}
```

**Hata kodları:**
- `400 INVALID_RANGE` — `from_a >= to_a` veya `from_b >= to_b`
- `400 TZ_REQUIRED` — datetime parametre timezone bilgisi içermiyor
- `401 AUTH_REQUIRED` — admin token eksik
- `403 FORBIDDEN_NOT_ADMIN` — kullanıcı super_admin değil

**Edge case'ler:**
- Boş dönem (`sample_count = 0`): `avg_*` ve latency alanları `null`. `delta_pct` ilgili alanı da `null`.
- A değeri 0 (örn. `cache_hit_ratio = 0`): `delta_pct` `null` (zero-division koruması).

**Yerine geçen:** Eski `/admin/dashboard/mvp-2-1-delta` endpoint'i ([#432](https://github.com/selmanays/nodrat/issues/432)) silindi. Bu endpoint jenerik versiyonudur; tüm tarih dönemleri için kullanılabilir.

---

## 11. User: Generation (Ana Akış)

### 11.1 `POST /app/generate` ⭐ (Core endpoint)

**Auth:** Bearer (user)
**Idempotency-Key:** Tavsiye edilir
**Quota:** Tier'a göre, hard cap (Pricing §8)

```json
// Request
{
  "request_text": "Bu hafta yapay zeka regülasyonlarıyla ilgili Türkiye ve dünyadaki gelişmeleri kullanarak 5 X paylaşımı üret",
  "output_type": "x_post",     // 'x_post' | 'x_thread' | 'summary' | 'analysis' | 'headline' | 'calendar' | 'briefing'
  "mode_hint": "current",       // opsiyonel; query planner override edebilir
  "tone": "tarafsız",           // opsiyonel
  "length": "short",
  "show_sources": true,
  "style_profile_id": null,     // Faz 5
  "max_posts": 5
}

// 200 OK (sync flow, MVP-1)
{
  "generation_id": "uuid",
  "status": "completed",
  "content_type": "x_post",
  "topic": "yapay zeka regülasyonları",
  "data_coverage": {
    "mode": "weekly",
    "from": "2026-04-25T00:00:00Z",
    "to": "2026-05-01T23:59:59Z",
    "source_count": 8,
    "agenda_card_count": 4,
    "chunk_count": 17
  },
  "posts": [
    {
      "text": "Türkiye yeni AI regülasyon paketinde Avrupa Union AI Act'i baz aldı. Etki: ...",
      "angle": "regülasyon karşılaştırması",
      "char_count": 234,
      "related_agenda_card_ids": ["..."]
    }
  ],
  "sources": [
    {
      "title": "AI Act Türkiye'ye uyumlanıyor",
      "source": "BBC Türkçe",
      "url": "https://...",
      "published_at": "..."
    }
  ],
  "warnings": [],
  "model_used": "deepseek_v3",
  "cost_estimate_usd": 0.0024,
  "created_at": "..."
}

// 422 INSUFFICIENT_DATA
{
  "title": "Veri yetersiz",
  "code": "INSUFFICIENT_DATA",
  "detail": "Bu konu için seçilen dönemde yeterli güvenilir haber verisi bulunamadı.",
  "data_coverage": { "agenda_card_count": 1, "minimum_required": 2 },
  "suggestions": [
    { "label": "Zaman aralığını genişlet (son 14 gün)", "params": { "mode_hint": "weekly" } }
  ]
}

// 403 QUOTA_EXCEEDED
{
  "code": "QUOTA_EXCEEDED",
  "detail": "Bu ay için 100 üretim hakkın doldu. Pro tier 500/ay.",
  "current_period_end": "2026-05-31",
  "upgrade_url": "/app/billing/plans"
}
```

### 11.2 `GET /app/generations`

```http
GET /app/generations?saved=true&mode=current&limit=20&cursor=...
```

```json
// 200 OK
{
  "data": [
    {
      "id": "...",
      "request_text": "...",
      "output_type": "x_post",
      "mode": "current",
      "status": "completed",
      "saved": true,
      "post_count": 5,
      "created_at": "..."
    }
  ],
  "pagination": { ... }
}
```

### 11.3 `GET /app/generations/{id}`

```json
// 200 OK — POST /app/generate response ile aynı şema
```

### 11.4 `POST /app/generations/{id}/save`

```json
// Request
{ "note": "Pazartesi paylaşım için" }
// 200 OK { "saved_at": "..." }
```

### 11.5 `DELETE /app/generations/{id}/save`

```http
// 204 No Content
```

### 11.6 `POST /app/generations/{id}/regenerate`

```json
// Request — opsiyonel parametre değişikliği
{ "tone": "eleştirel" }

// 202 Accepted — yeni generation oluşturur
{ "new_generation_id": "..." }
```

### 11.7 `POST /app/generations/{id}/flag`

Halüsinasyon / kalite flag (Risk Register R-PRD-01).

```json
// Request
{ "reason": "halu_person" | "halu_date" | "halu_event" | "off_topic" | "tone_off" }
// 200 OK
```

---

## 11.X. Admin: Settings Panel (#262, MVP-1.2)

Hardcoded `config.py` değerleri runtime-tunable. Her endpoint `require_admin` (super_admin role + JWT). Değişiklikler `admin_audit_log`'a yazılır, Redis pub/sub ile <30s'de tüm container'lara yansır.

### 11.X.1 `GET /admin/settings`

Tüm bilinen settings (`SETTING_REGISTRY`). Her item için default + override status.

Query: `?group=rag` (opsiyonel, gruba filter)

Response:
```json
{
  "data": [
    {
      "key": "rerank.min_combined_score",
      "value": 0.18,
      "default": 0.15,
      "type": "float",
      "group": "rag",
      "description": "combined_score < eşik → kart drop",
      "min_value": 0.0,
      "max_value": 1.0,
      "allowed_values": null,
      "requires_restart": false,
      "is_overridden": true,
      "updated_at": "2026-05-03T10:30:00Z",
      "updated_by": "uuid..."
    }
  ],
  "groups": ["rag"]
}
```

### 11.X.2 `GET /admin/settings/{key}`

Tek setting detayı (404 if unknown key).

### 11.X.3 `PUT /admin/settings/{key}`

Body: `{"value": <T>}` — `type`'a uygun cast edilir, `min_value/max_value/allowed_values` validate edilir.

Hatalar:
- 400 `INVALID_TYPE` — cast fail
- 400 `OUT_OF_RANGE` — min/max ihlali
- 404 `NOT_FOUND` — key SETTING_REGISTRY'de değil

Yan etki: audit log, Redis publish `settings:invalidate <key>`.

### 11.X.4 `DELETE /admin/settings/{key}`

DB row sil → caller fallback default'a döner.

---

## 11.Y. Admin: LLM Prompts Management (#262 PR-B, MVP-1.2)

LLM prompt'ları runtime tunable. Version history + 1-click restore. `require_admin` gate, `admin_audit_log`'a action='prompts.update'/'prompts.reset'/'prompts.restore'.

### 11.Y.1 `GET /admin/prompts`

Tüm bilinen prompts (`PROMPT_REGISTRY`) — current + default + override status.

Response item:
```json
{
  "name": "query_planner",
  "version": 3,
  "content": "Sen Nodrat'ın Query Planner ajanısın...",
  "default": "Sen Nodrat'ın Query Planner ajanısın...",  // kod-tarafı
  "description": "Kullanıcı isteğini intent + topic + ...",
  "model_hint": "deepseek-v4-flash",
  "is_overridden": true,
  "updated_at": "2026-05-03T12:00:00Z",
  "updated_by": "uuid..."
}
```

### 11.Y.2 `GET /admin/prompts/{name}/history`

Version archive (latest first). Query: `?limit=20`.

### 11.Y.3 `PUT /admin/prompts/{name}`

Body:
```json
{
  "content": "Yeni prompt metni...",
  "description": "opsiyonel",
  "model_hint": "deepseek-reasoner"
}
```

Yan etki:
- Eğer mevcut versiyon varsa → `app_prompt_history`'ye taşı
- `app_prompts` upsert: yeni `content` + `version + 1`
- Redis pub/sub `prompts:invalidate <name>`
- Audit log

Response: yeni versiyon DTO.

### 11.Y.4 `DELETE /admin/prompts/{name}`

Mevcut row sil → caller kod-tarafı default'a döner. **History korunur**.

### 11.Y.5 `POST /admin/prompts/{name}/restore/{version}`

History'deki versiyonu yeni current yap (yeni `version` numarası üretilir, original v# silinmez).

Errors: 404 NOT_FOUND (name veya version invalid).

---

## 12. User: Style Profiles (Faz 5)

### 12.1 `POST /app/style-profiles`

**Auth:** Bearer (Pro+ tier)

```json
// Request
{
  "name": "Mete'nin tonu",
  "source_type": "manual",
  "samples": [
    { "text": "..." },
    { "text": "..." }
  ]
}

// 201 Created — async style analyzer çalışır
{ "id": "...", "status": "analyzing" }
```

### 12.2 `GET /app/style-profiles`

```json
// 200 OK
{
  "data": [
    {
      "id": "...",
      "name": "Mete'nin tonu",
      "style_summary": "Analitik ve sade politik yorum",
      "rules": { "sentence_length": "medium", "tone": ["sade","eleştirel"], ... },
      "sample_count": 12,
      "is_ready": true
    }
  ]
}
```

### 12.3 `POST /app/style-profiles/{id}/samples`

```json
// Request
{ "text": "..." }
// 201 Created
```

---

## 13. User: Account & Usage

### 13.1 `GET /app/me`

```json
// 200 OK
{
  "user": {
    "id": "...",
    "email": "...",
    "full_name": "...",
    "tier": "pro",
    "email_verified": true,
    "totp_enabled": false,
    "locale": "tr-TR"
  },
  "subscription": {
    "plan_code": "pro",
    "status": "active",
    "current_period_end": "..."
  },
  "usage": {
    "generations_this_period": 45,
    "limit": 500,
    "remaining": 455
  }
}
```

### 13.2 `PATCH /app/me`

```json
// Request — full_name, locale, marketing_consent
```

### 13.3 `GET /app/usage`

```json
// 200 OK
{
  "current_period": {
    "from": "2026-05-01",
    "to": "2026-05-31",
    "generation_count": 45,
    "limit": 500,
    "by_mode": { "current": 30, "weekly": 12, "comparison": 3 },
    "by_output_type": { "x_post": 35, "x_thread": 8, "summary": 2 }
  }
}
```

### 13.4 `GET /app/me/data-export` (KVKK)

```json
// 202 Accepted — async export, email notification
{ "export_id": "...", "estimated_ready_at": "..." }
```

### 13.5 `DELETE /app/me` (KVKK silme talebi)

```json
// Request
{ "password": "...", "confirmation": "DELETE" }

// 202 Accepted — soft delete, 30 gün sonra hard delete
{ "deleted_at": "...", "hard_delete_at": "..." }
```

---

## 14. User: Billing (Faz 6)

### 14.1 `GET /app/billing/plans`

```json
// 200 OK — public, Data Model §10.3 seed
```

### 14.2 `POST /app/billing/checkout`

```json
// Request
{
  "plan_code": "pro",
  "billing_cycle": "monthly",
  "payment_provider": "iyzico"
}

// 200 OK
{
  "checkout_url": "https://sandbox-iyzico.com/...",
  "session_id": "...",
  "expires_at": "..."
}
```

### 14.3 `GET /app/billing/subscription`

```json
// 200 OK
{
  "plan_code": "pro",
  "status": "active",
  "billing_cycle": "monthly",
  "current_period_start": "...",
  "current_period_end": "...",
  "next_invoice_amount_try": 749.00,
  "payment_provider": "iyzico"
}
```

### 14.4 `POST /app/billing/cancel`

```json
// Request
{ "reason": "too_expensive" | "not_using" | "missing_features" | "chatgpt_enough" | "quality" | "other",
  "feedback": "..." }

// 200 OK
{ "canceled_at": "...", "active_until": "..." }
```

### 14.5 `GET /app/billing/invoices`

```json
// 200 OK
{ "data": [ { "id": "...", "invoice_number": "...", "total_try": 749.00, "earsiv_pdf_url": "..." } ] }
```

---

## 15. Webhooks

### 15.1 `POST /webhooks/payments/iyzico`

**Auth:** HMAC signature header
**Idempotency:** event_id'ye göre

```json
// Request — Iyzico subscription event
{
  "event_type": "subscription.activated",
  "subscription_id": "...",
  "user_id": "...",
  "event_id": "...",
  "timestamp": "..."
}

// 200 OK
// HMAC failsa: 401
```

### 15.2 `POST /webhooks/payments/stripe`

```json
// Stripe standard webhook
// Signature header: Stripe-Signature
```

---

## 16. Internal Endpoints (Worker → API)

⚠️ Sadece internal network'ten erişilebilir.

### 16.1 `POST /internal/rag/plan`

```json
// Request
{
  "user_request": "...",
  "current_time": "2026-05-01T12:00:00Z",
  "user_locale": "tr-TR"
}

// 200 OK — PRD §9.1 contract
{
  "intent": "current_content_generation",
  "topic_query": "...",
  "mode": "current",
  "timeframes": [],
  "output_type": "x_posts",
  "tone": "...",
  "constraints": [],
  "needs_sources": true
}
```

### 16.2 `POST /internal/rag/retrieve`

```json
// Request
{
  "topic_query": "...",
  "mode": "current",
  "timeframes": [{"from": "...", "to": "..."}],
  "min_results": 3,
  "max_results": 10
}

// 200 OK
{
  "agenda_cards": [ ... ],
  "supplementary_chunks": [ ... ],
  "data_coverage": { "source_count": 5, "card_count": 3 }
}
```

### 16.3 `POST /internal/rag/generate-card`

```json
// Request
{
  "event_cluster": { ... },
  "articles": [ ... ],
  "current_time": "..."
}
// 200 OK — PRD §9.2 contract
```

### 16.4 `POST /internal/rag/generate-content`

```json
// Request
{
  "request": "...",
  "retrieval_plan": { ... },
  "agenda_cards": [ ... ],
  "style_profile": null,
  "output_constraints": { "max_posts": 5 }
}
// 200 OK — PRD §9.3 contract
```

---

## 17. Rate Limit Politikaları

```text
Endpoint                           Per User           Per IP             Per Tier
─────────────────────────────────────────────────────────────────────────────────────
POST /public/trial/generate        —                  1/gün+fingerprint  N/A
POST /auth/login                   —                  10/dk              N/A
POST /auth/register                —                  3/saat             N/A
POST /app/generate                 5/sa (free)        —                  Pricing §3.1
                                   20/sa (starter)
                                   60/sa (pro)
                                   120/sa (agency seat)
GET  /app/generations              60/dk              —                  —
POST /admin/sources                30/dk              —                  super_admin only
POST /admin/sources/*/crawl-now    10/dk              —                  super_admin only
GET  /health                       60/dk              —                  —
```

---

## 18. MVP-1 Endpoint Listesi (ÖZET)

```text
✅ Auth:
  POST /auth/register
  POST /auth/login
  POST /auth/logout
  POST /auth/refresh
  POST /auth/verify-email
  POST /auth/forgot-password
  POST /auth/reset-password

✅ Admin (3-5 RSS source ile MVP):
  POST /admin/sources                    (RSS only)
  GET  /admin/sources
  GET  /admin/sources/{id}
  PATCH /admin/sources/{id}
  POST /admin/sources/{id}/test-detail   (test-listing MVP-2'de)
  POST /admin/sources/{id}/crawl-now
  GET  /admin/sources/{id}/health

  GET  /admin/articles
  GET  /admin/articles/{id}
  POST /admin/articles/{id}/reprocess

  GET  /admin/queue/overview
  GET  /admin/queue/failed
  POST /admin/queue/jobs/{id}/retry

✅ User:
  GET  /app/me
  POST /app/generate                     (current mode + x_post only)
  GET  /app/generations
  GET  /app/generations/{id}
  POST /app/generations/{id}/save
  GET  /app/usage

✅ Public:
  GET  /health
  GET  /readiness

❌ MVP-2'ye:
  test-listing, image endpoints, billing, style-profiles,
  comparison mode, x_thread, summary
```

---

## 19. OpenAPI Schema Üretimi

```text
FastAPI otomatik üretir:
  /api/openapi.json   — full spec
  /api/docs           — Swagger UI (sadece dev/staging)
  /api/redoc          — ReDoc

Production'da /docs ve /redoc disable.
shared-types paketi:
  Pydantic → JSON Schema → TypeScript codegen
  apps/web/src/types/api.ts (auto-gen)
```

---

## 20. Karar Noktaları

| ID | Karar | Önerim | Etki |
|---|---|---|---|
| D1 | Versioning | URL prefix yok (header X-API-Version) | Faz 7+ /v2 |
| D2 | Auth tipi | JWT access (15dk) + refresh (30g) | Standard |
| D3 | Pagination | Cursor-based | Performans |
| D4 | Error format | RFC 7807 problem+json | Standart |
| D5 | Rate limit | Slim middleware (Redis sliding) | Tier'a göre |
| D6 | Idempotency | POST /app/generate'de tavsiye | UX |
| D7 | OpenAPI publish | Sadece staging /docs | Production gizli |
| D8 | Webhook signature | HMAC + replay protection | Security |
| D9 | Internal endpoints | Network izolasyonu (internal docker) | Defense in depth |
| D10 | Generation sync mı async mı? | MVP-1 sync, Faz 7+ async option | UX vs scale |

---

## 21. Çapraz Referans

```text
/app/generate                 → PRD §3, IA §10.6, Prompt Contracts (sıradaki)
/admin/sources/* test         → PRD §1.4, UX Wireframes (sıradaki)
/internal/rag/*               → Architecture §3, Prompt Contracts
Rate limit                    → Pricing §8.1, Architecture §6
Auth flow                     → Threat Model (sıradaki)
Idempotency                   → Architecture §8 deployment
Cost tracking                 → Unit Economics §6, Data Model §4.5
KVKK data-export/delete       → Legal §2.3
Webhooks signature            → Security & Threat Model
OpenAPI codegen               → Architecture §11.2 packages/shared-types
```

---

**Sonuç:** **~50 endpoint** dokümante; MVP-1'de **~22 aktif**. **`POST /app/generate` çekirdek endpoint**, RFC 7807 hata formatı, JWT+refresh auth, cursor pagination. **Idempotency-Key** generation'da tavsiye, billing'de zorunlu. **Rate limit tier'a göre** (Pricing §3.1 ile uyumlu). **OpenAPI auto-gen FastAPI'den**, frontend codegen ile shared-types paketi tutarlı kalır.
