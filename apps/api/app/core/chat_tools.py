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
from typing import Any

logger = logging.getLogger(__name__)


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
                        "Wikipedia'da aranacak konu — kullanıcının sorusundaki "
                        "ana entity/kavram (örn. 'Donald Trump', 'NATO', "
                        "'Çin nüfusu'). Türkçe yaz."
                    ),
                },
            },
            "required": ["query"],
        },
    },
}


async def execute_search_wikipedia(
    arguments: dict[str, Any],
) -> tuple[str, list[dict[str, Any]]]:
    """search_wikipedia tool'unu çalıştır.

    Args:
        arguments: LLM'in tool call argümanları — {"query": "..."}.

    Returns:
        (tool_result_text, sources_used)
        - tool_result_text: LLM'e geri verilecek metin (Wikipedia özetleri,
          [W1][W2] formatında numaralı)
        - sources_used: chat message'a kaydedilecek source list
          (source_type='wikipedia')

    Hata/boş sonuç durumunda: ("Wikipedia'da sonuç bulunamadı.", [])
    """
    query = str(arguments.get("query") or "").strip()
    if not query:
        return "Geçersiz Wikipedia sorgusu (boş).", []

    try:
        from app.providers.wikipedia import get_wikipedia_provider

        provider = await get_wikipedia_provider()
        articles = await provider.search(query, lang=None, top_k=3)
    except Exception as exc:
        logger.warning("execute_search_wikipedia failed: %s", exc)
        return f"Wikipedia araması başarısız: {exc}", []

    if not articles:
        return (
            f"'{query}' için Wikipedia'da sonuç bulunamadı.",
            [],
        )

    # LLM'e numaralı kaynak bloğu (W1, W2, ...)
    blocks = []
    sources_used = []
    for i, a in enumerate(articles, start=1):
        blocks.append(f"[W{i}] {a.title} ({a.lang})\n{a.summary}")
        sources_used.append(
            {
                "source_type": "wikipedia",
                "source_name": f"Wikipedia ({a.lang.upper()})",
                "title": a.title,
                "url": a.url,
                "license": a.license,
            }
        )

    result_text = (
        "Wikipedia kaynakları (bunları [W1][W2] formatında citation ile "
        "kullan, 25 kelimeden uzun direct quote yapma):\n\n"
        + "\n\n---\n\n".join(blocks)
    )
    return result_text, sources_used


# Tool registry — chat_stream tool dispatch için
CHAT_TOOLS: dict[str, Any] = {
    "search_wikipedia": execute_search_wikipedia,
}

# LLM'e sunulacak tool tanımları listesi
CHAT_TOOL_DEFINITIONS: list[dict[str, Any]] = [SEARCH_WIKIPEDIA_TOOL]


__all__ = [
    "SEARCH_WIKIPEDIA_TOOL",
    "CHAT_TOOLS",
    "CHAT_TOOL_DEFINITIONS",
    "execute_search_wikipedia",
]
