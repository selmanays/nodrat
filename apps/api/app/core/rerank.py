"""Rerank wrapper — sadece LLM rerank (Faz 4 answer-aware) kaldı.

Tarihçe:
  - #181 (2026-03): Cross-encoder rerank (NIM rerank-qa-mistral-4b)
  - #347 (2026-05): Local bge-reranker-v2-m3 eklendi, eval gate negatif
  - #251/#252/#254/#259/#260: Cross-encoder Türkçe niş kalite sorunları
  - #750 (2026-05-12): A/B eval — her iki cross-encoder model
    production baseline'dan kötü çıktı → kalıcı disabled
  - #758 (2026-05-12): Cross-encoder kod path TAMAMEN KALDIRILDI.
    Yalnız LLM rerank (Faz 4 — DeepSeek answer-aware top-3) kalır.

`rerank_rows` adı backward-compat: caller'lar (hybrid_search_*) interface
bozulmadı, yalnız LLM rerank uygulanır (cross-encoder yok).

Eğer ileride yeni reranker model (Jina, BAAI v2-gemma vs.) eklenirse
ayrı provider modülü + bu modülde gerekli çağrı eklenir.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)


# Türkçe yaygın küçük-harf stop kelimeleri (entity adayı havuzundan çıkarılır).
# Kullanım: query'den özel-ad çıkartırken cap'li görünebilen ama anlamca özel
# olmayan kelimelerin elenmesi. Genel kural — vakaya özel değil.
_ENTITY_STOPWORDS: frozenset[str] = frozenset(
    [
        "ne", "neden", "nasıl", "kim", "kime", "kimle", "ne zaman", "nereye",
        "bu", "şu", "o", "bir", "ve", "ile", "için", "ama", "fakat", "ya",
        "yani", "çok", "az", "daha", "her", "hangi", "hangisi",
        "var", "yok", "olan", "olur", "olarak", "kadar", "gibi", "öyle",
        "böyle", "şöyle", "haber", "haberi", "haberler", "son", "yeni",
        "ilgili", "hakkında", "bilgi", "bilgiler", "ver", "sun",
        # #691 — niche_002/005 sonrası genişletme (Türkçe question/morpho)
        "nedir", "neler", "neresi", "kimdir", "kimler",
        "maç", "maçı", "maçın", "maçtan", "maçtaki",
        "işi", "işin", "işleri", "işler", "işten",
        "kaç", "kaçı", "kaça", "kaçtan",
        "bitti", "bitmiş", "bitince",
        # #699 — niche_010 fix: DeepSeek NER "dedi"/"dedim"/"dediği" common
        # kelime'yi entity diye kaydetmiş (df=1 halüsinasyon); single_rare
        # fallback ile yanlış article'a işaret ediyordu.
        "dedi", "dedim", "dedik", "dediği", "dediler",
        "diyor", "diyorlar", "söyledi", "söyleyen", "söylenen",
        # ASCII / single-letter stop'lar
        "the", "of", "and", "a", "an",
    ]
)

# Genel entity adayı regex: Türkçe alfabe + digit + "-" (F-16, COVID-19, AKP-MHP)
_ENTITY_TOKEN_RE = re.compile(r"[A-Za-zÇĞİıÖŞÜçğıöşü0-9][A-Za-zÇĞİıÖŞÜçğıöşü0-9\-]*")

# #691 — Türkçe possessive ekleri için apostrof SPACE'e dönüştürülmeli.
# Sadece apostrof varyantları yeter (smart quote olmasalar da koruma).
_APOSTROPHE_VARIANTS: tuple[str, ...] = ("'", "'", "'", "ʼ", "´", "`", "′")


def _turkish_safe_lower(s: str) -> str:
    """#699 — Türkçe büyük "İ" karakteri Python `lower()`'da combining char üretir
    (U+0069 + U+0307 = "i̇"), regex tek char yakaladığı için `[A-Za-z...]` patterni
    ilk i'yi matchler, combining char arkasından gelen harflerle "kopuk" token
    oluşturur ("İmamoğlu" → "mamoğlu"). Çözüm: lower() öncesi "İ" → "i" doğrudan
    değişim (combining dot atlanır). ASCII "I" normal `.lower()` ile "i" olur.

    Test: "İmamoğlu" → "imamoğlu" ✅, "İBB" → "ibb" ✅, "İSKİ" → "iski" ✅
    """
    return s.replace("İ", "i").lower()


def _extract_entity_candidates(query: str, *, min_len: int = 5) -> list[str]:
    """Query'den entity adayı (özel ad / teknik terim) listesi çıkar.

    Genel kural — vakaya özel değil:
    1) Token'lara böl (`[A-Za-z+TR]+ digit/-`).
    2) min_len char altı atla.
    3) Stop kelimeleri (Türkçe + İngilizce) atla.
    4) Tüm token'ları lowercase + quote-stripped halde döndür.

    Örnek:
      "Toprakaltı sergisi ne zamandı"  → ["toprakaltı", "sergisi", "zamandı"]
        (sonra kullanıcı tarafında > min_len filter zaten var)
      "F-16 21 ülke kim kazandı"       → ["f-16", "ülke", "kazandı"]
      "Bayraktar TB3 İHA özellikleri"  → ["bayraktar", "tb3", "iha", "özellikleri"]
    """
    if not query:
        return []
    # #699 — Türkçe büyük "İ" Python lower() ile combining char üretir; tokenleme
    # öncesi safe lower (İ→i doğrudan değişim) gerek.
    # #691 — Apostrof'u SPACE ile değiştir ki Türkçe possessive suffix'ler
    # ("Tutak'ın" → "tutak", "ın") ayrı token olsun. min_len cap'i suffix'i
    # filtreler. Aksi halde apostrof tamamen kaldırılıp "tutakın" tek token
    # olur, NER eşleşmesi DB'de bulunmaz.
    pre = _turkish_safe_lower(query)
    for q in _APOSTROPHE_VARIANTS:
        pre = pre.replace(q, " ")
    norm = pre  # apostrof zaten boşluğa çevrildi
    out: list[str] = []
    seen: set[str] = set()
    for match in _ENTITY_TOKEN_RE.finditer(norm):
        tok = match.group()
        if len(tok) < min_len:
            continue
        if tok in _ENTITY_STOPWORDS:
            continue
        if tok in seen:
            continue
        seen.add(tok)
        out.append(tok)
    return out


async def rerank_rows(
    *,
    query: str,
    rows: list[dict],
    top_k: int = 10,
    db: "AsyncSession | None" = None,  # type: ignore[name-defined]
) -> list[dict]:
    """Rerank stage — sadece LLM rerank (Faz 4 answer-aware).

    #758: Cross-encoder rerank kod path KALDIRILDI. Mevcut hat artık yalnız
    LLM rerank (DeepSeek answer-aware top-3, question query'lerde tetiklenir).

    Args:
        query: User query (raw text)
        rows: hybrid_search çıktısı (RRF sıralı top-K candidates)
        top_k: Nihai döndürülecek sonuç sayısı
        db: Opsiyonel AsyncSession — verilirse LLM rerank çağrısı
            `track_provider_call(operation="llm_rerank")` ile DB'ye loglanır.

    Returns:
        LLM rerank uygulanmışsa yeniden sıralı rows, aksi halde RRF sırası.
        Question query değilse veya llm_rerank kapalıysa rows[:top_k] döner.
    """
    if not rows or not query.strip():
        return rows[:top_k]

    # RRF sırasını koru — cross-encoder kaldırıldı (#758)
    out = list(rows[:top_k])

    # #652 Faz 4 — LLM rerank (answer-extraction)
    # DeepSeek'a top-3 passage gönder + "Bu passage sorguyu cevaplıyor mu?"
    # Yes diyenler combined_score'a +0.30 boost, no diyenler -0.10.
    # Sadece soru-tipinde sorgular için (cost guard).
    try:
        llm_rerank_enabled = await _load_llm_rerank_setting()
    except Exception:
        llm_rerank_enabled = False

    if llm_rerank_enabled and len(out) >= 2 and _is_question_query(query):
        try:
            out = await _llm_rerank_answer_aware(
                query=query, rows=out, top_k_final=top_k, db=db,
            )
            logger.info(
                "llm_rerank applied: query='%s..' → top-%d reordered",
                query[:50], len(out),
            )
        except Exception as exc:
            logger.warning("llm_rerank failed, fallback RRF order: %s", exc)

    return out


async def _load_llm_rerank_setting() -> bool:
    """retrieval.llm_rerank_enabled DB → fallback default OFF."""
    try:
        from app.core.db import get_session_factory
        from app.core.settings_store import settings_store

        factory = get_session_factory()
        async with factory() as db:
            return await settings_store.get_bool(
                db, "retrieval.llm_rerank_enabled", False
            )
    except Exception:
        return False


_QUESTION_MARKERS = (
    "?", "kim", "nedir", "neyi", "neyin", "ne zaman", "nerede",
    "nasıl", "neden", "kaç", "hangi", "var mı", "ne dedi",
    "söyledi", "yaptı", "ediyor", "olacak", "kimdi", "kaçıncı",
)


def _is_question_query(query: str) -> bool:
    """Sorgu cevap-arayan tipte mi? (cost guard for LLM rerank)"""
    q = query.lower().strip()
    return any(m in q for m in _QUESTION_MARKERS)


async def _llm_rerank_answer_aware(
    *,
    query: str,
    rows: list[dict],
    top_k_final: int,
    db: "AsyncSession | None" = None,  # type: ignore[name-defined]
) -> list[dict]:
    """LLM-based final-stage rerank: passage answers question?

    Top-3 row'a DeepSeek'a "Bu passage bu soruya cevap içeriyor mu?" sorusu.
    Yanıt format: JSON [{"idx": 0, "answers": true, "score": 8}, ...]
    score 1-10. Yes (>=6): combined_score'a +0.30 boost, No (<6): -0.10.

    #LLM-rerank-telemetry: db verilirse track_provider_call(operation='llm_rerank')
    ile provider_call_logs'a kayıt yapılır (cost + latency observability).
    """
    from app.providers.base import Message
    from app.providers.registry import registry

    chat_provider = registry.route_for_tier(operation="chat", tier="free")

    # Top-3 candidate'ı LLM'e gönder
    top3 = rows[:3]
    if len(top3) < 2:
        return rows

    passages = []
    for i, r in enumerate(top3):
        title = str(r.get("title") or r.get("article_title") or "")[:150]
        body = str(r.get("summary") or r.get("chunk_text") or "")[:500]
        passages.append(f"[{i}] {title}\n{body}")

    prompt = (
        f"Sorgu: {query}\n\n"
        f"Aşağıdaki {len(passages)} pasajdan her biri için: bu pasaj sorgu "
        f"sorusuna doğrudan cevap içeriyor mu? 1-10 arası alaka skoru ver.\n\n"
        + "\n\n".join(passages)
        + '\n\nÇıktı SADECE JSON array, başka metin YOK:\n'
        + '[{"idx": 0, "answers": true, "score": 8}, ...]'
    )

    # #LLM-rerank-telemetry: db varsa track_provider_call ile sar
    if db is not None:
        from app.core.cost_tracker import track_provider_call

        async with track_provider_call(
            db=db,
            provider=chat_provider.name,
            operation="llm_rerank",
        ) as tracker:
            response = await chat_provider.generate_text(
                messages=[Message(role="user", content=prompt)],
                max_tokens=200,
                temperature=0.1,
                json_mode=True,
            )
            tracker.record(
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                cached_tokens=getattr(response, "cached_input_tokens", 0),
                model=response.model,
                cost_usd=response.cost_usd,
            )
    else:
        # Fallback: tracker yok (legacy callers). Telemetri kayıp.
        response = await chat_provider.generate_text(
            messages=[Message(role="user", content=prompt)],
            max_tokens=200,
            temperature=0.1,
            json_mode=True,
        )

    import json as _json
    text = (response.text or "").strip()
    if text.startswith("```"):
        # markdown fence strip
        text = text.split("```", 2)[1]
        if text.startswith("json\n"):
            text = text[5:]
        text = text.rstrip("`").strip()
    try:
        verdicts = _json.loads(text)
    except _json.JSONDecodeError:
        return rows

    if not isinstance(verdicts, list):
        return rows

    # Apply boost/penalty
    boosted: list[tuple[float, dict]] = []
    for i, row in enumerate(top3):
        v = next((x for x in verdicts if x.get("idx") == i), None)
        combined = float(row.get("_combined_score", 0.5))
        if v:
            score = float(v.get("score", 5))
            answers = bool(v.get("answers", False))
            if answers and score >= 6:
                combined += 0.30
            elif not answers or score < 4:
                combined -= 0.10
            row["_llm_rerank_score"] = score
            row["_llm_rerank_answers"] = answers
        boosted.append((combined, row))

    # Re-sort top-3 by new combined, append rest unchanged
    boosted.sort(key=lambda x: x[0], reverse=True)
    new_top3 = [r for _, r in boosted]
    return new_top3 + rows[3:top_k_final]
