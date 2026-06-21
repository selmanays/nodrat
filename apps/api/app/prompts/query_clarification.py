"""Sorgu-netleştirme (#1701) — 0-kaynak/anlaşılmayan sorgu için niyet-anlama.

Türkçe haber korpusunda kullanıcının sorusuna DAYANAK KAYNAK bulunamadığında
(app_research_stream _cited_only_strict + not all_sources + substantive), bland
"bulamadım" yerine: uydurma CEVAP vermeden kullanıcının niyetini anlayıp kısa
açıklama + 2-3 yeniden-ifade/netleştirme önerisi üretir. Öneriler followup-chip
mekanizmasıyla gösterilir (tıkla → yeni sorgu).

Ayrı, hafif, best-effort LLM call (followup.py deseni #961); çıktı satır-bazlı
(JSON DEĞİL — küçük model JSON güvenilmezliği #819/#840 dersi), tolerant parse.
Citation-safe: yalnız netleştirme/öneri, olgusal iddia YOK (ana cevaba sızmaz —
ayrı call). Prompt admin-tunable (prompts_store "query_clarification").
"""

from __future__ import annotations

PROMPT_VERSION = "1.0.0"  # #1701

SYSTEM_PROMPT = """Sen Nodrat'ın sorgu-netleştirme yardımcısısın. Türkçe haber \
korpusunda kullanıcının sorusuna DAYANAK OLUŞTURACAK KAYNAK BULUNAMADI. Görevin: \
UYDURMA CEVAP VERMEDEN, kullanıcının ne sormak istediğini anlamaya çalışıp kısa bir \
açıklama + 2-3 netleştirme/yeniden-ifade önerisi üretmek.

ÇIKTI BİÇİMİ — tam olarak şu satırlar (markdown başlık/numara/ek metin YOK):
MESAJ: <1-2 cümle: dayanak kaynak bulunamadığını söyle + olası niyeti nazikçe belirt>
- <öneri 1>
- <öneri 2>
- <öneri 3>

KURALLAR:
- ASLA olgusal cevap, tarih, sayı veya iddia UYDURMA — yalnız netleştirme + öneri.
- Öneriler kullanıcının AĞZINDAN, somut, Türkçe gündem/haber konusuna yönelik \
yeniden-ifadelerdir ("X'in son açıklaması ne?", "Y maçının sonucu ne oldu?"). \
Cevabı tekrar ettiren/genel-geçer ("daha fazla bilgi") öneri YASAK.
- Sorguda yazım hatası/typo varsa düzeltilmiş biçimi öner.
- MESAJ kısa + dürüst ("Bu konuda dayanak kaynak bulamadım …"). Asistan-jargonu \
("istersen sana…"), öznel yorum, editoryal dil YOK (#851/#958)."""


def render_user_payload(query: str) -> str:
    """LLM'e geçen kullanıcı içeriği — kaynak bulunamayan sorgu."""
    return f"Kullanıcının sorusu (korpusta dayanak kaynak bulunamadı):\n{(query or '').strip()}"


def parse_clarification(text: str, *, max_suggestions: int = 3) -> dict | None:
    """Satır-bazlı tolerant parse → {message, suggestions}. Geçersizse None.

    'MESAJ:' satırı → message; '- ' satırları → suggestions (strip, dedupe,
    boş-ele, limit). MESAJ yoksa ilk bülten-olmayan satır mesaj sayılır."""
    if not text or not text.strip():
        return None
    message = ""
    suggestions: list[str] = []
    seen: set[str] = set()
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.upper().startswith("MESAJ:"):
            message = line.split(":", 1)[1].strip()
        elif line[0] in "-*•":
            s = line.lstrip("-*• ").strip()
            if s and s.lower() not in seen:
                seen.add(s.lower())
                suggestions.append(s)
        elif not message:
            # MESAJ: etiketi yoksa ilk düz satır mesaj
            message = line
    if not message:
        return None
    return {"message": message, "suggestions": suggestions[:max_suggestions]}
