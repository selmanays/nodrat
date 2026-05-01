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
    deepseek_api_key: SecretStr = SecretStr("")
    deepseek_base_url: str = "https://api.deepseek.com"

    nim_api_key: SecretStr = SecretStr("")
    nim_base_url: str = "https://integrate.api.nvidia.com/v1"

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

    # ---- Email -----------------------------------------------------------
    resend_api_key: SecretStr = SecretStr("")
    mail_from: str = "hello@nodrat.com"
    mail_from_name: str = "Nodrat"

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
    return Settings()
