"""VLM caption post-processing (#304 fix).

VLM bazen kişiyi `depicts` alanında doğru tanımlasa bile (örn. "Aziz Yıldırım"),
caption'da onu kullanmaktan çekinir ("bir adam konuşuyor"). Bu helper, VLM
çıktısındaki caption + depicts uyumsuzluğunu post-processing ile düzeltir.

Pure Python — sıfır API call.

Örnek:
    caption: "Fenerbahçe logosu önünde konuşan bir adam"
    depicts: ["Aziz Yıldırım"]
    →
    enriched: "Aziz Yıldırım, Fenerbahçe logosu önünde konuşuyor."
"""

from __future__ import annotations

import re

# "bir adam", "bir kadın", "bir kişi" gibi generic referansları kişi adıyla
# değiştirmek için pattern'ler. Sıralama önemli — en spesifik önce.
_GENERIC_PERSON_PATTERNS = [
    re.compile(r"\b[Bb]ir\s+(?:erkek\s+)?adam(?:ın)?\b"),
    re.compile(r"\b[Bb]ir\s+kadın\b"),
    re.compile(r"\b[Bb]ir\s+kişi\b"),
    re.compile(r"\b[Bb]ir\s+(?:erkek|bayan)\b"),
    re.compile(r"\b(?:[Bb]ir\s+)?(?:takım\s+elbiseli|kıyafetli)\s+(?:bir\s+)?(?:adam|kadın|kişi)(?:ın)?\b"),
]


def _name_in_caption(caption: str, name: str) -> bool:
    """İsim caption'da geçiyor mu? (whole-word, case-insensitive)"""
    if not name or not caption:
        return False
    # İsim 3+ char olmalı (yanlış kısa match'leri önle)
    if len(name.strip()) < 3:
        return False
    # Soyad vs ad kısmen geçebilir — 'Aziz' veya 'Yıldırım' caption'da varsa OK
    parts = [p for p in name.split() if len(p) >= 3]
    if not parts:
        return False
    caption_lower = caption.lower()
    return all(re.search(rf"\b{re.escape(p.lower())}\b", caption_lower) for p in parts)


def enrich_caption_with_depicts(
    caption: str,
    depicts: list[str] | None,
    alt_text: str = "",
) -> str:
    """Caption'ı depicts listesindeki tanıdık isimle zenginleştir.

    Strateji:
    1. depicts boşsa veya hepsi caption'da geçiyorsa → caption olduğu gibi
    2. caption'da generic referans var ("bir adam", "bir kadın") + depicts'te
       isim var → generic'i ilk depicts ismi ile değiştir
    3. caption'da generic yok ama depicts ismi yoksa → "<isim>, <caption>"
       prefix ekle (sadece ilk isim, virgüllü)

    Güvenlik kuralı (#304 fix): alt_text geçildiyse, depicts'teki isim
    alt_text'te de geçmek ZORUNDADIR. Aksi halde replacement YAPILMAZ —
    VLM yanlış atıf yapmış olabilir (örn: alt'ta haber içeriği var, depicts
    yanlış kişi listelemiş).

    Args:
        caption: Orijinal VLM caption (Türkçe)
        depicts: VLM'in çıkardığı kişi/obje listesi
        alt_text: HTML alt — depicts ismi burada da geçmeli (cross-reference)

    Returns:
        Zenginleştirilmiş caption (veya değiştirilmemiş orijinal)
    """
    if not caption or not depicts:
        return caption or ""

    # Tanıdık person-like isimleri filtrele (ilk harfi büyük + 3+ char)
    # "kürsü", "mikrofon" gibi obje değil — heuristik: ilk char upper
    person_names = [
        n.strip()
        for n in depicts
        if isinstance(n, str)
        and n.strip()
        and n.strip()[0].isupper()
        and len(n.strip()) >= 3
    ]

    if not person_names:
        return caption

    # Cross-reference: alt_text geçildiyse, depicts ismi alt'ta da geçmeli
    # (yanlış atıf koruması — VLM bazen alt'taki haber içeriğindeki ismi
    # depicts'e yanlışlıkla koyabilir)
    if alt_text:
        person_names = [n for n in person_names if _name_in_caption(alt_text, n)]
        if not person_names:
            return caption

    # Caption'da geçmeyen isimleri bul
    missing_names = [n for n in person_names if not _name_in_caption(caption, n)]
    if not missing_names:
        return caption  # Tüm isimler zaten caption'da

    primary_name = missing_names[0]

    # Strateji 2: generic referans replacement
    for pattern in _GENERIC_PERSON_PATTERNS:
        if pattern.search(caption):
            replaced = pattern.sub(primary_name, caption, count=1)
            if replaced != caption:
                return replaced

    # Strateji 3: prefix ekle ("X, <caption>")
    caption_body = caption[0].lower() + caption[1:] if caption else ""
    return f"{primary_name}, {caption_body}"
