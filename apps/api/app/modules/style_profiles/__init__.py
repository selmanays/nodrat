"""Module: style_profiles

Domain: kullanıcı yazı tarzı (style profile) analizi (#52, Faz 5).

Pro+ tier paywall + slot quota (Pro=3, Agency=10). PII redaction sample
import sırasında uygulanır (KVKK).

Public API:
    router          — FastAPI router (URL prefix `/app/style-profiles`)
    analyze_style_profile  — Celery task (name `tasks.style_profile.analyze`)

See:
    docs/engineering/api-contracts.md §12.1-12.3
    docs/engineering/modular-monolith-architecture.md §3.2
    wiki/plans/modular-monolith-transition-master-plan.md §2.2
"""

from app.modules.style_profiles.routes import router

__all__ = ["router"]
