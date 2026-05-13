"""Application configuration loaded from environment variables.

Tüm settings tek yerde — pydantic-settings ile env'den yüklenir.
docs/engineering/architecture.md §7 ile uyumlu.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- Environment -----------------------------------------------------
    environment: Literal["development", "staging", "production"] = "development"
    default_language: str = "tr"
    log_level: str = "INFO"

    # ---- Database --------------------------------------------------------
    database_url: str = Field(
        default="postgresql+asyncpg://nodrat:nodrat@localhost:5433/nodrat",
        description="Async PostgreSQL connection string",
    )
    # #256 — Connection pool tuning. 7 container × (pool_size + max_overflow)
    # = 7 × 15 = 105 max demand, postgres max_connections=300 yedeği var.
    # #684 PR-A — worker concurrency 1→4 + parallel rechunk için pool
    # boyutu artırıldı: 7 container × 30 conn = 210, postgres'i artırarak
    # mevcut max_connections=300 limit'i altında kalır.
    db_pool_size: int = Field(default=10, ge=1, le=50)
    db_max_overflow: int = Field(default=20, ge=0, le=100)
    db_pool_recycle_seconds: int = Field(
        default=300, ge=60, le=3600,
        description="Connection 5 dk sonra recycle — leak'i önler",
    )

    # ---- Redis -----------------------------------------------------------
    redis_url: str = Field(
        default="redis://localhost:6380/0",
        description="Redis connection string (broker + cache)",
    )
    redis_password: SecretStr = SecretStr("")

    # ---- MinIO (hot tier — VPS lokal volume) ----------------------------
    minio_endpoint: str = "localhost:9100"
    minio_root_user: str = "minio_admin"
    minio_root_password: SecretStr = SecretStr("change-me-minio")
    minio_bucket_images: str = "nodrat-images"
    minio_bucket_snapshots: str = "nodrat-snapshots"
    minio_bucket_backups: str = "nodrat-backups"
    minio_use_ssl: bool = False

    # ---- S3 cold tier (Contabo OS, #217 MVP-1.5) ------------------------
    s3_endpoint_url: str = "https://eu2.contabostorage.com"
    s3_region: str = "eu2"
    s3_bucket: str = "nodrat-prod"
    s3_access_key_id: str = ""
    s3_secret_access_key: SecretStr = SecretStr("")

    # ---- API secrets -----------------------------------------------------
    api_secret_key: SecretStr = SecretStr("change-me-32-byte-hex")
    jwt_secret: SecretStr = SecretStr("change-me-jwt-secret")
    jwt_access_expire_minutes: int = 15
    jwt_refresh_expire_days: int = 30
    fernet_key: SecretStr = SecretStr("")

    # ---- LLM Providers ---------------------------------------------------
    # DEPRECATED: DeepSeek V4 Flash NIM endpoint üzerinden çağrılıyor (#109).
    # Bu env'ler legacy — yeni adapter NIM_API_KEY kullanıyor.
    # Native DeepSeek API'si gerekiyorsa (Faz 6+ direkt billing) yeniden aktifleşir.
    deepseek_api_key: SecretStr = SecretStr("")
    deepseek_base_url: str = "https://api.deepseek.com"

    nim_api_key: SecretStr = SecretStr("")
    nim_base_url: str = "https://integrate.api.nvidia.com/v1"
    nim_chat_model: str = "deepseek-ai/deepseek-v3.1-terminus"
    """[DEPRECATED] NIM chat — #163 ile DeepSeek native API'ye geçildi.
    Geriye dönük backward compatibility için tutuluyor, PR-C cleanup'da kaldırılır.
    """

    # #758: Cross-encoder rerank tamamen kaldırıldı.
    # Eski settings: nim_rerank_base_url, nim_rerank_model, reranker_enabled,
    # reranker_candidate_pool, rerank_min_combined_score, rerank_min_query_words,
    # local_rerank_model, use_local_rerank — hepsi silindi.
    # LLM rerank bağımsız akışla rerank.py içinde çalışır (DeepSeek answer-aware).

    # Generic retrieval candidate pool — RRF top-N (rerank.candidate_pool yerine
    # geriye uyumlu admin setting retrieval.candidate_pool var, kod bunu okur).
    reranker_candidate_pool: int = 50
    """Hybrid retrieval RRF top-N candidate pool size. İsim 'reranker_*'
    backward-compat (eski cross-encoder kapsamı, yeni rerank yok ama
    candidate pool RRF için hala anlamlı)."""

    # DeepSeek native API (#163) — primary chat provider
    deepseek_api_key: SecretStr = SecretStr("")
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_chat_model: str = "deepseek-v4-flash"
    """DeepSeek primary chat model. Eski 'deepseek-chat' adı kullanımdan kalktı,
    bu modele redirect ediyor (#361). Alternatifler: deepseek-reasoner (R1)."""

    deepseek_campaign_discount: float = 0.25
    """2026-05-31 23:59 UTC'a kadar AKTİF kampanya: input/output -%75 indirim
    (multiplier 0.25). Kampanya bittiğinde 1.0'a çek."""

    # Google Gemini API (#778) — Gemma 4 modelleri (ücretsiz tier, 15 req/min)
    # Admin /settings'ten per-operation routing (NER/planner/rerank/generation).
    google_api_key: SecretStr = SecretStr("")
    google_gemini_default_model: str = "gemma-4-26b-a4b-it"
    """Gemma 4 26B A4B IT (MoE) — hızlı + ekonomik default. Alternatif:
    gemma-4-31b-it (256K context, daha kaliteli, daha yavaş)."""

    # Embedding (#420 — embedding tek provider: local BAAI/bge-m3, CPU on VPS).
    # Tarih: #163 ile local provider eklendi, #350 ile DB re-embed migration
    # tamamlandı (2026-05-06), #420 ile NIM fallback kaldırıldı.
    local_embedding_model: str = "BAAI/bge-m3"
    """sentence-transformers model id. Build-time preload (Dockerfile)."""

    # #758: local_rerank_model + use_local_rerank kaldırıldı (cross-encoder yok).

    openrouter_api_key: SecretStr = SecretStr("")
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    anthropic_api_key: SecretStr = SecretStr("")
    openai_api_key: SecretStr = SecretStr("")

    default_llm_provider: str = "deepseek"
    default_embedding_provider: str = "local_bge_m3"  # #420 — NIM kaldırıldı

    # Provider monthly cost cap (USD) — R-FIN-01 mitigation
    provider_monthly_cap_deepseek: float = 200.00
    provider_monthly_cap_anthropic: float = 300.00
    provider_monthly_cap_openrouter: float = 100.00

    # ---- Email (#68) ----------------------------------------------------
    resend_api_key: SecretStr = SecretStr("")
    mail_from: str = "hello@nodrat.com"
    mail_from_name: str = "Nodrat"

    # Sender role-based addresses (no personal names)
    resend_from_transactional: str = "no-reply@nodrat.com"
    """Email verify, password reset, quota warnings."""

    resend_from_hello: str = "hello@nodrat.com"
    """Welcome email + general onboarding."""

    resend_from_legal: str = "legal@nodrat.com"
    """Takedown / abuse / FSEK acknowledgments."""

    resend_from_dpo: str = "dpo@nodrat.com"
    """KVKK md.7 / md.11 acknowledgments."""

    resend_reply_to: str = "support@nodrat.com"
    """Reply-To header for transactional emails."""

    # Token TTL
    email_verify_token_ttl_hours: int = 24
    password_reset_token_ttl_hours: int = 1

    # ---- Lemon Squeezy MoR (#53, Epic #448) -----------------------------
    # Kullanıcı LS hesabı açtığında doldurulur. Boş kalırsa /app/billing/*
    # endpoint'leri 503 SERVICE_UNAVAILABLE döner ('billing_not_configured').
    lemonsqueezy_api_key: SecretStr = SecretStr("")
    """LS API token — https://app.lemonsqueezy.com → Settings → API."""

    lemonsqueezy_store_id: str = ""
    """LS Store ID (numeric). Variant'lar bu store altında tanımlı."""

    lemonsqueezy_signing_secret: SecretStr = SecretStr("")
    """Webhook HMAC SHA256 imza doğrulama secret'ı (LS dashboard → Webhooks)."""

    lemonsqueezy_base_url: str = "https://api.lemonsqueezy.com/v1"
    """LS API base URL — JSON:API spec."""

    lemonsqueezy_test_mode: bool = True
    """True ise checkout'lar test mode (gerçek charge yok)."""

    # Variant ID mapping — LS dashboard'da product/variant tanımlandıktan
    # sonra .env'de doldurulur. plans tablosu da seed'den sonra UPDATE ile
    # ya da /admin/plans UI üzerinden değer alabilir.
    # Her plan için monthly + yearly variant_id'si gerekir.
    ls_variant_starter_monthly: str = ""
    ls_variant_starter_yearly: str = ""
    ls_variant_pro_monthly: str = ""
    ls_variant_pro_yearly: str = ""
    ls_variant_agency_3_monthly: str = ""
    ls_variant_agency_3_yearly: str = ""
    ls_variant_agency_5_monthly: str = ""
    ls_variant_agency_5_yearly: str = ""
    ls_variant_agency_10_monthly: str = ""
    ls_variant_agency_10_yearly: str = ""

    # Customer Portal redirect URL (frontend tarafı)
    lemonsqueezy_customer_portal_url_template: str = (
        "https://app.lemonsqueezy.com/billing"
    )
    """LS Customer Portal kullanıcıya dönüş URL şablonu. checkout/portal-url
    endpoint'i bu URL'i döner. LS hesap aktive olduğunda gerçek tenant
    URL'i ile değiştirilir."""

    # ---- Frontend (CORS) ------------------------------------------------
    next_public_app_url: str = "http://localhost:3000"

    # ---- Domain / TLS ---------------------------------------------------
    domain: str = "nodrat.com"
    admin_email: str = "legal@nodrat.com"

    # ---- Monitoring -----------------------------------------------------
    sentry_dsn: str | None = None
    sentry_environment: str = "development"

    @property
    def is_production(self) -> bool:
        """Production environment kontrolü."""
        return self.environment == "production"

    @property
    def is_development(self) -> bool:
        """Development environment kontrolü."""
        return self.environment == "development"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings instance — uygulama başına bir kez yüklenir."""
    settings = Settings()

    # #138 — production'da NEXT_PUBLIC_APP_URL localhost ise email linkleri
    # tıklanamaz. Defensive warning (build/deploy'da gözden kaçmış olabilir).
    if settings.is_production and (
        "localhost" in settings.next_public_app_url
        or "127.0.0.1" in settings.next_public_app_url
    ):
        import logging

        logging.getLogger(__name__).error(
            "config.next_public_app_url.invalid",
            extra={
                "value": settings.next_public_app_url,
                "fix": "Set NEXT_PUBLIC_APP_URL=https://your-domain.com in .env",
            },
        )

    return settings
