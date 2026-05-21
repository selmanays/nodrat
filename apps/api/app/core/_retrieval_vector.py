"""Internal retrieval vector serialization helpers (T6 #1085 P5 PR-B internal split).

Pure data transforms for pgvector text format. Daha önce `app.core.retrieval`
(line 342 + line 558) içinde inline'dı; pure refactor — davranış değişikliği YOK.
Public consumer: `app.core.retrieval` (re-export).

Modül-dışı doğrudan import edilmez — stable API DEĞİL.

Refs:
- PR #1148 — retrieval characterization tests (regression safety-net)
- core/retrieval.py — public surface bu helper'ları kullanır
- #398 pgvector embedding storage format
"""

from __future__ import annotations


def _parse_pgvector_text(s: str | None) -> list[float] | None:
    """pgvector '[0.1,0.2,...]' text temsilini list[float]'a çevirir (#398).

    Aynı pattern raptor.py'de _parse_vector olarak kullanılıyor; burada
    retrieval.py'a yerel kopya — module bağımlılığı eklememek için.
    None / parse fail → None (caller embed_fn fallback eder).
    """
    if not s:
        return None
    try:
        inner = s.strip("[] \n")
        out = [float(x) for x in inner.split(",") if x.strip()]
        # 1024-dim olmayanları reddet (uyumsuz vektör)
        if len(out) != 1024:
            return None
        return out
    except (ValueError, AttributeError):
        return None


def _vector_to_pg_literal(vector: list[float]) -> str:
    """pgvector literal: '[0.1,0.2,...]'"""
    return "[" + ",".join(f"{v:.7f}" for v in vector) + "]"
