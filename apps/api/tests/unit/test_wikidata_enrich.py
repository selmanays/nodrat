"""Unit — Wikidata canonical-etiket zenginleştirme (#1710).

Saf karar mantığı: tip-gate (P31 ↔ NER), canonical-etiket seçimi + `_resolve_one`
akışı (FakeProvider ile ağsız). Asıl HTTP + DB upsert entegrasyon/manuel-doğrulama.
"""

from __future__ import annotations

import pytest
from app.modules.entities.wikidata_match import (
    select_canonical_label,
    strip_event_edition,
    type_matches,
)
from app.providers.wikipedia import WikiArticle, WikidataEntityMeta


# ---- tip-gate (P31 ↔ NER) -------------------------------------------------
def test_type_matches_person_requires_human():
    assert type_matches("person", ["Q5"]) is True
    assert type_matches("person", ["Q5", "Q82955"]) is True  # human + politician
    # insan değil (mahalle/üniversite/stadyum) → RED
    assert type_matches("person", ["Q3957"]) is False
    assert type_matches("person", []) is False  # P31 yok → person RED


def test_type_matches_place_org_event_deny_human_and_date():
    # yer/kurum/olay: insan veya tarih → RED; aksi kabul
    assert type_matches("place", ["Q6256"]) is True  # country
    assert type_matches("org", ["Q7278"]) is True  # political party
    assert type_matches("event", ["Q1190554"]) is True  # occurrence
    # "15 temmuz" → takvim günü (Q47150325) çözümü → RED (#997 hatası)
    assert type_matches("event", ["Q47150325"]) is False
    assert type_matches("place", ["Q577"]) is False  # year
    # yer diye etiketli ama insana çözülmüş → RED
    assert type_matches("place", ["Q5"]) is False
    # boş P31 → yer/kurum/olay kabul (tarih/insan değil)
    assert type_matches("place", []) is True


def test_type_matches_mixed_p31():
    # tarih + gerçek tip karışık → tarih varlığı RED (yanlış sayfa şüphesi)
    assert type_matches("event", ["Q1656682", "Q47150325"]) is False
    # insan + başka → person için Q5 yeterli
    assert type_matches("person", ["Q5", "Q33999"]) is True


# ---- canonical-etiket seçimi ----------------------------------------------
def test_select_canonical_label_prefers_trwiki_title():
    assert (
        select_canonical_label("Türkiye kadın millî voleybol takımı", "Filenin Sultanları")
        == "Türkiye kadın millî voleybol takımı"
    )
    # trwiki yoksa label
    assert select_canonical_label(None, "Recep Tayyip Erdoğan") == "Recep Tayyip Erdoğan"
    assert select_canonical_label("", "X") == "X"
    assert select_canonical_label(None, "") == ""


# ---- _resolve_one akışı (FakeProvider) ------------------------------------
class _FakeProvider:
    def __init__(self, articles=None, qid=None, meta=None):
        self._articles = articles or []
        self._qid = qid
        self._meta = meta

    async def search(self, query, *, top_k=1):
        return self._articles

    async def wikidata_qid_for_title(self, title, lang="tr"):
        return self._qid

    async def wikidata_entity_meta(self, qid, *, lang="tr"):
        return self._meta


def _article(title):
    return WikiArticle(title=title, summary="", url="", page_id=1, lang="tr")


@pytest.mark.asyncio
async def test_resolve_one_no_article():
    from app.modules.entities.tasks.wikidata_enrich import _resolve_one

    status, qid, _title, _aliases, _p31 = await _resolve_one(_FakeProvider(), "Bilinmeyen", "org")
    assert status == "no_match" and qid is None


@pytest.mark.asyncio
async def test_resolve_one_no_qid():
    from app.modules.entities.tasks.wikidata_enrich import _resolve_one

    prov = _FakeProvider(articles=[_article("Bir Şey")], qid=None)
    status, *_ = await _resolve_one(prov, "Bir Şey", "org")
    assert status == "no_match"


@pytest.mark.asyncio
async def test_resolve_one_type_mismatch():
    from app.modules.entities.tasks.wikidata_enrich import _resolve_one

    # "15 temmuz" event diye etiketli ama takvim gününe çözülmüş → type_mismatch
    meta = WikidataEntityMeta(
        qid="Q47150325",
        label_tr="15 Temmuz",
        trwiki_title="15 Temmuz",
        aliases_tr=[],
        p31=["Q47150325"],
    )
    prov = _FakeProvider(articles=[_article("15 Temmuz")], qid="Q47150325", meta=meta)
    status, _qid, _title, _aliases, p31 = await _resolve_one(prov, "15 temmuz", "event")
    assert status == "type_mismatch"
    assert p31 == ["Q47150325"]


@pytest.mark.asyncio
async def test_resolve_one_resolved_with_trwiki_title_and_aliases():
    from app.modules.entities.tasks.wikidata_enrich import _resolve_one

    meta = WikidataEntityMeta(
        qid="Q254101",
        label_tr="Türkiye kadın millî voleybol takımı",
        trwiki_title="Türkiye kadın millî voleybol takımı",
        aliases_tr=["Filenin Sultanları"],
        p31=["Q1194951"],  # national sports team
    )
    prov = _FakeProvider(articles=[_article("Filenin Sultanları")], qid="Q254101", meta=meta)
    status, qid, title, aliases, _p31 = await _resolve_one(prov, "Filenin Sultanları", "org")
    assert status == "resolved"
    assert title == "Türkiye kadın millî voleybol takımı"
    assert aliases == ["Filenin Sultanları"]
    assert qid == "Q254101"


# ---- #1714: olay yıl/sıra-öneki sıyırma -----------------------------------
def test_strip_event_edition():
    assert strip_event_edition("2026 Avrupa Tekvando Şampiyonası") == (
        "Avrupa Tekvando Şampiyonası",
        "2026",
    )
    assert strip_event_edition("49. G7 zirvesi") == ("G7 zirvesi", "49.")
    # önek yok → değişmez
    assert strip_event_edition("Yükseköğretim Kurumları Sınavı") == (
        "Yükseköğretim Kurumları Sınavı",
        None,
    )
    # kısa/anlamsız taban korunur ("1984 (roman)" → sıyrılmaz, base<3 değil ama (roman) korunmalı)
    assert strip_event_edition("2026 AB") == ("2026 AB", None)  # taban "AB" <3 → sıyrılmaz


@pytest.mark.asyncio
async def test_resolve_one_event_edition_stripped():
    from app.modules.entities.tasks.wikidata_enrich import _resolve_one

    # "49. G7 zirvesi" → jenerik taban "G7 zirvesi" birincil; spesifik form alias
    meta = WikidataEntityMeta(
        qid="Q113192713",
        label_tr="49. G7 zirvesi",
        trwiki_title="49. G7 zirvesi",
        aliases_tr=[],
        p31=["Q1190554"],  # occurrence
    )
    prov = _FakeProvider(articles=[_article("49. G7 zirvesi")], qid="Q113192713", meta=meta)
    status, _qid, title, aliases, _p31 = await _resolve_one(prov, "G7 Zirvesi", "event")
    assert status == "resolved"
    assert title == "G7 zirvesi"  # jenerik taban
    assert "49. G7 zirvesi" in aliases  # spesifik form alias kalır
