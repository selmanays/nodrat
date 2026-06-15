"""Entity canonicalization — varyant yüzey biçimlerini tek kimliğe bağlar (Faz 1, #1540).

Saf/deterministik (DB'siz, unit-testable). İki yöntem:
  1. **Küratörlü seed** — top TR kişi/kurum varyantları elle eşlenir (yüksek precision).
     Kurum akronim↔açık ad (CHP↔Cumhuriyet Halk Partisi) burada çözülür (kural ile
     türetilemez).
  2. **Unvan-soyma (yalnız person)** — "Cumhurbaşkanı Erdoğan" → "erdoğan" → seed eşleşmesi.

Konservatif: yalnız (a) doğrudan seed VEYA (b) unvan-soyup-seed eşleşen varyantlar
bağlanır. Riskli generic soyad-birleştirme (Emine/Bilal Erdoğan tuzağı) YAPILMAZ —
o uzun kuyruk Faz 2 (LLM batch) + admin review. `entities` tablosu okunmaz, dokunulmaz.
"""

from __future__ import annotations

from dataclasses import dataclass

# Türkçe kişi unvanları/ön-ekleri — person adının BAŞINDAN iteratif soyulur.
# Org alt-birim göstergeleri (belediye/meclisi/üyesi) KASITEN yok → alt-birimler
# org'a katılmaz (chp ≠ chp genel merkezi ≠ chp ... meclis üyesi).
_TITLE_PREFIXES: frozenset[str] = frozenset(
    {
        "cumhurbaşkanı",
        "cumhurbaskani",
        "başbakan",
        "başbakanı",
        "basbakan",
        "bakan",
        "bakanı",
        "başkan",
        "başkanı",
        "baskan",
        "genel",
        "sayın",
        "sayin",
        "dr",
        "prof",
        "doç",
        "doc",
        "av",
        "milletvekili",
        "vekili",
        "vali",
        "valisi",
        "kaymakam",
        "büyükelçi",
        "sözcüsü",
        "sozcusu",
        "lider",
        "lideri",
        "akpli",
        "chpli",
        "mhpli",
    }
)

# Küratörlü seed: (canonical_name, entity_type, [alias_normalized varyantları]).
# alias'lar entity_normalized biçiminde (lower). İlk-ad çakışan farklı kişiler
# (Emine/Bilal Erdoğan) seed'e KOYULMAZ → ayrı kalır.
SEED_GROUPS: list[tuple[str, str, list[str]]] = [
    # ---- Kişiler (çoğu unvan-soyma ile de yakalanır; soyad-only seed'lenir) ----
    ("Recep Tayyip Erdoğan", "person", ["recep tayyip erdoğan", "tayyip erdoğan", "erdoğan"]),
    ("Donald Trump", "person", ["donald trump", "trump"]),
    ("Kemal Kılıçdaroğlu", "person", ["kemal kılıçdaroğlu", "kılıçdaroğlu"]),
    ("Özgür Özel", "person", ["özgür özel"]),
    ("Ekrem İmamoğlu", "person", ["ekrem imamoğlu", "imamoğlu"]),
    ("Devlet Bahçeli", "person", ["devlet bahçeli", "bahçeli"]),
    ("Hakan Fidan", "person", ["hakan fidan"]),
    ("Mehmet Şimşek", "person", ["mehmet şimşek"]),
    ("Vladimir Putin", "person", ["vladimir putin", "putin"]),
    ("Binyamin Netanyahu", "person", ["binyamin netanyahu", "benyamin netanyahu", "netanyahu"]),
    ("Volodimir Zelenski", "person", ["volodimir zelenski", "zelenski", "zelensky"]),
    # ---- Kurumlar (akronim ↔ açık ad — seed'in ASIL değeri) -------------------
    ("Cumhuriyet Halk Partisi", "org", ["chp", "cumhuriyet halk partisi"]),
    ("AK Parti", "org", ["akp", "ak parti", "adalet ve kalkınma partisi"]),
    ("MHP", "org", ["mhp", "milliyetçi hareket partisi"]),
    ("İYİ Parti", "org", ["iyi parti", "iyi̇ parti"]),
    ("DEM Parti", "org", ["dem parti", "halkların eşitlik ve demokrasi partisi"]),
    (
        "Merkez Bankası",
        "org",
        ["tcmb", "merkez bankası", "merkez bankasi", "türkiye cumhuriyet merkez bankası"],
    ),
    ("TBMM", "org", ["tbmm", "türkiye büyük millet meclisi"]),
    ("İstanbul Büyükşehir Belediyesi", "org", ["ibb", "istanbul büyükşehir belediyesi"]),
    ("TÜİK", "org", ["tüik", "türkiye istatistik kurumu"]),
    ("TFF", "org", ["tff", "türkiye futbol federasyonu"]),
    ("Birleşmiş Milletler", "org", ["birleşmiş milletler", "bm"]),
    ("Avrupa Birliği", "org", ["avrupa birliği", "avrupa birli̇ği̇"]),
    ("NATO", "org", ["nato", "kuzey atlantik antlaşması örgütü"]),
    ("AFAD", "org", ["afad", "afet ve acil durum yönetimi başkanlığı"]),
    ("YÖK", "org", ["yök", "yükseköğretim kurulu"]),
    ("RTÜK", "org", ["rtük", "radyo ve televizyon üst kurulu"]),
    ("SPK", "org", ["spk", "sermaye piyasası kurulu"]),
    ("MİT", "org", ["mit", "milli istihbarat teşkilatı"]),
    ("Diyanet İşleri Başkanlığı", "org", ["diyanet", "diyanet işleri başkanlığı"]),
]


@dataclass(frozen=True)
class CanonicalMatch:
    canonical_name: str
    canonical_normalized: str
    entity_type: str
    source: str  # "seed" | "title_strip"


def canonical_norm(name: str) -> str:
    """Canonical_name → canonical_normalized (lower + trim). entity_normalized
    ile aynı temel normalize (strip_quote_variants builder'da uygulanır)."""
    return name.lower().strip()


def strip_titles(entity_normalized: str) -> str:
    """Person adının başındaki unvan/ön-ek token'larını iteratif soy.

    "cumhurbaşkanı erdoğan" → "erdoğan" · "akpli cumhurbaşkanı erdoğan" → "erdoğan".
    Tüm token'lar unvan ise (örn. yalnız "başkan") → değiştirme (boş döndürme).
    """
    tokens = entity_normalized.split()
    i = 0
    while i < len(tokens) and tokens[i] in _TITLE_PREFIXES:
        i += 1
    if i == 0 or i >= len(tokens):
        return entity_normalized
    return " ".join(tokens[i:])


# (alias_normalized, entity_type) → CanonicalMatch
def _build_seed_index() -> dict[tuple[str, str], CanonicalMatch]:
    index: dict[tuple[str, str], CanonicalMatch] = {}
    for canonical_name, etype, aliases in SEED_GROUPS:
        cnorm = canonical_norm(canonical_name)
        for alias in aliases:
            index[(alias, etype)] = CanonicalMatch(
                canonical_name=canonical_name,
                canonical_normalized=cnorm,
                entity_type=etype,
                source="seed",
            )
    return index


_SEED_INDEX: dict[tuple[str, str], CanonicalMatch] = _build_seed_index()


def resolve_canonical(entity_normalized: str, entity_type: str) -> CanonicalMatch | None:
    """Bir (entity_normalized, entity_type) → canonical eşleşmesi (yoksa None).

    1. Doğrudan seed. 2. Person ise unvan-soyup seed. Aksi None (ham kalır).
    """
    direct = _SEED_INDEX.get((entity_normalized, entity_type))
    if direct is not None:
        return direct
    if entity_type == "person":
        stripped = strip_titles(entity_normalized)
        if stripped != entity_normalized:
            hit = _SEED_INDEX.get((stripped, "person"))
            if hit is not None:
                return CanonicalMatch(
                    canonical_name=hit.canonical_name,
                    canonical_normalized=hit.canonical_normalized,
                    entity_type="person",
                    source="title_strip",
                )
    return None
