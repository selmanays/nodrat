"""HyDE (Hypothetical Document Embeddings) prompt (#720, taşındı).

Önceden app_generate.py:435 + app_generate_stream.py:420'de inline'dı.
Admin /prompts sayfasından override edilebilir.

Kullanım: prompts_store.get(db, "hyde_doc", HYDE_PROMPT_TEMPLATE) →
ardından `.format(query=plan.topic_query)` ile çağır.
"""

from __future__ import annotations


# {query} placeholder zorunlu — admin override ederken bu placeholder
# muhafaza edilmeli. Aksi halde KeyError → fallback default'a düşer.
SYSTEM_PROMPT = (
    "Aşağıdaki sorguya 1-2 cümlelik hipotetik bir haber başlığı + "
    "açılış cümlesi üret. Gerçek olmak zorunda değil — sorgunun "
    "semantic uzayını yakalayan bir tahmin. Kaynak referansı ekleme.\n\n"
    "Sorgu: {query}\n\n"
    "Hipotetik haber:"
)


def render_hyde_prompt(query: str, *, template: str | None = None) -> str:
    """HyDE prompt'u {query} placeholder substitusyonu ile render et.

    Args:
        query: Plan topic_query (genelde planner'dan).
        template: Opsiyonel admin override; None ise SYSTEM_PROMPT default.

    Returns:
        LLM'e gönderilecek user message content.
    """
    tmpl = template or SYSTEM_PROMPT
    try:
        return tmpl.format(query=query)
    except (KeyError, IndexError):
        # Admin {query} placeholder'ı sildiyse default'a düş
        return SYSTEM_PROMPT.format(query=query)
