"""Provider registry — runtime'da kullanılacak provider'ları kaydet ve seç.

docs/engineering/architecture.md §4.3 (routing logic)
docs/strategy/unit-economics.md §4.2 (tier × provider mapping)
"""

from __future__ import annotations

from typing import Literal

from app.providers.base import ModelProvider, ProviderType
from app.providers.nim import build_nim_provider

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
            return self._fallback("nim_bge_m3", "local_bge_m3")

        if operation == "rerank":
            # Faz 7+ — şimdilik unsupported
            raise NotImplementedError("Rerank Faz 7+ feature")

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

    Eklenenler (mevcut config'e göre):
        - NIM embedding (eğer NIM_API_KEY set ise)
        - Local bge-m3 fallback (her zaman)

    Faz 2+'de eklenecek:
        - DeepSeek V3 (chat default)
        - Anthropic Haiku 4.5 (Pro tier chat)
        - OpenRouter (chat fallback)
    """
    # NIM (opsiyonel — key yoksa skip)
    nim = build_nim_provider()
    if nim is not None and nim.name not in registry._providers:
        registry.register(nim)

    # Local bge-m3 (Faz 2'de aktive — sentence-transformers ~2GB image impact)
    # local = build_local_provider()
    # if local.name not in registry._providers:
    #     registry.register(local)
