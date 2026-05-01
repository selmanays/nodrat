# Nodrat — Teknik Mimari ve Deployment

**Doküman türü:** Technical Architecture & Deployment Spec
**Sürüm:** v0.1
**Bağımlılık:** PRD §6, IA §3, §13, Risk Register §4 (MVP-1 kapsamı), Unit Economics §2.4 (VPS)
**Hedef:** Tek VPS üzerinde çalışacak self-hosted servis topolojisi, network, secrets, deployment ve operasyonel runbook.

---

## 0. Yönetici Özeti

```text
Stack (lock-in):
  Frontend  : Next.js 14 (App Router) + shadcn/ui + Tailwind
  Backend   : FastAPI (Python 3.12) + Pydantic v2
  Worker    : Celery 5 + Redis broker
  Database  : PostgreSQL 16 + pgvector
  Queue     : Redis 7 (broker + cache)
  Storage   : MinIO (S3 API uyumlu)
  Proxy     : Caddy 2 (otomatik TLS)
  Container : Docker Compose
  Scheduler : Celery Beat
  Backup    : restic + Backblaze B2 (off-server)

Deployment:
  Platform  : Hetzner CCX23 (Ubuntu 22.04 LTS)
  Runtime   : Docker Compose v2
  CI/CD     : GitHub Actions → SSH deploy
  Secrets   : .env + age encryption (sops)
  TLS       : Caddy auto-issue (Let's Encrypt)

MVP-1 minimum: 4 vCPU, 16 GB RAM, 240 GB NVMe (~$29/ay Hetzner)
Ölçek hedefi: 8 vCPU, 32 GB, 500 GB (~$66/ay)
```

---

## 1. Mimari Prensipler

```text
A1. Monolith başlangıcı, queue ile bölünebilirlik
    API tek FastAPI service; worker'lar Celery tasks.
    İleride worker'lar ayrı VPS'e taşınabilir, kod paylaşımlı.

A2. Database tek source of truth
    Postgres içinde data + audit + queue ledger.
    Redis sadece broker + ephemeral cache.

A3. Provider abstraction zorunlu (PRD F0-R4)
    LLM/embedding/payment provider değiştirilebilir adapter.
    Hiçbir kod direkt provider SDK'sına bağlı olmaz.

A4. Stateless servisler, persistent volumes
    Container restart edilirse veri kaybı yok.
    State sadece volumes (postgres, redis, minio).

A5. Defense in depth
    Caddy → API → DB; her katman ayrı network'te.
    Postgres ve Redis dış dünyaya açık değil.

A6. Observability first-class
    Her service /health, structured JSON log,
    Prometheus metric (Faz 2+).

A7. Backup zorunlu (Risk Register R-OPS-03)
    Daily Postgres dump + weekly MinIO snapshot.
    Off-server şifreli (B2 + age key).

A8. Secret rotation hazırlığı
    .env doğrudan kullanılmaz, sops ile encrypted.
    Provider key'leri model_providers tablosunda
    encrypted at rest (Fernet).
```

---

## 2. Servis Topolojisi (MVP-1)

### 2.1 Container haritası

```text
┌──────────────────────────────────────────────────────────────────┐
│                        VPS (Hetzner CCX23)                        │
│                                                                    │
│  ┌──────────────┐                                                │
│  │   caddy      │  → 443 (TLS), 80 (redirect)                    │
│  │  reverse     │     auto-issue Let's Encrypt                   │
│  │  proxy       │                                                 │
│  └──────┬───────┘                                                │
│         │                                                         │
│    ┌────┴────┬─────────┐                                         │
│    ▼         ▼         ▼                                         │
│  ┌──────┐ ┌──────┐ ┌──────────┐                                 │
│  │ web  │ │ api  │ │ minio    │  → 9001 (admin only)             │
│  │ :3000│ │:8000 │ │ :9000    │                                  │
│  └──────┘ └──┬───┘ └────┬─────┘                                  │
│             │           │                                         │
│             └─────┬─────┘                                         │
│                   │                                               │
│       ┌───────────┼─────────────┐                                │
│       ▼           ▼             ▼                                │
│   ┌────────┐  ┌────────┐  ┌──────────────┐                      │
│   │postgres│  │ redis  │  │ workers      │                      │
│   │ :5432  │  │ :6379  │  │ (celery)     │                      │
│   └────────┘  └────────┘  └──────────────┘                      │
│                              │                                   │
│                       ┌──────┼──────┬──────────┬────────┐       │
│                       ▼      ▼      ▼          ▼        ▼       │
│                   scraper cleaner embed    rag     scheduler    │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘

Network'ler:
  edge      : caddy ↔ web, api  (public-facing)
  internal  : api ↔ postgres, redis, minio, worker'lar
  
Public exposure:
  - 80, 443 (caddy)
  - 22 (SSH, key-only, fail2ban)
  
Tüm diğer portlar firewall ile kapalı (ufw).
```

### 2.2 Compose servisleri

```yaml
# docker-compose.yml — schematik gösterim
services:
  caddy:
    image: caddy:2-alpine
    ports: ["80:80", "443:443"]
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile
      - caddy_data:/data
      - caddy_config:/config
    networks: [edge]
    restart: unless-stopped

  web:
    build: ./apps/web
    environment:
      - NEXT_PUBLIC_API_URL=https://nodrat.com/api
    networks: [edge]
    depends_on: [api]
    restart: unless-stopped

  api:
    build: ./apps/api
    environment:
      - DATABASE_URL=postgresql://nodrat:${POSTGRES_PASSWORD}@postgres:5432/nodrat
      - REDIS_URL=redis://redis:6379/0
      - MINIO_ENDPOINT=minio:9000
      - MINIO_ACCESS_KEY=${MINIO_ACCESS_KEY}
      - MINIO_SECRET_KEY=${MINIO_SECRET_KEY}
      - DEFAULT_LLM_PROVIDER=deepseek_v3
      - DEFAULT_EMBEDDING_PROVIDER=nim_bge_m3
      - SECRET_KEY=${API_SECRET_KEY}
    networks: [edge, internal]
    depends_on: [postgres, redis, minio]
    restart: unless-stopped

  postgres:
    image: pgvector/pgvector:pg16
    environment:
      - POSTGRES_DB=nodrat
      - POSTGRES_USER=nodrat
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    networks: [internal]
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    command: redis-server --appendonly yes --requirepass ${REDIS_PASSWORD}
    volumes:
      - redis_data:/data
    networks: [internal]
    restart: unless-stopped

  minio:
    image: minio/minio:latest
    environment:
      - MINIO_ROOT_USER=${MINIO_ACCESS_KEY}
      - MINIO_ROOT_PASSWORD=${MINIO_SECRET_KEY}
    command: server /data --console-address ":9001"
    volumes:
      - minio_data:/data
    networks: [internal]
    restart: unless-stopped

  worker_scraper:
    build: ./apps/api
    command: celery -A worker.celery_app worker -Q crawl_queue,media_queue -c 2
    environment: { ...same as api }
    networks: [internal]
    depends_on: [postgres, redis]
    restart: unless-stopped

  worker_cleaner:
    build: ./apps/api
    command: celery -A worker.celery_app worker -Q cleaning_queue -c 2
    environment: { ...same as api }
    networks: [internal]
    depends_on: [postgres, redis]
    restart: unless-stopped

  worker_embedding:
    build: ./apps/api
    command: celery -A worker.celery_app worker -Q embedding_queue -c 1
    environment: { ...same as api }
    networks: [internal]
    depends_on: [postgres, redis]
    restart: unless-stopped

  worker_rag:
    build: ./apps/api
    command: celery -A worker.celery_app worker -Q event_queue,generation_queue -c 2
    environment: { ...same as api }
    networks: [internal]
    depends_on: [postgres, redis]
    restart: unless-stopped

  scheduler:
    build: ./apps/api
    command: celery -A worker.celery_app beat
    environment: { ...same as api }
    networks: [internal]
    depends_on: [redis]
    restart: unless-stopped

networks:
  edge: { driver: bridge }
  internal: { internal: true, driver: bridge }

volumes:
  postgres_data:
  redis_data:
  minio_data:
  caddy_data:
  caddy_config:
```

### 2.3 Caddyfile

```text
nodrat.com, www.nodrat.com {
    encode gzip zstd
    
    # Frontend
    handle /api/* {
        reverse_proxy api:8000
    }
    handle {
        reverse_proxy web:3000
    }
    
    # Logging
    log {
        output file /var/log/caddy/access.log {
            roll_size 100mb
            roll_keep 7
        }
        format json
    }
    
    # Security headers
    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
        X-Frame-Options "DENY"
        X-Content-Type-Options "nosniff"
        Referrer-Policy "strict-origin-when-cross-origin"
        Permissions-Policy "geolocation=(), microphone=(), camera=()"
    }
}

# MinIO admin (sadece admin VPN/IP'den)
minio.nodrat.com {
    @admin remote_ip 192.168.1.0/24 1.2.3.4/32  # admin IP allowlist
    handle @admin {
        reverse_proxy minio:9001
    }
    respond 403
}
```

---

## 3. Worker Mimarisi

### 3.1 Queue grupları (PRD §7.2 + IA Faz 1-3)

```text
crawl_queue       : source.fetch_rss, source.fetch_category
                    article.discover, article.fetch_detail, article.extract
                    Concurrency: 2 (HTTP-bound)
                    Priority: scheduled normal, manuel high

media_queue       : media.discover, media.download, media.hash
                    Concurrency: 2 (download paralel)
                    
cleaning_queue    : article.clean, article.dedupe
                    Concurrency: 2 (CPU-bound)

embedding_queue   : article.embed (NIM/local)
                    Concurrency: 1 (rate limit'li)
                    Batch: 100 chunk per request

event_queue       : event.cluster, agenda_card.generate
                    Concurrency: 1 (LLM-bound, expensive)

generation_queue  : user.generate (sync API çağrıdan da kullanılır)
                    Concurrency: 3 (per-tier limited)
                    Priority: paid > free > trial

vision_queue      : (Faz 4) image.embed, image.vlm, image.ocr
                    Concurrency: 1
                    Priority: low

billing_queue     : (Faz 6) subscription.sync, webhook.process
                    Concurrency: 1
```

### 3.2 Retry ve dead letter (PRD §1.9)

```text
Retry policy (Celery autoretry_for):
  HTTPError 429:    backoff=exp, max=3, source-level cooldown
  HTTPError 5xx:    retry=3
  Timeout:          retry=2
  ParserError:      retry=0 → failed_jobs
  MediaError:       retry=2

Dead letter:
  Tüm başarısız job → failed_jobs tablosu
  Admin /admin/queue/failed ekranı
  Manuel retry endpoint
```

### 3.3 Celery Beat schedule (MVP-1)

```python
# celery_beat.py
beat_schedule = {
    'crawl-all-sources': {
        'task': 'tasks.scheduler.crawl_active_sources',
        'schedule': crontab(minute='*/15'),  # her 15 dk
    },
    'event-clustering': {
        'task': 'tasks.rag.cluster_recent_events',
        'schedule': crontab(minute=0, hour='*'),  # saatlik
    },
    'agenda-card-refresh': {
        'task': 'tasks.rag.refresh_active_cards',
        'schedule': crontab(minute=30, hour='*/2'),  # 2 saatte bir
    },
    'cleanup-old-snapshots': {
        'task': 'tasks.maintenance.cleanup_old_html_snapshots',
        'schedule': crontab(minute=0, hour=3),  # gece 03:00
    },
    'database-backup': {
        'task': 'tasks.maintenance.backup_database',
        'schedule': crontab(minute=0, hour=4),  # gece 04:00
    },
    'source-health-check': {
        'task': 'tasks.sources.healthcheck_all',
        'schedule': crontab(minute=0, hour='*/6'),  # 6 saatte bir
    },
}
```

---

## 4. Provider Katmanı (PRD F0-R4)

### 4.1 Adapter interface

```python
# packages/model-providers/base.py
class ModelProvider(Protocol):
    name: str
    supports_chat: bool
    supports_embeddings: bool
    supports_rerank: bool
    supports_vision: bool
    
    async def generate_text(
        self,
        messages: list[Message],
        model: str,
        max_tokens: int = 1024,
        temperature: float = 0.7,
        timeout: int = 30,
    ) -> GenerationResult: ...
    
    async def generate_structured_json(
        self,
        messages: list[Message],
        schema: dict,
        model: str,
    ) -> dict: ...
    
    async def create_embedding(
        self,
        texts: list[str],
        model: str,
    ) -> list[list[float]]: ...
    
    async def rerank(
        self,
        query: str,
        documents: list[str],
        top_k: int = 5,
    ) -> list[RerankResult]: ...
    
    async def healthcheck(self) -> ProviderHealth: ...
```

### 4.2 Adapter listesi (MVP-1: sadece DeepSeek + NIM)

```text
NimChatProvider (name='deepseek_v3')   — default LLM via NIM (deepseek-v3.2)
NimEmbeddingProvider (name='nim_bge_m3') — embedding via NIM (nvidia/nv-embedqa-e5-v5, 1024-dim)
OpenRouterProvider                       — chat fallback (generic, opsiyonel)
AnthropicProvider                        — Faz 2'de Pro tier (Haiku 4.5)
OpenAICompatibleProvider                 — son fallback
LocalBgeM3Provider                       — embedding fallback (sentence-transformers)

# NOT (2026-05-02 — #109): DeepSeek V3 chat NIM endpoint'i üzerinden çağrılıyor.
# NIM ücretsiz tier 30+ chat modeli host'lar (deepseek-v3.2, mistral-large-3,
# kimi-k2, glm-4.7, vb.). Tek API key (NIM_API_KEY) yeterli, ek native
# DeepSeek API key gerekmez. cost_usd=0 (free tier).
#
# NOT (2026-05-01): NIM'de baai/bge-m3 HTTP 500 veriyor, default
# nvidia/nv-embedqa-e5-v5'e değişti. Schema vector(1024) korundu.

Faz 4+:
  AnthropicVisionProvider, OpenAIVisionProvider
Faz 6+:
  IyzicoPaymentProvider, StripePaymentProvider
```

### 4.3 Routing logic

```python
# Pseudo-code
def route_request(user: User, task_type: str) -> Provider:
    if user.tier == "agency" and task_type == "comparison_generation":
        return AnthropicProvider(model="claude-sonnet-4-6")
    if user.tier in ("pro", "agency"):
        return AnthropicProvider(model="claude-haiku-4-5")
    if user.tier in ("starter", "free", "trial"):
        return DeepSeekProvider(model="deepseek-v3")
    raise ValueError("Unknown tier")

def with_fallback(primary: Provider, fallbacks: list[Provider]):
    # Circuit breaker pattern + retry
    ...
```

### 4.4 Cost tracking

```text
Her provider çağrısı sonrası provider_call_logs tablosuna yaz:
  - request_id (generation_id ile bağlı)
  - provider, model
  - input_tokens, output_tokens
  - cost_estimate_usd
  - latency_ms
  - error (if any)

Aggregate:
  Daily provider spend dashboard
  Per-user cost (P95 alarm)
  Top 20 spender flag
```

---

## 5. Storage Stratejisi

### 5.1 PostgreSQL

```text
Konum:        /var/lib/postgresql/data (volume)
Boyut tahmin:
  MVP-1 (3 kaynak, 30 gün):  ~2 GB
  Ölçek (50 kaynak, 1 yıl):  ~80 GB
  
Backup:       pg_dump günlük + WAL streaming opsiyonel
              restic ile B2'ye günde 1 kez
              Retention: 7 günlük + 4 haftalık + 6 aylık

Tuning (CCX23):
  shared_buffers = 4GB
  effective_cache_size = 12GB
  work_mem = 16MB
  maintenance_work_mem = 1GB
  max_connections = 100
  random_page_cost = 1.1  (NVMe)

Extension:
  pgvector (embedding)
  pg_trgm (full-text + similarity)
  pgcrypto (uuid, encryption)
```

### 5.2 MinIO (S3 uyumlu)

```text
Konum:        /var/lib/minio (volume)
Buckets:
  nodrat-images    : article görselleri
  nodrat-snapshots : raw HTML snapshots (Faz 2+)
  nodrat-backups   : DB dumps (off-server senkron öncesi)

Policy:
  Public read: hiçbiri (varsayılan private)
  API → presigned URL ile geçici erişim
  
Boyut tahmini:
  MVP-1: ~5 GB/ay
  Ölçek: ~50 GB/ay (Yıl 1: ~500 GB)

Path patern (PRD §1.8):
  /images/{source_slug}/{yyyy}/{mm}/{dd}/{image_id}.{ext}
```

### 5.3 Redis

```text
Konum:        /data (volume, AOF on)
Kullanım:
  - Celery broker (queue)
  - Session cache (TTL)
  - Embedding cache (TTL 24h, popular queries)
  - Query plan cache (TTL 1h)
  - Rate limit counter (sliding window)

Boyut:        ≤ 1 GB (cache eviction LRU)
Backup:       AOF ile dayanıklı, ama veri kaybedilebilir
              (kritik veri Postgres'te)
```

---

## 6. Network & Güvenlik

### 6.1 Firewall (ufw)

```bash
ufw default deny incoming
ufw default allow outgoing

ufw allow 22/tcp         # SSH (key-only)
ufw allow 80/tcp         # HTTP (Caddy redirect)
ufw allow 443/tcp        # HTTPS

# MinIO console: sadece admin IP
ufw allow from 1.2.3.4 to any port 9001

ufw enable
```

### 6.2 SSH hardening

```text
PasswordAuthentication no
PermitRootLogin no
PubkeyAuthentication yes
fail2ban enabled (3 strike, 1h ban)
```

### 6.3 TLS

```text
Caddy auto-issue Let's Encrypt
HSTS enabled (preload)
TLS 1.2+ only
```

### 6.4 Container network izolasyonu

```text
edge      : public-facing services (caddy, web, api)
internal  : data services (postgres, redis, minio, workers)

Workers internal'e bağlı, edge'e değil.
Postgres/Redis/MinIO sadece internal'de.
API her iki network'te (edge'den gelir, internal'e gönderir).
```

---

## 7. Secrets Yönetimi

### 7.1 Repository içinde

```text
.env.example       — şablon, repo'da
.env               — gitignore, sunucuda manuel
.env.sops          — sops ile encrypted, repo'da OK

Yöntem (önerilen):
  age key + sops + .env.sops
  Deploy script sops -d ile decrypt eder
```

### 7.2 .env şeması

```bash
# Database
POSTGRES_PASSWORD=...
DATABASE_URL=postgresql://nodrat:...@postgres:5432/nodrat

# Redis
REDIS_PASSWORD=...
REDIS_URL=redis://:${REDIS_PASSWORD}@redis:6379/0

# MinIO
MINIO_ACCESS_KEY=...
MINIO_SECRET_KEY=...
MINIO_ENDPOINT=minio:9000

# API
API_SECRET_KEY=...                 # session signing
JWT_SECRET=...                     # token signing

# Provider keys
DEEPSEEK_API_KEY=...
NIM_API_KEY=...
OPENROUTER_API_KEY=...              # fallback
ANTHROPIC_API_KEY=...               # Faz 2 (Pro tier)
OPENAI_API_KEY=...                  # son fallback

# Email (Faz 0+)
RESEND_API_KEY=...
MAIL_FROM=hello@nodrat.com

# Backup
B2_KEY_ID=...
B2_APP_KEY=...
B2_BUCKET=nodrat-backups
RESTIC_PASSWORD=...

# Defaults
DEFAULT_LLM_PROVIDER=deepseek_v3
DEFAULT_EMBEDDING_PROVIDER=nim_bge_m3
DEFAULT_LANGUAGE=tr
ENVIRONMENT=production
```

### 7.3 Provider key encryption at rest

```text
model_providers tablosunda:
  api_key_secret_ref VARCHAR(255)  → Fernet encrypted referans
  
Decryption:
  API_SECRET_KEY → Fernet.decrypt
  Sadece request anında decrypt edilir, log'a yazılmaz
```

---

## 8. Deployment Akışı

### 8.1 İlk kurulum (manual)

```bash
# 1. VPS provision (Hetzner)
# 2. SSH key ekle, SSH güvenlik
# 3. Docker + Docker Compose install
curl -fsSL https://get.docker.com | sh
apt install docker-compose-plugin

# 4. Repo clone
git clone https://github.com/[user]/nodrat /opt/nodrat
cd /opt/nodrat

# 5. .env oluştur (sops ile)
sops -d .env.sops > .env

# 6. Caddyfile DNS doğrulama
# Domain DNS A record VPS IP'ye gösterilmiş olmalı

# 7. İlk build + up
docker compose pull
docker compose build
docker compose up -d

# 8. Database migration
docker compose exec api alembic upgrade head

# 9. İlk admin oluştur
docker compose exec api python -m app.cli create_admin

# 10. Sağlık kontrolü
curl https://nodrat.com/api/health
```

### 8.2 CI/CD (GitHub Actions → SSH)

```yaml
# .github/workflows/deploy.yml — schematik
name: Deploy
on:
  push:
    branches: [main]
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: SSH deploy
        uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.VPS_HOST }}
          username: deploy
          key: ${{ secrets.SSH_KEY }}
          script: |
            cd /opt/nodrat
            git pull --ff-only
            sops -d .env.sops > .env
            docker compose pull
            docker compose build
            docker compose up -d --remove-orphans
            docker compose exec -T api alembic upgrade head
            docker compose exec -T api python -m app.cli warm_cache
            curl -fsS https://nodrat.com/api/health
```

### 8.3 Zero-downtime deployment

```text
MVP-1: kabul edilen ~30 sn downtime
       (web ve api restart ederken kuyruk birikir)

İleride (Faz 6+):
  - Caddy → blue-green container'lar
  - Migrations forward-compatible
  - Rolling restart with healthcheck
```

---

## 9. Backup ve Disaster Recovery

### 9.1 Backup matrisi

```text
Data tipi          Sıklık     Retention            Konum
──────────────────────────────────────────────────────────────────
PostgreSQL dump    Günlük     7 gün + 4 hafta + 6 ay  B2 (encrypted)
WAL streaming      Real-time  72 saat              VPS local volume
MinIO snapshot     Haftalık   4 hafta + 3 ay       B2 (encrypted)
Redis AOF          Real-time  1 gün                VPS local
.env / config      Aylık      Sınırsız             B2 (encrypted)
Caddy logs         7 gün      —                    VPS local
```

### 9.2 Restore drill (aylık zorunlu)

```bash
# Drill prosedürü
1. Yeni sandbox VPS provision
2. Latest B2 backup pull (restic)
3. Postgres restore: pg_restore < dump.sql
4. MinIO restore: mc mirror b2/nodrat-images minio/...
5. .env restore
6. docker compose up -d
7. Healthcheck + ana akış (login + 1 generation)
8. Süre ölçümü kayıt: hedef <90 dk

Bu drill ayda 1 yapılır → R-OPS-03 mitigation
```

### 9.3 RPO / RTO hedefleri

```text
RPO (Recovery Point Objective):
  - Postgres: <5 dk (WAL) | 24 saat (B2 dump)
  - MinIO:    <7 gün (haftalık snapshot)
  
RTO (Recovery Time Objective):
  - Tam VPS kaybı: <90 dk yeni VPS + restore
  - Servis crash:  <5 dk auto-restart
  - DB corruption: <30 dk pg restore

Kabul:
  MVP-1: RPO 24h / RTO 4h (yeterli)
  Olgun: RPO 1h  / RTO 1h
```

---

## 10. Monitoring & Observability

### 10.1 MVP-1 minimum

```text
Healthcheck:
  /api/health    → {status, db, redis, minio, providers}
  /api/readiness → migration done, providers healthy
  
Logging:
  Tüm servisler structured JSON log → stdout
  Caddy access log → /var/log/caddy/
  Docker logs persistent (max 100MB rotated)
  
Error tracking:
  Sentry (free tier) — Faz 1'de aktif
  
Uptime:
  Better Uptime (free tier) → 5 dk ping
  Slack/email alert
  
Resource:
  htop / vmstat manuel
  Disk usage cron alert (>%80 mail)
```

### 10.2 Faz 2+ Prometheus + Grafana

```text
Prometheus:
  - Servis /metrics endpoint'leri
  - Postgres exporter
  - Redis exporter
  - Node exporter (host)

Grafana dashboard'lar:
  - North Star (WSGAU live)
  - Source health
  - Queue lag & throughput
  - Provider cost & error rate
  - DB query latency
  - Disk/CPU/RAM trend

Alerting:
  - Alarm threshold (Metrics §6 ile uyumlu)
  - Slack webhook + email
```

### 10.3 Audit log

```text
admin_audit_log tablosu:
  - kim (user_id), ne (action), ne zaman, kaynak
  - source ekleme/silme
  - selector değişimi
  - kullanıcı yönetimi
  - provider config değişimi
  
Retention: 1 yıl (KVKK uyum + güvenlik)
```

---

## 11. Geliştirme Ortamı

### 11.1 Local dev setup

```bash
# docker-compose.dev.yml
# - Postgres + Redis + MinIO local
# - API hot-reload (uvicorn --reload)
# - Web hot-reload (next dev)
# - Worker'lar tek concurrency

make dev-up           # tek komut
make dev-migrate      # migration
make dev-seed         # seed admin + 1 kaynak
make test             # pytest
make lint             # ruff + black + mypy
```

### 11.2 Klasör yapısı (PRD F0-R1 ile uyumlu)

```text
/apps
  /web                  Next.js
  /api                  FastAPI + Celery worker'lar (tek paket)
/packages
  /shared-types         Pydantic + TS şemalar (codegen)
  /model-providers      Adapter implementasyonları
  /crawler-core         RSS + extractor + cleaner
  /rag-core             Chunking, retrieval, agenda
/infra
  docker-compose.yml
  docker-compose.dev.yml
  Caddyfile
  /scripts (deploy, restore, backup)
/docs
  prd.md
  architecture.md       ← BU DOKÜMAN
  data-model.md
  api-contracts.md
  prompt-contracts.md
  ...
/tests
  /unit
  /integration
  /e2e (Playwright)
```

---

## 12. MVP-1 → Ölçek Geçiş Planı

### 12.1 İlk darboğaz noktaları

```text
1. Embedding throughput (NIM rate limit)
   → Local bge-m3 fallback aktif
   → Batch size 100→500

2. Postgres connection pool
   → PgBouncer ekle (1.000+ user)

3. Worker concurrency
   → CCX43'e upgrade (8 vCPU, 32 GB)
   → Worker'lar farklı container'larda fragmenter

4. MinIO disk büyümesi
   → Image TTL policy (90 gün arşiv → soğuk depo)
   → Hetzner Storage Box (ucuz blob)

5. Generation latency
   → DeepSeek failover OpenRouter
   → Sonnet sadece Agency tier
```

### 12.2 Yatay ölçek (Faz 7+)

```text
- Web/API behind Caddy LB (multiple replica)
- Worker'lar ayrı VPS'lere (sadece DB + Redis paylaşımlı)
- PgBouncer connection pooling
- Read replica (analytics)
- CDN (Cloudflare) static assets

Bu ihtiyaç MRR ≥ $5K (yaklaşık 250 paid user) sonrası başlar.
```

---

## 13. Karar Noktaları

| ID | Karar | Önerim | Etki |
|---|---|---|---|
| D1 | Backend dili | Python + FastAPI | Worker'lar paylaşımlı |
| D2 | Process orchestrator | Docker Compose | k8s overengineering |
| D3 | Reverse proxy | Caddy | Auto-TLS, basit config |
| D4 | Queue | Celery + Redis | Olgun, Python ekosistem |
| D5 | Storage | MinIO self-host | S3 uyumlu, $0 |
| D6 | Backup | restic + B2 | Encryption + ucuz |
| D7 | Secret mgmt | sops + age | Repo-friendly |
| D8 | CI/CD | GitHub Actions + SSH | Basit, ücretsiz |
| D9 | Monitoring (MVP-1) | Sentry + Better Uptime | Free tier yeterli |
| D10 | Monitoring (Faz 2+) | Prometheus + Grafana | Self-host |

---

## 14. Çapraz Referans

```text
Provider abstraction       → PRD F0-R4, Unit Economics §4
Worker queue grupları       → PRD §7.2, IA §13 Faz mapping
Backup strategy             → Risk Register R-OPS-03
Secret encryption           → Legal Brief §2 (KVKK)
Provider cost tracking      → Unit Economics §6, Metrics §3.7
TLS + security headers      → Threat Model (sıradaki doc)
Migration strategy          → Data Model doc (sıradaki)
Healthcheck endpoints       → API Contracts doc (sıradaki)
Audit log                   → Legal Brief §5 (5651) + Metrics F11
DB tuning                   → Data Model §indexes
```

---

**Sonuç:** Tek VPS üzerinde **6 servis + 5 worker** Docker Compose ile orkestre. Caddy public layer, Postgres/Redis/MinIO internal-only. Provider katmanı zorunlu abstraction; MVP-1'de DeepSeek + NIM yeterli, Faz 2'de Anthropic eklenir. Backup B2'ye günlük şifreli zorunlu. **MVP-1 maliyeti ~$30/ay, ölçek ~$66/ay** (Unit Economics ile uyumlu). Yatay ölçek MRR $5K sonrası planlanır.
