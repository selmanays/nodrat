"""Provider abstraction layer — Issue #5.

Tüm LLM/embedding/rerank/vision/payment provider'ları bu interface'i implement eder.
docs/engineering/architecture.md §4 ile uyumlu.

KRITIK KURAL: Hiçbir kod doğrudan provider SDK'sına bağlı olmamalı.
            Tüm çağrılar bu abstraction üzerinden geçmeli.

PII REDACTION: Bu base sınıf provider çağrısı öncesi otomatik PII redaction
              uygular (docs/legal/opinion-integration.md §3.1).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Literal


class ProviderType(StrEnum):
    """Provider tipi enum."""

    LLM = "llm"
    EMBEDDING = "embedding"
    RERANK = "rerank"
    VISION = "vision"
    PAYMENT = "payment"


@dataclass
class ToolCall:
    """LLM'in çağırmak istediği tool (#822 — OpenAI-compatible function calling)."""

    id: str
    """Tool call ID — tool result mesajında tool_call_id olarak referans."""

    name: str
    """Fonksiyon adı (örn. 'search_wikipedia')."""

    arguments: dict[str, Any]
    """Parse edilmiş JSON argümanlar."""


@dataclass
class Message:
    """Chat message — LLM API'ları için ortak format.

    #822 tool-use: assistant tool_calls dönebilir; 'tool' rolündeki mesaj
    tool_call_id + content (tool sonucu) taşır.
    """

    role: Literal["system", "user", "assistant", "tool"]
    content: str
    tool_calls: list[ToolCall] | None = None
    """Assistant mesajında LLM'in talep ettiği tool çağrıları."""
    tool_call_id: str | None = None
    """role='tool' mesajında hangi tool call'a yanıt olduğu."""


@dataclass
class GenerationResult:
    """LLM generation çıktısı."""

    text: str
    """Üretilen metin."""

    model: str
    """Kullanılan model adı (örn. 'deepseek-v4-flash', 'claude-haiku-4-5')."""

    tool_calls: list[ToolCall] | None = None
    """#822 — LLM tool çağırmak istediyse (content boş/None olabilir)."""

    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0
    """#163 — DeepSeek prompt cache hit token sayısı (cache miss = input - cached).

    Cache hit token'lar 4-10x ucuz (DeepSeek pricing). Cost log'u için
    ayrı tutulur, hit ratio metric'i için kullanılır.
    """

    cost_usd: float = 0.0
    """Tahmini maliyet (provider rate × token, cache differential pricing dahil)."""

    latency_ms: int = 0
    """End-to-end latency."""

    raw_response: dict[str, Any] = field(default_factory=dict)
    """Provider'a özgü ham yanıt (debug için)."""


@dataclass
class StreamChunk:
    """Tek bir LLM stream chunk'ı (issue #527).

    Provider'ın streaming çıktısının ortak temsilî. delta_text genelde dolu;
    son chunk'ta usage doludur (token count + cache hits).
    """

    delta_text: str = ""
    """Bu chunk'ta gelen yeni text. Çoğu chunk'ta non-empty."""

    is_final: bool = False
    """True ise stream bitti; usage alanları doldurulmuş olabilir."""

    tool_calls: list[ToolCall] | None = None
    """#836 — final chunk'ta dolu olabilir: model stream içinde tool
    çağırdı (content boş, tool_calls dolu). Caller stream bitince
    kontrol eder; tool varsa tool-loop, yoksa stream edilen text final."""

    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0
    cost_usd: float = 0.0
    model: str = ""
    """Final chunk'ta dolu — generation log için."""

    raw_event: dict[str, Any] = field(default_factory=dict)
    """Provider raw event (debug)."""


@dataclass
class EmbeddingResult:
    """Embedding çıktısı."""

    vectors: list[list[float]]
    """Her input metin için vector (1024-dim bge-m3)."""

    model: str
    input_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0


@dataclass
class RerankResult:
    """Rerank çıktısı (Faz 7+ opsiyonel)."""

    index: int
    """Orijinal listede position."""

    score: float
    """Relevance skor."""


@dataclass
class ProviderHealth:
    """Provider health check sonucu."""

    healthy: bool
    latency_ms: int | None = None
    error: str | None = None


class ModelProvider(ABC):
    """Tüm model provider'ları (LLM, embedding, vb.) için base class.

    Her concrete provider:
        - generate_text() veya create_embedding() veya rerank() implement eder
        - desteklediği capability flag'lerini set eder
        - healthcheck() ile durum bilgisi sunar
    """

    name: str
    """Unique provider adı (örn. 'deepseek')."""

    type: ProviderType

    supports_chat: bool = False
    supports_embeddings: bool = False
    supports_rerank: bool = False
    supports_vision: bool = False

    cost_per_1m_input_tokens: float = 0.0
    cost_per_1m_output_tokens: float = 0.0

    async def generate_text(
        self,
        messages: list[Message],
        model: str,
        max_tokens: int = 1024,
        temperature: float = 0.7,
        timeout: int = 30,
        json_mode: bool = False,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str = "auto",
    ) -> GenerationResult:
        """LLM chat completion.

        #822 tool-use: `tools` OpenAI-compatible function tanımları. LLM
        tool çağırırsa GenerationResult.tool_calls dolu döner (text boş
        olabilir). `tool_choice`: 'auto' | 'none' | 'required'.

        Default: NotImplementedError. Concrete provider override eder.

        ZORUNLU: Override eden sınıf PII redaction uygulamalı:
            from app.core.pii import redact_messages
            redacted, _ = redact_messages([m.__dict__ for m in messages])
        """
        raise NotImplementedError(
            f"{self.name} chat desteklemiyor (supports_chat={self.supports_chat})"
        )

    def generate_text_stream(
        self,
        messages: list[Message],
        model: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.7,
        timeout: int | None = None,
        json_mode: bool = False,
    ) -> AsyncIterator[StreamChunk]:
        """LLM streaming chat completion (issue #527).

        Provider streaming destekliyorsa async iterator döner; her StreamChunk
        delta_text taşır. Son chunk is_final=True + usage doldurulur.

        Default: NotImplementedError. Concrete provider override eder.
        """
        raise NotImplementedError(f"{self.name} streaming desteklemiyor")

    async def generate_structured_json(
        self,
        messages: list[Message],
        schema: dict[str, Any],
        model: str,
        max_tokens: int = 1024,
        timeout: int = 30,
    ) -> dict[str, Any]:
        """Structured JSON output (Query Planner, Agenda Card için).

        Provider JSON mode destekliyorsa kullanılır, aksi halde prompt-level
        zorlama + retry yapılır.
        """
        raise NotImplementedError(f"{self.name} structured JSON desteklemiyor")

    async def create_embedding(
        self,
        texts: list[str],
        model: str,
    ) -> EmbeddingResult:
        """Batch embedding üret."""
        raise NotImplementedError(
            f"{self.name} embedding desteklemiyor (supports_embeddings={self.supports_embeddings})"
        )

    async def rerank(
        self,
        query: str,
        documents: list[str],
        top_k: int = 5,
    ) -> list[RerankResult]:
        """Rerank dokümanları."""
        raise NotImplementedError(f"{self.name} rerank desteklemiyor")

    async def analyze_image(
        self,
        image_url: str,
        prompt: str,
    ) -> dict[str, Any]:
        """VLM görsel analizi (Faz 4)."""
        raise NotImplementedError(f"{self.name} vision desteklemiyor")

    @abstractmethod
    async def healthcheck(self) -> ProviderHealth:
        """Provider'a basit ping at, healthy mi öğren."""
        ...


class ProviderError(Exception):
    """Base provider exception."""


class ProviderRateLimitError(ProviderError):
    """Provider rate limit aşıldı (429)."""


class ProviderQuotaExceededError(ProviderError):
    """Aylık monthly cap aşıldı — config'den."""


class ProviderTimeoutError(ProviderError):
    """Upstream timeout."""


class ProviderUnsafeOutputError(ProviderError):
    """Çıktı kalite/halüsinasyon kontrolünde flag yedi."""
