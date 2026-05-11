"""#696 (B6) — Module-level warm-up state.

PR-A #685 model warm-up (cold start fix) metrik kayıt. Lifespan startup'ta
embedding + rerank modelleri RAM'e yüklenirken süre ölçülür; admin
/rag/health endpoint'i bu değerleri okur.

Process-local; container restart'ta sıfırlanır.
"""
from __future__ import annotations

from datetime import datetime

STARTED_AT: datetime | None = None
COMPLETED_AT: datetime | None = None
DURATION_MS: float | None = None
EMBEDDING_MS: float | None = None
RERANK_MS: float | None = None
OK: bool = False
