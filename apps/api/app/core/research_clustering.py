"""Araştırma kümeleme — saf/deterministik yardımcılar (#1015 Faz 3).

Yalnız pure fonksiyonlar (DB/IO yok) → birim-test edilebilir; kümeleme
task'ının (cluster_assigner) çekirdek kararları burada izole.

AYRIM (kritik): `core/clustering.py` = haber-OLAY kümeleme (#20,
event_articles). BU dosya = kullanıcı sorgularının GLOBAL kanonik
ARAŞTIRMA kümeleri (#1015). Karıştırma.
"""

from __future__ import annotations

import re

from app.core.entity_noise import is_noise_entity

# CLAUDE.md §1.2 konvansiyonu — Türkçe → ASCII.
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
        (n, t, df) for (n, t, df) in candidates if n and n.strip() and df is not None and df >= 0
    ]
    if not valid:
        return None
    valid.sort(key=lambda c: (c[2], c[0]))
    return valid[0]


# #1590 — küme çapası Trends yapısına hizalandı: yalnız anlamlı entity tipleri
# (number/money/misc gürültü çapa OLMAZ; trends ENTITY_TREND_TYPES ile aynı).
ANCHOR_ENTITY_TYPES = frozenset({"person", "org", "place", "event"})

# #1705 — JENERİK-KATEGORİ eşiği. genericlik = bir norm'u BİLEŞEN olarak içeren FARKLI
# entity sayısı (çağıran corpus-türevli hesaplar, `cluster_resolver._anchor_genericness`).
# Jenerik kategori ("belediye meclisi" → "X Belediye Meclisi") çok entity'nin bileşeni
# (≥22); spesifik özel-ad ("tuvalu"/"filenin sultanları"/"hürmüz boğazı") ~0. Prod-ölçümü
# temiz boşluk: spesifik ≤6 ↔ jenerik ≥22; eşik = 15 (her iki yana marj). Korpus büyüdükçe
# jenerik artar, spesifik ~0 kalır → eşik stabil.
GENERIC_ANCHOR_MAX = 15


def _gate_anchor_candidates(
    candidates: list[tuple[str, str, int, int, bool, str | None]],
    *,
    min_articles: int = 2,
    min_sources: int = 2,
) -> list[tuple[str, str, int, int, bool, str | None]]:
    """GATE + tip + NER-gürültü filtresi (pure). select_canonical_anchor ile
    `resolve_anchor`'ın genericlik hesabı aynı valid-aday setini paylaşır (drift yok)."""
    return [
        c
        for c in candidates
        if c[0]
        and c[0].strip()
        and c[1] in ANCHOR_ENTITY_TYPES
        and c[2] is not None
        and c[2] >= min_articles
        and (c[3] or 0) >= min_sources
        and not is_noise_entity(c[0])
    ]


def select_canonical_anchor(
    candidates: list[tuple[str, str, int, int, bool, str | None]],
    *,
    genericness: dict[str, int] | None = None,
    min_articles: int = 2,
    min_sources: int = 2,
    generic_max: int = GENERIC_ANCHOR_MAX,
    prefer: str = "canonical",
) -> tuple[str, str, str | None] | None:
    """Canonical-farkında çapa seçimi — TRENDS mantığıyla hizalı (#1590/#1594/#1705).

    candidates: [(norm, entity_type, df, sources, has_canonical, display_name), ...]
    (`norm` = COALESCE(canonical_normalized, entity_normalized); çağıran SQL canonical'a
    maplenmiş). `genericness`: {norm → onu BİLEŞEN olarak içeren FARKLI entity sayısı}
    (corpus-türevli jenerik-kategori sinyali; çağıran `resolve_anchor` doldurur). None
    geçilirse jenerik-reddi atlanır + sort prominence'a düşer (test/geri-uyum).

    Sıra (#1594 rarest-wins YANLIŞTI: "hürmüz"(df6) "Hürmüz Boğazı"yı(df109) yeniyordu
    [fragment]; "var" gerçek entity'leri [gürültü]. #1697 kelime-sayısı da YANLIŞTI:
    jenerik çok-kelimeli "belediye meclisi" spesifik tek-kelimeli "tuvalu"yu yeniyordu):
      1. **GATE** (trends evidence-gate): df ≥ min_articles VE kaynak ≥ min_sources.
      2. Yalnız ANCHOR_ENTITY_TYPES + NER-gürültüsü ELE (#1598).
      3. **FRAGMENT-elim** (#1594/#1705): bir norm başka valid norm'un substring'iyse
         (eksik parça "hürmüz" ⊂ "hürmüz boğazı") DÜŞ — tam/uzun ad kazanır.
      4. **JENERİK-KATEGORİ reddi** (#1705): genericlik ≥ generic_max VE tip ≠ place →
         jenerik kategori ("belediye meclisi"/"milli takım"); çapa OLAMAZ. Yer (ülke/şehir)
         MUAF — "Almanya seçimleri" meşru özne. **Hepsi jenerikse → None** (yanlış jenerik
         küme yerine KÜME YOK; Fix#3 0-kaynak akışıyla uyumlu).
      5. **canonical-eşleşen** öncelik (curated; "trump"→"Donald Trump").
      6. **ÖZGÜLLÜK kovası** — jenerik-muaf-yer (gn ≥ generic_max) SONA; spesifik (gn düşük)
         özne ÖNCE. Ham-gn sort DEĞİL → iki spesifik canonical'da (chp gn7 vs özgür özel gn6)
         gürültülü tiebreak olmaz.
      7. Sonra **PROMINENCE** (-df) + tie-break norm.

    `prefer` (#1759):
      - "canonical" (default): canonical-eşleşen ÖNCE (yukarıdaki #5; query-gram +
        cluster_assigner yolu — "trump"→"Donald Trump" gibi curated tercih).
      - "df": cevap-tarafı (answer-driven) yol — cevapta en çok geçen ÖZNE kazanır;
        canonical yalnız df-eşitliğinde tiebreak. (DEM Parti df7 > Numan Kurtulmuş df2:
        canonical'lı ikincil, df-baskın özneyi bastırmaz.) Gate/fragment/jenerik-reddi AYNI.
    Dönüş: (norm, entity_type, display_name) | None.
    """
    valid = _gate_anchor_candidates(candidates, min_articles=min_articles, min_sources=min_sources)
    if not valid:
        return None
    # FRAGMENT-elim: bir valid norm başka valid norm'un substring'i ise (eksik parça) düş.
    norms = {c[0] for c in valid}
    valid = [c for c in valid if not any(c[0] != o and c[0] in o for o in norms)]

    def _gn(c: tuple[str, str, int, int, bool, str | None]) -> int:
        return genericness.get(c[0], 0) if genericness else 0

    if genericness is not None:
        # JENERİK-KATEGORİ reddi (yer MUAF). Hepsi jenerikse → None.
        non_generic = [c for c in valid if not (_gn(c) >= generic_max and c[1] != "place")]
        if not non_generic:
            return None
        valid = non_generic
    if prefer == "df":
        # df-baskın (answer-driven): jenerik-muaf-yer sona → -df → canonical tiebreak → norm.
        valid.sort(key=lambda c: (1 if _gn(c) >= generic_max else 0, -c[2], 0 if c[4] else 1, c[0]))
    else:
        # canonical önce → spesifik-kovası (jenerik-muaf-yer sona) → prominence (-df) → norm.
        valid.sort(key=lambda c: (0 if c[4] else 1, 1 if _gn(c) >= generic_max else 0, -c[2], c[0]))
    norm, etype, _df, _src, _has_canon, display = valid[0]
    return norm, etype, display


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


def infer_parent_edges(
    occ: dict[str, int],
    cooc: dict[tuple[str, str], int],
    df: dict[str, int],
    *,
    min_support: int = 3,
    coverage_hi: float = 0.6,
    coverage_lo: float = 0.35,
    df_ratio: float = 1.5,
) -> dict[str, str]:
    """Aggregate co-occurrence + df-asimetri → {child_id: parent_id} (#1020).

    Hiyerarşi ANSİKLOPEDİDEN değil kullanım deseninden:
      - Salt birlikte-geçme YETMEZ → simetrik ilişki kenar ÜRETMEZ
        (Erdoğan↔Özel yanlış-ebeveyn OLMAZ — acceptance).
      - B, A'nın çocuğu SADECE: B'lilerin çoğu A'da DA var (P(A|B)≥hi),
        A'lıların çoğu B'de DEĞİL (P(B|A)≤lo), VE A daha genel
        (df[A] ≥ df[B]·df_ratio ve occ[A] ≥ occ[B]).
      - coverage_hi > coverage_lo olduğundan 2-döngü matematiksel imkânsız;
        self-kenar engellenir. Çıkarım kesin değil → eşik-korumalı,
        düz-küme-önce, flag ile geri-alınabilir (task tarafında).

    Pure: yalnız aggregate SAYIM girer (kullanıcı içeriği İFŞA OLMAZ).
    `cooc` anahtarları kanonik (a, b) — a < b sıralı çift.
    """
    cand: dict[str, tuple[str, float]] = {}

    def _consider(child: str, parent: str, strength: float) -> None:
        if child == parent:
            return
        cur = cand.get(child)
        if cur is None or strength > cur[1]:
            cand[child] = (parent, strength)

    for (a, b), c in cooc.items():
        if c < min_support:
            continue
        oa, ob = occ.get(a, 0), occ.get(b, 0)
        if oa <= 0 or ob <= 0:
            continue
        p_a_given_b = c / ob  # B'lilerin A'da da olma oranı
        p_b_given_a = c / oa
        da, dbb = df.get(a, 0), df.get(b, 0)
        if (
            p_a_given_b >= coverage_hi
            and p_b_given_a <= coverage_lo
            and da >= dbb * df_ratio
            and oa >= ob
        ):
            _consider(b, a, p_a_given_b)  # A daha genel → B'nin ebeveyni A
        elif (
            p_b_given_a >= coverage_hi
            and p_a_given_b <= coverage_lo
            and dbb >= da * df_ratio
            and ob >= oa
        ):
            _consider(a, b, p_b_given_a)
        # else: simetrik / zayıf → kenar YOK (false-positive koruması)

    return {child: parent for child, (parent, _) in cand.items()}
