"""Regression tests for SFT curator fatal bugs (#audit 2026-05-15).

İki üretim-fatal hata, sıfır test kapsamı yüzünden aylarca fark edilmedi:
  1. `settings_store.get_bool("sft.curator.enabled", False)` — imza
     `get_bool(db, key, default)`; db'siz çağrı try/except DIŞINDA, ilk
     satırda → her gece task çöküyordu (curator hiç sample üretmedi).
  2. `redact_result.has_redactions` — RedactionResult'ta yok (`has_pii`).

Bu testler iki hatayı da regresyona karşı kilitler; gerçek
`settings_store` singleton + gerçek `RedactionResult` ile koşar.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from app.workers.tasks import sft_curator


class _FakeResult:
    def __init__(self, rows=None, scalar=None, first=None):
        self._rows = rows or []
        self._scalar = scalar
        self._first = first

    def all(self):
        return self._rows

    def scalar_one_or_none(self):
        return self._scalar

    def first(self):
        return self._first


class _FakeSession:
    """Sıralı .execute() sonuçları döndüren minimal async session mock."""

    def __init__(self, results: list[_FakeResult] | None = None):
        self._results = list(results or [])
        self.commits = 0
        self.rollbacks = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, *_a, **_kw):
        if self._results:
            return self._results.pop(0)
        return _FakeResult()  # boş: settings _db_get .first()=None → default

    async def flush(self):
        pass

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


def _factory(session: _FakeSession):
    def _make():
        return session
    return _make


def test_curator_disabled_path_does_not_crash():
    """Bug 1: gerçek settings_store.get_bool(db, ...) çağrısı db arg ile
    yapılmalı. db'siz olsaydı disabled kontrolünden ÖNCE TypeError/
    AttributeError ile patlardı. Default False → temiz 'disabled'."""
    session = _FakeSession()  # execute → boş result → settings default False
    with patch.object(
        sft_curator, "_get_session_factory", lambda: _factory(session)
    ):
        out = asyncio.run(sft_curator._sft_curator_async(None))
    assert out["status"] == "disabled"
    assert out["scanned"] == 0


def test_curator_pii_skip_uses_has_pii_attribute():
    """Bug 2: PII tespitinde `redact_result.has_pii` kullanılmalı.
    `has_redactions` (yok) olsaydı AttributeError → except → errors+1,
    skipped_pii=0. Gerçek redact()/RedactionResult ile koşar."""
    now = datetime.now(timezone.utc)
    conv_id, msg_id = uuid4(), uuid4()
    assistant = SimpleNamespace(
        id=msg_id,
        role="assistant",
        content="Cevap metni [1].",
        created_at=now,
        conversation_id=conv_id,
        sft_eligible=True,
        dpo_rejected=False,
        edited_content=None,
        dpo_chosen_content=None,
    )
    conv = SimpleNamespace(id=conv_id, user_id=uuid4())
    user = SimpleNamespace(id=conv.user_id)
    # Önceki user mesajı PII içerir (e-posta) → has_pii True beklenir
    prev_user = SimpleNamespace(
        id=uuid4(),
        role="user",
        content="Bana ulas: gizli.kullanici@example.com adresinden",
        created_at=now,
        conversation_id=conv_id,
    )
    session = _FakeSession([
        _FakeResult(rows=[(assistant, conv, user)]),  # rows_q
        _FakeResult(scalar=prev_user),                # prev user select
        _FakeResult(),                                # update(...)
    ])
    with (
        patch.object(
            sft_curator, "_get_session_factory", lambda: _factory(session)
        ),
        patch.object(
            sft_curator.settings_store, "get_bool",
            AsyncMock(return_value=True),
        ),
        patch.object(
            sft_curator.settings_store, "get_int",
            AsyncMock(return_value=10),
        ),
    ):
        out = asyncio.run(sft_curator._sft_curator_async(None))
    assert out["skipped_pii"] == 1
    assert out["errors"] == 0
    assert session.commits == 1


def test_settings_store_get_bool_requires_db_first_arg():
    """İmza kontratı kilidi: get_bool/get_int ilk pozisyonel param `db`.
    Curator'ın (veya başka çağıranın) db'siz çağrı yapması bu testle
    erken yakalanır."""
    import inspect

    from app.core.settings_store import settings_store

    for name in ("get_bool", "get_int", "get"):
        params = list(
            inspect.signature(getattr(settings_store, name)).parameters
        )
        assert params[0] == "db", f"{name} ilk param 'db' olmalı, {params}"
