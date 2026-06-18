"""NER gürültü filtresi — common-word mis-NER deterministik ele (#1598).

NER prompt'u zaten "generic/günlük kelimeler atlanır (haber, bugün, çarşamba,
vatandaş)" diyor; ama ucuz model (v4-flash) her zaman uymuyor → "var"(org) /
"bugün" / "zaman" gibi function/generic kelimeler entity etiketleniyor. Bu, prompt
kuralının **deterministik kod-enforcement'ı**: tek paylaşımlı katman hem NER
ingest'inde (yeni gürültüyü engelle) hem küme çapasında (mevcut gürültüyü çapa-dışı
bırak) kullanılır → trend ve küme aynı temiz entity tabanını paylaşır.

Saf/deterministik (DB/IO yok). MUHAFAZAKÂR liste: yalnız NET function/generic
kelimeler — asla bir named-entity (kişi/kurum/yer/olay) adı olmayanlar. Belirsizler
(alan, ece, borsa, küba, gram, elektrik, politico) KASITLA dışarıda: legit olabilir,
yanlış-eleme veri kaybıdır.
"""

from __future__ import annotations

import re
import unicodedata

# Türkçe → ASCII fold (research_clustering._TR_ASCII ile uyumlu; ı/İ NFKD ile
# çözülmediği için açık map gerek).
_TR_ASCII = str.maketrans(
    {
        "ş": "s",
        "Ş": "s",
        "ı": "i",
        "İ": "i",
        "ç": "c",
        "Ç": "c",
        "ö": "o",
        "Ö": "o",
        "ü": "u",
        "Ü": "u",
        "ğ": "g",
        "Ğ": "g",
        "â": "a",
        "î": "i",
        "û": "u",
    }
)


def _fold(s: str) -> str:
    """'Bugün' → 'bugun'. Lower + TR→ASCII + combining-mark strip + alnum-only.
    Combining-dot (İ.lower() → 'i̇') ve TR aksanlarına dayanıklı eşleşme için."""
    s = (s or "").lower().translate(_TR_ASCII)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", s)


# ASCII-folded biçimde tutulur (_fold ile karşılaştırılır). MUHAFAZAKÂR:
# yalnız asla named-entity olmayan function/generic kelimeler.
NER_NOISE_STOPWORDS: frozenset[str] = frozenset(
    {
        # varlık/durum fiilleri — asla kişi/kurum/yer/olay değil
        "var",
        "yok",
        "olur",
        "oldu",
        "olmus",
        "olacak",
        # zaman ifadeleri (prompt "bugün/çarşamba atla" der)
        "bugun",
        "dun",
        "yarin",
        "zaman",
        "simdi",
        # jenerik isimler
        "bilgi",
        "durum",
        "sey",
        "konu",
        "haber",
        "aciklama",
        "sonuc",
    }
)


def is_noise_entity(entity_normalized: str | None) -> bool:
    """entity_normalized NER-gürültüsü mü (common-word mis-NER)? Type-agnostik:
    bu kelimeler hiçbir entity tipinde geçerli ad değil. _fold ile eşleştirir →
    'Bugün'/'BUGÜN'/'bugün' hepsi yakalanır."""
    return _fold(entity_normalized or "") in NER_NOISE_STOPWORDS
