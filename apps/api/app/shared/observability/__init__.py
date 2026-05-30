"""Shared infrastructure: observability

Pure telemetry/metric primitives — Layer 0 saflık, app.core/api/models bağımsız.

Public modules:
    ner_stats   — NER pipeline mode dağılım counter (process-local Counter+Lock;
                  consumer: app.core.retrieval.resolve_target_ner + app.modules.rag.admin
                  /admin/rag/ner-stats). Phase 8 PR-8a-3 — app.modules.entities'den
                  taşındı (core→modules wrong-direction leak fix).
"""

from app.shared.observability import ner_stats

__all__ = ["ner_stats"]
