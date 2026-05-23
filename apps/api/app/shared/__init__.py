"""Shared infrastructure + pure parsing primitive libraries — see
wiki/plans/modular-monolith-transition-master-plan.md §2.3 and
wiki/decisions/modular-monolith-boundary.md §"Karar notu (2026-05-23):
Extraction primitives → shared/extraction/".

Layer 0 (alt — leaf). All higher layers (kernel/middle/üst/paralel) may
import `app.shared.*`; nothing in `app.shared.*` may import `app.modules.*`
(import-linter contract 1).

Sub-packages:
- Infrastructure: db, providers, prompts, util, http, storage, email,
  observability, runtime_config, workers.
- Pure parsing libraries: extraction (P4 PR-D, 2026-05-23).
"""
