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


# ---- #1720: canonical-katman merge (FakeDB) -------------------------------
class _FakeResult:
    def __init__(self, rows=None, scalar=None, scalar_list=None):
        self._rows = rows or []
        self._scalar = scalar
        self._scalar_list = scalar_list or []

    def mappings(self):
        return self

    def all(self):
        return self._rows

    def scalar(self):
        return self._scalar

    def scalars(self):
        outer = self

        class _S:
            def all(self_inner):
                return outer._scalar_list

        return _S()


class _FakeDB:
    """SQL metnine göre kanned sonuç döndüren sahte async session — kontrol akışını test eder.

    NOT: ON CONFLICT/CASCADE/FK semantiği sahte-DB ile DOĞRULANAMAZ (o, prod dry-run +
    küçük gerçek-run ile); bu test yalnız akış-sözleşmesini korur (dry-run yazmaz; merge
    DELETE eder; upgrade etmez).
    """

    def __init__(
        self, candidates=None, upsert_id=None, c_aliases=None, reheal_rows=None, reverify_rows=None
    ):
        self._candidates = candidates or []
        self._upsert_id = upsert_id
        self._c_aliases = c_aliases or []
        self._reheal_rows = reheal_rows or []
        self._reverify_rows = reverify_rows or []
        self.executed = []  # (tag, params)
        self.commits = 0
        self.rollbacks = 0

    async def execute(self, sql, params=None):
        s = str(sql)
        self.executed.append((s, params or {}))
        # re-verify SELECT (alias ⋈ canonical ⋈ resolutions) — reheal'den ÖNCE eşleştir
        if "a.alias_normalized AS alias" in s:
            return _FakeResult(rows=self._reverify_rows)
        # reheal SELECT (canonical ⋈ resolutions) — ana aday SELECT'inden ÖNCE eşleştir
        if "JOIN" in s and "wikidata_entity_resolutions" in s and "r.status" in s:
            return _FakeResult(rows=self._reheal_rows)
        if "FROM canonical_entities ce" in s and "token_subset" in s:
            return _FakeResult(rows=self._candidates)
        if "INSERT INTO canonical_entities" in s and "RETURNING id" in s:
            return _FakeResult(scalar=self._upsert_id)
        if "SELECT alias_normalized FROM entity_aliases" in s:
            return _FakeResult(scalar_list=self._c_aliases)
        return _FakeResult()

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1

    def tags(self, needle):
        return [p for (s, p) in self.executed if needle in s]


def _resolved_provider():
    meta = WikidataEntityMeta(
        qid="Q123",
        label_tr="15-16 Haziran olayları",
        trwiki_title="15-16 Haziran olayları",
        aliases_tr=["15-16 Haziran Direnişi"],
        p31=["Q1190554"],
    )
    return _FakeProvider(articles=[_article("15-16 Haziran olayları")], qid="Q123", meta=meta)


def _candidate(
    cid="c1", nm="15-16 Haziran Büyük İşçi Direnişi", cn="15-16 haziran buyuk isci direnisi"
):
    return {"id": cid, "nm": nm, "et": "event", "cn": cn}


async def _yes(_q, _t, _s):  # LLM precision gate stub → AYNI (merge geçer)
    return True


async def _no(_q, _t, _s):  # LLM precision gate stub → FARKLI (merge yok)
    return False


@pytest.mark.asyncio
async def test_canon_layer_dry_run_writes_nothing():
    from app.modules.entities.tasks.wikidata_enrich import _enrich_canonical_layer

    db = _FakeDB([_candidate()], upsert_id="w1", c_aliases=[])
    out = await _enrich_canonical_layer(
        db, _resolved_provider(), limit=50, refresh_days=30, dry_run=True, verifier=_yes
    )
    assert out["canon_scanned"] == 1
    assert out["canon_resolved"] == 1
    # dry-run: yalnız aday SELECT'i çalışmalı, hiçbir yazma/commit olmamalı
    assert db.commits == 0
    assert not db.tags("INSERT INTO")
    assert not db.tags("DELETE FROM canonical_entities")
    assert not db.tags("UPDATE canonical_entities")


@pytest.mark.asyncio
async def test_canon_layer_merge_deletes_orphan_and_repoints():
    from app.modules.entities.tasks.wikidata_enrich import _enrich_canonical_layer

    db = _FakeDB(
        [_candidate(cid="c1")],
        upsert_id="w1",  # ≠ c1 → merge yolu
        c_aliases=["eski alias"],
    )
    out = await _enrich_canonical_layer(
        db, _resolved_provider(), limit=50, refresh_days=30, dry_run=False, verifier=_yes
    )
    assert out["canon_resolved"] == 1
    assert out["canon_merged"] == 1
    assert out["canon_upgraded"] == 0
    # orphan C silindi
    deletes = db.tags("DELETE FROM canonical_entities")
    assert len(deletes) == 1 and deletes[0]["c"] == "c1"
    # alias'lar W'ye re-point edildi (C'nin alias'ı + C.normalized + Wikipedia alias'ı)
    alias_targets = [p for p in db.tags("INSERT INTO entity_aliases") if "cid" in p]
    assert alias_targets, "alias upsert çalışmadı"
    assert all(p["cid"] == "w1" for p in alias_targets)
    repointed = {p["alias"] for p in alias_targets}
    assert "eski alias" in repointed  # C'nin mevcut alias'ı re-point
    assert "15-16 haziran buyuk isci direnisi" in repointed  # C.normalized alias oldu
    # 'denendi' guard yazıldı
    assert db.tags("wikidata_entity_resolutions")


@pytest.mark.asyncio
async def test_canon_layer_upgrade_in_place_no_delete():
    from app.modules.entities.tasks.wikidata_enrich import _enrich_canonical_layer

    db = _FakeDB(
        [_candidate(cid="c1")],
        upsert_id="c1",  # == cid → yerinde yükseltme
        c_aliases=[],
    )
    out = await _enrich_canonical_layer(
        db, _resolved_provider(), limit=50, refresh_days=30, dry_run=False, verifier=_yes
    )
    assert out["canon_upgraded"] == 1
    assert out["canon_merged"] == 0
    assert not db.tags("DELETE FROM canonical_entities")  # orphan DELETE YOK


@pytest.mark.asyncio
async def test_canon_layer_no_match_no_merge():
    from app.modules.entities.tasks.wikidata_enrich import _enrich_canonical_layer

    db = _FakeDB([_candidate()], upsert_id="w1", c_aliases=[])
    prov = _FakeProvider(articles=[])  # çözülemez → no_match
    out = await _enrich_canonical_layer(
        db, prov, limit=50, refresh_days=30, dry_run=False, verifier=_yes
    )
    assert out["canon_no_match"] == 1
    assert out["canon_merged"] == 0 and out["canon_upgraded"] == 0
    assert not db.tags("DELETE FROM canonical_entities")
    # guard yine de yazıldı ('denendi')
    assert db.tags("wikidata_entity_resolutions")


@pytest.mark.asyncio
async def test_canon_layer_llm_reject_no_merge():
    """LLM precision gate HAYIR derse (konu-kayması) → llm_reject, merge YOK (#1720)."""
    from app.modules.entities.tasks.wikidata_enrich import _enrich_canonical_layer

    # provider tip-doğru çözer ama verifier=_no → llm_reject
    db = _FakeDB([_candidate()], upsert_id="w1", c_aliases=["eski alias"])
    out = await _enrich_canonical_layer(
        db, _resolved_provider(), limit=50, refresh_days=30, dry_run=False, verifier=_no
    )
    assert out["canon_llm_reject"] == 1
    assert out["canon_resolved"] == 0
    assert out["canon_merged"] == 0 and out["canon_upgraded"] == 0
    # merge yok → DELETE yok, alias re-point yok; ama 'denendi' guard yazıldı
    assert not db.tags("DELETE FROM canonical_entities")
    assert not [p for p in db.tags("INSERT INTO entity_aliases") if "cid" in p]
    assert db.tags("wikidata_entity_resolutions")


@pytest.mark.asyncio
async def test_canon_layer_dry_run_llm_reject_counts():
    """Dry-run'da verifier=_no → canon_llm_reject sayılır, yazma yok (#1720 preview)."""
    from app.modules.entities.tasks.wikidata_enrich import _enrich_canonical_layer

    db = _FakeDB([_candidate()], upsert_id="w1", c_aliases=[])
    out = await _enrich_canonical_layer(
        db, _resolved_provider(), limit=50, refresh_days=30, dry_run=True, verifier=_no
    )
    assert out["canon_llm_reject"] == 1
    assert out["canon_resolved"] == 0
    assert db.commits == 0
    assert not db.tags("INSERT INTO")


# ---- #1725: self-heal (cache'li resolved → LLM'siz yeniden merge) -----------
def _reheal_row(cid="c1", cn="15-16 haziran buyuk isci direnisi", title="15-16 Haziran olayları"):
    return {
        "id": cid,
        "nm": "15-16 Haziran Büyük İşçi Direnişi",
        "et": "event",
        "cn": cn,
        "title": title,
    }


@pytest.mark.asyncio
async def test_reheal_merges_cached_without_llm():
    """build_canonical'ın geri-yarattığı token_subset, cache'li resolved'dan LLM'siz merge (#1725)."""
    from app.modules.entities.tasks.wikidata_enrich import _reheal_canonical_layer

    db = _FakeDB(upsert_id="w1", c_aliases=["eski alias"], reheal_rows=[_reheal_row(cid="c1")])
    out = await _reheal_canonical_layer(db, limit=100, dry_run=False)
    assert out["reheal_scanned"] == 1
    assert out["reheal_merged"] == 1
    # orphan token_subset silindi + alias'lar W'ye re-point (provider/LLM ÇAĞRILMADAN)
    deletes = db.tags("DELETE FROM canonical_entities")
    assert len(deletes) == 1 and deletes[0]["c"] == "c1"
    alias_targets = [p for p in db.tags("INSERT INTO entity_aliases") if "cid" in p]
    assert alias_targets and all(p["cid"] == "w1" for p in alias_targets)
    assert "eski alias" in {p["alias"] for p in alias_targets}
    assert "15-16 haziran buyuk isci direnisi" in {p["alias"] for p in alias_targets}


@pytest.mark.asyncio
async def test_reheal_skips_when_title_is_self():
    """Cache'li başlık zaten bu canonical'ın kendisiyse (normalized eşit) → onarım yok."""
    from app.modules.entities.tasks.wikidata_enrich import _reheal_canonical_layer

    # title normalize → cn ile aynı → skip
    row = _reheal_row(cid="c1", cn="15-16 haziran olayları", title="15-16 Haziran olayları")
    db = _FakeDB(upsert_id="w1", reheal_rows=[row])
    out = await _reheal_canonical_layer(db, limit=100, dry_run=False)
    assert out["reheal_scanned"] == 1
    assert out["reheal_merged"] == 0
    assert not db.tags("DELETE FROM canonical_entities")


@pytest.mark.asyncio
async def test_reheal_dry_run_no_writes():
    """Dry-run reheal: sayar ama hiçbir yazma/commit yapmaz (#1725 preview)."""
    from app.modules.entities.tasks.wikidata_enrich import _reheal_canonical_layer

    db = _FakeDB(upsert_id="w1", reheal_rows=[_reheal_row(cid="c1")])
    out = await _reheal_canonical_layer(db, limit=100, dry_run=True)
    assert out["reheal_merged"] == 1
    assert db.commits == 0
    assert not db.tags("INSERT INTO")
    assert not db.tags("DELETE FROM canonical_entities")


# ---- #1729: entity-pass drift cleanup (re-verify) ---------------------------
def _reverify_row(alias="kemal irmak", cname="Mustafa Kemal Atatürk", cid="w1"):
    return {"alias": alias, "et": "person", "cid": cid, "cname": cname}


@pytest.mark.asyncio
async def test_reverify_deletes_drift_alias():
    """LLM 'farklı' derse (kemal irmak ✗ Atatürk) → alias SİL + guard llm_reject (#1729)."""
    from app.modules.entities.tasks.wikidata_enrich import _reverify_wikidata_aliases

    db = _FakeDB(reverify_rows=[_reverify_row(alias="kemal irmak", cid="w1")])
    out = await _reverify_wikidata_aliases(db, limit=100, dry_run=False, verifier=_no)
    assert out["reverify_scanned"] == 1
    assert out["reverify_deleted"] == 1
    dels = db.tags("DELETE FROM entity_aliases")
    assert dels and dels[0]["a"] == "kemal irmak" and dels[0]["c"] == "w1"
    # guard llm_reject'e çevrildi
    assert [p for p in db.tags("UPDATE wikidata_entity_resolutions") if p.get("a") == "kemal irmak"]


@pytest.mark.asyncio
async def test_reverify_keeps_correct_alias():
    """LLM 'aynı' derse (gazi paşa ✓ Atatürk) → dokunma, silme yok (#1729)."""
    from app.modules.entities.tasks.wikidata_enrich import _reverify_wikidata_aliases

    db = _FakeDB(reverify_rows=[_reverify_row(alias="gazi paşa")])
    out = await _reverify_wikidata_aliases(db, limit=100, dry_run=False, verifier=_yes)
    assert out["reverify_scanned"] == 1
    assert out["reverify_deleted"] == 0
    assert not db.tags("DELETE FROM entity_aliases")


@pytest.mark.asyncio
async def test_reverify_dry_run_no_writes():
    """Dry-run: drift'i sayar ama silmez/commit etmez (#1729 preview — gözle inceleme)."""
    from app.modules.entities.tasks.wikidata_enrich import _reverify_wikidata_aliases

    db = _FakeDB(reverify_rows=[_reverify_row(alias="kemal irmak")])
    out = await _reverify_wikidata_aliases(db, limit=100, dry_run=True, verifier=_no)
    assert out["reverify_deleted"] == 1
    assert db.commits == 0
    assert not db.tags("DELETE FROM entity_aliases")
