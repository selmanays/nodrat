"""Query decomposition — karmaşık sorguyu alt-sorgulara böl (#619).

Plan: wiki/plans/query-decomposition-mini-plan.md. Retrieval-time, query-side.

Strateji (kullanıcı kararı 2026-06-05): **heuristic + LLM-fallback**.
1. Deterministik heuristic (TR bağlaç-split) — bariz çok-bileşenli sorgular.
2. Heuristic yetersiz + ``llm_enabled`` → LLM fallback (örtük çok-niyet).
3. Her durumda fail / timeout / parse-error / geçersiz çıktı → **tek-query
   baseline** (zarif degrade; condense/query_rewrite #833 deseni).

Güvenlik invariant'ları:
- Sub-query cap ``MAX_SUB_QUERIES`` (4).
- Normalize-bazlı dedup; orijinale eşit alt-sorgu elenir.
- Aşırı kısa / boş alt-sorgu atılır.
- ``parse_decompose_response`` ASLA raise etmez (geçersiz → []).
- LLM call ``asyncio.wait_for`` çift-timeout + exception → [] (query_rewrite deseni).

PR-2 kapsamı: SAF primitive. Bu modül hiçbir yerden çağrılmaz; orchestration
wiring + settings flag okuma PR-3'tedir (``llm_enabled`` o zaman flag'ten gelir).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Decomposition güvenlik sabitleri
MAX_SUB_QUERIES = 4
DECOMPOSE_TIMEOUT_S = 6
_MIN_SUB_QUERY_WORDS = 2
_MIN_SUB_QUERY_CHARS = 6
# Orijinal sorgu bundan kısaysa (kelime) decomposition denenmez (tek konu).
_MIN_QUERY_WORDS_FOR_DECOMPOSE = 4

# TR çok-bileşen ayraç marker'ları (heuristic split). Boşlukla sarılı —
# kelime-içi eşleşmeyi (ör. "ve" → "devlet") önler.
_TR_SPLIT_MARKERS: tuple[str, ...] = (
    " ve ",
    " ayrıca ",
    " hem ",
    " bir de ",
    " ile ilgili ",
)
# re.split için: marker'ları case-insensitive boundary'de böl.
_SPLIT_RE = re.compile(
    r"\s+(?:ve|ayrıca|hem|bir de|ile ilgili)\s+",
    flags=re.IGNORECASE,
)


@dataclass(frozen=True)
class DecompositionResult:
    """Decomposition çıktısı.

    ``method == "single"`` (veya ``len(sub_queries) <= 1``) → decomposition
    yok; caller orijinal sorguyu tek-query olarak kullanır (baseline).
    """

    original: str
    sub_queries: list[str]
    method: str  # "single" | "heuristic" | "llm"
    # #619 PR-5 telemetry — single/baseline nedeni (coarse). Başarıda None.
    # empty_query | too_short | llm_disabled | llm_no_result | None
    fallback_reason: str | None = None

    @property
    def is_decomposed(self) -> bool:
        return self.method != "single" and len(self.sub_queries) > 1


DECOMPOSE_SYSTEM_PROMPT = """Sen bir arama sorgusu ayrıştırıcısısın. \
Karmaşık, çok-bileşenli bir haber/araştırma sorgusunu, her biri TEK BİR \
konuya odaklı, bağımsız aranabilir alt-sorgulara böl.

KURALLAR:
- Sorgu TEK bir konu içeriyorsa BÖLME — boş liste [] döndür.
- En fazla 4 alt-sorgu üret.
- Her alt-sorgu kendi başına anlaşılır (standalone), Türkçe, kısa ve öz olsun.
- Zaman ifadelerini (ör. "son 24 saat", "bugün", "bu hafta") HER alt-sorguda KORU.
- Alt-sorgular örtüşmesin (tekrar etme).
- Çıktı SADECE JSON dizisi: ["alt sorgu 1", "alt sorgu 2"]. Açıklama YOK, başka metin YOK."""


def render_decompose_payload(query: str) -> str:
    """LLM user payload'ı (saf; test edilebilir)."""
    return f"Sorgu: {query}\n\nAlt-sorgular (JSON dizisi):"


def _normalize(s: str) -> str:
    """Dedup/karşılaştırma için: lowercase + whitespace collapse + strip."""
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _clean_and_cap(candidates: list[str], *, original: str) -> list[str]:
    """Aday alt-sorguları temizle: strip, kısa/boş ele, dedup, cap, orijinali at.

    Ortak güvenlik katmanı — hem heuristic hem LLM çıktısı buradan geçer.
    """
    seen: set[str] = set()
    out: list[str] = []
    orig_norm = _normalize(original)
    for cand in candidates:
        s = (cand or "").strip().strip('"').strip()
        if not s:
            continue
        if len(s) < _MIN_SUB_QUERY_CHARS or len(s.split()) < _MIN_SUB_QUERY_WORDS:
            continue
        norm = _normalize(s)
        if not norm or norm in seen or norm == orig_norm:
            continue
        seen.add(norm)
        out.append(s)
        if len(out) >= MAX_SUB_QUERIES:
            break
    return out


def decompose_heuristic(query: str) -> list[str]:
    """Deterministik TR bağlaç-split. Bariz çok-bileşen değilse [] döndürür.

    Agresif değil: yalnız marker varsa böler; her parça ``_MIN_SUB_QUERY_WORDS``
    kelimeden kısaysa (ör. "Ahmet ve Mehmet") elenir → tek anlamlı parça kalırsa
    decomposition yok sayılır. Belirsizde [] (LLM fallback'e bırak).
    """
    text = (query or "").strip()
    if not text:
        return []
    low = f" {text.lower()} "
    if not any(marker in low for marker in _TR_SPLIT_MARKERS):
        return []
    parts = _SPLIT_RE.split(text)
    cleaned = _clean_and_cap(parts, original=text)
    # En az 2 anlamlı parça yoksa bariz çok-bileşen değil → bölme.
    if len(cleaned) < 2:
        return []
    return cleaned


def parse_decompose_response(raw: str, *, original: str) -> list[str]:
    """LLM çıktısını alt-sorgu listesine çevir. ASLA raise etmez (geçersiz → []).

    JSON dizisi beklenir; markdown fence toleranslı; JSON değilse satır-satır
    fallback. Tüm çıktı ``_clean_and_cap``'ten geçer (cap/dedup/kısa-ele).
    """
    if not raw:
        return []
    text = raw.strip()
    # Markdown fence (```json ... ```) topla
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text).strip()
    candidates: list[str] = []
    try:
        data = json.loads(text)
        if isinstance(data, list):
            candidates = [str(x) for x in data if isinstance(x, (str, int, float))]
    except (json.JSONDecodeError, ValueError, TypeError):
        # JSON değil → satır-satır (madde işareti/numara temizle)
        for line in text.split("\n"):
            cleaned = line.strip().lstrip("-*0123456789.) \t").strip()
            if cleaned:
                candidates.append(cleaned)
    return _clean_and_cap(candidates, original=original)


async def decompose_query_llm(
    provider,
    query: str,
    *,
    model: str | None = None,
    timeout_s: int | None = None,
    system_prompt: str | None = None,
) -> list[str]:
    """LLM ile decomposition. Fail/timeout/parse-error → [] (caller baseline'a düşer).

    query_rewrite.condense_followup_query deseni: ``asyncio.wait_for`` çift-timeout
    (provider timeout + dış +1.0s), exception → logger.warning + [].
    """
    from app.providers.base import Message as ProviderMessage

    if not query:
        return []
    try:
        result = await asyncio.wait_for(
            provider.generate_text(
                messages=[
                    ProviderMessage(
                        role="system",
                        content=system_prompt or DECOMPOSE_SYSTEM_PROMPT,
                    ),
                    ProviderMessage(
                        role="user",
                        content=render_decompose_payload(query),
                    ),
                ],
                model=model,
                max_tokens=200,
                temperature=0.1,
                timeout=int(timeout_s or DECOMPOSE_TIMEOUT_S),
            ),
            timeout=float(timeout_s or DECOMPOSE_TIMEOUT_S) + 1.0,
        )
        return parse_decompose_response(result.text or "", original=query)
    except Exception as exc:  # zarif degrade: her hata → tek-query baseline
        logger.warning("decompose_query_llm failed: %s", exc)
        return []


async def decompose_query(
    query: str,
    *,
    provider=None,
    llm_enabled: bool = False,
    model: str | None = None,
    timeout_s: int | None = None,
    system_prompt: str | None = None,
) -> DecompositionResult:
    """Sorguyu alt-sorgulara böl (heuristic → LLM-fallback → tek-query baseline).

    Args:
        query: ham (veya condense edilmiş) kullanıcı sorgusu.
        provider: LLM ModelProvider (generate_text). ``None`` ise LLM atlanır.
        llm_enabled: heuristic boş kalınca LLM denensin mi (PR-3'te flag'ten gelir;
            PR-2 default False → davranış-nötr, LLM yalnız test mock'uyla tetiklenir).

    Returns:
        DecompositionResult. ``method == "single"`` → decomposition yok, caller
        ``[original]`` ile baseline retrieval yapar.
    """
    original = (query or "").strip()
    if not original:
        return DecompositionResult(
            original="", sub_queries=[], method="single", fallback_reason="empty_query"
        )

    # Kısa/tek-konu sorgular: decomposition denemeye değmez → baseline.
    if len(original.split()) < _MIN_QUERY_WORDS_FOR_DECOMPOSE:
        return DecompositionResult(
            original=original,
            sub_queries=[original],
            method="single",
            fallback_reason="too_short",
        )

    # 1) Deterministik heuristic (LLM-suz, hızlı, ücretsiz)
    heuristic = decompose_heuristic(original)
    if len(heuristic) >= 2:
        return DecompositionResult(original=original, sub_queries=heuristic, method="heuristic")

    # 2) LLM fallback (flag-gated; örtük çok-niyet)
    llm_attempted = False
    if llm_enabled and provider is not None:
        llm_attempted = True
        llm_subs = await decompose_query_llm(
            provider,
            original,
            model=model,
            timeout_s=timeout_s,
            system_prompt=system_prompt,
        )
        if len(llm_subs) >= 2:
            return DecompositionResult(original=original, sub_queries=llm_subs, method="llm")

    # 3) Tek-query baseline (decomposition yok / yetersiz / fail)
    return DecompositionResult(
        original=original,
        sub_queries=[original],
        method="single",
        fallback_reason="llm_no_result" if llm_attempted else "llm_disabled",
    )


__all__ = [
    "DECOMPOSE_SYSTEM_PROMPT",
    "DECOMPOSE_TIMEOUT_S",
    "MAX_SUB_QUERIES",
    "DecompositionResult",
    "decompose_heuristic",
    "decompose_query",
    "decompose_query_llm",
    "parse_decompose_response",
    "render_decompose_payload",
]
