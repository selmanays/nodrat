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

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.api import (
    admin_clusters,  # #1017 Pivot — research_cluster + message_cluster gözlemi (Phase 6'da generations'a taşınacak)
    admin_rag,
    app_me,
    app_research,
    app_research_stream,
)
from app.config import get_settings

# T8-PRE-1 (v68): paket yerine doğrudan submodule path'den router import.
# Paket `__init__.py`'leri artık `from .routes import router` yapmıyor (collect-time
# circular import koruması — bkz. wiki/topics/t8-model-relocation-mini-plan.md §3
# hard-stop 11).
from app.modules.accounts.admin.routes import router as admin_users_router
from app.modules.accounts.auth.routes import router as auth_router
from app.modules.accounts.auth.two_factor import router as auth_2fa_router
from app.modules.accounts.consent.routes import router as app_consent_router
from app.modules.articles.admin.routes import router as articles_router
from app.modules.billing.admin.routes import router as admin_billing_router
from app.modules.billing.routes import router as billing_router
from app.modules.billing.webhooks import router as billing_webhooks_router
from app.modules.legal.routes import admin_router as legal_admin_router
from app.modules.legal.routes import router as legal_router
from app.modules.media.admin.routes import router as media_admin_router
from app.modules.ops.admin.audit import router as admin_audit_router
from app.modules.ops.admin.dashboard import router as admin_dashboard_router
from app.modules.ops.admin.queue import router as admin_queue_router
from app.modules.ops.admin.system import router as admin_system_router
from app.modules.prompts_admin.routes import router as prompts_admin_router
from app.modules.public.health import router as public_health_router
from app.modules.public.search import router as public_search_router
from app.modules.settings_admin.routes import router as settings_admin_router
from app.modules.sft.admin.routes import router as sft_admin_router
from app.modules.sources.admin.routes import router as sources_router
from app.modules.style_profiles.routes import router as style_profiles_router


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

        from app.shared.runtime_config.prompts_store import prompts_store
        from app.shared.runtime_config.settings_store import settings_store

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

    # #684 PR-A — Model warm-up (cold start fix)
    # Lazy load yerine startup'ta sentence-transformers model RAM'e yüklensin.
    # İlk embedding/rerank call ~2-3sn → ~50ms. UI TTFT için kritik.
    # #696 (B6) — Duration metrik admin /rag/health UI'da gösterilir.
    import time as _time
    from datetime import datetime as _dt

    from app.shared.observability import warmup_state  # module-level metric store

    try:
        import logging as _logging

        from app.providers.registry import registry

        warmup_state.STARTED_AT = _dt.now(UTC)
        _wm_t0 = _time.perf_counter()

        # Embedding model (bge-m3 veya e5) warm
        try:
            _t = _time.perf_counter()
            emb_provider = registry.route_for_tier(operation="embedding", tier="free")
            await emb_provider.create_embedding(["warmup"])
            warmup_state.EMBEDDING_MS = (_time.perf_counter() - _t) * 1000.0
            _logging.getLogger(__name__).info(
                "embedding model warmed in %.0fms",
                warmup_state.EMBEDDING_MS,
            )
        except Exception as exc:
            _logging.getLogger(__name__).warning("embedding warmup skip: %s", exc)

        # Rerank model warm
        try:
            _t = _time.perf_counter()
            rerank_provider = registry.route_for_tier(operation="rerank", tier="free")
            await rerank_provider.rerank(
                query="warmup",
                documents=["warmup passage"],
                top_k=1,
            )
            warmup_state.RERANK_MS = (_time.perf_counter() - _t) * 1000.0
            _logging.getLogger(__name__).info(
                "rerank model warmed in %.0fms",
                warmup_state.RERANK_MS,
            )
        except Exception as exc:
            _logging.getLogger(__name__).warning("rerank warmup skip: %s", exc)

        warmup_state.DURATION_MS = (_time.perf_counter() - _wm_t0) * 1000.0
        warmup_state.COMPLETED_AT = _dt.now(UTC)
        warmup_state.OK = True
    except Exception as exc:  # pragma: no cover
        import logging as _logging

        _logging.getLogger(__name__).warning("model warmup failed: %s", exc)
        warmup_state.OK = False

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
    app.include_router(public_health_router, tags=["operations"])
    app.include_router(auth_router, prefix="/auth", tags=["auth"])
    # #56 — 2FA TOTP endpoints (admin için zorunlu, paid launch öncesi)
    app.include_router(auth_2fa_router, prefix="/auth/2fa", tags=["auth", "2fa"])
    app.include_router(sources_router, prefix="/admin/sources", tags=["admin"])
    app.include_router(articles_router, prefix="/admin/articles", tags=["admin"])
    app.include_router(admin_dashboard_router, prefix="/admin/dashboard", tags=["admin"])
    app.include_router(admin_queue_router, prefix="/admin/queue", tags=["admin"])
    app.include_router(admin_users_router, prefix="/admin/users", tags=["admin"])
    app.include_router(admin_audit_router, prefix="/admin/audit", tags=["admin"])
    # #1017 Pivot Faz 3c — araştırma kümesi gözlem (salt-okuma; admin UI=ayrı seans)
    app.include_router(admin_clusters.router, prefix="/admin/clusters", tags=["admin"])
    # #358 MVP-1.6 B1 — sistem durum (observability) endpoint
    # Note: admin_system.router has prefix="/admin/system" baked in
    app.include_router(admin_system_router, tags=["admin"])
    app.include_router(admin_rag.router, prefix="/admin/rag", tags=["admin"])
    app.include_router(settings_admin_router, prefix="/admin/settings", tags=["admin"])
    app.include_router(sft_admin_router, prefix="/admin/sft", tags=["admin", "sft"])
    app.include_router(prompts_admin_router, prefix="/admin/prompts", tags=["admin"])
    # #304 MVP-1.4 PR-4 — image media (NIM VLM process & discard)
    app.include_router(media_admin_router, prefix="/admin/media", tags=["admin", "media"])
    # #800 S1A — Legacy form generation endpoints kaldırıldı (app_generate +
    # app_generate_stream dosyaları silindi). Tek erişim noktası /research/*.
    # #793 S1 — Conversation mode (Perplexity-style research UX)
    app.include_router(app_research.router, prefix="/research", tags=["user", "research"])
    # #793 S2 — Research streaming (context-aware retrieval + thinking events)
    app.include_router(
        app_research_stream.router, prefix="/research", tags=["user", "research", "streaming"]
    )
    app.include_router(app_me.router, prefix="/app/me", tags=["user"])
    # #470 MVP-3 — KVKK m.9 yurt dışı transfer açık rıza (server-side enforced)
    app.include_router(app_consent_router, prefix="/app/consent", tags=["user", "legal"])
    # #53 MVP-3 — Lemon Squeezy MoR billing (Epic #448)
    app.include_router(billing_router, prefix="/app/billing", tags=["user", "billing"])
    # #77 MVP-3 — Admin plan + LS variant_id yönetimi
    app.include_router(admin_billing_router, prefix="/admin/plans", tags=["admin", "billing"])
    # #52 Faz 5 — Stil profili (Pro+ tier paywall, server-side enforced)
    app.include_router(style_profiles_router, prefix="/app/style-profiles", tags=["user", "style"])
    # #450 MVP-3 — LS webhook handler (signature verify + 7 event tipi idempotent)
    app.include_router(billing_webhooks_router, prefix="/api/webhooks", tags=["webhooks"])
    # #261 Phase A — public anonim search (rate limited, no auth)
    app.include_router(public_search_router, prefix="/public", tags=["public"])
    # Legal — public takedown forms + admin moderation
    app.include_router(legal_router, prefix="/legal", tags=["legal"])
    app.include_router(legal_admin_router, prefix="/admin/legal/requests", tags=["admin", "legal"])

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
