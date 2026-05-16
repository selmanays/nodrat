"""Chat LLM tools — function calling definitions + executors (#822).

Plan: /Users/selmanay/.claude/plans/nerdi-in-ekilde-faz-2-unified-nebula.md

Mimari: LLM haber kaynaklarında kullanıcının sorusunu cevaplayacak bilgi
bulamazsa, `search_wikipedia` tool'unu KENDİSİ çağırır. Backend tool'u
çalıştırır, sonucu LLM'e geri verir, LLM Wikipedia kaynaklı final cevap
üretir. Tek akış — confidence routing / CTA banner / kullanıcı onayı YOK.

News-first STRICT (C2): tool sadece query_class != 'news_query' iken
LLM'e sunulur (chat_stream tarafında karar). "Trump bugün ne dedi?"
haber kaynaklarından cevaplanır, Wikipedia'ya düşmez.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


def _since_hours_from_timeframes(
    timeframes: Any, now: Any, *, default_h: int, min_h: int = 6
) -> int:
    """Planner timeframe(ler)inden retrieval pencere saatini türet (#906).

    #845 agentic sarmalı planner'ın ürettiği timeframe'i (örn. "bugün" →
    2026-05-16 00:00→23:59) retrieval'a HİÇ iletmiyordu; `since_hours`
    24*90 SABİT → "günün gelişmeleri" sorgusuna 90 günlük havuzdan eski
    semantik-benzer haberler giriyordu. #879 ile aynı aile: tool sarmalı,
    alt-katmanın ürettiği ZAMAN boyutunu düşürmemeli (planner prompt
    "retrieval bu tarihi filter eder" der — bağ #845'te kopmuştu).

    En ESKİ `from_iso` baz alınır (çoklu/comparison → en geniş pencere).
    Sonuç clamp [min_h, default_h]: default_h'yi (90g) ASLA aşmaz (mevcut
    tavan korunur), min_h timezone/saat-sınırı güvenliği. timeframe
    yok / parse edilemez → default_h (davranış değişmez). RRF/ranking'e
    DOKUNMAZ — yalnız `since_hours` (published_at >= since) filtresi.
    """
    if not timeframes or now is None:
        return default_h
    if getattr(now, "tzinfo", None) is None:
        try:
            now = now.replace(tzinfo=timezone.utc)
        except Exception:
            return default_h
    oldest: datetime | None = None
    for tf in timeframes:
        raw = (getattr(tf, "from_iso", "") or "").strip()
        if not raw:
            continue
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except Exception:
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        if oldest is None or dt < oldest:
            oldest = dt
    if oldest is None:
        return default_h
    delta_h = (now - oldest).total_seconds() / 3600.0
    return max(min_h, min(default_h, math.ceil(delta_h)))


# OpenAI-compatible function tanımı (DeepSeek native function calling).
SEARCH_WIKIPEDIA_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "search_wikipedia",
        "description": (
            "Verilen haber kaynaklarında kullanıcının sorusunu cevaplayacak "
            "bilgi YOKSA bu aracı çağır. Wikipedia'dan kaynaklı bilgi getirir "
            "(kişi yaşı, kurum kuruluş yılı, nüfus, tanım gibi evergreen "
            "factual bilgiler). Güncel haber/olay sorularında KULLANMA — "
            "onlar zaten haber kaynaklarında olmalı. Sadece haber "
            "kaynaklarında cevap bulamadığında çağır."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "SADECE aranan varlığın kanonik Türkçe Wikipedia "
                        "madde adı. Soru kelimelerini, niteleyicileri, "
                        "zaman/sezon/bölüm/sayı ifadelerini ÇIKAR — bunlar "
                        "arama relevance'ını bozar. Yabancı özel adların "
                        "Türkçe Wikipedia karşılığını kullan (Wikipedia TR "
                        "madde başlığı nasılsa öyle). "
                        "Örnek: 'Stargate SG-1 4. sezon ne zaman yayınlandı' "
                        "→ query='Yıldız Geçidi SG-1' (DİZİNİN kendisi, "
                        "İngilizce ad + 'sezon' DEĞİL). "
                        "'Trump kaç yaşında' → query='Donald Trump'. "
                        "'NATO ne zaman kuruldu' → query='NATO'."
                    ),
                },
            },
            "required": ["query"],
        },
    },
}


async def execute_search_wikipedia(
    arguments: dict[str, Any],
    *,
    cite_start: int = 0,
) -> tuple[str, list[dict[str, Any]]]:
    """search_wikipedia tool'unu çalıştır.

    Args:
        arguments: LLM'in tool call argümanları — {"query": "..."}.
        cite_start: #851 — citation token'ları GLOBAL benzersiz olsun diye
          döngü başlangıç offset'i. Token = `[{cite_start+k}]` (tek `[n]`
          namespace; multi-round'da çağrılar çakışmaz). source_type alanı
          news/wikipedia ayrımını taşır (UI badge).

    Returns:
        (tool_result_text, sources_used)
        - tool_result_text: LLM'e geri verilecek metin, `[n]` numaralı
        - sources_used: source list (source_type='wikipedia', `cite` alanı)

    Hata/boş sonuç durumunda: ("Wikipedia'da sonuç bulunamadı.", [])
    """
    query = str(arguments.get("query") or "").strip()
    if not query:
        return "Geçersiz Wikipedia sorgusu (boş).", []

    try:
        from app.providers.wikipedia import (
            WIKIDATA_FACTUAL_PROPS,
            get_wikipedia_provider,
        )

        provider = await get_wikipedia_provider()
        # #827 — Wikipedia prose (bağlam) + Wikidata structured facts.
        # REST summary doğum tarihi/nüfus/kuruluş (infobox) İÇERMEZ —
        # bu factual sorular Wikidata P-property'lerinde.
        #
        # #863 KRİTİK — bulletproof entity→fact zinciri:
        #  1. Wikipedia full-text ara (niteleyiciye TOLERANSlı; "Robert
        #     C. Cooper doğum tarihi" → doğru SAYFAyı bulur).
        #  2. O sayfanın `wikibase_item`'ı = DİL-BAĞIMSIZ kesin QID
        #     (fuzzy wbsearchentities yerine sitelink; TR sayfası da
        #     global Q'ya bağlı → yanlış entity ambiguity yok).
        #  3. `wbgetentities` (güvenilir Action API) ile P-property'ler.
        # Eski akış SPARQL (flaky 400/502) + fuzzy entity-search
        # (niteleyici-hassas) yüzünden TÜM "X kaç yaşında/doğum tarihi"
        # sorularını kırıyordu (prod conv 2c9bb90a).
        try:
            articles = await provider.search(query, lang=None, top_k=3)
        except Exception as exc:
            logger.warning("wikipedia search exc: %s", exc)
            articles = []
        try:
            _qid = None
            if articles:
                _qid = await provider.wikidata_qid_for_title(
                    articles[0].title, articles[0].lang,
                )
            wikidata = await provider.wikidata_factual(
                query, lang="tr", qid=_qid,
            )
        except Exception as exc:
            logger.warning("wikidata exc: %s", exc)
            wikidata = None
    except Exception as exc:
        logger.warning("execute_search_wikipedia failed: %s", exc)
        return f"Wikipedia araması başarısız: {exc}", []

    if not articles and wikidata is None:
        return (f"'{query}' için Wikipedia'da sonuç bulunamadı.", [])

    blocks: list[str] = []
    sources_used: list[dict[str, Any]] = []

    # 1. Wikidata structured facts (varsa — factual soruların asıl cevabı)
    if wikidata is not None and wikidata.properties:
        # Türkçe okunur label mapping (WIKIDATA_FACTUAL_PROPS = code→en_key)
        _TR_LABEL = {
            "P569": "Doğum tarihi",
            "P570": "Ölüm tarihi",
            "P1082": "Nüfus",
            "P571": "Kuruluş tarihi",
            "P36": "Başkent",
            "P39": "Pozisyon/görev",
            "P17": "Ülke",
            "P102": "Siyasi parti",
        }
        fact_lines = []
        for code, val in wikidata.properties.items():
            label = _TR_LABEL.get(code, WIKIDATA_FACTUAL_PROPS.get(code, code))
            # Tarih ISO formatı: "1946-06-14T00:00:00Z" → "1946-06-14"
            v = str(val)
            if "T" in v and v[:4].isdigit():
                v = v.split("T", 1)[0]
            fact_lines.append(f"- {label}: {v}")
        if fact_lines:
            _c = cite_start + len(sources_used) + 1
            blocks.append(
                f"[{_c}] Wikidata — {wikidata.label} (doğrulanmış yapısal veri)\n"
                + "\n".join(fact_lines)
            )
            sources_used.append(
                {
                    "source_type": "wikipedia",
                    "source_name": "Wikidata",
                    "title": wikidata.label,
                    "url": f"https://www.wikidata.org/wiki/{wikidata.qid}",
                    "license": "CC0 1.0",
                    "cite": f"[{_c}]",
                }
            )

    # 2. Wikipedia prose (bağlam/açıklama)
    for a in articles:
        idx = cite_start + len(sources_used) + 1
        blocks.append(f"[{idx}] {a.title} ({a.lang})\n{a.summary}")
        sources_used.append(
            {
                "source_type": "wikipedia",
                "source_name": f"Wikipedia ({a.lang.upper()})",
                "title": a.title,
                "url": a.url,
                "license": a.license,
                "cite": f"[{idx}]",
            }
        )

    if not blocks:
        return (f"'{query}' için Wikipedia'da sonuç bulunamadı.", [])

    result_text = (
        "Kaynaklar (her olguyu içeren kaynağı [n] formatında — köşeli "
        "parantez + numara — citation ile göster; 25 kelimeden uzun direct "
        "quote yapma; Wikidata yapısal verisi kesin/doğrulanmıştır, "
        "tarih/sayı için onu öncele):\n\n"
        + "\n\n---\n\n".join(blocks)
    )
    return result_text, sources_used


SEARCH_NEWS_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "search_news",
        "description": (
            "Nodrat'ın küratörlü güncel haber arşivinde arama yapar — "
            "kişiler, kurumlar, olaylar, açıklamalar, gelişmeler, herhangi "
            "haberle ilgili olabilecek HER konu için BİRİNCİL kaynağın. "
            "Kullanıcı güncel/araştırma niteliğinde bir şey sorduğunda "
            "(birinin ne dediği, bir olayın durumu, bir konunun son hâli) "
            "ÖNCE bunu çağır. Selamlama, kimlik veya konuşma hakkındaki "
            "meta sorular için ÇAĞIRMA."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "Haber arşivinde aranacak konu — kullanıcının "
                        "sorusunun bağlamlı, standalone Türkçe ifadesi "
                        "(follow-up ise önceki konuşmadan çözülmüş hâli). "
                        "Doğal arama cümlesi: 'Trump Çin ziyareti son "
                        "açıklamalar', 'İstanbul deprem son durum'."
                    ),
                },
            },
            "required": ["query"],
        },
    },
}


async def execute_search_news(
    arguments: dict[str, Any],
    *,
    db: Any,
    now: Any,
    user: Any,
    query_vec_hint: list[float] | None = None,
    content_top_k: int = 5,
    cite_start: int = 0,
) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    """search_news tool — Nodrat haber arşivi retrieval (mevcut pipeline sarmalı).

    Kalite makinesi DEĞİŞMEZ: planner → embed → hybrid_search_chunks
    (top_k/candidate_pool/since_hours/critical_entities) production parite.
    Sadece "her zaman ön-retrieval" yerine LLM tool kararıyla tetiklenir.

    Returns:
        (tool_result_text, sources, meta)
        - tool_result_text: [1][2] indeksli chunk blokları
        - sources: source_type='news' kaynak listesi (UI + citation)
        - meta: {query_class, topic, chunk_count} telemetri
    """
    query = str(arguments.get("query") or "").strip()
    if not query:
        return "Geçersiz haber sorgusu (boş).", [], {}

    from app.core.retrieval import hybrid_search_chunks
    from app.prompts.query_planner import plan_query
    from app.providers.registry import registry

    # 1. Planner (topic_query + critical_entities + query_class telemetri)
    try:
        plan_result = await plan_query(
            user_request=query,
            current_time=now,
            user_locale=getattr(user, "locale", "tr-TR") or "tr-TR",
            user_tier=getattr(user, "tier", "free"),
        )
        topic = getattr(plan_result, "topic_query", query) or query
        critical_entities = getattr(plan_result, "critical_entities", None) or []
        query_class = getattr(plan_result, "query_class", "news_query")
        plan_timeframes = getattr(plan_result, "timeframes", None) or []
    except Exception as exc:
        logger.warning("search_news planner failed: %s", exc)
        topic, critical_entities, query_class = query, [], "news_query"
        plan_timeframes = []

    # 2. Embedding (topic — ham sorgudan anlamlı farklıysa yeni embed)
    vec = query_vec_hint
    if topic.strip().lower() != query.strip().lower() or vec is None:
        try:
            _emb = registry.route_for_tier(operation="embedding", tier="free")
            _re = await _emb.create_embedding([topic])
            if _re.vectors:
                vec = _re.vectors[0]
        except Exception as exc:
            logger.warning("search_news embed failed: %s", exc)

    if vec is None:
        return (f"'{query}' için haber araması yapılamadı.", [], {})

    # 3. Hybrid retrieval — #906: planner timeframe'i retrieval penceresine
    # bağla (since_hours). top_k/candidate_pool/RRF/critical_entities/
    # rerank AYNI ("kalite makinesi DEĞİŞMEZ"); yalnız zaman penceresi
    # planner niyetine göre daralır. Dar pencerede sonuç YOKSA 90g'e düş
    # (kullanıcı: "güncelde yoksa genele"; "bulunamadı" riski yok).
    _FULL_H = 24 * 90
    since_h = _since_hours_from_timeframes(
        plan_timeframes, now, default_h=_FULL_H
    )
    _fallback_used = False  # #928 Ç2 — 90g fallback dalı recency-sort flag
    try:
        chunks = await hybrid_search_chunks(
            db,
            query_text=topic,
            query_vector=vec,
            top_k=10,
            candidate_pool=60,
            since_hours=since_h,
            critical_entities=critical_entities or None,
            rerank=False,
        )
        if not chunks and since_h < _FULL_H:
            logger.info(
                "search_news: dar pencere (%dh) boş → 90g fallback", since_h,
            )
            _fallback_used = True
            chunks = await hybrid_search_chunks(
                db,
                query_text=topic,
                query_vector=vec,
                top_k=10,
                candidate_pool=60,
                since_hours=_FULL_H,
                critical_entities=critical_entities or None,
                rerank=False,
            )
    except Exception as exc:
        logger.warning("search_news retrieval failed: %s", exc)
        return (f"'{query}' için haber araması başarısız.", [], {})

    if not chunks:
        return (
            f"'{query}' için güncel haber arşivinde sonuç bulunamadı.",
            [],
            {"query_class": query_class, "topic": topic, "chunk_count": 0},
        )

    def _pub_date(chunk: dict[str, Any]) -> str | None:
        """published_at → ISO gün (datetime | str | None toleranslı).

        retrieval.py her chunk'a `published_at` koyar; agentic tool
        sarmalı bunu LLM'e iletmezse model haberin NE ZAMAN olduğunu
        bilemez → eski haberi 'bugün' sanır (denetim 2026-05-15 prod
        kanıtı: conv 0a097738 'Rize mitingi 6 gün önceydi' → hâlâ
        'bugün'). Olayın zamanı = haberin yayın tarihi.
        """
        p = chunk.get("published_at")
        if not p:
            return None
        try:
            return p.strftime("%Y-%m-%d")
        except Exception:
            s = str(p)[:10]
            return s or None

    # #928 Ç2 — fallback dalı recency-sort. 90g'ye düşüldüyse RRF semantic
    # en-yakını recency-kör (eski-prototipik haber taze-niş'i yener — conv
    # 74eecc15: "Özgür Özel son haber" → 3 May Karabük). Yalnız FALLBACK
    # dalı sıralanır (ana dal RRF/#660 DEĞİŞMEZ; fallback zaten kalite
    # makinesi dışı kurtarma). ISO 'YYYY-MM-DD' string sort = kronolojik.
    if _fallback_used and chunks:
        chunks = sorted(
            chunks, key=lambda c: _pub_date(c) or "", reverse=True
        )

    # #928 Ç3 — tazelik boşluğu kod-sinyali (prompt değil — #906/#879
    # deseni). Kullanıcı güncel istedi (timeframe daraldı) ama en yeni
    # sonuç eski → scope-aware dürüstlük için LLM'e + meta'ya sinyal.
    recency_requested = since_h < _FULL_H
    _newest = max((d for d in (_pub_date(c) for c in chunks) if d),
                  default=None)
    freshness_gap_days: int | None = None
    if _newest and now is not None:
        try:
            _nd = now.date() if hasattr(now, "date") else None
            if _nd is not None:
                freshness_gap_days = (
                    _nd - datetime.fromisoformat(_newest).date()
                ).days
        except Exception:
            freshness_gap_days = None

    top_k = max(3, min(content_top_k, 15))
    # #912 — sunum-katmanı article-collapse. #661 `_expand_parent_documents`
    # aynı article'dan birden çok chunk verir (LLM context zenginliği:
    # çevreleyen paragraflar answer extraction'ı yükseltir — KORUNUR, tüm
    # chunk'lar block'a girer). Ama her chunk'a ayrı [n] vermek kullanıcıya
    # aynı haberi N kez gösterir + LLM dup cite eder (prod: [1]=[9] vb.).
    # Çözüm: cite index `article_id` bazlı — aynı article'ın tüm chunk'ları
    # TEK [n]; `sources` (kullanıcı kartı) article başına TEK (ilk = en iyi
    # RRF chunk = temsilci). cite_start / multi-round global sayaç (#851)
    # korunur. Retrieval/RRF/#661 DEĞİŞMEZ — yalnız sunum.
    sources: list[dict[str, Any]] = []
    blocks: list[str] = []
    _article_cite: dict[str, int] = {}
    _next_cite = cite_start + 1
    for c in chunks:
        aid = str(c.get("article_id") or "")
        # article_id yoksa chunk başına benzersiz (eski güvenli davranış)
        key = aid or f"_c:{c.get('chunk_id') or c.get('id') or id(c)}"
        text = (c.get("chunk_text") or "")[:2500]
        title = (c.get("article_title") or "")[:200]
        sname = c.get("source_name") or ""
        pd = _pub_date(c)
        date_lbl = (
            f" (yayın tarihi: {pd})" if pd else " (yayın tarihi: bilinmiyor)"
        )
        i = _article_cite.get(key)
        if i is None:
            if len(_article_cite) >= top_k:
                # Yeterli DISTINCT article toplandı; yeni haber alma.
                # (Mevcut article'ların ek chunk'ları yine block'a girer
                #  — #661 parent-doc context zenginliği bozulmaz.)
                continue
            i = _next_cite
            _article_cite[key] = i
            _next_cite += 1
            sources.append(
                {
                    "source_type": "news",
                    "article_id": aid,
                    "chunk_id": str(c.get("chunk_id") or c.get("id") or ""),
                    "title": title,
                    "url": c.get("article_canonical_url") or c.get("url"),
                    "source_name": sname,
                    "published_at": pd,
                    "cite": f"[{i}]",
                }
            )
        blocks.append(f"[{i}] {sname} — {title}{date_lbl}\n{text}")

    # #928 Ç3 — kod-üretilen scope-aware tazelik notu (LLM'e, prompt
    # değil; #879/#906 deseni). Kullanıcı güncel istedi ama en yeni
    # sonuç eski → sahte güncellik YASAK, açık scope-aware çerçeve.
    _freshness_note = ""
    if recency_requested and freshness_gap_days is not None and (
        freshness_gap_days >= 2
    ):
        _freshness_note = (
            f"DİKKAT — TAZELİK: Kullanıcı güncel/son haber istedi ama "
            f"elindeki EN YENİ kaynak {freshness_gap_days} gün önce "
            f"({_newest}). Sahte güncellik YASAK: '{_newest}' tarihinden "
            f"daha yeni sonuç bulunmadığını AÇIKÇA, scope-aware söyle "
            f"(örn. 'son {freshness_gap_days} günde daha yeni habere "
            f"ulaşamadım; en güncel kayıt {_newest}'). Bunu en güncel "
            f"haberi verirken belirt; eski haberi 'son/güncel' diye "
            f"sunma.\n\n"
        )
    result_text = (
        _freshness_note
        + "Güncel haber arşivi sonuçları. Her blok '(yayın tarihi: …)' "
        "taşır — bir olayın NE ZAMAN olduğu o haberin yayın tarihidir "
        "(bugünün tarihi DEĞİL). Her cümlede [n] citation ile kullan, "
        "SADECE bu metinde geçen olguları yaz:\n\n"
        + "\n\n---\n\n".join(blocks)
    )
    return (
        result_text,
        sources,
        {
            "query_class": query_class,
            "topic": topic,
            "chunk_count": len(chunks),
            "source_count": len(sources),  # #912 — distinct article kartı
            "recency_requested": recency_requested,  # #928 Ç3
            "newest_published_at": _newest,  # #928 Ç3
            "freshness_gap_days": freshness_gap_days,  # #928 Ç3
        },
    )


# Tool registry — chat_stream tool dispatch için (search_news db gerektirir,
# chat_stream tarafında per-request closure ile bind edilir)
CHAT_TOOLS: dict[str, Any] = {
    "search_wikipedia": execute_search_wikipedia,
}

# LLM'e sunulacak tool tanımları — search_news BİRİNCİL (Nodrat moat),
# search_wikipedia evergreen fallback. Sıra LLM'e öncelik sezgisi verir.
CHAT_TOOL_DEFINITIONS: list[dict[str, Any]] = [
    SEARCH_NEWS_TOOL,
    SEARCH_WIKIPEDIA_TOOL,
]


__all__ = [
    "SEARCH_WIKIPEDIA_TOOL",
    "SEARCH_NEWS_TOOL",
    "CHAT_TOOLS",
    "CHAT_TOOL_DEFINITIONS",
    "execute_search_wikipedia",
    "execute_search_news",
]
