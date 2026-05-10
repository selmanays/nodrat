"""Cross-encoder rerank wrapper (#181).

hybrid_search_* fonksiyonları RRF top-50 üretir, bu modül onu cross-encoder
ile rerank edip top-K döndürür.

Toggle: settings.reranker_enabled (False → no-op, original sıra korunur).

Provider abstraction: registry.route_for_tier(operation="rerank", tier="free")
Şu an NIM nv-rerankqa-mistral-4b-v3 (multilingual cross-encoder).
"""

from __future__ import annotations

import logging
import re
from typing import Any

from app.config import get_settings
from app.core.retrieval import strip_quote_variants
from app.providers.base import RerankResult
from app.providers.registry import registry

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
        # ASCII / single-letter stop'lar
        "the", "of", "and", "a", "an",
    ]
)

# Genel entity adayı regex: Türkçe alfabe + digit + "-" (F-16, COVID-19, AKP-MHP)
_ENTITY_TOKEN_RE = re.compile(r"[A-Za-zÇĞİıÖŞÜçğıöşü0-9][A-Za-zÇĞİıÖŞÜçğıöşü0-9\-]*")


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
    norm = strip_quote_variants(query.lower())
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


def _build_passage(row: dict) -> str:
    """Agenda card / chunk row'undan passage metni oluştur."""
    title = str(row.get("title") or row.get("article_title") or "")[:200]
    summary = str(row.get("summary") or row.get("chunk_text") or "")[:600]
    if title and summary:
        return f"{title}\n\n{summary}"
    return title or summary


def _entity_match_bonus(
    query_entities: list[str], row: dict, *, max_bonus: float = 0.10
) -> float:
    """Genel entity-aware rerank boost (#647 sistemik fix #3).

    Query'deki entity adaylarından kaç tanesi row passage'inde geçiyor sayar,
    her eşleşme için +0.025 boost (max +0.10). Reject DEĞİL — sadece sıralama
    yardımı: cross-encoder düşük logit verirse bile lexical entity match
    high-recall'u sıralarda korur.

    Vakaya özel kod yok: query'deki herhangi bir >=5 char özel-ad-benzeri
    token (Toprakaltı, Bayraktar, F-16, MKE, Galatasaray, COVID-19, ...)
    için aynı şekilde çalışır.
    """
    if not query_entities:
        return 0.0
    title = strip_quote_variants(
        str(row.get("title") or row.get("article_title") or "").lower()
    )
    summary = strip_quote_variants(
        str(row.get("summary") or row.get("chunk_text") or "").lower()
    )
    haystack = f"{title} {summary}"
    matches = sum(1 for ent in query_entities if ent in haystack)
    if not matches:
        return 0.0
    return min(max_bonus, matches * 0.025)


async def _load_rerank_settings(settings: Any) -> tuple[bool, int, float]:
    """Load runtime-tunable rerank settings (DB override → fallback).

    Returns: (enabled, min_query_words, min_combined_score)
    #266 — admin paneli üzerinden tune edilebilir.
    """
    enabled = settings.reranker_enabled
    min_query_words = settings.rerank_min_query_words
    min_combined = settings.rerank_min_combined_score
    try:
        from app.core.db import get_session_factory
        from app.core.settings_store import settings_store

        factory = get_session_factory()
        async with factory() as db:
            enabled = await settings_store.get_bool(
                db, "rerank.enabled", enabled
            )
            min_query_words = await settings_store.get_int(
                db, "rerank.min_query_words", min_query_words
            )
            min_combined = await settings_store.get_float(
                db, "rerank.min_combined_score", min_combined
            )
    except Exception as exc:  # pragma: no cover — config DB miss → fallback
        logger.debug("rerank settings load fallback: %s", exc)
    return enabled, min_query_words, min_combined


async def rerank_rows(
    *,
    query: str,
    rows: list[dict],
    top_k: int = 10,
) -> list[dict]:
    """RRF sonrası rerank stage.

    Args:
        query: User query (raw text)
        rows: hybrid_search çıktısı (her dict'te 'id', 'title', 'summary' var)
        top_k: Nihai döndürülecek sonuç sayısı

    Returns:
        Reranked rows (her row'a `_rerank_score` eklenir).
        Reranker disabled veya hata ise original sıra korunur.
    """
    settings = get_settings()

    # #266 — runtime-tunable settings (DB override → fallback hardcoded)
    enabled, min_query_words, min_combined = await _load_rerank_settings(
        settings
    )
    if not enabled:
        return rows[:top_k]

    if not rows or not query.strip():
        return rows[:top_k]

    # #253 — Cross-encoder kısa query'lerde başarısız (NIM rerank-qa "CHP",
    # "İmamoğlu" gibi tek-term'leri sürekli negatif logit'e işaretliyor →
    # alakalı CHP haberleri drop ediliyordu). Kısa query'ler için RRF sırasını
    # koru — RRF zaten title trigram + n-gram phrase match yapıyor.
    if len(query.split()) <= min_query_words - 1:
        logger.info(
            "rerank skip: short query (words=%d, min=%d)",
            len(query.split()),
            min_query_words,
        )
        return rows[:top_k]

    try:
        provider = registry.route_for_tier(operation="rerank", tier="free")
    except (RuntimeError, NotImplementedError) as exc:
        logger.warning("rerank provider unavailable, skip: %s", exc)
        return rows[:top_k]

    passages = [_build_passage(r) for r in rows]

    # #190 — cost_tracker entegrasyonu (admin RAG observability)
    factory = None
    try:
        from app.core.db import get_session_factory

        factory = get_session_factory()
    except Exception:  # pragma: no cover
        factory = None

    try:
        if factory is not None:
            from app.core.cost_tracker import track_provider_call

            async with factory() as db:
                async with track_provider_call(
                    db=db,
                    provider=provider.name,
                    operation="rerank",
                ) as tracker:
                    results = await provider.rerank(
                        query=query,
                        documents=passages,
                        top_k=min(top_k, len(passages)),
                    )
                    tracker.record(
                        input_tokens=len(query.split())
                        + sum(len(p.split()) for p in passages),
                        output_tokens=0,
                        cost_usd=0.0,
                        model=getattr(
                            provider, "_default_model", "nim_rerank"
                        ),
                    )
                await db.commit()
        else:
            results = await provider.rerank(
                query=query,
                documents=passages,
                top_k=min(top_k, len(passages)),
            )
    except Exception as exc:  # pragma: no cover
        logger.warning("rerank call failed, fallback to RRF order: %s", exc)
        return rows[:top_k]

    if not results:
        return rows[:top_k]

    # Index → rerank score map
    score_by_idx = {r.index: r.score for r in results}

    # #251/#259 — Combined ranking: alaka ön-koşullu importance boost.
    #   logit > 0 (cross-encoder pozitif sinyal):
    #     0.65 × sigmoid(logit) + 0.35 × importance
    #   logit ≤ 0 (alakasız):
    #     linear penalty × importance — tamamen sıfırlamak yerine kademeli
    #     skala. logit=-NEG_FLOOR ile drop, logit=0 ile yüksek puan.
    #     Önceki sürüm sadece sigmoid kullanıyordu → "Otomotiv ihracat"
    #     gibi orta-alakalı + high-imp kartlar Türkiye-ekonomi sorgusunda
    #     top'a çıkamıyordu (logit=-10 → 0 → drop).
    #   Adana sel (logit=-16, imp=0.85) ise factor=0.2 ile threshold altı.
    import math as _math

    RERANK_W = 0.65
    IMP_W = 0.35
    NEG_FLOOR = 20.0  # logit=-20 → tamamen sıfır
    MIN_COMBINED = min_combined

    # #647 sistemik fix #3 — entity-aware boost (genel kural):
    # Query'den çıkarılan >=5 char özel-ad-benzeri token'lar her row passage'inde
    # var mı kontrol edilir. Lexical eşleşme cross-encoder negatif logit'e
    # rağmen high-recall'u korur (Toprakaltı, Bayraktar, F-16, MKE vb. için
    # aynı şekilde çalışır — vakaya özel kod yok).
    query_entities = _extract_entity_candidates(query)

    def _combined(idx: int) -> float:
        logit = score_by_idx.get(idx, 0.0)
        try:
            imp = float(rows[idx].get("importance_score") or 0.5)
        except (TypeError, ValueError):
            imp = 0.5
        bonus = _entity_match_bonus(query_entities, rows[idx])
        if logit > 0:
            sig = 1.0 / (1.0 + _math.exp(-logit))
            return RERANK_W * sig + IMP_W * imp + bonus
        # logit ≤ 0: linear penalty
        # logit=-20 → factor=0,  logit=-10 → factor=0.5,  logit=0 → factor=1
        # entity bonus negatif logit'te de uygulanır: high-recall korunması.
        factor = max(0.0, 1.0 + logit / NEG_FLOOR)
        return factor * (0.5 * imp + 0.2) + bonus

    enriched = [(idx, score_by_idx[idx], _combined(idx)) for idx in score_by_idx]
    enriched.sort(key=lambda x: x[2], reverse=True)

    out: list[dict] = []
    dropped_low_relevance = 0
    for idx, raw_logit, combined in enriched[:top_k]:
        if 0 <= idx < len(rows):
            if combined < MIN_COMBINED:
                dropped_low_relevance += 1
                continue
            row = dict(rows[idx])
            row["_rerank_score"] = round(float(raw_logit), 4)
            row["_combined_score"] = round(float(combined), 4)
            out.append(row)

    logger.info(
        "rerank applied: input=%d → top-%d (dropped=%d), "
        "top_combined=%.3f, top_logit=%.3f",
        len(rows),
        len(out),
        dropped_low_relevance,
        out[0].get("_combined_score", 0.0) if out else 0.0,
        out[0].get("_rerank_score", 0.0) if out else 0.0,
    )

    # #652 Faz 4 — Final-stage LLM rerank (answer-extraction).
    # Cross-encoder relevance skorlar, ama "Bu passage sorguyu CEVAPLAR mı?"
    # sorusunu yapamaz — niş soru-cevap için kritik. LLM (DeepSeek)'a
    # top-K içinden top-3 passage gönder + yes/no + score (1-10) iste.
    # Yes diyenler combined_score'a +0.30 boost, no diyenler -0.10.
    # Sadece soru-tipinde sorgular için (?, "kim", "nasıl", "nedir", "var mı")
    # — generic kategori sorgularında skip (cost guard).
    try:
        llm_rerank_enabled = await _load_llm_rerank_setting()
    except Exception:
        llm_rerank_enabled = False

    if llm_rerank_enabled and len(out) >= 2 and _is_question_query(query):
        try:
            out = await _llm_rerank_answer_aware(
                query=query, rows=out, top_k_final=top_k,
            )
            logger.info(
                "llm_rerank applied: query='%s..' → top-%d reordered",
                query[:50], len(out),
            )
        except Exception as exc:
            logger.warning("llm_rerank failed, fallback CE order: %s", exc)

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
    *, query: str, rows: list[dict], top_k_final: int
) -> list[dict]:
    """LLM-based final-stage rerank: passage answers question?

    Top-3 row'a DeepSeek'a "Bu passage bu soruya cevap içeriyor mu?" sorusu.
    Yanıt format: JSON [{"idx": 0, "answers": true, "score": 8}, ...]
    score 1-10. Yes (>=6): combined_score'a +0.30 boost, No (<6): -0.10.
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
