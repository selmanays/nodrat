"""Local bge-reranker provider tests (#224 MVP-1.5 PR-9).

DB / model integration testleri E2E (CrossEncoder import gerek). Burada
source inspection + settings + Dockerfile.
"""

from __future__ import annotations


def test_use_local_rerank_default_false():
    """Default False — eval gate (NDCG@10 ≥ 0.90) öncesi NIM kalır."""
    from app.config import Settings

    s = Settings()
    assert s.use_local_rerank is False


def test_local_rerank_model_default():
    from app.config import Settings

    s = Settings()
    assert s.local_rerank_model == "BAAI/bge-reranker-v2-m3"


def test_local_rerank_provider_name_backward_compat():
    """name='nim_rerank' — NIM ile aynı (provider_call_logs uyumu)."""
    from app.providers.local_rerank import LocalBgeRerankerProvider

    assert LocalBgeRerankerProvider.name == "nim_rerank"


def test_local_rerank_supports_rerank_only():
    """Rerank-only provider (chat/embed/vision False)."""
    from app.providers.local_rerank import LocalBgeRerankerProvider

    p = LocalBgeRerankerProvider()
    assert p.supports_rerank is True
    assert p.supports_chat is False
    assert p.supports_embeddings is False
    assert p.supports_vision is False


def test_local_rerank_zero_cost():
    from app.providers.local_rerank import LocalBgeRerankerProvider

    assert LocalBgeRerankerProvider.cost_per_1m_input_tokens == 0.0
    assert LocalBgeRerankerProvider.cost_per_1m_output_tokens == 0.0


def test_build_local_rerank_factory_disabled_returns_none():
    """USE_LOCAL_RERANK=false ise build_local_rerank_provider None döner."""
    import os
    from unittest.mock import patch

    from app.providers.local_rerank import build_local_rerank_provider

    with patch.dict(os.environ, {"USE_LOCAL_RERANK": "false"}):
        # Settings cache'lenebilir → import sırası önemli
        from app.config import get_settings
        get_settings.cache_clear()
        result = build_local_rerank_provider()
        assert result is None


def test_registry_routes_rerank_local_first_when_enabled():
    """bootstrap_default_providers — local rerank kayıtlı ise NIM register etme."""
    import inspect

    from app.providers import registry as reg_mod

    source = inspect.getsource(reg_mod.bootstrap_default_providers)
    # Önce local rerank deniyor (build_local_rerank_provider), yoksa NIM
    assert "build_local_rerank_provider" in source
    # NIM rerank else branch'inde
    assert "NimRerankProvider" in source


def test_dockerfile_preloads_bge_reranker():
    """Dockerfile builder bge-reranker-v2-m3 preload eder."""
    from pathlib import Path

    df = (
        Path(__file__).parent.parent.parent / "Dockerfile"
    ).read_text()
    assert "BAAI/bge-reranker-v2-m3" in df
    assert "CrossEncoder" in df
