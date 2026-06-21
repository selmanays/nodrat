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


def select_canonical_anchor(
    candidates: list[tuple[str, str, int, int, bool, str | None]],
    *,
    min_articles: int = 2,
    min_sources: int = 2,
) -> tuple[str, str, str | None] | None:
    """Canonical-farkında çapa seçimi — TRENDS mantığıyla hizalı (#1590/#1594).

    candidates: [(norm, entity_type, df, sources, has_canonical, display_name), ...]
    (`norm` = COALESCE(canonical_normalized, entity_normalized); çağıran SQL canonical'a
    maplenmiş). #1594 düzeltme — rarest-wins YANLIŞTI (trends volume seçerken küme nadir
    seçiyordu → "hürmüz"(df6) "Hürmüz Boğazı"yı(df109) yeniyor [fragment]; "var"(df5)
    gerçek entity'leri yeniyor [gürültü]). Trends gibi:
      1. **GATE** (trends evidence-gate gibi): df ≥ min_articles **VE** kaynak ≥ min_sources —
         nadir/tek-kaynak gürültü ("zaman" df1) ELENİR.
      2. Yalnız ANCHOR_ENTITY_TYPES (person/org/place/event).
      3. **NER-gürültüsü ELE** (#1598): common-word mis-NER ("var"/"bugün"/"zaman")
         gate'i geçse bile çapa OLAMAZ → trend ile aynı temiz taban.
      4. **canonical-eşleşen** öncelik (curated birleşik kimlik; "trump"→"Donald Trump").
      5. **ÖZGÜLLÜK** — daha çok-kelimeli norm önce (#1697): sorgunun ASIL öznesi
         genelde çok-kelimeli özel-ad ("filenin sultanları" 2w), jenerik tek-kelimeli
         yer/ülke ("almanya" 1w, df=732) ise çevresel bağlam. DF-prominence tek başına
         jenerik ülkeyi özneye tercih ediyordu (place:almanya → org:filenin sultanları'nı
         eziyordu). #1594 fragment-sorununu (hürmüz 1w vs "Hürmüz Boğazı" 2w) da
         özgüllükle DAHA SAĞLAM çözer.
      6. Sonra **PROMINENCE** — en YÜKSEK df (aynı özgüllükte tam/baskın entity kazanır,
         real > rare-noise).
      7. Deterministik tie-break: norm.
    Dönüş: (norm, entity_type, display_name) | None.
    """
    valid = [
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
    if not valid:
        return None
    # canonical önce (True=0), sonra ÖZGÜLLÜK (-kelime sayısı = daha çok-kelimeli özne
    # önce), sonra prominence (-df = en yüksek), sonra norm.
    valid.sort(key=lambda c: (0 if c[4] else 1, -len(c[0].split()), -c[2], c[0]))
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
