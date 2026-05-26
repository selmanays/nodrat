"""Module: style_profiles

Domain: kullanıcı yazı tarzı (style profile) analizi (#52, Faz 5).

Pro+ tier paywall + slot quota (Pro=3, Agency=10). PII redaction sample
import sırasında uygulanır (KVKK).

Public API (T8-PRE-1 sonrası — submodule path):
    `app.modules.style_profiles.routes.router`            — public router (/app/style-profiles)
    `app.modules.style_profiles.tasks.analyze_style_profile` — Celery task (string-bound)

See:
    docs/engineering/api-contracts.md §12.1-12.3
    docs/engineering/modular-monolith-architecture.md §3.2
    wiki/plans/modular-monolith-transition-master-plan.md §2.2
    wiki/topics/t8-model-relocation-mini-plan.md §3 hard-stop 11 (lazy `__init__.py`)
"""

# T8-PRE-1 (v68): route eager re-export kaldırıldı (collect-time circular
# import koruması).

__all__: list[str] = []
