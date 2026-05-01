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
from app.api import admin_queue, admin_sources, auth, health
from app.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan — startup/shutdown hooks.

    Startup:
        - Sentry init (production'da)
        - DB connection pool warmup (Faz 0+1)
        - Provider config load (Faz 2)

    Shutdown:
        - Cleanup connections
    """
    settings = get_settings()

    # Sentry init (production-only — placeholder)
    if settings.sentry_dsn and settings.is_production:
        # import sentry_sdk
        # sentry_sdk.init(dsn=settings.sentry_dsn, environment=settings.environment)
        pass

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
    app.include_router(admin_sources.router, prefix="/admin/sources", tags=["admin"])
    app.include_router(admin_queue.router, prefix="/admin/queue", tags=["admin"])

    # Faz 1+ eklenecek:
    # app.include_router(app_generate.router, prefix="/app", tags=["user"])
    # app.include_router(legal.router, prefix="/legal", tags=["legal"])

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
