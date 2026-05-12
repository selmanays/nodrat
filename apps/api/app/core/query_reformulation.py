"""Query reformulation helpers — #746 (Faz 7c Aşama 2).

niche_006/007/009 fail vakaları için multi-query variant'ları zenginleştir.
Diagnostic veri (#742) gösterdi ki:
- Mevcut 2-3 variant doğru article'ı top-K'a sokmaya yetmiyor
- Niş "kaç X / yüzde kaç" sorularında semantic alan kaymıyor

3 helper:
1. `entity_only_variant` — stopword + soru kelime temizliği (Rodos Devleti kuruluş)
2. `is_numerical_question` — "kaç / yüzde kaç" detection
3. `reformulate_numerical_query` — "kaç X" → "X sayısı"
"""

from __future__ import annotations

import re


# Türkçe soru kelimeleri + yardımcı stopword'ler.
# "Bir" / "bu" / "ki" / "ile" gibi yaygın hiyerarşik bağlaçlar dahil.
_QUERY_CHROME = {
    # Soru kelimeleri
    "kim", "kimdi", "kime", "kimin", "kimler",
    "ne", "nedir", "neyi", "neye", "neden", "niye",
    "nasıl", "ne kadar", "kaç", "kaçtır", "kaçı", "kaçını", "kaçtan",
    "hangi", "hangisini", "hangisi",
    "nerede", "nereye", "nereden",
    "ne zaman", "ne zamana", "ne zamandan",
    # Yardımcı fiil
    "var", "varmış", "varsa", "yok", "yokmuş",
    "olmuş", "oldu", "oldur", "olur", "ola",
    "yaptı", "yapıyor", "yapacak",
    # Bağlaç + bağlayıcılar
    "bir", "bu", "şu", "o", "böyle", "şöyle", "öyle",
    "ki", "ile", "için", "gibi", "kadar", "üzere",
    "bizim", "sizin", "onların", "kendi",
    "birlikte", "beraber", "arasında", "arada",
    "esnasında", "sırasında", "sonrasında", "öncesinde",
    # İsim çekim ekleri yakalanmaz (regex eksik), ama '-nın/-nin' suffix removal
    # Aşağı'da regex ile yapılır.
}

# Soru/eylem kalıbı pattern'ları
_NUMERICAL_QUESTION = re.compile(
    r"\b(?:yüzde\s+ka[çc]|ka[çc]\s+(?:ana|büyük|küçük|farklı|toplam|yaklaşık)?\s*"
    r"(?:[a-zçğıöşü]+)|ne\s+kadar)",
    flags=re.IGNORECASE,
)

# "kaç X" → "X sayısı" reformulation pattern
_HOW_MANY_X = re.compile(
    r"ka[çc]\s+(?:ana|büyük|küçük|farklı|toplam|yaklaşık)?\s*"
    r"([a-zçğıöşü]+)",
    flags=re.IGNORECASE,
)

# "yüzde kaç X" → "X yüzdesi"
_WHAT_PERCENT_X = re.compile(
    r"yüzde\s+ka[çc]\w*\s+([a-zçğıöşü]+)",
    flags=re.IGNORECASE,
)


def entity_only_variant(query: str) -> str:
    """Query'den stopword + soru kelimelerini temizleyip entity-only form üret.

    Args:
        query: Original user query (Türkçe).

    Returns:
        Cleaned query — sadece anahtar entity'ler ve isimler.

    Örnek:
        "Rodos Devleti'ni kaç ana kent bir araya gelerek kurdu"
        → "rodos devleti kent kurdu" (yaklaşık)
        "ABD'nin hürmüz boğazının yüzde kaçını kullanma hakkı var"
        → "abd hürmüz boğazı kullanma hakkı"
    """
    if not query:
        return ""
    # Apostrof + suffix temizle ("Rodos'un" → "rodos")
    cleaned = re.sub(r"['’]\w+", "", query)
    # Birim suffix (-nın, -nin, -nun, -nün) — sadece kelime sonunda
    cleaned = re.sub(
        r"\b([a-zçğıöşü]+)(?:'?(?:nın|nin|nun|nün|ın|in|un|ün|na|ne|nu|nü|ya|ye|yi|yu|yü|i|ı|u|ü))\b",
        r"\1",
        cleaned,
        flags=re.IGNORECASE,
    )
    tokens = [t for t in re.split(r"\s+", cleaned.lower()) if t]
    out = [t for t in tokens if t not in _QUERY_CHROME and len(t) >= 2]
    return " ".join(out).strip()


def is_numerical_question(query: str) -> bool:
    """Query niş "kaç X / yüzde kaç" sorgusu mu?"""
    if not query:
        return False
    return bool(_NUMERICAL_QUESTION.search(query))


def reformulate_numerical_query(query: str) -> str | None:
    """Niş sayısal sorgu için reformulation variant.

    "Rodos Devleti'ni kaç ana kent kurdu" → "Rodos Devleti ana kent sayısı"
    "ABD hürmüz yüzde kaç kullanır" → "ABD hürmüz kullanma yüzdesi"

    Returns None if pattern not detected (caller skip eder).
    """
    if not query:
        return None

    # 1) "yüzde kaç X" → "X yüzdesi"
    m = _WHAT_PERCENT_X.search(query)
    if m:
        x = m.group(1).strip()
        # Query'den "yüzde kaç" çıkar, "X yüzdesi" ekle
        before = query[: m.start()].strip()
        after = query[m.end():].strip()
        return f"{before} {x} yüzdesi {after}".strip()

    # 2) "kaç X" → "X sayısı"
    m = _HOW_MANY_X.search(query)
    if m:
        x = m.group(1).strip()
        before = query[: m.start()].strip()
        after = query[m.end():].strip()
        return f"{before} {x} sayısı {after}".strip()

    return None


__all__ = [
    "entity_only_variant",
    "is_numerical_question",
    "reformulate_numerical_query",
]
