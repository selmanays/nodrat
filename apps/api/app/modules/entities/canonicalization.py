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

import collections
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


# =============================================================================
# Token-altküme birleştirmesi (#1548) — çok-kelimeli event varyantları
# =============================================================================

# Token-altküme kuralı YALNIZ bu tiplere uygulanır. person (Emine/Bilal soyad
# tuzağı) + place (alt-bölge: "Kıbrıs"⊊"Kuzey Kıbrıs") + org (alt-birim:
# "Ankara Üniversitesi"⊊"...Tıp Fakültesi") HARİÇ → event-only (en güvenli).
SUBSET_TYPES: frozenset[str] = frozenset({"event"})
SUBSET_MIN_TOKENS = 2  # alt-küme ≥2 token (tek-jenerik-token merge yok)


def build_subset_groups(items: list[tuple[str, int]]) -> dict[str, str]:
    """Token-set tabanlı varyant birleştirme (saf, deterministik). Tek tip için.

    items: [(entity_normalized, freq)] — caller SUBSET_TYPES'a göre filtreler.
    Kural: (1) **eşit token-set** (sıra-bağımsız) → birleş; (2) A'nın token-set'i
    **tek bir minimal üst-küme** token-set'inin gerçek alt-kümesi → birleş
    (A ≥SUBSET_MIN_TOKENS token). Çoklu minimal üst-küme (belirsiz) → birleşME.

    Dönüş: {member_norm: canonical_norm} (yalnız ≥2 üyeli gruplar). canonical =
    en sık üye (eşitse en uzun). Örnek: "2026 dünya kupası" + "fifa dünya kupası"
    + "fifa 2026 dünya kupası" → "2026 fifa dünya kupası"; ama "dünya kupası"
    (2026 ve 2002 alt-kümesi = belirsiz) ve "2002 dünya kupası" ayrı kalır.
    """
    if len(items) < 2:
        return {}
    toks: dict[str, frozenset[str]] = {norm: frozenset(norm.split()) for norm, _ in items}
    freq: dict[str, int] = dict(items)
    norms = list(toks)

    parent: dict[str, str] = {n: n for n in norms}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    # (1) eşit token-set (sıra farkı: "2026 fifa dünya kupası" = "fifa 2026 dünya kupası")
    by_set: dict[frozenset[str], list[str]] = collections.defaultdict(list)
    for n in norms:
        by_set[toks[n]].append(n)
    for members in by_set.values():
        for m in members[1:]:
            union(members[0], m)

    # (2) tek minimal üst-küme (set düzeyinde — eşit-set'ler tek sayılır)
    distinct_sets = set(toks.values())
    for n in norms:
        ta = toks[n]
        if len(ta) < SUBSET_MIN_TOKENS:
            continue
        supersets = [ts for ts in distinct_sets if ta < ts]  # gerçek alt-küme (⊊)
        if not supersets:
            continue
        min_size = min(len(ts) for ts in supersets)
        minimal = [ts for ts in supersets if len(ts) == min_size]
        if len(minimal) == 1:
            target_norm = next(m for m in norms if toks[m] == minimal[0])
            union(n, target_norm)

    comp: dict[str, list[str]] = collections.defaultdict(list)
    for n in norms:
        comp[find(n)].append(n)
    result: dict[str, str] = {}
    for members in comp.values():
        if len(members) < 2:
            continue
        canonical = max(members, key=lambda m: (freq[m], len(m)))
        for m in members:
            result[m] = canonical
    return result
