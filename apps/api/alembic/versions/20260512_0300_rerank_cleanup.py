"""Cross-encoder rerank kalıntı temizliği (#758).

#750 eval ile cross-encoder rerank (local_bge_reranker + nim_rerank) kalıcı
disabled kararlaştırıldı. Provider modülleri silindi (#758). Bu migration:

  1. provider_call_logs: rows where provider IN ('local_bge_reranker',
     'nim_rerank') — silinir (~1722 row, audit log temizliği).
  2. app_settings: silinen setting key'lerin override rows'ları —
     rerank.enabled, rerank.candidate_pool, rerank.min_combined_score,
     rerank.min_query_words, llm.nim_rerank_model, llm.nim_rerank_timeout,
     llm.use_local_rerank.

Geri alınma: rows back-fill imkansız (silindi). Tarihsel audit için
provider_call_logs.created_at filtreleri bu rows'ları zaten görmez.
"""

from __future__ import annotations

from alembic import op

# revision identifiers
revision = "20260512_0300"
down_revision = "20260512_0200"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. provider_call_logs cleanup
    op.execute(
        "DELETE FROM provider_call_logs WHERE provider IN ('local_bge_reranker', 'nim_rerank')"
    )

    # 2. app_settings override cleanup (rerank.*)
    op.execute(
        "DELETE FROM app_settings "
        "WHERE key IN ("
        "  'rerank.enabled',"
        "  'rerank.candidate_pool',"
        "  'rerank.min_combined_score',"
        "  'rerank.min_query_words',"
        "  'llm.nim_rerank_model',"
        "  'llm.nim_rerank_timeout',"
        "  'llm.use_local_rerank'"
        ")"
    )

    # 3. app_prompt_history aynı pattern (eğer rerank prompt'u yoksa no-op)
    # NOT: LLM rerank prompt'u prompt registry'de yok (inline rerank.py:_llm_rerank_answer_aware).


def downgrade() -> None:
    # Silinen rows back-fill edilemez. Cleanup geri alımı yok.
    pass
