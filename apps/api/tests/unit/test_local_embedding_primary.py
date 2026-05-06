"""Local bge-m3 primary provider tests (#223 MVP-1.5 PR-8).

DB / model integration testleri E2E framework'te (sentence-transformers
import gerek). Burada source inspection + settings + Dockerfile.
"""

from __future__ import annotations


def test_use_local_embedding_default_false_until_migration():
    """config.py default False — NIM ↔ local embeddings orthogonal (cosine≈0).

    Migration task chunks + agenda_cards re-embed yapana kadar flag False
    kalır (ayrı issue). Bu PR sadece sentence-transformers + Dockerfile
    preload + scaffold sağlar.
    """
    from app.config import Settings

    s = Settings()
    assert s.use_local_embedding is False, (
        "Migration öncesi default False olmalı; True yapmak retrieval'ı kırar"
    )


def test_local_embedding_model_default():
    """bge-m3 default model id."""
    from app.config import Settings

    s = Settings()
    assert s.local_embedding_model == "BAAI/bge-m3"


def test_local_provider_distinct_name():
    """name='local_bge_m3' — NIM'den ayrı, dashboard'da şeffaf gözlem.

    #345 MVP-1.5 sonrası: PR-8 backward-compat trick (aynı name) kaldırıldı;
    eski log'lar 'nim_bge_m3' olarak kalır (NIM'di), yeni log'lar
    'local_bge_m3'. Grafik ayrı sütun.
    """
    from app.providers.local_embedding import LocalBgeM3Provider

    assert LocalBgeM3Provider.name == "local_bge_m3"


def test_local_provider_dim_1024():
    """bge-m3 → 1024-dim (pgvector schema değişmez)."""
    from app.providers.local_embedding import LOCAL_EMBEDDING_DIM

    assert LOCAL_EMBEDDING_DIM == 1024


def test_routing_embedding_local_primary():
    """Registry route_for_tier embedding: local primary, NIM yedek (#345)."""
    import inspect

    from app.providers import registry as reg_mod

    source = inspect.getsource(reg_mod.ProviderRegistry.route_for_tier)
    # _fallback sırası önemli: ilk argüman primary
    assert '_fallback("local_bge_m3", "nim_bge_m3")' in source, (
        "Embedding routing local primary, NIM yedek sırası bozuk"
    )


def test_bootstrap_registers_local_when_enabled():
    """bootstrap_default_providers — use_local_embedding=True ise local kaydeder."""
    import inspect

    from app.providers import registry as reg_mod

    source = inspect.getsource(reg_mod.bootstrap_default_providers)
    # Build → register pattern
    assert "build_local_provider" in source
    assert "registry.register(local_emb)" in source


def test_dockerfile_installs_sentence_transformers():
    """Dockerfile builder'da sentence-transformers + torch yüklemeli."""
    from pathlib import Path

    df = (
        Path(__file__).parent.parent.parent / "Dockerfile"
    ).read_text()
    # PyTorch CPU wheel index'i + base pip install
    assert "download.pytorch.org/whl/cpu" in df
    # bge-m3 build-time preload (image hazır geliyor)
    assert "BAAI/bge-m3" in df
    assert "SentenceTransformer" in df


def test_pyproject_lists_sentence_transformers():
    """pyproject.toml dependencies'inde sentence-transformers olmalı."""
    from pathlib import Path

    pyp = (
        Path(__file__).parent.parent.parent / "pyproject.toml"
    ).read_text()
    # Yorumlu olmamalı (aktif olarak yüklenmesi lazım)
    active_lines = [
        line.strip()
        for line in pyp.splitlines()
        if "sentence-transformers" in line and not line.strip().startswith("#")
    ]
    assert active_lines, "sentence-transformers aktif dependencies'te değil"
