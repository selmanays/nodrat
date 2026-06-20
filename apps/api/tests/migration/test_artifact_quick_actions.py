"""Integration — Faz 3b-2 LLM quick-action revizyonları (testcontainers).

`artifact_quick_action` endpoint'i (app_me) provider-mock ile doğrudan çağrılır
(HTTP'siz; mevcut test_artifact_revisions.py deseni). Provider routing
`app.providers.registry.registry.route_for_tier` + flag `settings_store.get_bool`
monkeypatch'lenir; gerçek LLM/maliyet çağrısı YOK. add_revision zinciri (seq++,
head, intent) + guard'lar (flag-off 403, ownership 404, geçersiz intent 422,
LLM-hata 502) doğrulanır.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from app.api.app_me import QuickActionBody, artifact_quick_action
from app.modules.generations.artifacts import create_artifact_with_revision
from fastapi import HTTPException
from sqlalchemy import text

pytestmark = pytest.mark.integration


# ---- helpers (test_artifact_revisions.py ile aynı, self-contained) ----------
async def _user(db) -> uuid.UUID:
    uid = uuid.uuid4()
    await db.execute(
        text("INSERT INTO users (id, email, password_hash) VALUES (:id, :e, 'x')"),
        {"id": uid, "e": f"u-{uid.hex[:8]}@test.local"},
    )
    return uid


async def _cluster(db) -> uuid.UUID:
    cid = uuid.uuid4()
    await db.execute(
        text(
            "INSERT INTO research_clusters (id, cluster_key, cluster_type, canonical_name) "
            "VALUES (:id, :k, 'topic', 'Asgari Ücret')"
        ),
        {"id": cid, "k": f"topic:{cid.hex[:10]}"},
    )
    return cid


class _FakeResult:
    """generate_text dönüşü — best-effort cost-log alanları dahil."""

    def __init__(self, text_: str):
        self.text = text_
        self.input_tokens = 120
        self.output_tokens = 40
        self.cached_input_tokens = 0
        self.cost_usd = 0.0001
        self.model = "deepseek-v4-flash"


def _patch_provider(monkeypatch, *, text_="Kısaltılmış içerik [1].", raises=None):
    """registry.route_for_tier → generate_text'i mock'layan provider döndür."""
    from app.providers.registry import registry as _reg

    p = SimpleNamespace(name="deepseek")
    if raises is not None:
        p.generate_text = AsyncMock(side_effect=raises)
    else:
        p.generate_text = AsyncMock(return_value=_FakeResult(text_))
    monkeypatch.setattr(_reg, "route_for_tier", lambda **_kw: p)
    return p


def _patch_flag(monkeypatch, value: bool):
    from app.shared.runtime_config.settings_store import settings_store as _ss

    monkeypatch.setattr(_ss, "get_bool", AsyncMock(return_value=value))


async def test_quick_action_success_creates_llm_revision(test_db_session, monkeypatch):
    db = test_db_session
    uid = await _user(db)
    cid = await _cluster(db)
    src = [{"title": "Kaynak A"}, {"url": "https://x.example/b"}]
    aid = await create_artifact_with_revision(
        db,
        user_id=uid,
        cluster_id=cid,
        content="Uzun orijinal metin [1] detaylarla.",
        sources_used=src,
    )
    p = _patch_provider(monkeypatch, text_="Kısa metin [1].")
    _patch_flag(monkeypatch, True)

    resp = await artifact_quick_action(
        artifact_id=aid,
        body=QuickActionBody(intent="quick_shorter"),
        user=SimpleNamespace(id=uid),
        db=db,
    )
    assert resp["revision_seq"] == 2
    assert resp["content"] == "Kısa metin [1]."
    p.generate_text.assert_awaited_once()

    revs = (
        await db.execute(
            text(
                "SELECT revision_seq, revision_intent, content, sources_used "
                "FROM artifact_revisions WHERE artifact_id=:a ORDER BY revision_seq"
            ),
            {"a": aid},
        )
    ).all()
    assert [r.revision_seq for r in revs] == [1, 2]
    assert revs[1].revision_intent == "quick_shorter"
    assert revs[1].content == "Kısa metin [1]."
    # sources_used yeni revizyona TAŞINDI (provenance korunur — review HIGH fix).
    assert revs[1].sources_used == src
    head = (
        await db.execute(text("SELECT head_revision_id FROM artifacts WHERE id=:a"), {"a": aid})
    ).scalar()
    head_seq = (
        await db.execute(
            text("SELECT revision_seq FROM artifact_revisions WHERE id=:h"), {"h": head}
        )
    ).scalar()
    assert head_seq == 2  # head en güncel revizyona taşındı


async def test_quick_action_flag_off_403_no_llm(test_db_session, monkeypatch):
    db = test_db_session
    uid = await _user(db)
    cid = await _cluster(db)
    aid = await create_artifact_with_revision(db, user_id=uid, cluster_id=cid, content="metin")
    p = _patch_provider(monkeypatch)
    _patch_flag(monkeypatch, False)

    with pytest.raises(HTTPException) as exc:
        await artifact_quick_action(
            artifact_id=aid,
            body=QuickActionBody(intent="quick_rewrite"),
            user=SimpleNamespace(id=uid),
            db=db,
        )
    assert exc.value.status_code == 403
    p.generate_text.assert_not_awaited()  # flag kapalı → LLM çağrılmaz


async def test_quick_action_invalid_intent_422(test_db_session, monkeypatch):
    db = test_db_session
    uid = await _user(db)
    cid = await _cluster(db)
    aid = await create_artifact_with_revision(db, user_id=uid, cluster_id=cid, content="metin")
    _patch_provider(monkeypatch)
    _patch_flag(monkeypatch, True)

    # 'edit'/'freetext' LLM intent'i DEĞİL → quick-action endpoint reddeder (422).
    with pytest.raises(HTTPException) as exc:
        await artifact_quick_action(
            artifact_id=aid,
            body=QuickActionBody(intent="edit"),
            user=SimpleNamespace(id=uid),
            db=db,
        )
    assert exc.value.status_code == 422


async def test_quick_action_ownership_404(test_db_session, monkeypatch):
    db = test_db_session
    uid = await _user(db)
    other = await _user(db)
    cid = await _cluster(db)
    aid = await create_artifact_with_revision(db, user_id=uid, cluster_id=cid, content="metin")
    _patch_provider(monkeypatch)
    _patch_flag(monkeypatch, True)

    with pytest.raises(HTTPException) as exc:
        await artifact_quick_action(
            artifact_id=aid,
            body=QuickActionBody(intent="quick_longer"),
            user=SimpleNamespace(id=other),  # başkası
            db=db,
        )
    assert exc.value.status_code == 404


async def test_quick_action_llm_failure_502(test_db_session, monkeypatch):
    db = test_db_session
    uid = await _user(db)
    cid = await _cluster(db)
    aid = await create_artifact_with_revision(db, user_id=uid, cluster_id=cid, content="metin")
    _patch_provider(monkeypatch, raises=RuntimeError("provider down"))
    _patch_flag(monkeypatch, True)

    with pytest.raises(HTTPException) as exc:
        await artifact_quick_action(
            artifact_id=aid,
            body=QuickActionBody(intent="quick_shorter"),
            user=SimpleNamespace(id=uid),
            db=db,
        )
    assert exc.value.status_code == 502
    # revizyon eklenmedi (yalnız initial)
    cnt = (
        await db.execute(
            text("SELECT count(*) FROM artifact_revisions WHERE artifact_id=:a"), {"a": aid}
        )
    ).scalar()
    assert cnt == 1


async def test_quick_action_empty_llm_output_502(test_db_session, monkeypatch):
    db = test_db_session
    uid = await _user(db)
    cid = await _cluster(db)
    aid = await create_artifact_with_revision(db, user_id=uid, cluster_id=cid, content="metin")
    _patch_provider(monkeypatch, text_="   ")  # boş/whitespace çıktı
    _patch_flag(monkeypatch, True)

    with pytest.raises(HTTPException) as exc:
        await artifact_quick_action(
            artifact_id=aid,
            body=QuickActionBody(intent="multi_share"),
            user=SimpleNamespace(id=uid),
            db=db,
        )
    assert exc.value.status_code == 502
