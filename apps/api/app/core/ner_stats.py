"""#696 (B5) — NER mode telemetri (in-memory, process-lifetime).

PR #693 #691 Faz 6.1 IDF + multi-entity AND scoring overhaul sonrası
production'da hangi mode kaç kez tetiklendi? Persistent storage olmadan
hızlı feedback için module-level counter.

Mode'lar:
  - multi_and: 2+ rare entity (df<NER_DF_THRESHOLD) intersect → K=20 boost
  - multi_and_common: common entity AND intersect dar (<threshold) → K=20
  - single_rare: tek rare entity → K=30 (Faz 6 eski seviye)
  - no_match: hiçbiri → boost yok (sinyal güvensiz)

Process restart'ta sıfırlanır. Container birden fazla worker varsa
worker-local (uvicorn --workers > 1 production'da bu agregat değil).
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from threading import Lock

_lock = Lock()
_counter: Counter[str] = Counter()
_first_seen: datetime | None = None
_last_seen: datetime | None = None
_total: int = 0


def record(mode: str) -> None:
    """Bir NER sorgu mode'u kaydet (retrieval.py _ner_idf_match_aids sonrasında)."""
    global _first_seen, _last_seen, _total
    with _lock:
        _counter[mode] += 1
        _total += 1
        now = datetime.now(UTC)
        if _first_seen is None:
            _first_seen = now
        _last_seen = now


def snapshot() -> dict:
    """Current state (admin endpoint için)."""
    with _lock:
        total = max(_total, 1)
        dist = dict(_counter.items())
        ratios = {m: round(c / total, 4) for m, c in _counter.items()}
        return {
            "total": _total,
            "distribution": dist,
            "ratios": ratios,
            "first_seen": _first_seen,
            "last_seen": _last_seen,
        }
