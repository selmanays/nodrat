"""Provider çağrı tracker — call → `provider_call_logs` INSERT (raw SQL, T7-6).

docs/engineering/data-model.md §4.5
docs/strategy/unit-economics.md §6

Kullanım:
    async with track_provider_call(provider='local_bge_m3', operation='embedding',
                                    user_id=None, article_id=art_id) as tracker:
        result = await provider.create_embedding(texts)
        tracker.record(
            input_tokens=result.token_count,
            output_tokens=0,
            model=result.model,
        )

    # Auto: latency_ms (with süresi), success (no exception),
    # cost_usd (provider rate × tokens), error_message (raise)

Asenkron context manager — caller'a görünmez insert.
Hata olursa exception propagate ama log INSERT gerçekleşir.
"""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


@dataclass
class CallTracker:
    """Context manager state — tracker.record() ile token + model bilgisi yazılır."""

    provider: str
    operation: str
    started_at_perf: float

    user_id: UUID | None = None
    generation_id: UUID | None = None
    article_id: UUID | None = None

    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cached_tokens: int | None = None  # #171 — DeepSeek cache hit
    cost_usd: Decimal | None = None

    success: bool = True
    error_message: str | None = None

    def record(
        self,
        *,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        cached_tokens: int | None = None,
        model: str | None = None,
        cost_usd: Decimal | float | None = None,
    ) -> None:
        """Provider call sonrası tracker'a metrik yaz."""
        if input_tokens is not None:
            self.input_tokens = input_tokens
        if output_tokens is not None:
            self.output_tokens = output_tokens
        if cached_tokens is not None:
            self.cached_tokens = cached_tokens
        if model is not None:
            self.model = model
        if cost_usd is not None:
            self.cost_usd = cost_usd if isinstance(cost_usd, Decimal) else Decimal(str(cost_usd))


def estimate_cost_usd(
    *,
    provider: str,
    input_tokens: int | None,
    output_tokens: int | None,
    cost_per_1m_input: float = 0.0,
    cost_per_1m_output: float = 0.0,
) -> Decimal:
    """Provider rate'lerinden cost hesabı.

    NIM free tier → 0.0 USD.
    DeepSeek/Anthropic → adapter rate'leri kullanılır.
    """
    if not input_tokens and not output_tokens:
        return Decimal("0.0")
    in_cost = Decimal(input_tokens or 0) * Decimal(str(cost_per_1m_input)) / Decimal(1_000_000)
    out_cost = Decimal(output_tokens or 0) * Decimal(str(cost_per_1m_output)) / Decimal(1_000_000)
    total = in_cost + out_cost
    return total.quantize(Decimal("0.000001"))


@asynccontextmanager
async def track_provider_call(
    *,
    db: AsyncSession,
    provider: str,
    operation: str,
    user_id: UUID | None = None,
    generation_id: UUID | None = None,
    article_id: UUID | None = None,
) -> AsyncIterator[CallTracker]:
    """Async context manager — provider call'u sarar, sonucu DB'ye INSERT eder.

    Caller exception fırlatırsa: success=False + error_message kaydedilir,
    sonra exception re-raise.
    Caller başarıyla biterse: success=True kaydedilir.
    Yine de INSERT edilir (best-effort, INSERT hatası swallowed + warning log).
    """
    tracker = CallTracker(
        provider=provider,
        operation=operation,
        started_at_perf=time.perf_counter(),
        user_id=user_id,
        generation_id=generation_id,
        article_id=article_id,
    )

    try:
        yield tracker
    except Exception as exc:
        tracker.success = False
        tracker.error_message = str(exc)[:1000]
        # Re-raise sonrası finally'de INSERT
        raise
    finally:
        latency_ms = int((time.perf_counter() - tracker.started_at_perf) * 1000)
        # T7-6: ORM `ProviderCallLog(...)` + `db.add` yerine raw INSERT (tablo adı
        # `provider_call_logs` sabit). Böylece core/ artık `app.models.provider_log`
        # import etmez → ProviderCallLog T8-7'de modules/ops/models'e taşınabilir
        # (core→modules ihlali doğmaz). `id` + `created_at` server_default
        # (gen_random_uuid() / now()) → INSERT'te omit edilir. **Davranış birebir:**
        # caller'ın master transaction'ı INSERT'i kapsar (eskiden db.add commit'te
        # flush'lardı); `no_autoflush` caller'ın pending ORM objelerini erken flush
        # etmeyi önler (eski db.add finally'de flush ZORLAMIYORDU — bu semantik korunur).
        try:
            with db.sync_session.no_autoflush:
                await db.execute(
                    text(
                        "INSERT INTO provider_call_logs "
                        "(provider, model, operation, input_tokens, output_tokens, "
                        "cached_tokens, cost_usd, latency_ms, user_id, generation_id, "
                        "article_id, success, error_message) VALUES "
                        "(:provider, :model, :operation, :input_tokens, :output_tokens, "
                        ":cached_tokens, :cost_usd, :latency_ms, :user_id, :generation_id, "
                        ":article_id, :success, :error_message)"
                    ),
                    {
                        "provider": tracker.provider,
                        "model": tracker.model,
                        "operation": tracker.operation,
                        "input_tokens": tracker.input_tokens,
                        "output_tokens": tracker.output_tokens,
                        "cached_tokens": tracker.cached_tokens,
                        "cost_usd": tracker.cost_usd,
                        "latency_ms": latency_ms,
                        "user_id": tracker.user_id,
                        "generation_id": tracker.generation_id,
                        "article_id": tracker.article_id,
                        "success": tracker.success,
                        "error_message": tracker.error_message,
                    },
                )
        except Exception as inner_exc:  # pragma: no cover
            logger.warning(
                "provider_call_log INSERT failed provider=%s op=%s err=%s",
                provider,
                operation,
                inner_exc,
            )
