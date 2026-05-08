# Nodrat — Veri Modeli (DDL + Migration Stratejisi)

**Doküman türü:** Database Schema & Migrations
**Sürüm:** v0.1
**Bağımlılık:** PRD §1.10, §2.4, §3.6, §4.4, §5.6, §6.3, IA §7, Architecture §5.1, Risk Register §4 (MVP-1 kapsamı)
**Hedef:** Tüm tablolar için tam DDL, indeksler, kısıtlar, foreign key kuralları, seed verileri ve migration stratejisi.

⚠️ **Konvansiyon:** Tüm DDL PostgreSQL 16 + pgvector. Migrasyon Alembic ile yönetilir. Her tablo: `id` UUID, `created_at` ve `updated_at` (gerekiyorsa) timestamp.

---

## 0. Yönetici Özeti

```text
Toplam tablo: ~25 (tüm fazlar)
MVP-1'de aktif: 16 tablo

Faz dağılımı (IA §7.2):
  Faz 0:   users, sessions
  Faz 1:   sources, source_configs, source_health,
           articles, article_images,
           crawler_jobs, failed_jobs,
           model_providers (config taşıyıcı)
  Faz 2:   article_chunks (pgvector),
           event_clusters, event_articles,
           agenda_cards (pgvector),
           provider_call_logs
  Faz 3:   generations, usage_events,
           saved_generations, admin_audit_log
  Faz 4:   entities, image_analysis,
           image_embeddings (pgvector), image_labels
  Faz 5:   style_profiles, style_samples
  Faz 6:   plans, subscriptions, invoices

Extension'lar:
  - pgvector       (embedding)
  - pg_trgm        (text similarity, full-text)
  - pgcrypto       (uuid_generate_v4, encryption)
  - citext         (case-insensitive email)
```

---

## 1. Migration Stratejisi

### 1.1 Araç: Alembic

```text
Konum:           /apps/api/alembic/
Versiyonlama:    Otomatik (Alembic revision)
İsim format:     YYYYMMDD_HHMM_short_description.py
Lifecycle:
  alembic revision -m "add_xxx" --autogenerate
  alembic upgrade head
  alembic downgrade -1   (sadece dev'de)
```

### 1.2 Forward-compatible migration kuralları

```text
R1. Sütun ekleme: NULL veya DEFAULT şart (zero-downtime)
R2. Sütun silme: 2 deploy (önce kod stop kullanım, sonra DROP)
R3. Sütun yeniden adlandırma: 2 deploy (yeni sütun ekle + dual-write,
    sonra eski sil)
R4. Foreign key: ON DELETE CASCADE veya RESTRICT açık tanımlı
R5. Index: CONCURRENTLY (üretim ortamında lock'suz)
R6. Veri migration: ayrı script (alembic'te değil)
R7. Geri alma: production'da RUN once + rollback playbook
```

### 1.3 Initial extension setup

```sql
-- Migration 00000_init_extensions
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "vector";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
CREATE EXTENSION IF NOT EXISTS "citext";
```

---

## 2. Faz 0 — Identity & Access

### 2.1 `users`

```sql
CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email           CITEXT NOT NULL UNIQUE,
    password_hash   TEXT NOT NULL,                   -- argon2id
    full_name       VARCHAR(120),
    role            VARCHAR(32) NOT NULL DEFAULT 'user',  -- 'super_admin' | 'user'
    tier            VARCHAR(32) NOT NULL DEFAULT 'free',  -- 'free' | 'starter' | 'pro' | 'agency_seat'
    locale          VARCHAR(10) NOT NULL DEFAULT 'tr-TR',
    email_verified  BOOLEAN NOT NULL DEFAULT FALSE,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    
    -- KVKK consent (Legal §2.3)
    kvkk_consent_at TIMESTAMPTZ,
    foreign_transfer_consent_at TIMESTAMPTZ,
    marketing_consent_at TIMESTAMPTZ,
    
    -- 2FA (Faz 6+)
    totp_secret     TEXT,
    totp_enabled    BOOLEAN NOT NULL DEFAULT FALSE,
    
    -- Tracking
    last_login_at   TIMESTAMPTZ,
    last_login_ip   INET,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at      TIMESTAMPTZ                      -- soft delete (KVKK silme talep)
);

CREATE INDEX idx_users_role ON users(role) WHERE deleted_at IS NULL;
CREATE INDEX idx_users_tier ON users(tier) WHERE deleted_at IS NULL;
CREATE INDEX idx_users_email_verified ON users(email_verified) WHERE deleted_at IS NULL;
```

### 2.2 `sessions`

```sql
CREATE TABLE sessions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash      TEXT NOT NULL UNIQUE,            -- SHA-256 of bearer token
    user_agent      TEXT,
    ip_address      INET,
    expires_at      TIMESTAMPTZ NOT NULL,
    revoked_at      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_sessions_user_id ON sessions(user_id) WHERE revoked_at IS NULL;
CREATE INDEX idx_sessions_expires_at ON sessions(expires_at) WHERE revoked_at IS NULL;
```

---

## 3. Faz 1 — Source Management

### 3.1 `sources` (PRD §1.10)

```sql
CREATE TABLE sources (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(120) NOT NULL,
    slug            VARCHAR(80) NOT NULL UNIQUE,
    domain          VARCHAR(180) NOT NULL,
    type            VARCHAR(32) NOT NULL,            -- 'rss' | 'category_page' | 'manual'
    base_url        TEXT NOT NULL,
    language        VARCHAR(10) NOT NULL DEFAULT 'tr',
    country         VARCHAR(8) NOT NULL DEFAULT 'TR',
    category        VARCHAR(80),
    
    reliability_score   NUMERIC(3,2) NOT NULL DEFAULT 0.70,  -- 0.00..1.00
    is_active           BOOLEAN NOT NULL DEFAULT FALSE,
    crawl_interval_minutes INTEGER NOT NULL DEFAULT 30,
    
    last_crawled_at TIMESTAMPTZ,
    
    -- Compliance (Legal §4)
    robots_txt_check_at TIMESTAMPTZ,
    robots_txt_compliant BOOLEAN,
    tos_acknowledged    BOOLEAN NOT NULL DEFAULT FALSE,
    
    created_by      UUID REFERENCES users(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    CHECK (type IN ('rss', 'category_page', 'manual')),
    CHECK (reliability_score >= 0.0 AND reliability_score <= 1.0)
);

CREATE INDEX idx_sources_active ON sources(is_active) WHERE is_active = TRUE;
CREATE INDEX idx_sources_type ON sources(type);
CREATE INDEX idx_sources_domain ON sources(domain);
```

### 3.2 `source_configs` (versioned)

```sql
CREATE TABLE source_configs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id       UUID NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    config_json     JSONB NOT NULL,                  -- selectors, RSS field maps, pagination
    version         INTEGER NOT NULL,
    is_active       BOOLEAN NOT NULL DEFAULT FALSE,
    created_by      UUID REFERENCES users(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    UNIQUE (source_id, version)
);

CREATE INDEX idx_source_configs_active ON source_configs(source_id) WHERE is_active = TRUE;

-- Sadece bir aktif config per source (partial unique)
CREATE UNIQUE INDEX uniq_source_configs_one_active
  ON source_configs(source_id) WHERE is_active = TRUE;
```

### 3.3 `source_health`

```sql
CREATE TABLE source_health (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id       UUID NOT NULL REFERENCES sources(id) ON DELETE CASCADE UNIQUE,
    last_status     VARCHAR(16) NOT NULL DEFAULT 'unknown',  -- 'green' | 'yellow' | 'red' | 'unknown'
    last_success_at TIMESTAMPTZ,
    last_failure_at TIMESTAMPTZ,
    failure_count_24h INTEGER NOT NULL DEFAULT 0,
    avg_fetch_ms    INTEGER,
    avg_extract_confidence NUMERIC(3,2),
    last_error      TEXT,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_source_health_status ON source_health(last_status);
```

### 3.4 `articles` (PRD §1.10)

```sql
CREATE TABLE articles (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id       UUID NOT NULL REFERENCES sources(id) ON DELETE RESTRICT,
    
    canonical_url   TEXT NOT NULL,
    source_url      TEXT NOT NULL,
    title           TEXT NOT NULL,
    subtitle        TEXT,
    author          VARCHAR(180),
    
    published_at    TIMESTAMPTZ,
    fetched_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    crawled_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    raw_html_storage_path TEXT,                       -- MinIO key, Faz 2'de kullanılır
    body_html       TEXT,
    clean_text      TEXT,
    
    language        VARCHAR(10) NOT NULL DEFAULT 'tr',
    
    -- Dedupe (PRD §1.7)
    content_hash    CHAR(64) NOT NULL,               -- SHA-256
    title_hash      CHAR(64) NOT NULL,
    
    extraction_confidence NUMERIC(3,2),
    status          VARCHAR(16) NOT NULL DEFAULT 'discovered',
    -- 'discovered' | 'fetched' | 'cleaned' | 'failed' | 'archived'
    
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    UNIQUE (canonical_url),
    UNIQUE (source_id, content_hash),
    CHECK (status IN ('discovered', 'fetched', 'cleaned', 'failed', 'archived'))
);

CREATE INDEX idx_articles_source_published ON articles(source_id, published_at DESC);
CREATE INDEX idx_articles_published_at ON articles(published_at DESC) WHERE status = 'cleaned';
CREATE INDEX idx_articles_status ON articles(status, created_at DESC);
CREATE INDEX idx_articles_title_hash ON articles(title_hash);
CREATE INDEX idx_articles_title_trgm ON articles USING gin(title gin_trgm_ops);
CREATE INDEX idx_articles_clean_text_trgm ON articles USING gin(clean_text gin_trgm_ops);
```

### 3.5 `article_images` (PRD §1.10) — Process & Discard (#304 MVP-1.4)

**Mimari değişikliği (MVP-1.4):** Görseller artık MinIO/S3'te depolanmaz.
NIM Llama 4 Maverick (VLM) ile geçici download → metadata extraction →
bytes discard. Sadece `original_url` (kaynak haberin orijinal URL'si) +
VLM çıktıları (`vlm_caption`, `ocr_text`, `depicts`) saklanır. Storage
maliyeti ~98% azaldı (5 TB/yıl → 90 GB/yıl).

```sql
CREATE TABLE article_images (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    article_id      UUID NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    source_id       UUID NOT NULL REFERENCES sources(id),

    -- Kaynak referansı (process & discard: bytes saklanmaz)
    original_url    TEXT NOT NULL,                   -- Kaynak haberin <img src>'i

    -- HTML scrape metadata
    caption         TEXT,                            -- <figcaption>
    alt_text        TEXT,                            -- <img alt>

    -- NIM VLM çıktıları (#300/#304 PR-3)
    vlm_caption     TEXT,                            -- Türkçe görsel açıklama (≤5000 char)
    ocr_text        TEXT,                            -- Görseldeki yazı (≤10000 char)
    depicts         JSONB,                           -- ["Erdoğan","Kılıçdaroğlu",...]

    -- Position (haber içi sıra)
    position        INTEGER,                         -- 0-indexed gallery sırası

    -- Discovery metadata
    discovered_from VARCHAR(32),
    -- 'body' (DOM'daki gerçek görsel — RSS thumbnail KAPALI #304)
    -- 'opengraph' | 'gallery'

    -- Lifecycle
    status          VARCHAR(16) NOT NULL DEFAULT 'pending',
    -- 'pending' | 'processed' | 'failed' | 'skipped'

    processed_at    TIMESTAMPTZ,                     -- VLM işleme tamamlanma anı
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CHECK (status IN ('pending', 'processed', 'failed', 'skipped'))
);

CREATE INDEX idx_article_images_article ON article_images(article_id);
CREATE INDEX idx_article_images_status ON article_images(status);
CREATE INDEX idx_article_images_processed_at ON article_images(processed_at)
    WHERE processed_at IS NOT NULL;
```

**Kaldırılan kolonlar (MVP-1.4 migration):**
- `storage_url` (artık MinIO'ya yazılmıyor)
- `mime_type`, `width`, `height`, `file_size` (bytes saklanmadığı için irrelevant)
- `sha256_hash`, `perceptual_hash` (dedup gerekli değil — kaynaktaki URL canonical)

**Status mapping:** Eski `'downloaded'/'duplicate'` → `'pending'`; yeni `'processed'`
NIM VLM tamamlandığında set edilir; `'skipped'` settings flag kapalıyken set edilir.

### 3.6 `crawler_jobs`

```sql
CREATE TABLE crawler_jobs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_type        VARCHAR(64) NOT NULL,
    -- 'source.fetch_rss' | 'source.fetch_category' | 'article.discover'
    -- 'article.fetch_detail' | 'article.extract' | 'article.clean'
    -- 'media.download' | 'media.hash' | 'article.dedupe' | 'source.healthcheck'
    
    status          VARCHAR(16) NOT NULL DEFAULT 'queued',
    -- 'queued' | 'running' | 'succeeded' | 'failed' | 'dead'
    
    priority        SMALLINT NOT NULL DEFAULT 50,    -- 10..100, yüksek = öncelikli
    payload_json    JSONB NOT NULL DEFAULT '{}'::jsonb,
    
    attempt_count   INTEGER NOT NULL DEFAULT 0,
    max_attempts    INTEGER NOT NULL DEFAULT 3,
    
    scheduled_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at      TIMESTAMPTZ,
    finished_at     TIMESTAMPTZ,
    error_message   TEXT,
    
    -- Polymorphic ref
    source_id       UUID REFERENCES sources(id) ON DELETE CASCADE,
    article_id      UUID REFERENCES articles(id) ON DELETE CASCADE,
    
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    CHECK (status IN ('queued', 'running', 'succeeded', 'failed', 'dead'))
);

CREATE INDEX idx_crawler_jobs_status ON crawler_jobs(status, priority DESC, scheduled_at);
CREATE INDEX idx_crawler_jobs_type ON crawler_jobs(job_type, status);
CREATE INDEX idx_crawler_jobs_source ON crawler_jobs(source_id) WHERE source_id IS NOT NULL;
CREATE INDEX idx_crawler_jobs_article ON crawler_jobs(article_id) WHERE article_id IS NOT NULL;
```

### 3.7 `failed_jobs` (Dead Letter Queue)

```sql
CREATE TABLE failed_jobs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    original_job_id UUID,
    job_type        VARCHAR(64) NOT NULL,
    payload_json    JSONB NOT NULL,
    
    source_id       UUID REFERENCES sources(id) ON DELETE SET NULL,
    article_url     TEXT,
    
    error_message   TEXT NOT NULL,
    stack_trace     TEXT,                             -- sadece admin
    retry_count     INTEGER NOT NULL DEFAULT 0,
    last_attempt_at TIMESTAMPTZ NOT NULL,
    
    resolved_at     TIMESTAMPTZ,
    resolved_by     UUID REFERENCES users(id),
    resolution_note TEXT,
    
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_failed_jobs_unresolved ON failed_jobs(created_at DESC) WHERE resolved_at IS NULL;
CREATE INDEX idx_failed_jobs_source ON failed_jobs(source_id) WHERE source_id IS NOT NULL;
```

### 3.8 `model_providers` (config)

```sql
CREATE TABLE model_providers (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(80) NOT NULL UNIQUE,
    type            VARCHAR(32) NOT NULL,
    -- 'llm' | 'embedding' | 'rerank' | 'vision' | 'payment'
    
    base_url        TEXT,
    api_key_secret_ref TEXT,                          -- Fernet encrypted
    
    supports_chat       BOOLEAN NOT NULL DEFAULT FALSE,
    supports_embeddings BOOLEAN NOT NULL DEFAULT FALSE,
    supports_rerank     BOOLEAN NOT NULL DEFAULT FALSE,
    supports_vision     BOOLEAN NOT NULL DEFAULT FALSE,
    
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    priority        SMALLINT NOT NULL DEFAULT 50,
    
    -- Cost tracking (Unit Economics)
    cost_per_1m_input_tokens  NUMERIC(10,4),
    cost_per_1m_output_tokens NUMERIC(10,4),
    
    -- Cap (Risk Register R-FIN-01)
    monthly_cost_cap_usd NUMERIC(10,2),
    
    config_json     JSONB NOT NULL DEFAULT '{}'::jsonb,
    
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    CHECK (type IN ('llm', 'embedding', 'rerank', 'vision', 'payment'))
);

CREATE INDEX idx_model_providers_type_active
  ON model_providers(type, priority DESC) WHERE is_active = TRUE;
```

---

## 4. Faz 2 — RAG Layer

### 4.1 `article_chunks` (pgvector)

```sql
CREATE TABLE article_chunks (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    article_id      UUID NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    source_id       UUID NOT NULL REFERENCES sources(id),
    
    chunk_index     INTEGER NOT NULL,
    chunk_text      TEXT NOT NULL,
    token_count     INTEGER NOT NULL,
    
    embedding       vector(1024),                     -- bge-m3 dim
    embedding_model VARCHAR(80),                      -- 'bge-m3' tracking
    embedding_provider VARCHAR(80),
    
    published_at    TIMESTAMPTZ,                      -- denormalized (filtre hızı)
    
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    UNIQUE (article_id, chunk_index)
);

-- Vector index (PRD §7.5)
-- ivfflat MVP'de yeterli; 1M+ chunk sonrası HNSW
CREATE INDEX idx_article_chunks_embedding
  ON article_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

CREATE INDEX idx_article_chunks_article ON article_chunks(article_id);
CREATE INDEX idx_article_chunks_published ON article_chunks(published_at DESC)
  WHERE published_at IS NOT NULL;
CREATE INDEX idx_article_chunks_source_published ON article_chunks(source_id, published_at DESC);
```

### 4.2 `event_clusters`

```sql
CREATE TABLE event_clusters (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    canonical_title VARCHAR(500) NOT NULL,
    current_summary TEXT,
    embedding       vector(1024),
    
    first_seen_at   TIMESTAMPTZ NOT NULL,
    last_seen_at    TIMESTAMPTZ NOT NULL,
    last_updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    status          VARCHAR(16) NOT NULL DEFAULT 'developing',
    -- 'developing' | 'active' | 'cooling' | 'stale' | 'archived'
    
    importance_score NUMERIC(3,2),
    freshness_score  NUMERIC(3,2),
    source_count     INTEGER NOT NULL DEFAULT 0,
    article_count    INTEGER NOT NULL DEFAULT 0,
    
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    CHECK (status IN ('developing', 'active', 'cooling', 'stale', 'archived'))
);

CREATE INDEX idx_event_clusters_status_updated
  ON event_clusters(status, last_updated_at DESC);
CREATE INDEX idx_event_clusters_embedding
  ON event_clusters USING ivfflat (embedding vector_cosine_ops) WITH (lists = 50);
```

### 4.3 `event_articles`

```sql
CREATE TABLE event_articles (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id        UUID NOT NULL REFERENCES event_clusters(id) ON DELETE CASCADE,
    article_id      UUID NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    source_id       UUID NOT NULL REFERENCES sources(id),
    
    published_at    TIMESTAMPTZ,
    relationship_score NUMERIC(3,2),
    
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    UNIQUE (event_id, article_id)
);

CREATE INDEX idx_event_articles_event ON event_articles(event_id);
CREATE INDEX idx_event_articles_article ON event_articles(article_id);
```

### 4.4 `agenda_cards` (PRD §2.6)

```sql
CREATE TABLE agenda_cards (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id        UUID NOT NULL REFERENCES event_clusters(id) ON DELETE CASCADE,
    
    title           VARCHAR(500) NOT NULL,
    summary         TEXT NOT NULL,
    key_points      JSONB NOT NULL DEFAULT '[]'::jsonb,
    content_angles  JSONB NOT NULL DEFAULT '[]'::jsonb,
    timeline        JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_refs     JSONB NOT NULL DEFAULT '[]'::jsonb,
    
    status          VARCHAR(16) NOT NULL DEFAULT 'developing',
    freshness_score NUMERIC(3,2),
    importance_score NUMERIC(3,2),
    
    embedding       vector(1024),
    
    -- Lineage
    generated_by_model VARCHAR(80),
    generation_request_id UUID,
    
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    CHECK (status IN ('developing', 'active', 'cooling', 'stale'))
);

CREATE INDEX idx_agenda_cards_status_created
  ON agenda_cards(status, created_at DESC);
CREATE INDEX idx_agenda_cards_event ON agenda_cards(event_id);
CREATE INDEX idx_agenda_cards_embedding
  ON agenda_cards USING ivfflat (embedding vector_cosine_ops) WITH (lists = 50);
```

### 4.5 `provider_call_logs` (Unit Economics §6)

```sql
CREATE TABLE provider_call_logs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    provider        VARCHAR(80) NOT NULL,
    model           VARCHAR(120),
    operation       VARCHAR(64) NOT NULL,            -- 'chat' | 'embedding' | 'rerank' | 'vision'
    
    input_tokens    INTEGER,
    output_tokens   INTEGER,
    cost_usd        NUMERIC(10,6),
    latency_ms      INTEGER,
    
    -- Lineage
    user_id         UUID REFERENCES users(id) ON DELETE SET NULL,
    generation_id   UUID,
    article_id      UUID,
    
    success         BOOLEAN NOT NULL,
    error_message   TEXT,
    
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Yüksek hacimli, çok kayıt → partition önerisi (Faz 7+)
CREATE INDEX idx_provider_call_logs_created
  ON provider_call_logs(created_at DESC);
CREATE INDEX idx_provider_call_logs_user_created
  ON provider_call_logs(user_id, created_at DESC) WHERE user_id IS NOT NULL;
CREATE INDEX idx_provider_call_logs_provider_created
  ON provider_call_logs(provider, created_at DESC);
```

---

## 5. Faz 3 — User Generation

### 5.1 `generations` (PRD §3.6)

```sql
CREATE TABLE generations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    
    request_text    TEXT NOT NULL,
    mode            VARCHAR(16) NOT NULL,            -- 'current' | 'weekly' | 'archive' | 'comparison'
    output_type     VARCHAR(32) NOT NULL,            -- 'x_post' | 'x_thread' | 'summary' | 'analysis' | ...
    tone            VARCHAR(32),
    length          VARCHAR(16),                     -- 'short' | 'medium' | 'long'
    show_sources    BOOLEAN NOT NULL DEFAULT TRUE,
    
    -- Pipeline state
    status          VARCHAR(20) NOT NULL DEFAULT 'queued',
    -- 'queued' | 'running' | 'completed' | 'failed' | 'insufficient_data'
    
    retrieval_plan_json   JSONB,
    used_agenda_card_ids  UUID[] DEFAULT '{}',
    used_chunk_ids        UUID[] DEFAULT '{}',
    
    -- Output
    output_json     JSONB,                           -- {posts:[], summary:..., sources:[], warnings:[]}
    warnings        JSONB DEFAULT '[]'::jsonb,
    
    -- Provider tracking
    model_provider  VARCHAR(80),
    model_name      VARCHAR(120),
    input_tokens    INTEGER,
    output_tokens   INTEGER,
    cost_estimate_usd NUMERIC(10,6),
    
    -- Style (Faz 5)
    style_profile_id UUID REFERENCES style_profiles(id) ON DELETE SET NULL,
    
    -- Quality
    halu_flagged_at TIMESTAMPTZ,
    halu_flagged_by UUID REFERENCES users(id),
    
    -- User actions
    saved_at        TIMESTAMPTZ,
    
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    CHECK (mode IN ('current', 'weekly', 'archive', 'comparison')),
    CHECK (status IN ('queued', 'running', 'completed', 'failed', 'insufficient_data'))
);

CREATE INDEX idx_generations_user_created ON generations(user_id, created_at DESC);
CREATE INDEX idx_generations_status ON generations(status, created_at DESC);
CREATE INDEX idx_generations_saved ON generations(user_id, saved_at DESC) WHERE saved_at IS NOT NULL;
CREATE INDEX idx_generations_mode ON generations(mode, created_at DESC);
```

### 5.2 `usage_events` (PRD §3.7)

```sql
CREATE TABLE usage_events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    
    event_type      VARCHAR(64) NOT NULL,
    -- 'generation' | 'embedding' | 'login' | 'save' | 'export'
    
    provider        VARCHAR(80),
    model           VARCHAR(120),
    input_tokens    INTEGER,
    output_tokens   INTEGER,
    cost_usd        NUMERIC(10,6),
    
    metadata        JSONB DEFAULT '{}'::jsonb,
    
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_usage_events_user_created ON usage_events(user_id, created_at DESC);
CREATE INDEX idx_usage_events_type ON usage_events(event_type, created_at DESC);

-- Quota query optimization (kalan üretim hesabı)
CREATE INDEX idx_usage_events_user_type_created
  ON usage_events(user_id, event_type, created_at DESC);
```

### 5.3 `saved_generations` (kullanıcı favori)

```sql
CREATE TABLE saved_generations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    generation_id   UUID NOT NULL REFERENCES generations(id) ON DELETE CASCADE,
    note            TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    UNIQUE (user_id, generation_id)
);

CREATE INDEX idx_saved_generations_user ON saved_generations(user_id, created_at DESC);
```

### 5.4 `admin_audit_log` (Legal §8.3)

```sql
CREATE TABLE admin_audit_log (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_id        UUID NOT NULL REFERENCES users(id),
    action          VARCHAR(80) NOT NULL,
    target_type     VARCHAR(80),
    target_id       UUID,
    metadata        JSONB DEFAULT '{}'::jsonb,
    ip_address      INET,
    user_agent      TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_admin_audit_log_actor_created ON admin_audit_log(actor_id, created_at DESC);
CREATE INDEX idx_admin_audit_log_action_created ON admin_audit_log(action, created_at DESC);
CREATE INDEX idx_admin_audit_log_target ON admin_audit_log(target_type, target_id)
  WHERE target_id IS NOT NULL;
```

### 5.X `app_settings` + `app_prompts` (#262, MVP-1.2 admin panel)

Hardcoded `config.py` değerlerinin runtime-tunable alternatifi. Admin paneli üzerinden tune edilir, deploy/restart gerektirmez. `SettingsStore` Redis pub/sub ile multi-container koordinasyon sağlar.

```sql
CREATE TABLE app_settings (
    key                 TEXT PRIMARY KEY,
    value               JSONB NOT NULL,
    type                VARCHAR(16) NOT NULL,
        -- 'float' | 'int' | 'bool' | 'string' | 'json'
    group_name          VARCHAR(64) NOT NULL,
        -- 'rag' | 'clustering' | 'retrieval' | 'quota' | 'scraping' | 'llm'
    description         TEXT,
    min_value           NUMERIC,
    max_value           NUMERIC,
    allowed_values      JSONB,
    requires_restart    BOOLEAN NOT NULL DEFAULT FALSE,
    updated_by          UUID REFERENCES users(id) ON DELETE SET NULL,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT app_settings_type_check
        CHECK (type IN ('float','int','bool','string','json'))
);

CREATE INDEX idx_app_settings_group ON app_settings(group_name);
```

**SettingsStore akışı**:
1. `get(key, default)` → L1 hit → return; miss → DB query → L1 cache (TTL 30s)
2. `set(key, value)` → DB upsert → L1 invalidate → Redis publish `settings:invalidate <key>`
3. Tüm container'lar pub/sub listener → kendi L1'lerini invalidate eder

**Audit**: her değişiklik `admin_audit_log` 'a `action='settings.update'` veya `'settings.reset'`, `metadata={key, old_value, new_value}` ile yazılır.

**Tasarım notu**: Default değerler `SETTING_REGISTRY` (kod) içinde tanımlı; DB sadece **override** kayıt eder. DB'de bir key yoksa caller `default` parametresini alır. Bu yaklaşım yeni setting eklemenin migration gerektirmemesini sağlar.

#### `app_prompts` + `app_prompt_history`

LLM prompt'ları DB'ye taşıyan paralel yapı. Default kod-tarafında (`app/prompts/*.py`), DB'de override + version history.

```sql
CREATE TABLE app_prompts (
    name            VARCHAR(80) PRIMARY KEY,
    version         INTEGER NOT NULL DEFAULT 1,
    content         TEXT NOT NULL,
    description     TEXT,
    model_hint      VARCHAR(120),
    updated_by      UUID REFERENCES users(id) ON DELETE SET NULL,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE app_prompt_history (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(80) NOT NULL,
    version         INTEGER NOT NULL,
    content         TEXT NOT NULL,
    updated_by      UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (name, version)
);

CREATE INDEX idx_app_prompt_history_name_created
    ON app_prompt_history(name, created_at DESC);
```

**PromptsStore akışı**:
1. `get(name, default)` → L1 (TTL 30s) → DB → fallback default
2. `set(name, content, user_id)` → eğer mevcut versiyon varsa → eski versiyonu `app_prompt_history`'ye archive → `app_prompts.version+1`
3. Redis pub/sub `prompts:invalidate <name>` — multi-container sync
4. `restore(name, version)` → history'den fetch → yeni versiyon olarak set (orijinal v# yerine v_current+1)

**Migrate edilen prompts**:
- `query_planner` — `app/prompts/query_planner.py:SYSTEM_PROMPT`
- `agenda_card` — `app/prompts/agenda_card.py:SYSTEM_PROMPT`
- `content_generator` — `app/prompts/content_generator.py:SYSTEM_PROMPT_X_POST`

**Audit**: `admin_audit_log` action='prompts.update'/'prompts.reset'/'prompts.restore', metadata={prompt_name, old_version, new_version}.

---

## 6. Faz 4 — Visual Intelligence

### 6.1 `entities`

```sql
CREATE TABLE entities (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    type            VARCHAR(32) NOT NULL,
    -- 'person' | 'organization' | 'location' | 'topic' | 'object' | 'visual_type'
    name            VARCHAR(180) NOT NULL,
    aliases         JSONB DEFAULT '[]'::jsonb,
    description     TEXT,
    
    -- KVKK uyumluluğu (Legal §2.3)
    is_public_figure BOOLEAN NOT NULL DEFAULT FALSE,
    sensitivity_flag VARCHAR(32),                    -- 'health' | 'religion' | 'political' | NULL
    
    created_by      UUID REFERENCES users(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    UNIQUE (type, name)
);

CREATE INDEX idx_entities_type ON entities(type);
CREATE INDEX idx_entities_name_trgm ON entities USING gin(name gin_trgm_ops);
```

### 6.2 `image_analysis`

```sql
CREATE TABLE image_analysis (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    image_id        UUID NOT NULL REFERENCES article_images(id) ON DELETE CASCADE UNIQUE,
    
    vlm_caption     TEXT,
    ocr_text        TEXT,
    detected_objects JSONB DEFAULT '[]'::jsonb,
    scene_tags      JSONB DEFAULT '[]'::jsonb,
    auto_label_candidates JSONB DEFAULT '[]'::jsonb,
    confidence_json JSONB DEFAULT '{}'::jsonb,
    
    provider        VARCHAR(80),
    model_name      VARCHAR(120),
    
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### 6.3 `image_embeddings`

```sql
CREATE TABLE image_embeddings (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    image_id        UUID NOT NULL REFERENCES article_images(id) ON DELETE CASCADE UNIQUE,
    embedding       vector(1024),
    provider        VARCHAR(80),
    model_name      VARCHAR(120),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_image_embeddings_vec
  ON image_embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists = 50);
```

### 6.4 `image_labels` (PRD §4.7)

```sql
CREATE TABLE image_labels (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    image_id        UUID NOT NULL REFERENCES article_images(id) ON DELETE CASCADE,
    entity_id       UUID NOT NULL REFERENCES entities(id) ON DELETE RESTRICT,
    
    label_type      VARCHAR(32),                     -- 'person' | 'object' | 'scene' | ...
    confidence      NUMERIC(3,2),
    source          VARCHAR(32) NOT NULL,
    -- 'model' | 'admin' | 'context' | 'similarity'
    status          VARCHAR(16) NOT NULL DEFAULT 'suggested',
    -- 'suggested' | 'verified' | 'rejected' | 'uncertain'
    
    verified_by     UUID REFERENCES users(id),
    verified_at     TIMESTAMPTZ,
    
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    UNIQUE (image_id, entity_id),
    CHECK (status IN ('suggested', 'verified', 'rejected', 'uncertain'))
);

CREATE INDEX idx_image_labels_image ON image_labels(image_id);
CREATE INDEX idx_image_labels_entity ON image_labels(entity_id);
CREATE INDEX idx_image_labels_status ON image_labels(status, created_at DESC);
```

---

## 7. Faz 5 — Style Cloning

### 7.1 `style_profiles` (PRD §5.6)

```sql
CREATE TABLE style_profiles (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name            VARCHAR(180) NOT NULL,
    source_type     VARCHAR(32) NOT NULL,
    -- 'manual' | 'x_personal' | 'csv_import' | 'public_account'
    
    style_summary   TEXT,
    rules_json      JSONB NOT NULL DEFAULT '{}'::jsonb,
    sample_count    INTEGER NOT NULL DEFAULT 0,
    
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_style_profiles_user ON style_profiles(user_id, created_at DESC);
```

### 7.2 `style_samples`

```sql
CREATE TABLE style_samples (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    style_profile_id  UUID NOT NULL REFERENCES style_profiles(id) ON DELETE CASCADE,
    text              TEXT NOT NULL,
    source_url        TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_style_samples_profile ON style_samples(style_profile_id);
```

---

## 8. Faz 6 — Billing

### 8.1 `plans` (Pricing §2)

```sql
CREATE TABLE plans (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code            VARCHAR(32) NOT NULL UNIQUE,     -- 'free' | 'starter' | 'pro' | 'agency'
    name            VARCHAR(80) NOT NULL,
    price_monthly_try NUMERIC(10,2),
    price_yearly_try  NUMERIC(10,2),
    price_monthly_usd NUMERIC(10,2),
    
    monthly_generation_limit INTEGER,
    max_context_cards         INTEGER,
    allowed_modes             JSONB DEFAULT '[]'::jsonb,
    allowed_output_types      JSONB DEFAULT '[]'::jsonb,
    allowed_models            JSONB DEFAULT '[]'::jsonb,
    
    style_profiles_allowed    INTEGER DEFAULT 0,
    visual_features_allowed   BOOLEAN NOT NULL DEFAULT FALSE,
    seats                     INTEGER NOT NULL DEFAULT 1,
    
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### 8.2 `subscriptions`

```sql
CREATE TABLE subscriptions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    plan_id         UUID NOT NULL REFERENCES plans(id),
    
    status          VARCHAR(20) NOT NULL DEFAULT 'trialing',
    -- 'trialing' | 'active' | 'past_due' | 'canceled' | 'expired'
    
    billing_cycle   VARCHAR(8) NOT NULL DEFAULT 'monthly', -- 'monthly' | 'yearly'
    current_period_start TIMESTAMPTZ NOT NULL,
    current_period_end   TIMESTAMPTZ NOT NULL,
    canceled_at     TIMESTAMPTZ,
    
    payment_provider VARCHAR(32) NOT NULL DEFAULT 'lemon_squeezy',  -- Epic #448: 'lemon_squeezy' (MoR, USD primary). 'iyzico'/'paytr'/'stripe' reddedildi.
    provider_subscription_id VARCHAR(180),            -- LS subscription_id
    ls_customer_id           VARCHAR(180),            -- LS customer_id
    ls_variant_id            VARCHAR(180),            -- LS variant_id (plan_id ile cross-ref)
    ls_order_id              VARCHAR(180),            -- LS ilk order_id (audit)
    seat_count               INT NOT NULL DEFAULT 1,  -- Agency variants: 3/5/10 (#451)
    
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    CHECK (status IN ('trialing', 'active', 'past_due', 'canceled', 'expired')),
    CHECK (billing_cycle IN ('monthly', 'yearly'))
);

-- Sadece bir aktif subscription per user (Pricing §2.4)
CREATE UNIQUE INDEX uniq_subscriptions_active_per_user
  ON subscriptions(user_id) WHERE status IN ('trialing', 'active');

CREATE INDEX idx_subscriptions_status ON subscriptions(status);
CREATE INDEX idx_subscriptions_period_end ON subscriptions(current_period_end)
  WHERE status IN ('active', 'trialing');
```

### 8.3 `invoices` (Lemon Squeezy MoR — LS keser, Nodrat sadece referans saklar)

> **2026-05-08 revize (Epic #448):** Eski plan e-Arşiv uyumluluğu için `invoice_number`, `vat_amount_try`, `earsiv_pdf_url`, `earsiv_xml_url` sütunları içeriyordu. **Lemon Squeezy MoR sayesinde Nodrat fatura kesmez** — LS müşteriye fatura keser ve PDF'i kendi sisteminde host eder. Bu tablo artık sadece **LS invoice referans cache**'i; gerçek fatura LS Customer Portal'da. KDV/VAT global olarak LS keser.

```sql
CREATE TABLE invoices (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    subscription_id UUID NOT NULL REFERENCES subscriptions(id),
    user_id         UUID NOT NULL REFERENCES users(id),

    -- Lemon Squeezy referans (LS invoice resmi sahibi)
    ls_invoice_id   VARCHAR(180) UNIQUE NOT NULL,    -- LS invoice ID
    ls_invoice_url  TEXT,                            -- LS hosted PDF URL (signed)
    ls_order_id     VARCHAR(180),                    -- LS order ID

    -- Tutar (USD primary; TL display ref opsiyonel — LS payload'undan)
    amount_usd      NUMERIC(10,2) NOT NULL,
    tax_amount_usd  NUMERIC(10,2),                   -- LS keser (KDV/VAT global)
    total_usd       NUMERIC(10,2) NOT NULL,
    currency        VARCHAR(8) NOT NULL DEFAULT 'USD',
    fx_rate_tl      NUMERIC(10,4),                   -- snapshot, display amaçlı

    -- LS lifecycle
    issued_at       TIMESTAMPTZ NOT NULL,            -- LS invoice.created_at
    paid_at         TIMESTAMPTZ,

    metadata        JSONB DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_invoices_user_created ON invoices(user_id, created_at DESC);
CREATE INDEX idx_invoices_ls_id ON invoices(ls_invoice_id);
```

### 8.4 `webhook_events` (Lemon Squeezy idempotency — #450)

```sql
CREATE TABLE webhook_events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ls_event_id     VARCHAR(180) UNIQUE NOT NULL,    -- LS event UUID (idempotency key)
    event_type      VARCHAR(64) NOT NULL,            -- 'subscription_created', etc.
    payload         JSONB NOT NULL,
    signature_valid BOOLEAN NOT NULL,
    processed_at    TIMESTAMPTZ,
    error_message   TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_webhook_events_unprocessed ON webhook_events(created_at)
  WHERE processed_at IS NULL;
```

### 8.5 `agency_seats` (Multi-seat Agency — #451)

```sql
CREATE TABLE agency_seats (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    subscription_id UUID NOT NULL REFERENCES subscriptions(id) ON DELETE CASCADE,
    user_id         UUID REFERENCES users(id) ON DELETE SET NULL,  -- nullable: invite pending
    invited_email   VARCHAR(180) NOT NULL,
    invite_token    VARCHAR(64) UNIQUE,
    accepted_at     TIMESTAMPTZ,
    role            VARCHAR(32) NOT NULL DEFAULT 'editor',  -- 'admin' | 'editor'
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CHECK (role IN ('admin', 'editor'))
);

CREATE INDEX idx_agency_seats_subscription ON agency_seats(subscription_id);
CREATE UNIQUE INDEX uniq_agency_seats_email_per_sub ON agency_seats(subscription_id, invited_email);
```

---

## 9. Triggers ve Otomasyonlar

### 9.1 `updated_at` auto-update

```sql
CREATE OR REPLACE FUNCTION trg_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Tüm `updated_at` taşıyan tablolara apply edilir.
-- Örnek:
CREATE TRIGGER trg_users_updated_at
  BEFORE UPDATE ON users
  FOR EACH ROW EXECUTE FUNCTION trg_set_updated_at();
```

### 9.2 Soft delete kuralı

```text
- users.deleted_at NOT NULL ise → tüm session'lar revoked
- Kullanıcı silinince generations korunur (audit + analitik)
- 30 gün soft delete sonra hard delete (KVKK uyum)
- Cron job: pg_cron veya celery beat tetikler
```

### 9.3 Source health auto-update

```text
Her crawler_jobs.status='succeeded' veya 'failed' olduğunda
source_health.last_*_at güncellenir.
Trigger değil, worker code içinde tutarlı.
```

---

## 10. Seed Verileri (MVP-1)

### 10.1 İlk admin

```sql
-- Bu SQL CLI ile değil python -m app.cli create_admin ile yapılır
-- Şifre Argon2 hash üretilir
```

### 10.2 Default model_providers

```sql
INSERT INTO model_providers (
  name, type, base_url, supports_chat, supports_embeddings,
  cost_per_1m_input_tokens, cost_per_1m_output_tokens,
  monthly_cost_cap_usd, priority, is_active
) VALUES
  ('deepseek_v3', 'llm', 'https://api.deepseek.com',
   TRUE, FALSE, 0.27, 1.10, 200.00, 100, TRUE),
  ('nim_bge_m3', 'embedding', 'https://integrate.api.nvidia.com/v1',
   FALSE, TRUE, 0.00, 0.00, 0.00, 100, TRUE),
  ('local_bge_m3', 'embedding', 'http://embedding:8001',
   FALSE, TRUE, 0.00, 0.00, 0.00, 50, TRUE),
  ('openrouter', 'llm', 'https://openrouter.ai/api/v1',
   TRUE, FALSE, 0.30, 0.40, 100.00, 80, TRUE);

-- Faz 2'de eklenir:
-- ('anthropic_haiku', 'llm', 'https://api.anthropic.com',
--  TRUE, FALSE, 1.00, 5.00, 300.00, 90, TRUE);
```

### 10.3 Default plans (Faz 6)

```sql
INSERT INTO plans (
  code, name,
  price_monthly_try, price_yearly_try, price_monthly_usd,
  monthly_generation_limit, allowed_modes, allowed_output_types,
  allowed_models, style_profiles_allowed, visual_features_allowed, seats
) VALUES
  ('free', 'Ücretsiz',
    0, 0, 0,
    10, '["current","weekly"]'::jsonb, '["x_post","summary"]'::jsonb,
    '["deepseek_v3"]'::jsonb, 0, FALSE, 1),
  
  ('starter', 'Starter',
    249, 2490, 8,
    100, '["current","weekly","archive"]'::jsonb,
    '["x_post","x_thread","summary","headline"]'::jsonb,
    '["deepseek_v3","openrouter"]'::jsonb, 0, FALSE, 1),
  
  ('pro', 'Pro',
    749, 7490, 24,
    500, '["current","weekly","archive","comparison"]'::jsonb,
    '["x_post","x_thread","summary","analysis","headline","calendar","briefing"]'::jsonb,
    '["deepseek_v3","openrouter","anthropic_haiku"]'::jsonb, 3, TRUE, 1),
  
  ('agency', 'Agency',
    2499, 24990, 80,
    2500, '["current","weekly","archive","comparison"]'::jsonb,
    '["x_post","x_thread","summary","analysis","headline","calendar","briefing"]'::jsonb,
    '["deepseek_v3","openrouter","anthropic_haiku","anthropic_sonnet"]'::jsonb, 10, TRUE, 3);
```

---

## 11. Index Stratejisi (PRD §7.5 ile uyumlu)

### 11.1 Vector indexes

```text
ivfflat (MVP-1):
  - lists = sqrt(rows) / 2 başlangıç
  - article_chunks: lists=100 (~10K chunk hedef)
  - agenda_cards:   lists=50  (~2K card hedef)
  - image_emb:      lists=50

HNSW (Faz 7+, 1M+ row):
  CREATE INDEX ... USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
```

### 11.2 B-tree composite indexes (sıkça birlikte sorgulananlar)

```sql
-- Retrieval (current mode)
articles(source_id, published_at DESC)
article_chunks(source_id, published_at DESC)
agenda_cards(status, created_at DESC) WHERE status IN ('developing','active')

-- User dashboard
generations(user_id, created_at DESC)
saved_generations(user_id, created_at DESC)
usage_events(user_id, event_type, created_at DESC)

-- Admin operations
crawler_jobs(status, priority DESC, scheduled_at)
failed_jobs(created_at DESC) WHERE resolved_at IS NULL

-- Quota query (en sık sorgu)
usage_events(user_id, event_type, created_at DESC) -- son 30 gün count
```

### 11.3 GIN indexes (full-text + JSONB)

```sql
-- Full-text aramalar (Faz 7+ keyword search)
CREATE INDEX idx_articles_clean_text_trgm
  ON articles USING gin(clean_text gin_trgm_ops);

CREATE INDEX idx_articles_title_trgm
  ON articles USING gin(title gin_trgm_ops);

-- JSONB sorguları (output filter)
CREATE INDEX idx_generations_output_gin
  ON generations USING gin(output_json jsonb_path_ops);
```

---

## 12. Maintenance Görevleri

### 12.1 Bakım takvimi

```text
Real-time:    autovacuum (Postgres default)
Günlük:       backup, eski cache temizliği
Haftalık:     ANALYZE büyük tablolar
Aylık:        VACUUM FULL nadir, REINDEX vector
3 aylık:      Eski article snapshot temizliği
6 aylık:      Index seçim audit, ivfflat → hnsw geçiş değerlendirmesi
```

### 12.2 Retention politikaları

```text
articles:                90 gün cleaned, sonra archived (clean_text → NULL)
article_chunks:          archived article'lar silinir (RAG context kaybı kabul)
crawler_jobs:            30 gün sonra silinir (succeeded ones)
failed_jobs:             90 gün sonra silinir (resolved ones)
provider_call_logs:      6 ay sonra archive partition'a (Faz 7 partition)
admin_audit_log:         1 yıl saklanır (yasal)
sessions:                expires_at + 30 gün sonra silinir
usage_events:            18 ay (KVKK gerekirse anonimize)
generations:             kullanıcı silmedikçe sonsuz
saved_generations:       kullanıcı sahipliği — sonsuz
```

### 12.3 Bakım job tanımları

```text
maintenance_queue:
  - cleanup_old_html_snapshots     (günlük)
  - vacuum_analyze_chunks          (haftalık)
  - reindex_vector                 (aylık)
  - archive_old_articles           (3 aylık)
  - cleanup_old_jobs               (haftalık)
  - cleanup_revoked_sessions       (günlük)
```

---

## 13. Karar Noktaları

| ID | Karar | Önerim | Etki |
|---|---|---|---|
| D1 | UUID vs bigserial | UUID (gen_random_uuid) | Distributed-friendly |
| D2 | Soft delete vs hard | Soft (deleted_at), 30g sonra hard | KVKK uyum |
| D3 | Embedding dim | 1024 (bge-m3) | Provider-bağımsız |
| D4 | Vector index tipi | ivfflat (MVP), HNSW (Faz 7+) | Scaling |
| D5 | JSONB vs ayrı tablo | JSONB (key_points, sources) | Esneklik |
| D6 | Audit log retention | 1 yıl | Yasal minimum |
| D7 | Migrations araç | Alembic | Python ekosistem |
| D8 | provider_call_logs partition | Faz 7+ | Şimdi gerekmez |
| D9 | Article TTL | 90 gün cleaned, sonra archive | Maliyet kontrolü |
| D10 | content_hash unique scope | Per source_id | Cross-source dup OK |

---

## 14. Çapraz Referans

```text
Tüm tablolar              → IA §7.1 entity diagram
sources, source_configs   → PRD §1.10
articles, article_chunks  → PRD §2.4
event_clusters, agenda_*  → PRD §2.5, §2.6
generations, usage_events → PRD §3.6, §3.7
image_*, entities         → PRD §4.4–4.7
style_*                   → PRD §5.6
plans, subscriptions      → PRD §6.3, Pricing §2
model_providers           → Architecture §4
provider_call_logs        → Unit Economics §6, Metrics §3.7
admin_audit_log           → Legal §8.3
Vector indexes            → PRD §7.5
Quota query indexes       → Pricing §8.1 (hard cap)
Soft delete deleted_at    → Legal §2.3 (KVKK silme)
```

---

**Sonuç:** Toplam **~25 tablo**, MVP-1'de **16 aktif**. pgvector ivfflat MVP için yeterli; **1M+ chunk sonrası HNSW**'ye geçilir. Tüm tablolar `id UUID + created_at` pattern'inde. Soft delete + 30 gün hard delete KVKK uyumlu. Migration **Alembic** + forward-compatible kuralları zorunlu. Provider config + cost cap + audit log **Risk Register R-FIN-01 ve R-LGL-01 mitigation'lar**ıyla doğrudan eşleşir.
