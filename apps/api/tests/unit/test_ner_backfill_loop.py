"""NER backfill sonsuz döngüsü regresyon testleri (#1602).

Kök neden: entity-üretmeyen (gürültü: burç/tarif/moda) makaleler NER'de boş liste
dönünce `entities` tablosuna hiçbir şey yazılmıyordu → `NOT EXISTS(entities)` ile
backfill aynı makaleleri her 30 dk yeniden DeepSeek'e gönderiyordu (son 7 günde
NER çağrılarının %61'i israf). Fix: `_mark_ner_attempted` makaleyi
`entities_extracted_at=now()` ile işaretler; backfill `IS NULL` ile eler.

Bu testler iki invariant'ı korur:
  1. `_mark_ner_attempted` doğru kolonu doğru article için set eder.
  2. backfill eligibility sorgusu `entities_extracted_at IS NULL` guard'ını içerir
     (guard kaldırılırsa döngü geri döner → test fail).
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

from app.modules.entities.tasks.entities import (
    _backfill_entities_async,
    _mark_ner_attempted,
)


async def test_mark_ner_attempted_sets_extracted_at():
    """_mark_ner_attempted → UPDATE articles SET entities_extracted_at = now()."""
    db = AsyncMock()
    aid = uuid.uuid4()

    await _mark_ner_attempted(db, aid)

    db.execute.assert_awaited_once()
    stmt, params = db.execute.call_args.args
    sql = str(stmt)
    assert "entities_extracted_at" in sql
    assert "now()" in sql.lower()
    # doğru article'a binding (yanlış makaleyi işaretlememeli)
    assert params["aid"] == str(aid)


async def test_backfill_eligibility_query_has_extracted_guard(monkeypatch):
    """backfill COUNT sorgusu #1602 guard'ını (entities_extracted_at IS NULL) içermeli.

    Guard düşerse entity-üretmeyen makaleler tekrar eligible olur → sonsuz döngü.
    """
    executed_sqls: list[str] = []

    class _Result:
        def scalar(self) -> int:
            return 0  # eligible yok → dry_run dalına gir, dispatch'i atla

    class _Session:
        async def __aenter__(self) -> _Session:
            return self

        async def __aexit__(self, *_args: object) -> bool:
            return False

        async def execute(self, stmt: object, *_a: object, **_k: object) -> _Result:
            executed_sqls.append(str(stmt))
            return _Result()

        async def commit(self) -> None:
            return None

    # entities modülündeki _get_session_factory referansını mock session ile değiştir
    monkeypatch.setattr(
        "app.modules.entities.tasks.entities._get_session_factory",
        lambda: _Session,
    )

    summary = await _backfill_entities_async(dry_run=True)

    assert summary["status"] == "dry_run"
    assert any("entities_extracted_at IS NULL" in sql for sql in executed_sqls), (
        f"backfill eligibility sorgusunda #1602 guard yok: {executed_sqls}"
    )
