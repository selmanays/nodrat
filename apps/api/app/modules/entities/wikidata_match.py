"""Wikidata eşleştirme — saf yardımcılar (#1710/#1714). Tip-gate + canonical-etiket.

DB/IO yok → birim-test edilebilir. Asıl çözüm (Wikipedia/Wikidata HTTP) `tasks/
wikidata_enrich.py`'de; buradaki saf karar mantığı oradan çağrılır.
"""

from __future__ import annotations

import re

# P31 (instance of) tip doğrulama — #997 dersi: çıplak-keyword QID disambiguation
# güvenilmez ("15 temmuz" → takvim günü). Tip-gate yanlış-eşlemeyi reddeder.
_P31_HUMAN = "Q5"  # human
# takvim günü / zaman-noktası / yıl / tarih — '15 temmuz'→takvim hatası (tüm tipler için RED)
_P31_DATE = frozenset(
    {
        "Q47150325",  # calendar day of a given year
        "Q14795564",  # point in time with respect to recurrent timeframe
        "Q577",  # year
        "Q3186692",  # calendar year
        "Q18602249",  # specific calendar date
        "Q41825",  # calends? (date-ish noise)
        "Q205892",  # calendar date
        "Q1985727",  # month
    }
)

# #1714 — olay edisyon-öneki: "2026 ..." (yıl) veya "49. ..." (sıra). Birincil etiket
# jenerik taban olmalı (founder): "49. G7 zirvesi"→"G7 zirvesi", "2026 Avrupa Tekvando
# Şampiyonası"→"Avrupa Tekvando Şampiyonası". Spesifik form alias kalır → edisyonlar tek
# kümede toplanır (evergreen; yeni yıl/sayı otomatik aynı tabana düşer, case-specific değil).
_EVENT_YEAR_PREFIX = re.compile(r"^\d{4}\s+(\S.*)$")
_EVENT_ORDINAL_PREFIX = re.compile(r"^\d+\.\s+(\S.*)$")


def type_matches(ner_type: str, p31: list[str]) -> bool:
    """NER tipi ↔ Wikidata P31 uyumu (deny-temelli; lenient ama #997 hatalarını yakalar).

    - **person:** P31 = Q5 (human) ŞART — insanlar Wikidata'da daima Q5, güvenilir
      sinyal; insan-olmayan sayfaya (mahalle/üniversite/stadyum) çözülmeyi reddeder.
    - **place/org/event:** P31 İNSAN veya TARİH içeriyorsa RED (yanlış sayfaya çözülmüş);
      aksi halde kabul (yer/kurum/olay P31'leri çok çeşitli → whitelist kırılgan olur,
      deny daha sağlam). Boş P31 → person RED, diğerleri kabul (tarih/insan değilse).
    """
    pset = set(p31 or [])
    if ner_type == "person":
        return _P31_HUMAN in pset
    if _P31_HUMAN in pset:
        return False  # yer/kurum/olay diye etiketli ama insana çözülmüş
    # tarihe çözülmüşse RED (15 temmuz → takvim günü); aksi kabul
    return not (pset & _P31_DATE)


def is_generic_concept_title(title: str) -> bool:
    """Wikipedia başlığı JENERİK kavram mı (özel-ad değil)? (#1714)

    TR'de özel-adlar büyük harfle başlar ("TCMB", "Avrupa Tekvando Şampiyonası",
    "G7 zirvesi"); jenerik ortak-isim kavramları küçük harfle ("merkez bankası",
    "yapay zeka", "borsa"). İlk karakter küçük harfse → jenerik kavram → çapa OLAMAZ
    (#1705 genericliğinin Wikidata-çözüm seviyesindeki karşılığı; tip-gate'in
    yakalayamadığı "geçerli-ama-jenerik-org/kavram" yanlış-eşlemesini eler)."""
    t = (title or "").strip()
    if not t:
        return True
    return t[0].islower()


def strip_event_edition(title: str) -> tuple[str, str | None]:
    """Olay başlığından yıl/sıra önekini ayır → (jenerik_taban, edisyon|None). (#1714)

    "2026 Avrupa Tekvando Şampiyonası" → ("Avrupa Tekvando Şampiyonası", "2026")
    "49. G7 zirvesi" → ("G7 zirvesi", "49."). Önek yoksa (title, None). YALNIZ event
    tipi için çağrılmalı (çağıran tip-gate eder) — recurring-edition adlandırması olaylara
    özgü; "1984 (roman)" gibi eser-adları event olmadığı için sıyrılmaz. Taban ≥3 char
    (anlamsız kalıntıya karşı güvenlik)."""
    t = (title or "").strip()
    for rx in (_EVENT_YEAR_PREFIX, _EVENT_ORDINAL_PREFIX):
        m = rx.match(t)
        if m:
            base = m.group(1).strip()
            if len(base) >= 3:
                return base, t[: m.start(1)].strip()
    return t, None


def select_canonical_label(trwiki_title: str | None, label_tr: str) -> str:
    """Canonical etiket = Wikipedia TR madde başlığı (sitelink) öncelikli; yoksa
    Wikidata TR label (labels.tr — TR maddesi olmayan EN-kaynaklı entity'de bile TR
    karşılığını verir, #1714 EN-fallback). İkisi de 'Wikipedia başlık karşılığı'."""
    return (trwiki_title or label_tr or "").strip()
