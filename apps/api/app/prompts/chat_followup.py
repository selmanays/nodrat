"""Chat takip sorusu üretimi (#961) — cevap-sonrası 5 dinamik keşif sorusu.

Ana cevap üretildikten SONRA ayrı, hafif, non-blocking bir LLM call ile
çalışır (final_text → _simulate_stream düz-metin omurgası DEĞİŞMEZ;
#819/#840 yapısal-parse riski ana cevaptan İZOLE). Çıktı satır-bazlı
(JSON DEĞİL — küçük/hızlı model JSON güvenilmezliği, #819/#840 dersi);
tolerant parse + ana cevaba sızma imkânsız (ayrı call).

Nodrat kimliği (#851/#958): üretilen sorular kullanıcı-ağzından,
NESNEL keşif soruları — editoryal/öznel/asistan-jargonu YOK. "İstersen
sana …" gibi hizmet-teklifi ASLA (kullanıcı kararı: cevap-içi öneri
cümlesi yok; devam yalnız bu sorularla — keşif yardımı, motor-uyumlu).
"""

from __future__ import annotations

import re

PROMPT_VERSION = "1.0.0"  # #961

SYSTEM_PROMPT = """Sen Nodrat'ın takip-sorusu üreticisisin. Az önce
verilen cevabın ARDINDAN, kullanıcının bu konuda doğal olarak merak
edebileceği **5 takip sorusu** üretirsin.

ÇIKTI BİÇİMİ — SADECE 5 satır, her satır tek soru, başında "- ":
- <soru 1>
- <soru 2>
- <soru 3>
- <soru 4>
- <soru 5>
Markdown başlık, açıklama, numara, ek metin YOK. Yalnız 5 "- " satırı.

KURALLAR:
- Sorular **kullanıcının ağzından** yazılır (kullanıcı sana sormuş
  gibi): "X ne zaman oldu?", "Y'nin son durumu ne?", "Z neden …?".
- **Nesnel ve spesifik** — cevaptaki/konudaki somut kişi, olay,
  tarih, kurum üzerine. Genel-geçer ("daha fazla bilgi verir misin")
  YASAK.
- **Doğal devam**: cevabın açtığı yan başlıklar, bir sonraki mantıklı
  merak, ilgili gelişme. Cevabı tekrar ettiren soru sorma.
- Nodrat bir güncel-haber araştırma motorudur: sorular **haber/olay/
  açıklama** ekseninde olmalı (Nodrat'ın `search_news`/`search_wikipedia`
  ile gerçekten yanıtlayabileceği türden). Kişisel/öznel/"sana göre"
  tarzı veya Nodrat'ın yapamayacağı (dosya üret, hesapla vs.) sorular
  YASAK.
- Editoryal/öznel niteleme, asistan-jargonu ("ister misin",
  "yardımcı olayım"), imza, emoji YOK.
- Dil: kullanıcının/cevabın dili (Türkçe içerikte Türkçe).
- Her soru kısa (≤ ~12 kelime), birbirinden FARKLI açı.

Yalnız 5 satırı döndür."""


def render_user_payload(user_question: str, answer: str) -> str:
    """Takip-sorusu LLM'ine verilecek bağlam (kısa tutulur — hafif call)."""
    a = (answer or "").strip()
    if len(a) > 1500:
        a = a[:1500] + " …"
    q = (user_question or "").strip()[:400]
    return (
        f"Kullanıcının sorusu:\n{q}\n\n"
        f"Verilen cevap:\n{a}\n\n"
        "Bu cevabın ardından kullanıcının sorabileceği 5 takip "
        "sorusunu yukarıdaki biçimde üret."
    )


_LINE_RE = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+(.+?)\s*$")
# Türkçe + İngilizce soru-işaretçileri (öneksiz fallback filtresi)
_Q_HINT = re.compile(
    r"\?|\b(ne|neden|nas[ıi]l|kim|nere|hangi|ka[çc]|m[ıiuü]|mi|"
    r"what|why|how|who|when|where|which)\b",
    re.IGNORECASE,
)


def _clean(s: str) -> str:
    return s.strip().strip('"').strip("«»").strip()


def parse_followups(text: str, *, limit: int = 5) -> list[str]:
    """Tolerant ama gürültü-dayanıklı satır-bazlı parse (JSON DEĞİL —
    #819/#840 dersi).

    Öncelik **önekli** satırlar ("- "/"1." /"*" /"•") — LLM sözleşmesi
    bu. Yeterli önekli satır varsa öneksiz satırlar (açıklama/gürültü)
    ELENİR. Hiç önekli yoksa fallback: öneksiz ama **soru-benzeri**
    (soru işareti / soru kelimesi) satırlar. 10–160 char, dedup,
    ≤limit. Min 10 → "çok kısa" tipi gürültü elenir."""
    if not text:
        return []

    prefixed: list[str] = []
    plain: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        m = _LINE_RE.match(line)
        if m:
            prefixed.append(_clean(m.group(1)))
        else:
            plain.append(_clean(line))

    pool = prefixed if len(prefixed) >= 2 else (prefixed + plain)
    require_q = not (len(prefixed) >= 2)  # öneksiz fallback'te soru şart

    out: list[str] = []
    seen: set[str] = set()
    for cand in pool:
        if not cand or (cand.endswith(":") and len(cand) < 30):
            continue
        if not (10 <= len(cand) <= 160):
            continue
        if require_q and not _Q_HINT.search(cand):
            continue
        key = cand.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(cand)
        if len(out) >= limit:
            break
    return out


__all__ = [
    "PROMPT_VERSION",
    "SYSTEM_PROMPT",
    "parse_followups",
    "render_user_payload",
]
