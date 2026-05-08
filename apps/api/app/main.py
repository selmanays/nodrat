"""FastAPI application entry point.

Bu dosya FastAPI uygulamasını ve middleware zincirini kurar.

Routing yapısı (docs/engineering/api-contracts.md §0):
    /public/*    — Auth gerektirmeyen, rate limit'li
    /auth/*      — Login, register, password reset, 2FA
    /app/*       — Kullanıcı (registered, JWT)
    /admin/*     — Super admin (JWT + role + 2FA)
    /internal/*  — Sadece worker'lar (mTLS / token)
    /webhooks/*  — Provider callback'leri
    /legal/*     — Takedown / abuse / privacy-request
    /health, /readiness — operasyon
"""

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.api import (
    admin_articles,
    admin_audit,
    admin_billing,
    admin_dashboard,
    admin_media,
    admin_prompts,
    admin_queue,
    admin_rag,
    admin_settings,
    admin_sources,
    admin_system,
    admin_users,
    app_consent,
    app_generate,
    app_me,
    auth,
    auth_2fa,
    billing,
    health,
    legal,
    public_search,
    webhooks_lemonsqueezy,
)
from app.config import get_settings


def _init_sentry() -> None:
    """Sentry SDK init — production-only (#42).

    DSN env'den okunur (config.py:sentry_dsn). traces_sample_rate=0.1
    production için varsayılan; release ve environment alanları otomatik
    set edilir.
    """
    settings = get_settings()
    dsn = (settings.sentry_dsn or "").strip()
    if not dsn or not dsn.startswith(("http://", "https://")) or not settings.is_production:
        return

    import sentry_sdk
    from sentry_sdk.integrations.asyncio import AsyncioIntegration
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.starlette import StarletteIntegration

    try:
        sentry_sdk.init(
            dsn=dsn,
            environment=settings.environment,
            release=f"nodrat-api@{__version__}",
            traces_sample_rate=0.1,
            profiles_sample_rate=0.1,
            send_default_pii=False,  # KVKK — PII Sentry'ye gitmez
            integrations=[
                FastApiIntegration(transaction_style="endpoint"),
                StarletteIntegration(transaction_style="endpoint"),
                AsyncioIntegration(),
            ],
        )
    except Exception:  # pragma: no cover — Sentry init never crashes app startup
        import logging
        logging.getLogger(__name__).warning("Sentry init skipped (invalid DSN)")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan — startup/shutdown hooks.

    Startup:
        - Sentry init (production'da)  (#42)
        - DB connection pool warmup (Faz 0+1)
        - Provider config load (Faz 2)

    Shutdown:
        - Cleanup connections
    """
    _init_sentry()

    # #264 — SettingsStore Redis pub/sub listener (cache invalidation)
    try:
        import logging as _logging

        from app.core.prompts_store import prompts_store
        from app.core.settings_store import settings_store

        await settings_store.start_listener()
        await prompts_store.start_listener()
    except Exception as exc:  # pragma: no cover
        _logging.getLogger(__name__).warning(
            "settings/prompts store listener start failed: %s", exc
        )

    # #273 — Provider registry async bootstrap (DB-backed HTTP timeouts)
    try:
        import logging as _logging

        from app.core.db import get_db
        from app.providers.registry import bootstrap_default_providers_async

        async for _db in get_db():
            await bootstrap_default_providers_async(_db)
            break
    except Exception as exc:  # pragma: no cover
        _logging.getLogger(__name__).warning(
            "provider registry async bootstrap failed: %s — fallback to lazy "
            "sync bootstrap with default timeouts",
            exc,
        )
        # Fallback ok: lazy bootstrap_default_providers() endpoint çağrılarında
        # devreye girer (env/class default timeout'larla).

    yield

    # Cleanup hooks gelecekte buraya


def create_app() -> FastAPI:
    """Application factory pattern — testability için."""
    settings = get_settings()

    app = FastAPI(
        title="Nodrat API",
        description="Türkçe gündem RAG SaaS — kaynaklı X içerik üretim aracı",
        version=__version__,
        # Production'da /docs ve /redoc disabled
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        openapi_url="/openapi.json" if not settings.is_production else None,
        lifespan=lifespan,
    )

    # ---- Middleware ------------------------------------------------------
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.next_public_app_url],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    # ---- Routers ---------------------------------------------------------
    app.include_router(health.router, tags=["operations"])
    app.include_router(auth.router, prefix="/auth", tags=["auth"])
    # #56 — 2FA TOTP endpoints (admin için zorunlu, paid launch öncesi)
    app.include_router(auth_2fa.router, prefix="/auth/2fa", tags=["auth", "2fa"])
    app.include_router(admin_sources.router, prefix="/admin/sources", tags=["admin"])
    app.include_router(admin_articles.router, prefix="/admin/articles", tags=["admin"])
    app.include_router(admin_dashboard.router, prefix="/admin/dashboard", tags=["admin"])
    app.include_router(admin_queue.router, prefix="/admin/queue", tags=["admin"])
    app.include_router(admin_users.router, prefix="/admin/users", tags=["admin"])
    app.include_router(admin_audit.router, prefix="/admin/audit", tags=["admin"])
    # #358 MVP-1.6 B1 — sistem durum (observability) endpoint
    # Note: admin_system.router has prefix="/admin/system" baked in
    app.include_router(admin_system.router, tags=["admin"])
    app.include_router(admin_rag.router, prefix="/admin/rag", tags=["admin"])
    app.include_router(admin_settings.router, prefix="/admin/settings", tags=["admin"])
    app.include_router(admin_prompts.router, prefix="/admin/prompts", tags=["admin"])
    # #304 MVP-1.4 PR-4 — image media (NIM VLM process & discard)
    app.include_router(admin_media.router, prefix="/admin/media", tags=["admin", "media"])
    app.include_router(app_generate.router, prefix="/app", tags=["user"])
    app.include_router(app_me.router, prefix="/app/me", tags=["user"])
    # #470 MVP-3 — KVKK m.9 yurt dışı transfer açık rıza (server-side enforced)
    app.include_router(app_consent.router, prefix="/app/consent", tags=["user", "legal"])
    # #53 MVP-3 — Lemon Squeezy MoR billing (Epic #448)
    app.include_router(billing.router, prefix="/app/billing", tags=["user", "billing"])
    # #77 MVP-3 — Admin plan + LS variant_id yönetimi
    app.include_router(admin_billing.router, prefix="/admin/plans", tags=["admin", "billing"])
    # #450 MVP-3 — LS webhook handler (signature verify + 7 event tipi idempotent)
    app.include_router(
        webhooks_lemonsqueezy.router, prefix="/api/webhooks", tags=["webhooks"]
    )
    # #261 Phase A — public anonim search (rate limited, no auth)
    app.include_router(public_search.router, prefix="/public", tags=["public"])
    # Legal — public takedown forms + admin moderation
    app.include_router(legal.router, prefix="/legal", tags=["legal"])
    app.include_router(
        legal.admin_router, prefix="/admin/legal/requests", tags=["admin", "legal"]
    )

    return app


app = create_app()


@app.exception_handler(Exception)
async def global_exception_handler(request, exc: Exception) -> JSONResponse:  # type: ignore[no-untyped-def]
    """Production'da stack trace user'a gitmez (security)."""
    settings = get_settings()
    if settings.is_production:
        return JSONResponse(
            status_code=500,
            content={
                "type": "https://nodrat.com/errors/internal",
                "title": "Internal Server Error",
                "status": 500,
                "code": "INTERNAL_ERROR",
                "detail": "Beklenmeyen bir hata oluştu. Tekrar deneyin.",
            },
        )
    # Development: re-raise for debugger
    raise exc
