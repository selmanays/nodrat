"""Module: agenda

Domain: agenda card generation domain. Event cluster-based daily agenda card
production pipeline (#21). Vector(1024) embeddings for semantic similarity
to research questions.

**Scope:** Standalone module for AgendaCard ORM + (future) agenda generation
admin surface. Per kullanıcı locked decision (2026-05-26 v67) `agenda` is a
SEPARATE module from `generations/` even though Phase 6 mini-cycle initially
hosted agenda tasks there. Agenda Celery tasks (`tasks.agenda.*`) currently
live in `modules/generations/tasks/agenda.py` and consume this module's
AgendaCard ORM via `from app.modules.agenda.models import AgendaCard` (T8-10
caller flip).

**Layer:** middle (Phase 1/§2.4 — depends on shared models; consumed by
generations upper layer).

**B-group:** This package is NOT in `_MODULES_REQUIRING_LAZY_INIT` (test
isolation purge list — A-group of 8 modules). T8-6 LAZY+_purge_cached_modules
incompatibility ders does NOT apply. Standard B-group lazy `__init__.py`
discipline (docstring + `__all__: list[str] = []`).

Public API:
    None yet (models-only module; admin/tasks/routes added in future phases)

See:
    wiki/plans/modular-monolith-transition-master-plan.md §2.4
    wiki/topics/t8-model-relocation-mini-plan.md (T8-10 / Wave D scope)
"""

__all__: list[str] = []
