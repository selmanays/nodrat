"""Provider registry — runtime'da kullanılacak provider'ları kaydet ve seç.

docs/engineering/architecture.md §4.3 (routing logic)
docs/strategy/unit-economics.md §4.2 (tier × provider mapping)
"""

from __future__ import annotations

import logging
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.providers.base import ModelProvider, ProviderType

logger = logging.getLogger(__name__)

# Local bge-m3 fallback Faz 2'de aktif edilecek (sentence-transformers ~2GB)
# from app.providers.local_embedding import build_local_provider


UserTier = Literal["trial", "free", "starter", "pro", "agency_seat"]


class ProviderRegistry:
    """Provider'ları kaydeden ve tier'a göre routing yapan singleton.

    Faz 0+ — concrete adapter'lar eklendikçe registry doluyor.
    """

    def __init__(self) -> None:
        self._providers: dict[str, ModelProvider] = {}

    def register(self, provider: ModelProvider) -> None:
        """Provider'ı kaydet."""
        if provider.name in self._providers:
            raise ValueError(f"Provider {provider.name} zaten kayıtlı")
        self._providers[provider.name] = provider

    def get(self, name: str) -> ModelProvider:
        """Provider'a name ile eriş."""
        if name not in self._providers:
            raise KeyError(f"Provider {name} bulunamadı. Kayıtlı: {list(self._providers)}")
        return self._providers[name]

    def list_by_type(self, type_: ProviderType) -> list[ModelProvider]:
        """Tip bazında listele."""
        return [p for p in self._providers.values() if p.type == type_]

    def route_for_tier(
        self,
        operation: Literal["chat", "embedding", "rerank", "vision"],
        tier: UserTier,
        comparison_mode: bool = False,
        op_name: str | None = None,
    ) -> ModelProvider:
        """Tier'a göre provider seç (docs/strategy/unit-economics.md §4.2).

        #778 — op_name parametresi: per-operation LLM routing (admin /settings
        üzerinden değiştirilebilir). Geçerli op_name değerleri:
          - "ner" → llm.routing.ner DB setting
          - "planner" → llm.routing.planner
          - "rerank" → llm.routing.rerank
          - "generation" → llm.routing.generation
          - None → default deepseek (backward-compat)
        DB settings runtime'da `_resolve_chat_routing()` ile okunur (async path).

        Routing kuralları:
            chat:
                trial / free / starter → DeepSeek V4 Flash (default)
                                       → admin /settings ile Gemma'ya değiştirilebilir
                pro / agency_seat      → Claude Haiku 4.5
                agency comparison      → Claude Sonnet 4.6

            embedding:
                tüm tier'lar           → local bge-m3

        NOT: op_name None ise mevcut davranış (DeepSeek default).
        """
        if operation == "chat":
            if tier in ("agency_seat",) and comparison_mode:
                return self._fallback("anthropic_sonnet", "anthropic_haiku", "deepseek")
            if tier in ("pro", "agency_seat"):
                return self._fallback("anthropic_haiku", "deepseek")
            # #778 — sync path: backward-compat default DeepSeek.
            # Async path için resolve_chat_provider() async fonksiyonu kullanılır.
            return self._fallback("deepseek", "openrouter")

        if operation == "embedding":
            # #681 Faz 7b — settings flag ile e5 / bge-m3 seçimi
            # Eğer LocalE5 register edilmişse ve flag aktifse onu kullan,
            # yoksa bge-m3'e düş (geriye uyumlu default).
            return self._fallback("local_e5_multilingual", "local_bge_m3")

        if operation == "rerank":
            # #758 (2026-05-12): Cross-encoder rerank tamamen kaldırıldı.
            # local_bge_reranker + nim_rerank her ikisi de eval'de baseline'dan
            # kötü çıktı (#750), provider modülleri silindi. LLM rerank (Faz 4
            # answer-aware) bağımsız akışla rerank.py içinde çalışıyor.
            raise RuntimeError(
                "Cross-encoder rerank kaldırıldı (#758). "
                "LLM rerank (rerank.py:rerank_rows) aktif kullanın."
            )

        if operation == "vision":
            return self._fallback("anthropic_haiku")  # Faz 4'te aktif

        raise ValueError(f"Unknown operation: {operation}")

    def _fallback(self, *candidates: str) -> ModelProvider:
        """İlk kayıtlı candidate'ı döndür, hiçbiri yoksa hata."""
        for name in candidates:
            if name in self._providers:
                return self._providers[name]
        raise RuntimeError(
            f"Hiçbir candidate kayıtlı değil. Aranan: {candidates}, "
            f"kayıtlı: {list(self._providers)}"
        )


# Module-level singleton (Faz 0 simple, ileride DI ile değiştirilebilir)
registry = ProviderRegistry()


# #778 — Multi-LLM routing constants
_VALID_OP_NAMES = ("ner", "planner", "rerank", "generation")
_VALID_PROVIDERS_FOR_OP = ("deepseek", "gemini")
_DEFAULT_PROVIDER_PER_OP = {
    "ner": "deepseek",
    "planner": "deepseek",
    "rerank": "deepseek",
    "generation": "deepseek",
}


async def resolve_chat_provider(
    db,
    *,
    op_name: str,
    tier: UserTier = "free",
) -> ModelProvider:
    """Async: per-operation chat provider resolver (#778).

    Admin /settings'ten `llm.routing.{op_name}` setting okur, registry'den
    provider seçer. Eğer setting yok veya provider kayıtsız ise DeepSeek'e
    fallback (backward-compat).

    Args:
        db: AsyncSession (settings_store.get_str için).
        op_name: "ner" | "planner" | "rerank" | "generation".
        tier: User tier (pro/agency için Anthropic Haiku, ileride).

    Returns:
        ModelProvider — registry'den, registered ise.
    """
    if op_name not in _VALID_OP_NAMES:
        raise ValueError(f"Invalid op_name: {op_name}. Valid: {_VALID_OP_NAMES}")

    # Pro / agency tier still uses Anthropic Haiku (when implemented)
    if tier in ("pro", "agency_seat"):
        return registry._fallback("anthropic_haiku", "deepseek")

    # Free / trial / starter: setting-based routing
    from app.core.settings_store import settings_store

    default = _DEFAULT_PROVIDER_PER_OP[op_name]
    try:
        provider_name = await settings_store.get(
            db, f"llm.routing.{op_name}", default
        )
    except Exception:
        provider_name = default

    if provider_name not in _VALID_PROVIDERS_FOR_OP:
        provider_name = default

    # Registry'de kayıtlı mı? Yoksa fallback
    if provider_name in registry._providers:
        return registry._providers[provider_name]
    return registry._fallback("deepseek", "openrouter")


def bootstrap_default_providers() -> None:
    """Default provider'ları registry'ye kaydet.

    Çağrı yeri: app.main lifespan startup.

    Provider precedence (#163 DeepSeek migration, #420 NIM embedding kaldırma,
    #720 NIM chat fallback kaldırma):
      Chat (name='deepseek'):
        1. DeepSeek native API (DEEPSEEK_API_KEY zorunlu) — tek provider
      Embedding (name='local_bge_m3'):
        1. Local BAAI/bge-m3 (sentence-transformers, CPU on VPS) — tek provider
    """
    # Chat: DeepSeek primary (#163) — #720 NIM chat fallback kaldırıldı
    # (deprecated, prod environment DEEPSEEK_API_KEY zorunlu olarak ayarlı).
    from app.providers.deepseek import build_deepseek_provider

    deepseek = build_deepseek_provider()
    if deepseek is not None and deepseek.name not in registry._providers:
        registry.register(deepseek)

    # Embedding: Local BAAI/bge-m3 (sentence-transformers, CPU on VPS).
    from app.providers.local_embedding import build_local_provider

    local_emb = build_local_provider()
    if local_emb is not None and local_emb.name not in registry._providers:
        registry.register(local_emb)

    # #681 Faz 7b — LocalE5 alternative (intfloat/multilingual-e5-large)
    # ENV var EMBEDDING_PROVIDER=e5 ile aktif edilir (DB-async bootstrap'ta
    # settings flag ile de açılır). Default OFF — bge-m3 primary.
    import os as _os

    if _os.environ.get("EMBEDDING_PROVIDER", "").lower() in ("e5", "local_e5"):
        from app.providers.local_e5 import build_local_e5_provider

        local_e5 = build_local_e5_provider()
        if local_e5 is not None and local_e5.name not in registry._providers:
            registry.register(local_e5)

    # #758: Cross-encoder rerank provider'ları kaldırıldı (local_bge_reranker +
    # nim_rerank — #750 eval baseline'dan kötü). Yalnız LLM rerank aktif
    # (rerank.py:rerank_rows, DeepSeek answer-aware top-3).

    # #778 — Gemini provider (Gemma 4 modelleri). Ücretsiz tier (15 req/min).
    # Admin /settings'ten per-operation routing değiştirilebilir.
    # API key yoksa register edilmez (factory None döner).
    from app.providers.gemini import build_gemini_provider

    gemini = build_gemini_provider()
    if gemini is not None and gemini.name not in registry._providers:
        registry.register(gemini)


async def bootstrap_default_providers_async(db: AsyncSession) -> None:
    """DB-backed provider bootstrap (#273 MVP-2).

    settings_store'dan provider HTTP timeout'larını okur, factory'lere geçirir.
    Çağrı yeri: app.main lifespan startup.

    Lazy bootstrap'ları (worker tasks, scripts) etkilemez — onlar provider
    default timeout'larını kullanır. Setting değişimi için API container
    restart gerek (UI'da requires_restart=True badge).
    """
    from app.core.settings_store import settings_store

    # #420 — `nim_embedding` timeout kaldırıldı; embedding artık tek provider
    # (local CPU, HTTP timeout yok).
    # #720: nim_chat timeout artık okunmuyor (NIM chat fallback kaldırıldı).
    # #758: nim_rerank timeout kaldırıldı (cross-encoder rerank tamamen silindi).
    timeouts = {
        "deepseek": await settings_store.get_float(db, "llm.deepseek_timeout", 60.0),
        "nim_vlm": await settings_store.get_float(db, "llm.nim_vlm_timeout", 30.0),
    }

    # Lazy bootstrap önce çalıştıysa registry'yi temizle ki DB-backed
    # timeout'lar etkili olsun (idempotent).
    registry._providers.clear()

    # Chat: DeepSeek primary (#163) — #720 NIM chat fallback kaldırıldı.
    from app.providers.deepseek import build_deepseek_provider

    deepseek = build_deepseek_provider(timeout=timeouts["deepseek"])
    if deepseek is not None and deepseek.name not in registry._providers:
        registry.register(deepseek)

    # Embedding: Local BAAI/bge-m3 (sentence-transformers, CPU on VPS).
    from app.providers.local_embedding import build_local_provider

    local_emb = build_local_provider()  # local — HTTP timeout yok (CPU)
    if local_emb is not None and local_emb.name not in registry._providers:
        registry.register(local_emb)

    # #681 Faz 7b — LocalE5 alternative, DB settings flag ile aktif
    use_e5 = await settings_store.get_bool(db, "embedding.use_e5", False)
    if use_e5:
        from app.providers.local_e5 import build_local_e5_provider

        local_e5 = build_local_e5_provider()
        if local_e5 is not None and local_e5.name not in registry._providers:
            registry.register(local_e5)
            logger.info("local_e5 provider registered (Faz 7b flag aktif)")

    # #758: Cross-encoder rerank kaldırıldı (provider modülleri silindi).
    # LLM rerank (rerank.py) bağımsız akışla DeepSeek üzerinden çalışır.

    # #778 — Gemini provider (Gemma 4) — GOOGLE_API_KEY varsa register
    from app.providers.gemini import build_gemini_provider

    gemini_timeout = await settings_store.get_float(db, "llm.gemini_timeout", 60.0)
    gemini = build_gemini_provider(timeout=gemini_timeout)
    if gemini is not None and gemini.name not in registry._providers:
        registry.register(gemini)
        logger.info("gemini provider registered (model=%s)", gemini._default_model)

    logger.info(
        "provider_registry_async_bootstrap timeouts ds=%.0fs nim_vlm=%.0fs "
        "registered=%s",
        timeouts["deepseek"],
        timeouts["nim_vlm"],
        sorted(registry._providers.keys()),
    )
