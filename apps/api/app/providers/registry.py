"""Provider registry — runtime'da kullanılacak provider'ları kaydet ve seç.

docs/engineering/architecture.md §4.3 (routing logic)
docs/strategy/unit-economics.md §4.2 (tier × provider mapping)
"""

from __future__ import annotations

import logging
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.providers.base import ModelProvider, ProviderType
from app.providers.nim_chat import build_nim_chat_provider

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
    ) -> ModelProvider:
        """Tier'a göre provider seç (docs/strategy/unit-economics.md §4.2).

        Routing kuralları:
            chat:
                trial / free / starter → DeepSeek V3
                pro / agency_seat      → Claude Haiku 4.5
                agency comparison      → Claude Sonnet 4.6

            embedding:
                tüm tier'lar           → NIM bge-m3 (free), local fallback

        NOT: Faz 0'da sadece DeepSeek + NIM kayıtlı. Anthropic Faz 2'de eklenir.
        """
        if operation == "chat":
            if tier in ("agency_seat",) and comparison_mode:
                return self._fallback("anthropic_sonnet", "anthropic_haiku", "deepseek_v3")
            if tier in ("pro", "agency_seat"):
                return self._fallback("anthropic_haiku", "deepseek_v3")
            return self._fallback("deepseek_v3", "openrouter")

        if operation == "embedding":
            # #350 — embedding tek provider: local BAAI/bge-m3 (CPU on VPS).
            # NIM nim_bge_m3 (nv-embedqa-e5-v5) #420 ile sistemden kaldırıldı.
            return self._fallback("local_bge_m3")

        if operation == "rerank":
            # #224 MVP-1.5 PR-9 — local primary, NIM yedek
            return self._fallback("local_bge_reranker", "nim_rerank")

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


def bootstrap_default_providers() -> None:
    """Default provider'ları registry'ye kaydet.

    Çağrı yeri: app.main lifespan startup.

    Provider precedence (#163 DeepSeek migration, #420 NIM embedding kaldırma):
      Chat (name='deepseek_v3'):
        1. DeepSeek native API (DEEPSEEK_API_KEY varsa) — primary
        2. NIM chat (NIM_API_KEY varsa) — DEPRECATED fallback (PR-C'de kaldırılır)
      Embedding (name='local_bge_m3'):
        1. Local BAAI/bge-m3 (sentence-transformers, CPU on VPS) — tek provider
    """
    # Chat: DeepSeek primary (#163)
    from app.providers.deepseek import build_deepseek_provider

    deepseek = build_deepseek_provider()
    if deepseek is not None and deepseek.name not in registry._providers:
        registry.register(deepseek)
    else:
        # Fallback: NIM chat (deprecated, only when DeepSeek key missing)
        nim_chat = build_nim_chat_provider()
        if nim_chat is not None and nim_chat.name not in registry._providers:
            registry.register(nim_chat)

    # Embedding: Local bge-m3 (#350 migration tamamlandı 2026-05-06).
    # #420 — NIM nim_bge_m3 fallback kaldırıldı; tek provider.
    from app.providers.local_embedding import build_local_provider

    local_emb = build_local_provider()
    if local_emb is not None and local_emb.name not in registry._providers:
        registry.register(local_emb)

    # Rerank: Local bge-reranker-v2-m3 primary (#224 PR-9), NIM yedek (#181)
    # Yeni isim ayrımı (local_bge_reranker vs nim_rerank) sayesinde her ikisi
    # de register olabilir; route_for_tier sırasını kullanır.
    from app.providers.local_rerank import build_local_rerank_provider

    local_rerank = build_local_rerank_provider()
    if local_rerank is not None and local_rerank.name not in registry._providers:
        registry.register(local_rerank)

    # NIM rerank yedek
    from app.providers.nim_rerank import NimRerankProvider

    try:
        nim_rerank = NimRerankProvider()
        if nim_rerank.name not in registry._providers:
            registry.register(nim_rerank)
    except ValueError:
        # NIM_API_KEY yoksa rerank disabled (graceful)
        pass


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
    timeouts = {
        "deepseek": await settings_store.get_float(db, "llm.deepseek_timeout", 60.0),
        "nim_chat": await settings_store.get_float(db, "llm.nim_chat_timeout", 120.0),
        "nim_rerank": await settings_store.get_float(db, "llm.nim_rerank_timeout", 15.0),
        "nim_vlm": await settings_store.get_float(db, "llm.nim_vlm_timeout", 30.0),
    }

    # Lazy bootstrap önce çalıştıysa registry'yi temizle ki DB-backed
    # timeout'lar etkili olsun (idempotent).
    registry._providers.clear()

    # Chat: DeepSeek primary (#163)
    from app.providers.deepseek import build_deepseek_provider

    deepseek = build_deepseek_provider(timeout=timeouts["deepseek"])
    if deepseek is not None and deepseek.name not in registry._providers:
        registry.register(deepseek)
    else:
        # Fallback: NIM chat (deprecated, sadece DeepSeek key yoksa)
        nim_chat = build_nim_chat_provider(timeout=timeouts["nim_chat"])
        if nim_chat is not None and nim_chat.name not in registry._providers:
            registry.register(nim_chat)

    # Embedding: Local bge-m3 (#350 migration tamam, #420 NIM kaldırıldı).
    from app.providers.local_embedding import build_local_provider

    local_emb = build_local_provider()  # local — HTTP timeout yok (CPU)
    if local_emb is not None and local_emb.name not in registry._providers:
        registry.register(local_emb)

    # Rerank: Local bge-reranker-v2-m3 primary (#224 PR-9), NIM yedek
    from app.providers.local_rerank import build_local_rerank_provider

    local_rerank = build_local_rerank_provider()  # local — HTTP timeout yok
    if local_rerank is not None and local_rerank.name not in registry._providers:
        registry.register(local_rerank)

    from app.providers.nim_rerank import NimRerankProvider

    try:
        nim_rerank = NimRerankProvider(timeout=timeouts["nim_rerank"])
        if nim_rerank.name not in registry._providers:
            registry.register(nim_rerank)
    except ValueError:
        pass

    logger.info(
        "provider_registry_async_bootstrap timeouts ds=%.0fs nim_chat=%.0fs "
        "nim_rerank=%.0fs nim_vlm=%.0fs registered=%s",
        timeouts["deepseek"],
        timeouts["nim_chat"],
        timeouts["nim_rerank"],
        timeouts["nim_vlm"],
        sorted(registry._providers.keys()),
    )
