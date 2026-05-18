# Nodrat — API Sözleşmeleri (OpenAPI Spec)

**Doküman türü:** REST API Contracts
**Sürüm:** v0.8
**Son güncelleme:** 2026-05-17 (v1.0 — #927 zinciri §17.5.6: `search_news` tool meta `recency_requested`/`newest_published_at`/`freshness_gap_days` + KOD-ÜRETİLEN "DİKKAT—TAZELİK" result_text yönergesi (#928/#929); Türkçe entity match kalite-iyileşmesi notu (#939/#942/#947 — şema değişmez). v0.9 — denetim staleness sync: §17.5.7 wikipedia-fallback KALDIRILDI notu (§17.5.6 ile çelişki giderildi), §17 rate-limit + §18 endpoint listesi `/app/generate*`→`/chat/*`, §11.2b deprecation marker + yanlış "backward compat korunur" düzeltildi). Önceki: 2026-05-14 (v0.8 — #800 chat-only migration: §11 `/app/generate*` + `/app/generations/*` kaldırıldı; §17.5 `/chat/*` primary). 2026-05-11 (v0.7 — #696/#700 admin RAG 4 endpoint)
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
      "deepseek": "ok",
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

Kaynağın **runtime tunable alanlarını** günceller (#565). Slug/domain/type/base_url **immutable**; `is_active` ayrı endpoint (`POST /activate`) — compliance checklist bypass yok.

**Auth:** Bearer (super_admin)
**Side effect:** Source kaydı update + `admin_audit_log` (`source.update` action, değişen alanların `from`/`to` snapshot'ı)

```json
// Request — partial update; en az 1 alan zorunlu (yoksa 422 EMPTY_PATCH)
{
  "crawl_interval_minutes": 5,        // 5..1440 dakika; bant tasarrufu için Conditional GET aktif
  "realtime_enabled": true,            // Faz 2+ adaptive tier opt-in (default false)
  "name": "Yeni İsim",                 // 2..120 char (opsiyonel)
  "category": "siyaset"                // 0..80 char (opsiyonel; null da olur)
}

// 200 OK — güncel SourcePublic
{
  "id": "uuid",
  "name": "...",
  "slug": "...",
  "domain": "...",
  "type": "rss",
  "base_url": "...",
  "language": "tr",
  "country": "TR",
  "category": "...",
  "reliability_score": 0.7,
  "is_active": true,
  "crawl_interval_minutes": 5,
  "robots_txt_compliant": true,
  "tos_acknowledged": true,
  "realtime_enabled": true,
  "polling_tier": "normal",          // 'hot' | 'normal' | 'cold' | 'hibernate' — Faz 3'te apply edilir
  "would_be_tier": "hot",            // #578 Faz 2 shadow mode hesabı (henüz uygulanmadı)
  "tier_changed_at": "2026-05-10T11:30:00Z",
  "tier_metadata": {                  // compute_tier telemetri
    "items_1h": 5,
    "items_6h": 18,
    "last_item_at": "2026-05-10T11:55:30Z",
    "hours_since_new": 0.075,
    "consecutive_unchanged": 0,
    "computed_at": "2026-05-10T12:00:00Z",
    "cold_start": false,
    "candidate_tier": "hot",
    "dwell_remaining_sec": 0
  },
  "consecutive_unchanged": 0
}

// 422 EMPTY_PATCH — hiç alan gelmemiş
// 422 ValidationError — crawl_interval_minutes range dışı (< 5 veya > 1440)
// 404 SOURCE_NOT_FOUND
```

**Notlar:**
- `realtime_enabled=true` set edildiğinde davranış henüz değişmez (Faz 2'de adaptive tier devreye girince etkili olur). Bu PR (Faz 0+1) sadece bayrak persist eder.
- `crawl_interval_minutes` her kaynak için bağımsızdır; düşük değerler kaynak sunucusuna yük bindirir, ama Conditional GET (ETag/If-Modified-Since) aktif olduğu için bandwidth ~%80 düşüktür.
- Config (selectors, RSS field maps) güncellemesi için ayrı versioned endpoint: `POST /admin/sources/{id}/configs` (yeni version oluşturur, eskisi pasifleşir).

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

### 4.6 `POST /admin/sources/{id}/test-detail` — KALDIRILDI (#904)

Detay extraction artık generic (Tier-0 JSON-LD → trafilatura density →
fallback); kaynağa özel detay selector'ı olmadığı için bu test endpoint'i
**kaldırıldı**. Detay çıkarım sağlığı per-domain telemetri ile izlenir:

### 4.6 `GET /admin/sources/{id}/extraction-stats` (#904 — YENİ)

Kaynak detay sayfasında gösterilen per-domain çıkarım telemetrisi.

```json
// 200 OK
{
  "avg_confidence": 0.86,
  "quarantine_rate": 0.04,
  "strategy_breakdown": { "json_ld": 312, "density": 1180, "fallback": 27 },
  "buckets": [ { "day": "2026-05-15", "avg": 0.84 } ]
}
```

`avg_confidence < 0.70` → kaynak `last_status='red'` + warning DLQ alarmı
(R-OPS-01 gate). `POST /admin/sources/{id}/test-listing` (§4.5) KORUNUR
(`category_page` keşfi için liste selector testi hâlâ gerekli).

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

// 409 Conflict — yalnız terminal 'discarded' için (#904)
{ "code": "DISCARDED_NOT_REPROCESSABLE" }
```

#904: `status='quarantine'` makaleler reprocess EDİLEBİLİR (eski `archived`
409 davranışı kaldırıldı). Yalnız `discarded` (gerçek kalıcı) reprocess
edilemez. Toplu kurtarma: `tasks.articles.recover_quarantined` (admin
`/admin/queue/maintenance/{task}/run-now` üzerinden tetiklenir).

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
      "name": "deepseek",
      "type": "llm",
      "is_active": true,
      "priority": 100,
      "cost_per_1m_input": 0.14,
      "cost_per_1m_output": 0.28,
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

### 10.5 `POST /admin/rag/benchmark/run` (#179, #696 Faz A, #700 async)

**Auth:** Bearer (admin)
**Amaç:** Manuel retrieval benchmark trigger. #700 sonrası async — anında `started: true` döner, polling ile takip.

**Query parametreleri:**
- `golden: string` (default `"retrieval_golden_tr.yaml"`) — golden set adı
- `suite: "cards" | "chunks"` (default `"chunks"`) — #696 Faz A. **chunks** = production /api/generate/stream path (NER + IDF dahil); **cards** = legacy agenda card retrieval
- `top_k: int` (default 20)
- `candidate_pool: int` (default 50) — #696 düzeltme (önce admin endpoint'inden geçmiyordu)

**Response 200:**
```json
{
  "started": true,
  "run_id": "uuid-of-newest-completed-or-null",
  "message": "Benchmark arka planda başlatıldı (suite=chunks, ~5-10dk)..."
}
```

`started: false` döner eğer halihazırda bir koşum varsa.

### 10.6 `GET /admin/rag/benchmark/status` (#700)

**Auth:** Bearer (admin)
**Amaç:** Background benchmark koşum durumu (frontend polling, 10s interval).

```json
{
  "running": true,
  "started_at": "2026-05-11T15:00:00Z",
  "triggered_by": "admin:user@example.com",
  "suite": "chunks",
  "golden": "retrieval_golden_tr.yaml",
  "error": null
}
```

### 10.7 `GET /admin/rag/ner-stats` (#696 B5, Faz 6.1)

**Auth:** Bearer (admin)
**Amaç:** NER pipeline mode dağılımı telemetri (process-lifetime in-memory counter). UI: `/admin/rag` sayfası "NER" sekmesi.

```json
{
  "total": 1247,
  "distribution": {
    "multi_and": 312,
    "multi_and_common": 89,
    "single_rare": 645,
    "no_match": 201
  },
  "ratios": {
    "multi_and": 0.2502,
    "multi_and_common": 0.0714,
    "single_rare": 0.5172,
    "no_match": 0.1612
  },
  "first_seen": "2026-05-11T08:00:00Z",
  "last_seen": "2026-05-11T15:30:00Z",
  "note": "Process-lifetime counter; container restart'ta sıfırlanır."
}
```

### 10.8 `GET /admin/rag/health` (extended #696 B6 warm_up)

`warm_up` alanı (model warm-up duration metriği — PR-A #685 cold start fix):

```json
{
  "flags": { ... },
  "counts": { ... },
  "last_eval": { ... },
  "warm_up": {
    "started_at": "2026-05-11T08:00:00Z",
    "completed_at": "2026-05-11T08:00:00.250Z",
    "duration_ms": 248,
    "embedding_ms": 145,
    "rerank_ms": 103,
    "ok": true
  }
}
```

### 10.9 `POST /admin/rag/inspect-query` (extended #696 B4)

Request'e `suite: "cards" | "chunks"` eklendi. Chunks suite'inde response'a `ner` alanı:

```json
{
  "query": "...",
  "suite": "chunks",
  "ner": {
    "enabled": true,
    "query_entities": ["karşıyaka", "bursaspor"],
    "df_map": {"karşıyaka": 18, "bursaspor": 6},
    "mode": "multi_and",
    "target_aids_count": 2,
    "target_aids_sample": ["ddae4672-...", "8d528735-..."]
  },
  ...
}
```

---

## 11. User: Generation (Ana Akış)

> ⚠️ **2026-05-14 — Chat-only migration (#800 epic):** Bu bölümdeki **tüm endpoint'ler kaldırıldı.** `/app/generate`, `/app/generate-stream`, `/app/generations/*` (list/detail/save/regenerate/flag/action/delete) route'ları artık 404 döner. `apps/api/app/api/app_generate.py` + `app_generate_stream.py` dosyaları SİLİNDİ.
>
> **Yeni primary akış:** §17.5 `/chat/*` endpoint'leri. Eşdeğer mapping:
>
> | Eski endpoint | Yeni eşdeğer |
> |---|---|
> | `POST /app/generate` | `POST /chat/conversations` + `POST /chat/conversations/{id}/messages` (SSE) |
> | `POST /app/generate-stream` | `POST /chat/conversations/{id}/messages` (SSE) |
> | `GET /app/generations` | `GET /chat/conversations` |
> | `GET /app/generations/{id}` | `GET /chat/conversations/{id}` |
> | `POST /app/generations/{id}/save` | (DROP — kayıtlı sayfası kaldırıldı) |
> | `DELETE /app/generations/{id}/save` | (DROP) |
> | `POST /app/generations/{id}/flag` | `POST /chat/messages/{id}/flag-halu` (DPO chosen_content desteği) |
> | `POST /app/generations/{id}/copied\|posted\|edited` | `POST /chat/messages/{id}/action` (action enum) |
> | `DELETE /app/generations/{id}` | `DELETE /chat/conversations/{id}` (archive) |
>
> Aşağıdaki §11.1-§11.7 **historical contract** olarak bilgi amaçlı durur — production'da çalışmaz. İlgili wiki kararı: [chat-only-migration](../../wiki/decisions/chat-only-migration.md). PR'lar: [#800](https://github.com/selmanays/nodrat/pull/800), [#805](https://github.com/selmanays/nodrat/pull/805).

### 11.1 `POST /app/generate` ⭐ (DEPRECATED — KALDIRILDI 2026-05-14)

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
  "model_used": "deepseek",
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

### 11.2b `POST /app/generate-stream` ⭐ SSE streaming (issue #527) — KALDIRILDI 2026-05-14

> ⚠️ **KALDIRILDI (#800).** Route 404. Yerine `POST /chat/conversations/{id}/messages` (SSE, agentic generate — §17.5.6). Aşağısı tarihsel sözleşmedir; `text/event-stream` akış mimarisinin evrimi için §17.5.6 + [agentic-generate-orchestration](../../wiki/decisions/agentic-generate-orchestration.md).

`/app/generate` ile **aynı request payload + auth + quota + style profile** semantiği; tek fark response gövdesi `text/event-stream` SSE event akışı şeklinde gelir. Hedef: TTFT (Time-To-First-Token) <1s.

```http
POST /app/generate-stream
Authorization: Bearer <access_token>
Content-Type: application/json
Accept: text/event-stream
```

Request payload `/app/generate` ile birebir aynı.

**Response — SSE event sequence (sırasıyla):**

```text
event: progress
data: {"stage": "planning", "detail": "Plan hazırlanıyor"}

event: meta
data: {
  "generation_id": "uuid",
  "mode": "current",
  "output_type": "x_post",
  "tone": "tarafsız",
  "plan": {"intent": "...", "topic_query": "...", "keywords": [...], "requested_count": 3}
}

event: progress
data: {"stage": "retrieving", "detail": "Kaynaklar getiriliyor"}

event: progress
data: {"stage": "generating", "detail": "İçerik üretiliyor", "agenda_count": 5}

event: chunk
data: {"delta": "{\"posts\":"}                  # ham LLM token deltası
... (N chunk eventi)

event: post
data: {                                          # tamamlanan her post anlık emit
  "index": 0,
  "text": "İlk paylaşım metni [#1]",
  "angle": "haber-özet",
  "char_count": 27,
  "related_agenda_card_ids": ["uuid"]
}
... (her post için bir event)

event: parsed
data: {                                          # tüm response yapılandırılmış
  "posts": [...],
  "summary": "...",
  "sources": [{"title": "...", "source": "...", "url": "..."}, ...],
  "warnings": [],
  "summary_doc_title": "",
  "summary_doc_items": []
}

event: progress
data: {"stage": "validating", "detail": "Doğrulama"}

event: citation
data: {                                          # citation post-stream
  "repairs": 0,
  "unsupported_warnings": [],
  "posts_after_repair": [{"index": 0, "text": "...", "char_count": 27}, ...]
}

event: image                                     # opsiyonel — suggest_enabled=true ise
data: {"image_id": "uuid", "original_url": "...", ...}

event: done
data: {
  "generation_id": "uuid",
  "status": "completed",
  "cost_usd": 0.0034,
  "completed_at": "2026-05-09T18:30:21.987Z",
  "ttfb_ms": 720
}
```

**Hata akışı:**
- Quota / consent ihlali — stream başlamadan HTTP 429 / 403 (eski endpoint ile aynı).
- Stream içi hata (planner timeout, provider 5xx, parse fail) — `event: error` + `event: done` (status="failed"). Connection kapanır.

**Mimari karakteristikler:**

- Speculative retrieval: kullanıcı sorgusunun embedding'i planner ile paralel hesaplanır; planner sonucu raw sorguya çok yakınsa embedding reuse, aksi halde re-embed. Net kazanç ~150-300ms ortalama.
- Planner cache: `qp:v1:{sha1(request_text+locale+tier+yyyymmdd)}` Redis 24h TTL. Cache hit'te plan_query LLM çağrısı yapılmaz (~10ms).
- DeepSeek streaming: provider `stream: true` + `stream_options.include_usage: true`. Final chunk'ta usage geldiği için cost tracking eski sync endpoint ile birebir aynı.
- Citation + image: stream tamamlandıktan sonra `asyncio.gather` ile paralel; FSEK 25-kelime / halü kontrol gate'leri korunur, sadece user-facing latency'ye sızmaz.
- DB persist: row `running` statüsünde başta insert + commit; stream sonunda `completed`/`insufficient_data`/`failed` update + commit.
- **HyDE conditional (#686 PR-C):** Generic kategori sorgularında (entity-suz, ≤3 kelime, soru kelimesi yok) HyDE LLM call atlanır → TTFT -1-2sn, cost -%15-20. Niş/soru sorgularda HyDE devam (Karşıyaka hakemleri, Trump 6 Mayıs).
- **Batch embedding (#688 PR-D):** enriched_query + hyde_doc tek batch'te embed; eski 2 round-trip → 1. ~200-500ms TTFT tasarrufu.
- **Retrieval defaults (#688 PR-D, #696 B7+C8 runtime tunable):**
  - `top_k = max(10, content_top_k * 2)` (eski 15) — LLM rerank candidate -%33
  - `content_max_tokens = 1500` (eski 2000) — streaming kısalır, cost -%25
  - NER scoring (Faz 6.1, PR #693): IDF threshold + multi-entity AND, 4 mode (multi_and / multi_and_common / single_rare / no_match)
  - Tüm RRF + NER K weights ve threshold'lar `app_settings` üzerinden runtime tunable (`retrieval.ner_*`, `retrieval.rrf_*`)

**Backward compatibility:** ~~Eski `POST /app/generate` (sync JSON) endpoint'i aynen korunur.~~ — **GEÇERSİZ (#800):** hem `/app/generate` hem `/app/generate-stream` KALDIRILDI; tek akış `/chat/conversations/{id}/messages` (SSE). Bu satır tarihsel bağlam için bırakıldı.

**Telemetry:** `done` event'indeki `ttfb_ms` ve `provider_call_logs` üzerinden P95 stream first-byte ölçülür. `/admin/rag` Performans sekmesi MVP-2.2 sonrası bu metric'i de gösterecek (sonraki iterasyon).


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

### 11.8 SFT user-action telemetry (#566, MVP-1.7)

Trendyol-LLM-7B-chat-v4.1.0 üzerine domain-spesifik fine-tune için altın etiketleme sinyalleri. Tüm endpoint'ler auth'lu, ownership check'li (user_id ≠ current_user → 404), idempotent.

Her action sonrası backend'de `_apply_user_action(gen, user, action)` helper çalışır:
- `user_action`, `action_at`, `time_to_action_sec` günceller
- `_recompute_sft_eligibility(gen, user)` 7 koşullu kuralı uygular → `sft_eligible` + `sft_excluded_reason` set eder

Bağlı: [data-model.md §5.1](data-model.md), [wiki/concepts/sft-data-pipeline.md](../../wiki/concepts/sft-data-pipeline.md).

#### `POST /app/generations/{id}/copied`

```text
// 204 No Content — copy-to-clipboard sinyali
```

#### `POST /app/generations/{id}/posted`

```text
// 204 No Content — X / başka platforma paylaşıldı
```

#### `POST /app/generations/{id}/edited`

```json
// Request
{ "edited_text": "..." }   // 1 ≤ len ≤ 20000

// 200 OK
{
  "status": "edited",
  "edit_distance": 0.023,        // Levenshtein normalize, NULL olabilir
  "sft_eligible": true,
  "sft_excluded_reason": null
}
```

#### `POST /app/generations/{id}/regenerated`

Negatif sinyal — kullanıcı aynı request_text ile yeniden üretti.

```text
// 204 No Content
```

#### `DELETE /app/generations/{id}`

Negatif sinyal — kullanıcı içeriği sildi (`user_action='deleted'`). Generation row korunur (audit trail). Hard delete KVKK self-service `DELETE /app/me` ile cascade yapılır.

```text
// 204 No Content
```

### 11.9 Model Improvement Consent (KVKK 5. checkbox, #564 + #566)

KVKK md.5/2-a açık rıza — model eğitiminde kullanım için ayrı izin (data_processing + foreign_transfer'den **bağımsız**).

Bağlı: [docs/legal/kvkk-aydinlatma.md §3 madde 7 + §13](../legal/kvkk-aydinlatma.md), [wiki/decisions/own-slm-strategy.md](../../wiki/decisions/own-slm-strategy.md).

#### `GET /app/me/consent/model-improvement`

```json
// 200 OK
{
  "is_active": true,
  "granted_at": "2026-05-10T10:30:00Z",
  "revoked_at": null,
  "text_version": "v0.3"
}
```

#### `POST /app/me/consent/model-improvement`

Idempotent — aynı endpoint 2 kez çağrılırsa timestamp güncellenir, `revoked_at` temizlenir (re-grant).

```json
// Request
{
  "text_version": "v0.3",                              // KVKK aydınlatma metin sürümü
  "text_hash": "<sha256-hex>"                          // opsiyonel, immutable kanıt
}

// 200 OK
{
  "status": "granted",
  "granted_at": "2026-05-10T10:30:00Z",
  "text_version": "v0.3"
}
```

Backend yan etkileri: `users.model_improvement_consent_at|version|ip|text_hash` set, `revoked_at` clear, `admin_audit_log` `consent.model_improvement.grant` insert.

#### `DELETE /app/me/consent/model-improvement`

KVKK md.11 — geri çekme.

```json
// 200 OK
{
  "status": "revoked",
  "revoked_at": "2026-05-10T10:35:00Z",
  "generations_affected": 12   // sft_eligible=true → false yapılan kayıt sayısı
}

// 404 NOT_FOUND
{ "code": "NO_CONSENT", "message": "Geri çekilecek bir model improvement consent yok." }
```

Backend yan etkileri:
- `users.model_improvement_consent_revoked_at = NOW()`
- `UPDATE messages SET sft_eligible=false, sft_excluded_reason='consent_revoked' WHERE conversation_id IN (SELECT id FROM conversations WHERE user_id=X) AND sft_eligible=true` (2026-05-14 #800: generations DROP edildi, source messages tablosu)
- `training_samples` cascade delete: #567 ETL worker `apply_async` task ile (bu endpoint sadece flag günceller).
- `admin_audit_log` `consent.model_improvement.revoke` insert (`messages_affected` metadata).

---

## 11.Y. Admin: SFT Data Pipeline Dashboard (#569, MVP-1.7)

ETL pipeline (#567) çıktısını gözleme + ChatML JSONL export. Her endpoint `require_admin` (super_admin role + JWT). Bağlı: [data-model.md §5.5](data-model.md), [wiki/concepts/sft-data-pipeline.md](../../wiki/concepts/sft-data-pipeline.md).

### 11.Y.1 `GET /admin/sft/stats?days=30`

```json
// 200 OK
{
  "total_samples": 12453,
  "by_task_type": {"content_generator": 12453},
  "by_split": {"train": 9961, "val": 1247, "test": 1245},
  "daily_curated": [{"date": "2026-05-08", "count": 412}, ...],
  "quality_p50_edit_distance": 0.018,
  "quality_p50_char_count": 247,
  "eligible_pending": 84,
  "excluded_breakdown": {
    "review_buffer": 1203,
    "no_consent": 5421,
    "wrong_action": 2104,
    "edit_too_large": 92,
    "halu_flagged": 8,
    "consent_revoked": 3,
    "pii_secondary_hit": 12
  }
}
```

### 11.Y.2 `GET /admin/sft/recent?limit=50`

```json
// 200 OK
[
  {
    "id": "...",
    "generation_id": "...",
    "task_type": "content_generator",
    "sft_split": "train",
    "edit_distance": 0.012,
    "char_count": 247,
    "curated_at": "2026-05-10T02:45:30Z",
    "exported_at": null,
    "input_preview": "{...kullanıcı talebi (240 char ile sansürlü)...}",
    "output_preview": "...AI çıktısı (240 char ile sansürlü)..."
  },
  ...
]
```

### 11.Y.3 `POST /admin/sft/export`

```json
// Request
{
  "task_type": "content_generator",
  "sft_split": "train",            // null → tüm split
  "format": "chatml",              // şu an sadece chatml
  "mark_exported": true            // exported_at = NOW() set et
}

// 200 OK — StreamingResponse (application/x-ndjson)
// Content-Disposition: attachment; filename="nodrat-sft-content_generator-train.jsonl"
//
// Her satır JSON-encoded ChatML record:
// {"messages":[{"role":"system",...},{"role":"user",...},{"role":"assistant",...}],
//  "metadata":{...}}
```

Yan etki: `mark_exported=true` ise her exportlanan sample için `exported_at = NOW()`. `admin_audit_log` `sft.export` insert.

### 11.Y.4 `POST /admin/sft/recompute-eligibility?days=30`

Eligibility kuralı değiştiğinde admin manuel tetikler — son `days` gün **assistant mesajlarını** rescan eder (2026-05-14 #800: generations DROP edildi, source messages tablosu).

```json
// 200 OK
{
  "scanned": 1842,
  "became_eligible": 23,
  "became_ineligible": 7
}
```

### 11.Y.4b `POST /admin/sft/run?batch=N`

ETL worker'ı **şimdi tetikle** (nightly 02:45 UTC schedule'ını beklemeden). Celery `apply_async()` ile worker_embedding queue'ya dispatch eder.

```json
// 200 OK
{
  "task_id": "...",
  "queued": true,
  "note": "ETL worker queue'ya dispatch edildi. ..."
}
```

**Önemli:** Kill switch (`sft.curator.enabled`) hâlâ kapalıysa task no-op döner (`{"status": "disabled"}`). Manuel trigger admin override DEĞİL — önce kill switch açılmalı.

`batch` parametresi opsiyonel: `daily_max_samples` setting'ini override eder (1..10000).

### 11.Y.5 `GET /admin/sft/consent-stats`

```json
// 200 OK
{
  "total_users": 1284,
  "opted_in": 412,
  "opted_in_revoked": 18,
  "never_opted_in": 854
}
```

### 11.Y.6 Manuel HF Hub push (script)

`apps/api/scripts/sft_push_hf.py` — JSONL → Hugging Face Hub private push (KVKK güvenlik gereği OTOMATIK değil).

```bash
python apps/api/scripts/sft_push_hf.py \
    --jsonl nodrat-sft-content_generator-train.jsonl \
    --dataset-name nodrat/turkish-content-generation \
    --hf-token $HF_TOKEN \
    --split train
    # default --private (KVKK + IP koruması)
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

## 14. User: Billing (Faz 6 — Lemon Squeezy MoR, Epic #448)

> **2026-05-08 revize:** Lemon Squeezy MoR (USD primary) entegrasyonu. LS hosted checkout + customer portal + invoice PDF. Cancel akışı LS portal'da; Nodrat sadece "Aboneliği yönet" butonu sunar. Webhook handler ayrı endpoint ([#450](https://github.com/selmanays/nodrat/issues/450) — §15).

### 14.1 `GET /app/billing/plans`

```json
// 200 OK — public, Data Model §10.3 seed
{
  "plans": [
    { "code": "starter", "price_usd": 8, "price_tl_display_ref": 249, "ls_variant_id": "...", "limit": 100, "seats": 1 },
    { "code": "pro", "price_usd": 24, "price_tl_display_ref": 749, "ls_variant_id": "...", "limit": 500, "seats": 1 },
    { "code": "agency_3", "price_usd": 79, "price_tl_display_ref": 2499, "ls_variant_id": "...", "limit": 2500, "seats": 3 },
    { "code": "agency_5", "price_usd": 129, "price_tl_display_ref": 4090, "ls_variant_id": "...", "limit": 2500, "seats": 5 },
    { "code": "agency_10", "price_usd": 249, "price_tl_display_ref": 7890, "ls_variant_id": "...", "limit": 2500, "seats": 10 }
  ]
}
```

### 14.2 `POST /app/billing/checkout`

```json
// Request
{
  "plan_code": "pro",
  "billing_cycle": "monthly"
}

// 200 OK — LS hosted checkout URL döner
{
  "checkout_url": "https://nodrat.lemonsqueezy.com/checkout/buy/<variant_uuid>?embed=1",
  "ls_variant_id": "...",
  "expires_at": "..."
}
// Frontend kullanıcıyı yeni tab'da bu URL'e yönlendirir.
// Subscription state webhook ile DB'ye yansır (subscription_created, §15.1)
```

### 14.3 `GET /app/billing/subscription`

```json
// 200 OK
{
  "plan_code": "pro",
  "status": "active",                  // 'trialing' | 'active' | 'past_due' | 'canceled' | 'expired'
  "billing_cycle": "monthly",
  "current_period_start": "...",
  "current_period_end": "...",
  "next_invoice_amount_usd": 24.00,
  "next_invoice_amount_tl_display_ref": 749.00,    // anlık FX, display only
  "payment_provider": "lemon_squeezy",
  "ls_subscription_id": "...",
  "seat_count": 1
}
```

### 14.4 `GET /app/billing/portal-url` (LS Customer Portal — #450)

```json
// 200 OK — LS hosted portal URL (cancel, update card, change plan, invoice list)
{
  "portal_url": "https://nodrat.lemonsqueezy.com/billing?expires=...&signature=...",
  "expires_at": "..."   // signed URL TTL
}
// /app/billing/manage button → bu URL'e yeni tab'da yönlendirir.
// Cancel webhook ile yansır (subscription_cancelled, §15.1)
```

### 14.5 `GET /app/billing/invoices`

```json
// 200 OK — LS invoice referans cache (Data Model §8.3)
{
  "data": [
    {
      "id": "...",
      "ls_invoice_id": "...",
      "ls_invoice_url": "https://lemon-squeezy.com/invoices/...",  // LS hosted PDF
      "issued_at": "...",
      "amount_usd": 24.00,
      "tax_amount_usd": 4.80,                  // LS keser (KDV/VAT/sales tax global)
      "total_usd": 28.80,
      "currency": "USD"
    }
  ]
}
// Not: Nodrat fatura kesmez (LS MoR). PDF link LS hosted; expires after TTL.
```

### 14.6 `GET /app/billing/seats` (Agency tier — #451)

```json
// 200 OK — Agency tier'a özel
{
  "subscription_id": "...",
  "plan_code": "agency_3",
  "seat_count": 3,
  "seats": [
    { "id": "...", "user_id": "...", "email": "...", "role": "admin", "accepted_at": "..." },
    { "id": "...", "user_id": null, "email": "invited@...", "role": "editor", "accepted_at": null }
  ]
}
```

### 14.7 `POST /app/billing/seats/invite`

```json
// Request
{ "email": "...", "role": "editor" }

// 200 OK — invite email gönderildi
{ "seat_id": "...", "invite_url": "/app/seats/accept?token=..." }

// 409 Conflict — seat dolu
{ "error": "seat_limit_exceeded", "message": "Plan upgrade required" }
```

---

## 15. Webhook: Lemon Squeezy (Faz 6 — Epic #448, #450)

### 15.1 `POST /api/webhooks/lemonsqueezy`

```text
Headers:
  X-Event-Name: subscription_created | subscription_updated | subscription_cancelled |
                subscription_resumed | subscription_payment_success |
                subscription_payment_failed | subscription_payment_recovered
  X-Signature: <HMAC SHA256 hex>           # LEMONSQUEEZY_SIGNING_SECRET ile verify

Idempotency:
  webhook_events.ls_event_id UNIQUE         # aynı event 2x → 200 ack, no-op
  Data Model §8.4

Response:
  200 OK              → event işlendi (veya idempotent skip)
  401 Unauthorized    → signature verify fail
  400 Bad Request     → unknown event_type / malformed payload
```

7 event handler özeti:
- `subscription_created` → DB row insert (status='trialing' | 'active'), welcome email
- `subscription_updated` → variant değişimi (plan_code update + seat_count)
- `subscription_cancelled` → status='canceled', retain access until current_period_end
- `subscription_resumed` → status='active'
- `subscription_payment_success` → invoice row + last_paid_at
- `subscription_payment_failed` → status='past_due' (LS dunning otomatik)
- `subscription_payment_recovered` → status='active'

---

## 16. Consent Endpoints (Faz 6 — KVKK m.9, Epic #448, #470)

> **Avukat şartlı onayı (Epic #448 §3.9 N-09 RESOLVED):** Server-side enforcement zorunlu. `users.foreign_transfer_consent_at` NULL ise aşağıdaki 5 akışın hepsi 403 döner: LS checkout, LS portal, LLM provider, email worker, embedding fallback.

### 16.1 `POST /app/consent/foreign-transfer`

```json
// Request
{
  "consent_text_version": "v0.2",                  // aydınlatma metin sürümü
  "checkbox_id": "foreign_transfer_lemon_squeezy"  // hangi checkbox'tan
}

// 200 OK — DB kayıt: timestamp, IP, version, text_hash
{ "consent_at": "2026-05-08T17:00:00Z", "version": "v0.2" }
```

### 16.2 `DELETE /app/consent/foreign-transfer`

```json
// Geri çekme — KVKK m.11 (haklar)
// 200 OK — foreign_transfer_consent_revoked_at SET, mevcut session token invalidate
{ "revoked_at": "...", "active_until": "..." }
// Sonuç: 5 akış (LS checkout/portal, LLM, email, embedding fallback) 403 döner
```

### 16.3 Consent-required response format (5 akışta ortak)

```json
// 403 Forbidden — açık rıza eksik veya geri çekilmiş
{
  "error": "foreign_transfer_consent_required",
  "message": "Bu özelliği kullanmak için yurt dışı veri transferi açık rızası gerekli.",
  "consent_url": "/app/consent",
  "metin_versiyon": "v0.2"
}
```

**Etkilenen 5 endpoint:**
1. `POST /app/billing/checkout` (§14.2)
2. `GET /app/billing/portal-url` (§14.4)
3. `POST /app/generate` (LLM çağrısı)
4. `worker.send_email()` task (Resend/Postmark)
5. Embedding yurt dışı fallback (NIM bge-m3 failover)

---

## 17. Internal Endpoints (Worker → API)

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

## 17.5 Chat Endpoints (#793 — Perplexity-style conversation mode)

Conversation-based chat UX. Mevcut `/app/generate-stream` form-based deneyim
backward-compat olarak korunur.

### 17.5.1 `POST /chat/conversations`
Yeni boş conversation oluştur. İlk mesajdan title auto-update.

**Body:**
```json
{"title": "Optional, max 200 char"}
```

**Response (201):**
```json
{
  "id": "uuid",
  "title": "Yeni sohbet",
  "summary": null,
  "message_count": 0,
  "last_answer_snippet": null,
  "archived": false,
  "created_at": "ISO8601",
  "updated_at": "ISO8601"
}
```

### 17.5.2 `GET /chat/conversations`
Sidebar list — user'ın conversations.

**Query:** `include_archived` (bool), `limit` (1-200, default 50), `offset`

**Response:**
```json
{
  "items": [
    {
      "id": "uuid",
      "title": "...",
      "message_count": 3,
      "last_answer_snippet": "Adalet Bakanı Akın Gürlek...",
      "updated_at": "ISO8601"
    }
  ],
  "total": 12
}
```

### 17.5.3 `GET /chat/conversations/{id}`
Full thread — tüm mesajlar created_at ASC.

**Response:** `ConversationThread` (id, title, summary, archived, timestamps, messages[])

`messages[]` her item:
```json
{
  "id": "uuid",
  "role": "user" | "assistant",
  "content": "...",
  "generation_id": "uuid | null",
  "sources_used": [{"source_type", "article_id?", "chunk_id?", "title", "url", "source_name", "cite", "license?"}] | null,  // #845 cited-only: cevapta citation token'ı geçen kaynaklar
  "sources_considered": [...] | null,  // #845: taranan tüm kaynaklar (UI collapsed "Taranan diğer kaynaklar")
  "thinking_steps": [{"phase", "detail", "latency_ms"}] | null,
  "created_at": "ISO8601"
}
```

### 17.5.4 `PATCH /chat/conversations/{id}`
Title manuel rename.

**Body:** `{"title": "string"}` (1-200 char)

### 17.5.5 `DELETE /chat/conversations/{id}`
Arşivle (soft delete — `archived=true`). KVKK m.11 uyumlu, veriler korunur.

**Response:** 204

### 17.5.6 `POST /chat/conversations/{id}/messages` (SSE Streaming)

Yeni mesaj + SSE stream + assistant cevap persist. Context-aware retrieval
(önceki kaynaklar reuse hint), SSE thinking events.

**Body:**
```json
{
  "content": "string (1-5000 char)",
  "output_type": "x_post",        // opsiyonel, default
  "tone": null,
  "max_posts": null
}
```

**Pipeline akışı (#845 agentic + #848 çok-turlu + #851):** Ön-retrieval/planner/confidence/meta-handler KALDIRILDI.
1. **Step 1.5 — Conversational query rewrite** (multi-turn, #833 korundu): `condense_followup_query` follow-up'ı standalone `effective_query`'ye çevirir (`query_rewrite` event). İlk mesajda atlanır. **#851:** asistan/kimlik/meta soru topic follow-up DEĞİL → değiştirilmeden geçer. **#854:** talimat-odaklı follow-up ("wikipedia'da ara", "bu sorumu bul") önceki substantive soruyu TAŞIR (jenerik araması üretmez). **#854 latency tavanı:** condense `asyncio.wait_for(chat.condense_timeout_s, def 6s)` — aşılırsa ham mesajla devam (zarif degrade; 43s hang fix). Loop generate_text + tool dispatch da tavanlı (`chat.tool_round_timeout_s`/`tool_exec_timeout_s`/`max_tool_rounds` — admin-tunable settings).
2. **System prompt:** `render_nodrat_agent_prompt(current_date)` — Nodrat kimliği + **güncel tarih enjekte** (sistem now, TR UTC+3) + tool politikası + C1.
3. **#848 çok-turlu agentic döngü (MAX 3 tur):** `generate_text(convo, tools=[search_news, search_wikipedia], tool_choice="auto")` **non-streaming** (#840 DSML-safe korunur). `wikipedia.enabled=False` → sadece search_news.
   - **tool_calls varsa:** her tc dispatch — `search_news` (db/now/user closure → planner+embed+`hybrid_search_chunks` sarmalı, kalite değişmedi) / `search_wikipedia` (#842). `source_discovered` event per kaynak. Sonuçlar convo'ya eklenir → **döngü tekrar** (LLM yetersizse başka tool çağırabilir: search_news↔search_wikipedia — #848 tek-tur tuzağı çözümü).
   - **tool_calls yoksa:** `decision.text` = final cevap, döngü biter.
   - MAX 3 tur dolduysa toolsuz `generate_text` ile zorla cevap.
   - **#851 C1 backstop:** tool_calls yoksa ve `decision.text` citation token (`[n]`) içeriyor ama hiç tool kaynak üretmemişse (`all_sources` boş) → kanıtlı sahte (bellekten cevap) → 1× `tool_choice="required"` düzeltici tur (`_CITE_TOKEN_RE` yapısal invariant; #819 DEĞİL). Selamlama/kimlik (citation yok) etkilenmez.
4. **Final:** `final_text` → `_simulate_stream` (ekstra LLM call yok; tüm turlar non-streaming, `generate_text_stream` #848'de kaldırıldı). Selamlama/kimlik/meta → tur 0'da tool yok → doğrudan (retrieval YOK).
5. **#851 cite namespace:** tek `[n]` (her tool çağrısı `cite_start` global offset; `[Wn]` prefix kaldırıldı, `source_type` news/wiki ayrımını taşır). **cited-only:** `sources_used` = cevapta `[n]` token'ı geçen kaynaklar (`cite` alanı); `sources_considered` = taranan tümü (UI collapsed). SourcePill gerçek `cite` token'ını gösterir.
6. **#912 article-collapse (search_news sunum):** `cite` artık **article-level** — `_expand_parent_documents` (#661) aynı article'dan birden çok chunk getirir (answer-extraction context zenginliği, korunur); `execute_search_news` bu chunk'ları **article başına TEK `[n]`** altında toplar, `sources`/`source_discovered` her article için **TEK kart** üretir (ilk = en iyi RRF chunk = temsilci; `title`/`url`/`published_at` article-level). LLM context blokları parent-doc chunk'larını **ortak `[n]`** ile görmeye devam eder (#661 zenginlik DEĞİŞMEZ). `search_news` tool meta'sı `chunk_count` (ham chunk) ve `source_count` (distinct article kartı) taşır. `[n]` token formatı + `cite_start` global offset (#851) korunur — yalnız aynı haberin chunk'larına ayrı `[n]` verilmesi engellendi. Retrieval/RRF/#661 DEĞİŞMEZ (yalnız sunum). Detay: [agentic-generate-orchestration](../../wiki/decisions/agentic-generate-orchestration.md) #912 callout.
7. **#928/#929 scope-aware tazelik (search_news meta + result_text):** `execute_search_news` tool meta'sı `chunk_count`/`source_count`'a ek üç alan taşır: `recency_requested` (bool — planner/sorgu güncellik istedi mi), `newest_published_at` (date|null — sonuç kümesindeki en yeni yayın tarihi), `freshness_gap_days` (int|null — bugün ile `newest_published_at` farkı). `recency_requested=True` ve `freshness_gap_days` eşik üstündeyse (veri istenen tazelikte değil), `execute_search_news` **result_text başına KOD-ÜRETİLEN** "DİKKAT — TAZELİK" yönergesi enjekte eder (LLM prompt'una değil tool çıktısına — #906/#879 deseni: prompt olasılıksal, deterministik kod-sinyali bypass/DB-override-bağışık). LLM bu sinyalle eski veriyi "son haber" diye sunmaz (C1/C6 sahte güncellik koruması). 90g fallback dalı recency-sort'lu (yalnız fallback; ana RRF dalı DEĞİŞMEZ). Eş prompt kuralı: prompt-contracts §4 SYSTEM_PROMPT_NODRAT_AGENT scope-aware tazelik + REWRITE itiraz≠parametre (#929). Detay: [news-timeframe-retrieval-contract](../../wiki/decisions/news-timeframe-retrieval-contract.md) (conv 74eecc15 ailesi).
8. **#939/#942/#947 Türkçe entity match (retrieval iç — sözleşme etkisi yok):** `search_news` sonuç **kalitesi** iyileşti (Türkçe-karakterli entity'ler artık RESCUE/FILTER'da eşleşiyor): DB C-locale `LOWER()` Türkçe büyük harf küçültmüyordu → `LOWER(x COLLATE "tr-TR-x-icu")` (#939); planner `critical_entities` kök-form garantisi + cache prompt_version invalidation (#942/#947). Tool **şeması/çıktı sözleşmesi DEĞİŞMEZ** — yalnız hangi article'ların döndüğü iyileşti (benchmark recall@10 0.818→0.909). Detay: architecture.md §4.5 + [turkish-collation-entity-match](../../wiki/decisions/turkish-collation-entity-match.md).

**SSE Events:**

| Event | Data | Açıklama |
|---|---|---|
| `thinking_step` | `{phase, detail, latency_ms}` | Pipeline adımı (#845: context_check, query_rewrite, tool_use, generating — planner/retrieve/confidence/meta_query_handler KALDIRILDI) |
| `source_discovered` | `{source_type, article_id?, chunk_id?, title, url, source_name, cite}` | Tool sonucu kaynağı (real-time, taranan). `source_type='news'`\|`'wikipedia'`; `cite`=tek `[n]` token, döngü-global benzersiz (#851; `[Wn]` kaldırıldı). **#912:** news kartı **article başına TEK** (aynı article'ın #661 parent-doc chunk'ları ayrı event üretmez; `cite` article-level) |
| `chunk` | `{delta}` | Token akışı. Tool path: Aşama 2 gerçek token streaming (toolsuz). No-tool path (selamlama/meta): `_simulate_stream` (#840) |
| `done` | `{conversation_id, user_message_id, assistant_message_id, is_followup, similarity, query_class, used_wikipedia, sources_used_count, sources_considered_count}` | Stream tamamlandı (#845: `confidence` kaldırıldı; query_class search_news meta'dan veya `conversational`) |
| `error` | `{code, title, reason}` | Stream hatası (done event'i de izler) |

> **Kaldırılan event'ler:** `requires_user_consent` + `insufficiency_signal` (#823 — CTA/banner mimarisi tool-use ile değişti); `POST /chat/conversations/{id}/wikipedia-fallback` (#823). **#845:** `confidence_score` event de kaldırıldı (ön-retrieval/confidence yok; query_class artık search_news çağrılırsa planner meta'sından, aksi halde `conversational`).

**Context-aware follow-up:** Multi-turn'de conversation context (content + assistant kaynak özeti) condense step'e beslenir → `effective_query`. is_related embedding similarity (`0.65`) `prev_sources` reuse hint için kullanılır ama condense bağımsız çalışır (generic follow-up'ları embedding kaçırabildiği için).

**Auth:** `get_current_user` (JWT bearer), conversation ownership doğrulanır (404 başkasınınkinde).

**Quota:** `enforce_quota` user.tier limit (HTTP 429 stream başlamadan).

---

### 17.5.7 `POST /chat/conversations/{id}/wikipedia-fallback` — KALDIRILDI (#823)

> ⚠️ **KALDIRILDI (#823, 2026-05-15).** Wikipedia onay CTA endpoint'i
> tool-use mimarisiyle silindi (route artık 404). `requires_user_consent`
> + `insufficiency_signal` event'leri de aynı PR'da kaldırıldı (bkz.
> §17.5.6 "Kaldırılan event'ler" notu — bu bölüm o notla tutarlıdır).
> Güncel davranış: LLM kaynak yetersizse `search_wikipedia` tool'unu
> **kendi kararıyla** çağırır (kullanıcı CTA'sı YOK); cevap tek `[n]`
> namespace ile cite edilir (`[W]` prefix #851'de kaldırıldı). Kanonik
> mimari: [llm-tool-use-wikipedia](../../wiki/decisions/llm-tool-use-wikipedia.md)
> · [agentic-generate-orchestration](../../wiki/decisions/agentic-generate-orchestration.md).
> Tarihsel sözleşme detayı için git geçmişine bakın (#813 Faz 2 2B).

---

## 17. Rate Limit Politikaları

```text
Endpoint                           Per User           Per IP             Per Tier
─────────────────────────────────────────────────────────────────────────────────────
POST /public/trial/generate        —                  1/gün+fingerprint  N/A
POST /auth/login                   —                  10/dk              N/A
POST /auth/register                —                  3/saat             N/A
POST /chat/conversations/{id}/messages  5/sa (free)   —                  Pricing §3.1
                                   20/sa (starter)
                                   60/sa (pro)
                                   120/sa (agency seat)
GET  /chat/conversations           60/dk              —                  —
# (#800: /app/generate + /app/generations KALDIRILDI → /chat/* — bkz §11 banner)
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
  POST /chat/conversations               (#800 — /app/generate KALDIRILDI)
  POST /chat/conversations/{id}/messages (SSE — agentic generate)
  GET  /chat/conversations
  GET  /chat/conversations/{id}
  DELETE /chat/conversations/{id}         (archive)
  POST /chat/messages/{id}/flag-halu
  POST /chat/messages/{id}/action         (copied|posted|edited)
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
