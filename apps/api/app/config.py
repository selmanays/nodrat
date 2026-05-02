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

    # ---- Redis -----------------------------------------------------------
    redis_url: str = Field(
        default="redis://localhost:6380/0",
        description="Redis connection string (broker + cache)",
    )
    redis_password: SecretStr = SecretStr("")

    # ---- MinIO -----------------------------------------------------------
    minio_endpoint: str = "localhost:9100"
    minio_root_user: str = "minio_admin"
    minio_root_password: SecretStr = SecretStr("change-me-minio")
    minio_bucket_images: str = "nodrat-images"
    minio_bucket_snapshots: str = "nodrat-snapshots"
    minio_bucket_backups: str = "nodrat-backups"
    minio_use_ssl: bool = False

    # ---- API secrets -----------------------------------------------------
    api_secret_key: SecretStr = SecretStr("change-me-32-byte-hex")
    jwt_secret: SecretStr = SecretStr("change-me-jwt-secret")
    jwt_access_expire_minutes: int = 15
    jwt_refresh_expire_days: int = 30
    fernet_key: SecretStr = SecretStr("")

    # ---- LLM Providers ---------------------------------------------------
    # DEPRECATED: DeepSeek V3 NIM endpoint üzerinden çağrılıyor (#109).
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

    # NIM rerank (#181) — RAG retrieval ikinci aşaması
    nim_rerank_base_url: str = "https://ai.api.nvidia.com/v1"
    nim_rerank_model: str = "nvidia/rerank-qa-mistral-4b"

    reranker_enabled: bool = True
    """Toggle: True ise hybrid_search sonuçları cross-encoder ile yeniden
    sıralanır (top-50 → top-10). Acil rollback için False."""

    reranker_candidate_pool: int = 50
    """Reranker'a gönderilen aday sayısı (RRF top-50)."""

    rerank_min_combined_score: float = 0.15
    """#251/#253 — combined_score < bu eşik ise kart drop edilir (alakasız
    sonuç kullanıcıya sızmasın). Sıfır kart kalırsa app_generate
    insufficient_data döndürür. Tipik değerler:
      0.10 → çok permisif (logit≈-2.2 dahil)
      0.15 → varsayılan (orta-uzun sorgular dahil, logit≈-1.7)
      0.20 → orta sıkı (logit≈-1.4 cut)
      0.30 → agresif"""

    rerank_min_query_words: int = 3
    """#253 — Cross-encoder (NIM rerank-qa) kısa query'lerde başarısız:
    'CHP', 'İmamoğlu' gibi tek-term'leri hep negatif logit yapıyor →
    alakalı kartlar drop. Bu eşiğin altında kelime sayısı varsa rerank
    bypass edilir (RRF sırası korunur). Default 3 → 1-2 kelime bypass."""

    # DeepSeek native API (#163) — primary chat provider
    deepseek_api_key: SecretStr = SecretStr("")
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_chat_model: str = "deepseek-chat"
    """DeepSeek primary chat model. Alternatifler: deepseek-reasoner (R1)."""

    deepseek_campaign_discount: float = 0.25
    """31 May 2026 kampanyası: input/output -%75 indirim (multiplier 0.25).
    Kampanya bittiğinde 1.0'a çek."""

    # Local embedding (#163 — NIM bge-m3 yerine local sentence-transformers)
    local_embedding_model: str = "BAAI/bge-m3"
    """sentence-transformers model id. Build-time preload (Dockerfile)."""

    use_local_embedding: bool = True
    """True ise local bge-m3 primary (NIM yerine). False'a çekilirse NIM
    fallback (eğer NIM_API_KEY varsa)."""

    openrouter_api_key: SecretStr = SecretStr("")
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    anthropic_api_key: SecretStr = SecretStr("")
    openai_api_key: SecretStr = SecretStr("")

    default_llm_provider: str = "deepseek_v3"
    default_embedding_provider: str = "nim_bge_m3"

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
