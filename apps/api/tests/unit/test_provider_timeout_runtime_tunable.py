"""#273 MVP-2 — Provider HTTP timeout runtime tunable testleri.

Async bootstrap (`bootstrap_default_providers_async`) settings_store'dan
timeout okuyup factory'lere geçirir. Bu testler:
  - admin_settings.SETTING_REGISTRY'de 5 timeout key var mı
  - Factory'ler timeout parametresi alıyor mu (backward compat)
  - Async bootstrap settings_store.get_float çağrılıyor mu (source inspect)
"""

from __future__ import annotations

import inspect


def test_setting_registry_has_provider_timeouts():
    """admin_settings.SETTING_REGISTRY'de 5 provider timeout setting kayıtlı."""
    from app.api.admin_settings import SETTING_REGISTRY

    expected_keys = [
        "llm.deepseek_timeout",
        "llm.nim_chat_timeout",
        "llm.nim_rerank_timeout",
        "llm.nim_embedding_timeout",
        "llm.nim_vlm_timeout",
    ]
    for key in expected_keys:
        assert key in SETTING_REGISTRY, f"{key} eksik"
        meta = SETTING_REGISTRY[key]
        assert meta["type"] == "float", f"{key} type float olmalı"
        assert meta["group"] == "llm", f"{key} group llm olmalı"
        # requires_restart=True — provider __init__ time'da set edilir
        assert meta["requires_restart"] is True, (
            f"{key} requires_restart True olmalı (provider singleton init time)"
        )
        # min/max bounds tanımlı
        assert "min_value" in meta and "max_value" in meta, (
            f"{key} min/max bounds eksik"
        )


def test_factories_accept_timeout_parameter():
    """build_*_provider fonksiyonları timeout opsiyonel parametre alıyor."""
    from app.providers.deepseek import build_deepseek_provider
    from app.providers.nim import build_nim_provider
    from app.providers.nim_chat import build_nim_chat_provider
    from app.providers.nim_vlm import build_nim_vlm_provider

    for factory in (
        build_deepseek_provider,
        build_nim_provider,
        build_nim_chat_provider,
        build_nim_vlm_provider,
    ):
        sig = inspect.signature(factory)
        assert "timeout" in sig.parameters, (
            f"{factory.__name__} timeout parametre almıyor"
        )
        # Default None — backward compat (None ise class default)
        assert sig.parameters["timeout"].default is None, (
            f"{factory.__name__} timeout default None olmalı (backward compat)"
        )


def test_async_bootstrap_reads_settings_store():
    """bootstrap_default_providers_async kaynak kodunda settings_store.get_float
    çağrısı 5 timeout key için yapılıyor."""
    from app.providers import registry as reg_mod

    assert inspect.iscoroutinefunction(reg_mod.bootstrap_default_providers_async)
    source = inspect.getsource(reg_mod.bootstrap_default_providers_async)
    # 5 timeout settings_store'dan okunuyor
    for key in (
        "llm.deepseek_timeout",
        "llm.nim_chat_timeout",
        "llm.nim_rerank_timeout",
        "llm.nim_embedding_timeout",
        "llm.nim_vlm_timeout",
    ):
        assert key in source, f"async bootstrap {key} okumuyor"
    # Factory'lere timeout geçiriliyor
    assert "timeout=timeouts[" in source, (
        "async bootstrap factory'lere timeout dict geçirmiyor"
    )


def test_async_bootstrap_clears_registry_for_idempotent_init():
    """Async bootstrap registry'yi temizleyerek idempotent çalışır.

    Lazy sync bootstrap önce çalıştıysa async bootstrap DB-backed timeout'larla
    yeniden init etmeli."""
    from app.providers import registry as reg_mod

    source = inspect.getsource(reg_mod.bootstrap_default_providers_async)
    assert "registry._providers.clear()" in source, (
        "async bootstrap idempotent değil — clear() çağrısı eksik"
    )


def test_main_lifespan_calls_async_bootstrap():
    """main.py lifespan'da bootstrap_default_providers_async çağrılır."""
    from app import main as main_mod

    source = inspect.getsource(main_mod.lifespan)
    assert "bootstrap_default_providers_async" in source, (
        "main.lifespan async bootstrap'ı çağırmıyor"
    )
