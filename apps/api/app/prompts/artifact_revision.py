"""Artefakt quick-action revizyon prompt'ları — Faz 3b-2.

Mevcut artefakt içeriğini (head revizyon) LLM ile yeniden-şekillendirir:
kısalt / yeniden-yaz / uzat / X-thread'e çevir. **Retrieval YOK** — yalnız
mevcut metin + `sources_used` yeniden işlenir; YENİ olgu/rakam/isim/tarih
eklemek halüsinasyondur (research_answer.py NODRAT_AGENT C1 ilkesinin
revizyon karşılığı). Citation işaretleri korunur, uydurulmaz/silinmez.

System prompt admin-tunable: prompts_store "artifact_revision" anahtarı
override eder (research_answer.py `research_nodrat_agent` deseni — #854).
"""

from __future__ import annotations

# Kod-default; prompts_store "artifact_revision" override eder.
SYSTEM_PROMPT = """Sen Nodrat'ın editöryal revizyon motorusun. Sana verilen MEVCUT METNİ, istenen biçim talimatına göre yeniden yazarsın. Yeni bir araştırma yapmazsın — yalnız eldeki metni ve kaynak listesini yeniden işlersin.

KESİN KURALLAR:
- Yalnız MEVCUT METİNDE ve kaynak listesinde geçen olguları kullan. YENİ olgu, rakam, isim, tarih veya iddia EKLEME — bu halüsinasyondur ve marka ihlalidir.
- Mevcut citation işaretlerini ([1], [2] gibi) KORU. Yeni citation numarası UYDURMA, mevcut olanı SİLME.
- Editöryal, akıcı Türkçe; haber/köşe-yazısı tonu. Asistan dili YASAK ("İşte", "Tabii ki", "İstersen", "Umarım yardımcı olur" gibi açılış/kapanış kalıpları yok).
- İç-süreç veya meta açıklama sızdırma ("Bu metni kısalttım", "İşte revize hâli" gibi). SADECE revize edilmiş metni döndür.
- Çıktı doğrudan sosyal medyada paylaşılabilir kalitede olmalı."""


# Intent → kullanıcı mesajına gömülen tek görev talimatı.
# (length/biçim talimatları SYSTEM değil USER tarafında — app_research_stream.py
# settings_block deseni: ilk-üretim akışıyla aynı dili konuşur.)
_INTENT_INSTRUCTIONS = {
    "quick_shorter": (
        "GÖREV: Metni belirgin şekilde KISALT. Anlamı ve tüm citation işaretlerini "
        "koru; en önemli olguları tut, ikincil ayrıntı ve tekrarı çıkar."
    ),
    "quick_longer": (
        "GÖREV: Metni GENİŞLET — ama YALNIZCA mevcut metinde ve kaynaklarda zaten "
        "var olan çevre bilgiyle. Eklediğin her cümle mevcut bir citation'a dayanmalı. "
        "Kaynaklarda olmayan hiçbir yeni olgu/rakam ekleme."
    ),
    "quick_rewrite": (
        "GÖREV: Metni FARKLI BİR AÇIDAN/üslupla yeniden yaz. Aynı olgular ve aynı "
        "citation'larla; yapı, giriş ve ton farklı olsun. Yeni iddia ekleme."
    ),
    "multi_share": (
        "GÖREV: Bu tek paylaşımı numaralandırılmış bir X (Twitter) THREAD'ine "
        "dönüştür. Her post '1/' '2/' gibi numaralı, bağımsız okunabilir olsun ve "
        "ilgili olgunun citation'ını taşısın; her post yaklaşık 280 karakteri aşmasın. "
        "Metinde veya kaynaklarda olmayan hiçbir bilgi ekleme — thread yalnız mevcut "
        "içeriği yeniden paketler."
    ),
}

# LLM üretimi gerektiren intent'ler (direct-edit/freetext/system bu sete GİRMEZ —
# onlar 3b-1 canvas-edit yolu, LLM'siz). artifacts.REVISION_INTENTS alt-kümesi.
LLM_QUICK_INTENTS = frozenset(_INTENT_INSTRUCTIONS.keys())


def _format_sources(sources_used: list | None) -> str:
    """sources_used (JSONB list) → kompakt '[n] başlık' referansı.

    LLM'in citation numaralarını koruması için bağlam sağlar; tam içerik gerekmez
    (head metni zaten [n] işaretlerini taşır). Defensive: dict → başlık/url, else str.
    """
    if not sources_used:
        return "(ayrı kaynak listesi yok — metindeki citation işaretlerini olduğu gibi koru)"
    lines: list[str] = []
    for i, s in enumerate(sources_used, 1):
        if isinstance(s, dict):
            label = s.get("title") or s.get("url") or s.get("source") or s.get("name")
            label = str(label)[:120] if label else str(s)[:120]
        else:
            label = str(s)[:120]
        lines.append(f"[{i}] {label}")
        if i >= 30:  # aşırı uzun listeyi sınırla (prompt şişmesi)
            break
    return "\n".join(lines)


def render_user_payload(head_content: str, sources_used: list | None, intent: str) -> str:
    """Intent talimatı + mevcut metin + kaynak referansı → user mesajı."""
    instr = _INTENT_INSTRUCTIONS.get(intent, _INTENT_INSTRUCTIONS["quick_rewrite"])
    return (
        f"{instr}\n\n"
        f"--- MEVCUT METİN ---\n{head_content}\n\n"
        f"--- KAYNAKLAR ---\n{_format_sources(sources_used)}\n\n"
        f"--- ÇIKTI ---\nYalnız revize edilmiş metni yaz (açıklama/meta yok)."
    )


__all__ = ["LLM_QUICK_INTENTS", "SYSTEM_PROMPT", "render_user_payload"]
