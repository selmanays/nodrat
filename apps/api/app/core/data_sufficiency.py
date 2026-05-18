"""Data sufficiency checker (#26).

PRD §2.10 + §3.4 (INSUFFICIENT_DATA flow)
docs/engineering/api-contracts.md §15

Sorgu: retrieval_plan'a göre yeterli kaynak var mı?
  - mode='current' + her timeframe için min_evidence_per_period kart
  - mode='comparison' her dönem için min_evidence_per_period kart

Eğer YETERSİZ:
  - 3 actionable suggestion (kullanıcıya alternatif önerisi)
  - status='insufficient_data' generation döner

Anti-pattern: yetersiz veriyle içerik üretme YASAK (PRD §12).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


@dataclass
class SufficiencyReport:
    """Data sufficiency sonucu — caller'a karar bildirir."""

    sufficient: bool
    """True ise content gen devam eder, False ise INSUFFICIENT_DATA flow."""

    counts_per_period: dict[str, int] = field(default_factory=dict)
    """Her timeframe label'ı için bulunan agenda card sayısı."""

    suggestions: list[str] = field(default_factory=list)
    """Yetersizse 3 actionable öneri (PRD §3.4)."""

    reason: str | None = None


async def check_sufficiency(
    db: AsyncSession,
    *,
    retrieval_plan: dict[str, Any],
    min_evidence_per_period: int = 2,
) -> SufficiencyReport:
    """Plan'a göre agenda card mevcudiyetini kontrol et.

    SQL:
      Her timeframe için event_clusters JOIN agenda_cards WHERE
      last_seen_at IN (from, to) AND status IN (active, developing, cooling).
      Active öncelikli sayılır.
    """
    timeframes = retrieval_plan.get("timeframes") or []

    if not timeframes:
        # No timeframes → use last 24h as default current
        now = datetime.now(UTC)
        timeframes = [
            {
                "label": "current_24h",
                "from": (now - timedelta(hours=24)).isoformat(),
                "to": now.isoformat(),
            }
        ]

    counts: dict[str, int] = {}

    for tf in timeframes:
        label = str(tf.get("label", "unnamed"))
        from_iso = tf.get("from")
        to_iso = tf.get("to")
        if not from_iso or not to_iso:
            counts[label] = 0
            continue

        try:
            from_dt = datetime.fromisoformat(str(from_iso).replace("Z", "+00:00"))
            to_dt = datetime.fromisoformat(str(to_iso).replace("Z", "+00:00"))
        except ValueError:
            counts[label] = 0
            continue

        # Count agenda_cards in window via event_clusters last_seen_at
        result = await db.execute(
            sa_text(
                """
                SELECT COUNT(*)
                FROM agenda_cards ac
                JOIN event_clusters ec ON ec.id = ac.event_id
                WHERE ec.last_seen_at >= :from_dt
                  AND ec.last_seen_at <= :to_dt
                  AND ec.status IN ('active', 'developing', 'cooling')
                """
            ),
            {"from_dt": from_dt, "to_dt": to_dt},
        )
        counts[label] = int(result.scalar() or 0)

    # Sufficiency rule
    insufficient_periods = [label for label, c in counts.items() if c < min_evidence_per_period]

    if insufficient_periods:
        # Generate 3 actionable suggestions
        suggestions = _build_suggestions(
            retrieval_plan=retrieval_plan,
            counts=counts,
            min_evidence=min_evidence_per_period,
        )
        return SufficiencyReport(
            sufficient=False,
            counts_per_period=counts,
            suggestions=suggestions,
            reason=(
                f"Yetersiz kaynak: {len(insufficient_periods)} dönem için "
                f"{min_evidence_per_period}+ agenda card gerekli. "
                f"{insufficient_periods}: {[counts[p] for p in insufficient_periods]}"
            ),
        )

    return SufficiencyReport(
        sufficient=True,
        counts_per_period=counts,
    )


def _build_suggestions(
    *,
    retrieval_plan: dict[str, Any],
    counts: dict[str, int],
    min_evidence: int,
) -> list[str]:
    """3 actionable suggestion üret — kullanıcıya somut alternatif.

    Standart öneri pattern'i (PRD §3.4):
      1. Konu kapsamını genişlet
      2. Zaman aralığını genişlet (current → weekly → archive)
      3. Manual mode (kaynaklı standalone içerik)
    """
    topic = str(retrieval_plan.get("topic_query", "konu") or "konu")
    mode = retrieval_plan.get("mode", "current")

    suggestions: list[str] = []

    # 1) Kapsam genişletme
    suggestions.append(
        f"'{topic}' için kapsamı genişletin. Daha geniş anahtar "
        f"kelimelerle (örn. ilgili sektör, daha üst tema) tekrar deneyin."
    )

    # 2) Zaman aralığı genişletme
    if mode == "current":
        suggestions.append(
            f"'{topic}' için son 24 saatte yeterli haber yok — "
            "haftalık özet (mode='weekly') deneyin."
        )
    elif mode == "weekly":
        suggestions.append(
            f"'{topic}' için bu hafta yeterli haber yok — "
            "arşiv (mode='archive') seçeneğini deneyin."
        )
    else:
        suggestions.append(
            "Daha kısa bir dönem seçerek (örn. son 7 gün) yoğun haberli pencerede arayabilirsiniz."
        )

    # 3) Standalone alternative
    suggestions.append(
        "Bağlamsız standalone içerik istiyorsanız ChatGPT/Claude vs. "
        "kullanmayı düşünebilirsiniz — Nodrat sadece kaynaklı üretir."
    )

    return suggestions[:3]
