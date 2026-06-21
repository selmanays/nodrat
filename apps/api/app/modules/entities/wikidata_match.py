"""Wikidata eşleştirme — saf yardımcılar (#1710). Tip-gate + canonical-etiket seçimi.

DB/IO yok → birim-test edilebilir. Asıl çözüm (Wikipedia/Wikidata HTTP) `tasks/
wikidata_enrich.py`'de; buradaki saf karar mantığı oradan çağrılır.
"""

from __future__ import annotations

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


def select_canonical_label(trwiki_title: str | None, label_tr: str) -> str:
    """Canonical etiket = Wikipedia TR madde başlığı (sitelink) öncelikli; yoksa
    Wikidata TR label. İkisi de 'Wikipedia başlık karşılığı' (founder isteği)."""
    return (trwiki_title or label_tr or "").strip()
