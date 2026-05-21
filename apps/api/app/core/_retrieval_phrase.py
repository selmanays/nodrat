"""Internal retrieval phrase + quote helpers (T6 #1085 P5 PR-B internal split).

Pure string transforms + LUT + N-gram phrase generation. Daha önce
`app.core.retrieval` (lines 255-446 segments) içinde inline'dı; pure refactor —
davranış değişikliği YOK. Public consumer: `app.core.retrieval` (re-export).

Modül-dışı doğrudan import edilmez — stable API DEĞİL. Public API olarak
kullanılacaklar (`strip_quote_variants`, `normalize_tr_query`) `app.core.retrieval`
üzerinden çağrılır.

Refs:
- PR #1148 — retrieval characterization tests (regression safety-net)
- core/retrieval.py — public surface bu helper'ları re-export eder
- #647 Bianet "Toprakaltı" quote-strip vakası
"""

from __future__ import annotations

# ============================================================================
# Quote-strip constants + helpers (#647 root fix)
# ============================================================================

_QUOTE_CHARS_TO_STRIP: tuple[str, ...] = (
    "'",  # ASCII apostrof (chr 39)
    "‘",  # ' LEFT SINGLE QUOTATION MARK
    "’",  # ’ RIGHT SINGLE QUOTATION MARK
    "‚",  # ‚ SINGLE LOW-9 QUOTATION MARK
    "‛",  # ‛ SINGLE HIGH-REVERSED-9
    "′",  # ′ PRIME
    "ʼ",  # ʼ MODIFIER LETTER APOSTROPHE
    "ʹ",  # ʹ MODIFIER LETTER PRIME
    '"',  # ASCII çift tırnak (chr 34)
    "“",  # " LEFT DOUBLE QUOTATION MARK
    "”",  # " RIGHT DOUBLE QUOTATION MARK  ← Bianet vakası buraydı
    "„",  # „ DOUBLE LOW-9 QUOTATION MARK
    "‟",  # ‟ DOUBLE HIGH-REVERSED-9
    "″",  # ″ DOUBLE PRIME
    "«",  # « LEFT-POINTING GUILLEMET
    "»",  # » RIGHT-POINTING GUILLEMET
    "‹",  # ‹ SINGLE LEFT-POINTING ANGLE QUOTATION
    "›",  # › SINGLE RIGHT-POINTING ANGLE QUOTATION
    "`",  # backtick (chr 96) — bazı kaynaklarda yer alıyor
)

# SQL tarafında aynı strip için CASE/REPLACE chain inşa edilebilsin diye
# UTF-8 hex temsillerini export ediyoruz (sa.text içinde format string kullanılacak).
_QUOTE_CHARS_FOR_SQL: list[str] = list(_QUOTE_CHARS_TO_STRIP)


def strip_quote_variants(text: str) -> str:
    """Tüm major quote varyantlarını metinden kaldır (Python tarafı).

    Kullanıcı sorgusu ve normalize edilmiş chunk text karşılaştırılırken
    iki taraf da aynı strip işlemini geçmeli, aksi halde phrase match
    patlar (#647 Bianet "Toprakaltı" vakası).
    """
    if not text:
        return ""
    s = text
    for q in _QUOTE_CHARS_TO_STRIP:
        if q in s:
            s = s.replace(q, "")
    return s


def normalize_tr_query(text: str) -> str:
    """Türkçe sorgu normalize: lowercase + tüm quote varyantları temizle +
    whitespace collapse.

    Single + double quote varyantları (smart, low-9, guillemets, prime)
    silinir ki Bianet/Hürriyet/T24 gibi smart-quote kullanan kaynaklarda
    phrase match'i deterministik olsun (#647).

    Trigram benzerliği büyük/küçük harf duyarlı değil ama tırnak işareti
    ayrıştırıyor. 'CHP'li', '"Toprakaltı" sergisi', "İmamoğlu'nun davası"
    artık tutarlı şekilde normalize ediliyor.

    Public API (#397 MVP-2.1) — handler tarafında bir kez çağrılıp
    hybrid_search_* fonksiyonlarına `pre_normalized` olarak geçirilebilir.
    """
    if not text:
        return ""
    s = strip_quote_variants(text.lower())
    return " ".join(s.split())


def _build_sql_quote_strip(column_expr: str) -> str:
    """Verilen column expression'a tüm quote varyantlarını silen REPLACE chain'i sar.

    Örn: _build_sql_quote_strip("c.chunk_text") →
      REPLACE(REPLACE(REPLACE(c.chunk_text, '\\u2018', ''), '\\u2019', ''), ...)

    SQL tarafında Python `strip_quote_variants` ile birebir aynı set'i kaldırır.
    Hybrid search SQL'leri bu fonksiyonu kullanarak Python normalize ile
    deterministik şekilde eşleşir (#647 root fix).
    """
    expr = column_expr
    for q in _QUOTE_CHARS_FOR_SQL:
        # SQL string literal escaping: ASCII single quote ('') iki kez yazılır.
        # Diğer Unicode chars için doğrudan literal kullanılır (UTF-8 db'de).
        sql_literal = "''''" if q == "'" else "'" + q + "'"
        expr = f"REPLACE({expr}, {sql_literal}, '')"
    return expr


# ============================================================================
# Phrase match threshold (LUT) + N-gram phrase generation
# ============================================================================


def _phrase_match_threshold(query: str) -> float:
    """Trigram filter eşiği — kısa query'lerde daha gevşek.

    'CHP' (3 char) gibi kısa query'ler postgres trigram ile dezavantajlı;
    eşiği düşürürüz. 'izmir çevre yolu' (16 char) için standart 0.15.
    """
    n = len(query)
    if n <= 3:
        return 0.05
    if n <= 6:
        return 0.10
    return 0.15


# Türkçe yardımcı kelimeler — phrase boost için anlamsız (gürültü).
# Tek başına geçen bu kelimelerin phrase match'i atlanır.
_TR_NOISE_WORDS = {
    "mi",
    "mı",
    "mu",
    "mü",
    "olacak",
    "ne",
    "neden",
    "nasıl",
    "kim",
    "kime",
    "bu",
    "şu",
    "o",
    "bir",
    "ve",
    "ile",
    "için",
    "ama",
    "fakat",
    "ya",
    "yani",
    "çok",
    "az",
    "daha",
}


def _phrase_grams(query: str, n_min: int = 2, n_max: int = 4) -> list[str]:
    """Sorguyu 2/3/4-gram phrase'lere böler — her biri ayrı ILIKE match.

    'izmir çevre yolu ücretli mi olacak' →
        ['izmir çevre', 'çevre yolu', 'yolu ücretli', 'ücretli mi', 'mi olacak',
         'izmir çevre yolu', 'çevre yolu ücretli', 'yolu ücretli mi',
         'ücretli mi olacak',
         'izmir çevre yolu ücretli', 'çevre yolu ücretli mi',
         'yolu ücretli mi olacak']

    Sadece "noise" kelimelerden oluşan grup'lar (örn. 'mi olacak') filtrelenir.
    En az 1 anlamlı kelime içermeli + min 5 char.

    Args:
        query: normalize edilmiş query (lowercase, apostrofsuz)
        n_min/n_max: gram boyut sınırları (varsayılan 2-4)
    """
    if not query:
        return []
    words = [w for w in query.split() if w]
    if len(words) < n_min:
        return []

    grams: list[str] = []
    seen: set[str] = set()
    upper_n = min(n_max, len(words))
    for n in range(n_min, upper_n + 1):
        for i in range(len(words) - n + 1):
            chunk = words[i : i + n]
            # En az 1 anlamlı kelime şart
            if all(w in _TR_NOISE_WORDS for w in chunk):
                continue
            phrase = " ".join(chunk)
            if len(phrase) < 5:
                continue
            if phrase in seen:
                continue
            seen.add(phrase)
            grams.append(phrase)
    return grams
