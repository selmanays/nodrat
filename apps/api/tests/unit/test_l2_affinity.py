"""#1019 (Pivot Faz 5) — L2 retrieval-affinity invariant testleri.

`apply_l2_affinity_boost`: flag+user gate'li ADDITIVE boost, retrieval
cache SONRASI. Bu testler güvenlik invaryantlarını KANITLAR:
  - flag-off | user-None | affinity-yok | eşleşme-yok → byte-identical no-op
    (#854; aynı liste objesi, gereksiz DB yok)
  - additive-only, ASLA down-rank (S6): eşleşen +boost, diğeri DOKUNULMAZ
  - SQL user-scoped (S11) + deprecated-excluded (S12)
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

from app.core.retrieval import apply_l2_affinity_boost
from app.shared.runtime_config.settings_store import settings_store

_UID = uuid.uuid4()


class _ScalarsRes:
    def __init__(self, items: list):
        self._items = items

    def scalars(self):
        return self

    def all(self):
        return self._items


class _RowsRes:
    def __init__(self, rows: list):
        self._rows = rows

    def all(self):
        return self._rows


def _chunk(aid: str, score: float) -> dict:
    return {"article_id": aid, "_rrf_score": score, "chunk_id": f"c-{aid}"}


async def test_user_id_none_byte_identical():
    chunks = [_chunk("a1", 0.5)]
    db = AsyncMock()
    out = await apply_l2_affinity_boost(db, user_id=None, chunks=chunks)
    assert out is chunks  # aynı obje = byte-identical
    db.execute.assert_not_called()


async def test_empty_chunks_noop():
    db = AsyncMock()
    out = await apply_l2_affinity_boost(db, user_id=_UID, chunks=[])
    assert out == []
    db.execute.assert_not_called()


async def test_flag_off_byte_identical(monkeypatch):
    monkeypatch.setattr(settings_store, "get_bool", AsyncMock(return_value=False))
    chunks = [_chunk("a1", 0.5)]
    db = AsyncMock()
    out = await apply_l2_affinity_boost(db, user_id=_UID, chunks=chunks)
    assert out is chunks
    db.execute.assert_not_called()  # flag kapalı → hiç sorgu yok


async def test_no_affinity_noop(monkeypatch):
    monkeypatch.setattr(settings_store, "get_bool", AsyncMock(return_value=True))
    monkeypatch.setattr(settings_store, "get_float", AsyncMock(return_value=0.05))
    chunks = [_chunk("a1", 0.5)]
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[_ScalarsRes([])])  # affinity boş
    out = await apply_l2_affinity_boost(db, user_id=_UID, chunks=chunks)
    assert out is chunks
    assert db.execute.call_count == 1  # entity sorgusu HİÇ çalışmadı


async def test_no_entity_match_noop(monkeypatch):
    monkeypatch.setattr(settings_store, "get_bool", AsyncMock(return_value=True))
    monkeypatch.setattr(settings_store, "get_float", AsyncMock(return_value=0.05))
    chunks = [_chunk("a1", 0.5), _chunk("a2", 0.6)]
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _ScalarsRes(["Özgür Özel"]),
            _RowsRes([("a1", "başka entity"), ("a2", "alakasız")]),
        ]
    )
    out = await apply_l2_affinity_boost(db, user_id=_UID, chunks=chunks)
    assert out is chunks  # eşleşme yok → değişmedi
    assert [c["_rrf_score"] for c in out] == [0.5, 0.6]


async def test_additive_only_no_downrank(monkeypatch):
    """S6: eşleşen +boost; eşleşmeyen skor DOKUNULMAZ; sıralama desc."""
    monkeypatch.setattr(settings_store, "get_bool", AsyncMock(return_value=True))
    monkeypatch.setattr(settings_store, "get_float", AsyncMock(return_value=0.05))
    chunks = [_chunk("a1", 0.50), _chunk("a2", 0.60)]
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _ScalarsRes(["Özgür Özel"]),
            _RowsRes([("a1", "özgür özel")]),  # yalnız a1 eşleşir
        ]
    )
    out = await apply_l2_affinity_boost(db, user_id=_UID, chunks=chunks)
    by = {c["article_id"]: c["_rrf_score"] for c in out}
    assert by["a1"] == 0.55  # +0.05 additive
    assert by["a2"] == 0.60  # DOKUNULMADI (no down-rank)
    # Hiçbir skor azalmadı
    assert all(by[a] >= s for a, s in (("a1", 0.50), ("a2", 0.60)))
    # desc sıralı
    assert [c["_rrf_score"] for c in out] == sorted([c["_rrf_score"] for c in out], reverse=True)


async def test_boost_reorders_up_only(monkeypatch):
    """Recall sinyali: yeterli boost eşleşeni öne taşır; diğerinin SKORU
    değişmez (rank kayması additive sonucu, negatif düzeltme YOK)."""
    monkeypatch.setattr(settings_store, "get_bool", AsyncMock(return_value=True))
    monkeypatch.setattr(settings_store, "get_float", AsyncMock(return_value=0.20))
    chunks = [_chunk("a2", 0.60), _chunk("a1", 0.50)]
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[_ScalarsRes(["X"]), _RowsRes([("a1", "x")])])
    out = await apply_l2_affinity_boost(db, user_id=_UID, chunks=chunks)
    assert out[0]["article_id"] == "a1"  # 0.50+0.20=0.70 > 0.60 → öne
    assert out[0]["_rrf_score"] == 0.70
    assert out[1]["article_id"] == "a2"
    assert out[1]["_rrf_score"] == 0.60  # skor değişmedi (sadece rank)


async def test_sql_user_scoped_and_deprecated_excluded(monkeypatch):
    """S11: yalnız mc.user_id=:uid. S12: deprecated_at IS NULL."""
    monkeypatch.setattr(settings_store, "get_bool", AsyncMock(return_value=True))
    monkeypatch.setattr(settings_store, "get_float", AsyncMock(return_value=0.05))
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[_ScalarsRes([])])
    await apply_l2_affinity_boost(db, user_id=_UID, chunks=[_chunk("a1", 0.5)])
    call = db.execute.call_args_list[0]
    sql = str(call.args[0])
    params = call.args[1]
    assert "mc.user_id = :uid" in sql
    assert "deprecated_at IS NULL" in sql
    assert params == {"uid": str(_UID)}
