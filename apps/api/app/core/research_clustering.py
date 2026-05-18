"""Araştırma kümeleme — saf/deterministik yardımcılar (#1015 Faz 3).

Yalnız pure fonksiyonlar (DB/IO yok) → birim-test edilebilir; kümeleme
task'ının (cluster_assigner) çekirdek kararları burada izole.

AYRIM (kritik): `core/clustering.py` = haber-OLAY kümeleme (#20,
event_articles). BU dosya = kullanıcı sorgularının GLOBAL kanonik
ARAŞTIRMA kümeleri (#1015). Karıştırma.
"""

from __future__ import annotations

import re

# CLAUDE.md §1.2 konvansiyonu — Türkçe → ASCII.
_TR_ASCII = str.maketrans(
    {
        "ş": "s", "Ş": "s", "ı": "i", "İ": "i", "ç": "c", "Ç": "c",
        "ö": "o", "Ö": "o", "ü": "u", "Ü": "u", "ğ": "g", "Ğ": "g",
        "â": "a", "î": "i", "û": "u",
    }
)
_NON_KEBAB = re.compile(r"[^a-z0-9]+")


def tr_ascii_kebab(s: str) -> str:
    """'Özgür Özel' → 'ozgur-ozel'. Deterministik, ASCII, kebab-case."""
    s = (s or "").translate(_TR_ASCII).lower()
    s = _NON_KEBAB.sub("-", s).strip("-")
    return s


def canonical_cluster_key(entity_type: str, entity_normalized: str) -> str:
    """Dedup omurgası: '<type>:<kebab-ascii-name>'. Aynı (type, ad) HER
    ZAMAN aynı key → sistemde tek kanonik düğüm (binlerce per-user
    değil). Çakışmada type-prefix doğal ayrım (wiki kategori-prefix
    deseni). Boş ad → ValueError (çağıran atlamalı)."""
    et = tr_ascii_kebab(entity_type) or "topic"
    name = tr_ascii_kebab(entity_normalized)
    if not name:
        raise ValueError("empty entity_normalized → cluster_key üretilemez")
    return f"{et}:{name}"


def select_anchor(
    candidates: list[tuple[str, str, int]],
    *,
    df_threshold: int = 30,
) -> tuple[str, str, int] | None:
    """Nadir-entity çapa seçimi (mevcut retrieval df/nadirlik mantığı
    reuse). candidates: [(entity_normalized, entity_type, df), ...] —
    HEPSİ haber-korpusu (`entities`) entity'si olmalı (S11: çağıran
    yalnız korpus entity'si geçirir; özel-sorgu adı global küme
    MİNTLEMEZ → gizlilik sızması yok).

    Kural: en NADİR (en düşük df) entity kazanır — en ayırt edici çapa.
    Eşitlikte deterministik (df, entity_normalized) sıralaması. Aday
    yoksa None → çağıran embedding-fallback'e düşer (yalnız MEVCUT
    küme'ye bağlar; yeni global küme mintlemez)."""
    if not candidates:
        return None
    valid = [
        (n, t, df)
        for (n, t, df) in candidates
        if n and n.strip() and df is not None and df >= 0
    ]
    if not valid:
        return None
    valid.sort(key=lambda c: (c[2], c[0]))
    return valid[0]


_WORD = re.compile(r"[\wçğıöşüâîûÇĞİÖŞÜ]+", re.UNICODE)


def query_grams(text: str, *, max_n: int = 3, cap: int = 60) -> list[str]:
    """Mesaj metninden 1..max_n kelimelik normalize n-gram adayları
    (entities.entity_normalized ile EŞLEŞTİRMEK için). Deterministik;
    küçük harf + Türkçe korunur (entity_normalized de TR tutar).
    Salt aday üretir — korpus eşleşmesi DB tarafında (S11)."""
    toks = [t.lower() for t in _WORD.findall(text or "")]
    grams: list[str] = []
    seen: set[str] = set()
    for n in range(1, max_n + 1):
        for i in range(len(toks) - n + 1):
            g = " ".join(toks[i : i + n]).strip()
            if g and g not in seen:
                seen.add(g)
                grams.append(g)
                if len(grams) >= cap:
                    return grams
    return grams
