"""Unit tests for binary quantization scaffold (#221 MVP-1.5 PR-6).

DB integration ayrı (live pgvector + binary_quantize gerek).
Burada saf Python helpers + import surface + settings + task export.
"""

from __future__ import annotations


def test_vector_to_pg_literal_basic():
    from app.core.embedding_binary import vector_to_pg_literal

    assert vector_to_pg_literal([0.1, 0.2, -0.3]) == "[0.1000000,0.2000000,-0.3000000]"


def test_vector_to_pg_literal_empty():
    from app.core.embedding_binary import vector_to_pg_literal

    assert vector_to_pg_literal([]) == "[]"


def test_vector_to_pg_literal_precision():
    from app.core.embedding_binary import vector_to_pg_literal

    result = vector_to_pg_literal([1 / 3])
    # 7 hane precision (mevcut retrieval.py ile tutarlı)
    assert "0.3333333" in result


def test_quantize_chunk_batch_exported():
    """async helper import edilebilir (DB lazy)."""
    from app.core.embedding_binary import quantize_chunk_batch

    assert callable(quantize_chunk_batch)


def test_search_chunks_binary_exported():
    """search routing'in opt-in için kullanacağı helper."""
    from app.core.embedding_binary import search_chunks_binary

    assert callable(search_chunks_binary)


def test_quantize_chunks_celery_task_exported():
    """maintenance.quantize_chunks task export."""
    from app.workers.tasks.maintenance import quantize_chunks

    assert quantize_chunks.name == "tasks.maintenance.quantize_chunks"


def test_vector_quantization_settings_present():
    """vector_quantization.enabled + backfill_batch admin settings'te var."""
    from app.api.admin_settings import SETTING_REGISTRY

    assert "vector_quantization.enabled" in SETTING_REGISTRY
    entry = SETTING_REGISTRY["vector_quantization.enabled"]
    assert entry["default"] is False, "Eval gate öncesi default False olmalı"
    assert entry["type"] == "bool"
    assert entry["group"] == "storage"

    assert "vector_quantization.backfill_batch" in SETTING_REGISTRY
    bf = SETTING_REGISTRY["vector_quantization.backfill_batch"]
    assert bf["type"] == "int"
    assert bf["default"] == 500


def test_migration_revision_chain():
    """Migration zinciri: 20260506_1830 → 20260506_1500 (cold tier)."""
    import importlib.util
    from pathlib import Path

    mig_path = (
        Path(__file__).parent.parent.parent
        / "alembic"
        / "versions"
        / "20260506_1830_chunk_embedding_binary.py"
    )
    assert mig_path.exists(), "Migration dosyası eksik"

    spec = importlib.util.spec_from_file_location("mig", mig_path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    assert mod.revision == "20260506_1830"
    assert mod.down_revision == "20260506_1500"


def test_embedding_worker_writes_binary():
    """embedding.py UPDATE'inde embedding_binary = binary_quantize(...)
    yer almalı (yeni chunk INSERT'leri otomatik dual-write)."""
    import inspect

    from app.workers.tasks import embedding as emb_mod

    source = inspect.getsource(emb_mod._embed_chunks_async)
    assert "embedding_binary = binary_quantize" in source, (
        "Worker INSERT'te binary dual-write eksik (#221)"
    )
