"""Integration — canonical entity admin SQL invariant'ları (#1554, Docker-gated).

İki kritik invariant:
  1. **Builder admin kararını EZMEZ:** builder alias upsert'ü
     `DO UPDATE ... WHERE source <> 'admin'` ile korunur → admin'in source='admin'
     alias'ı yeniden çalışan builder tarafından başka canonical'a taşınmaz.
     (Kontrol: source='token_subset' alias normal şekilde ezilir.)
  2. **Merge/split semantiği:** merge → kaynak alias'ları hedefe taşınır + kaynak
     silinir (FK CASCADE no-op, önce taşındığı için); split → alias kaydı kalkar.

test_db_session transaction-rollback fixture'ı içinde (commit yok) — testler izole.
tests/migration/ altında: CI'ın testcontainers job'u (`pytest tests/migration/ -m
integration`, `alembic upgrade head` ile tam şema) bu invariant'ları KOŞAR.
Docker yoksa (lokal) otomatik skip.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.integration


async def _mk_canonical(db, name: str, etype: str, source: str) -> uuid.UUID:
    cid = uuid.uuid4()
    await db.execute(
        text(
            "INSERT INTO canonical_entities "
            "(id, canonical_name, entity_type, canonical_normalized, source, status) "
            "VALUES (:id, :n, :t, :cn, :src, 'active')"
        ),
        {"id": cid, "n": name, "t": etype, "cn": name.lower(), "src": source},
    )
    return cid


async def _mk_alias(db, alias: str, etype: str, cid: uuid.UUID, source: str) -> None:
    await db.execute(
        text(
            "INSERT INTO entity_aliases "
            "(alias_normalized, entity_type, canonical_id, confidence, source) "
            "VALUES (:a, :t, :cid, 1.000, :src)"
        ),
        {"a": alias, "t": etype, "cid": cid, "src": source},
    )


# Builder'ın canonical.py'deki alias upsert'ünün BİREBİR kopyası (guard dahil).
_BUILDER_UPSERT = text(
    """
    INSERT INTO entity_aliases
        (alias_normalized, entity_type, canonical_id, confidence, source)
    VALUES (:alias, :etype, :cid, 0.900, 'token_subset')
    ON CONFLICT (alias_normalized, entity_type)
    DO UPDATE SET canonical_id = EXCLUDED.canonical_id,
                  source = EXCLUDED.source
    WHERE entity_aliases.source <> 'admin'
    """
)


async def _alias_state(db, alias: str, etype: str) -> tuple[uuid.UUID, str]:
    row = (
        await db.execute(
            text(
                "SELECT canonical_id, source FROM entity_aliases "
                "WHERE alias_normalized = :a AND entity_type = :t"
            ),
            {"a": alias, "t": etype},
        )
    ).one()
    return row.canonical_id, row.source


async def test_builder_does_not_overwrite_admin_alias(test_db_session):
    db = test_db_session
    a = await _mk_canonical(db, "Kanon A", "event", "admin")
    b = await _mk_canonical(db, "Kanon B", "event", "token_subset")
    await _mk_alias(db, "ortak varyant", "event", a, "admin")

    # builder B'ye taşımaya çalışır → guard engeller
    await db.execute(_BUILDER_UPSERT, {"alias": "ortak varyant", "etype": "event", "cid": b})

    cid, src = await _alias_state(db, "ortak varyant", "event")
    assert cid == a, "admin alias'ı builder tarafından taşınmamalı"
    assert src == "admin"


async def test_builder_overwrites_nonadmin_alias(test_db_session):
    db = test_db_session
    a = await _mk_canonical(db, "Kanon A2", "event", "token_subset")
    b = await _mk_canonical(db, "Kanon B2", "event", "token_subset")
    await _mk_alias(db, "serbest varyant", "event", a, "token_subset")

    await db.execute(_BUILDER_UPSERT, {"alias": "serbest varyant", "etype": "event", "cid": b})

    cid, src = await _alias_state(db, "serbest varyant", "event")
    assert cid == b, "admin-olmayan alias normal şekilde taşınmalı (kontrol)"
    assert src == "token_subset"


async def test_merge_moves_aliases_and_deletes_source(test_db_session):
    db = test_db_session
    target = await _mk_canonical(db, "Hedef", "org", "admin")
    source = await _mk_canonical(db, "Kaynak", "org", "seed")
    await _mk_alias(db, "hedef alias", "org", target, "admin")
    await _mk_alias(db, "kaynak a1", "org", source, "seed")
    await _mk_alias(db, "kaynak a2", "org", source, "token_subset")

    # merge endpoint mantığı: taşı → sil
    await db.execute(
        text(
            "UPDATE entity_aliases SET canonical_id = :tgt, source = 'admin' "
            "WHERE canonical_id = :src"
        ),
        {"tgt": target, "src": source},
    )
    await db.execute(text("DELETE FROM canonical_entities WHERE id = :src"), {"src": source})

    moved = (
        await db.execute(
            text("SELECT count(*) FROM entity_aliases WHERE canonical_id = :tgt"),
            {"tgt": target},
        )
    ).scalar()
    assert moved == 3, "tüm alias'lar hedefe taşınmalı"

    orphan = (
        await db.execute(
            text("SELECT count(*) FROM entity_aliases WHERE canonical_id = :src"),
            {"src": source},
        )
    ).scalar()
    assert orphan == 0, "kaynak canonical alias'ı kalmamalı"

    gone = (
        await db.execute(
            text("SELECT count(*) FROM canonical_entities WHERE id = :src"), {"src": source}
        )
    ).scalar()
    assert gone == 0, "kaynak canonical silinmeli"


async def test_remove_alias_split(test_db_session):
    db = test_db_session
    c = await _mk_canonical(db, "Grup", "person", "admin")
    await _mk_alias(db, "ayrılacak", "person", c, "admin")
    await _mk_alias(db, "kalacak", "person", c, "admin")

    res = await db.execute(
        text(
            "DELETE FROM entity_aliases WHERE canonical_id = :cid "
            "AND alias_normalized = :a AND entity_type = 'person'"
        ),
        {"cid": c, "a": "ayrılacak"},
    )
    assert res.rowcount == 1

    remaining = (
        (
            await db.execute(
                text("SELECT alias_normalized FROM entity_aliases WHERE canonical_id = :cid"),
                {"cid": c},
            )
        )
        .scalars()
        .all()
    )
    assert remaining == ["kalacak"]


async def test_list_search_matches_alias(test_db_session):
    """#1558: liste araması canonical adını VEYA bağlı bir alias'ı eşlemeli.

    "chp" araması "Cumhuriyet Halk Partisi"yi getirmeli (chp = alias).
    list_canonical read-only (commit yok) → test_db_session içinde güvenli çağrılır.
    """
    from app.api.admin_entities import list_canonical

    db = test_db_session
    c = await _mk_canonical(db, "Cumhuriyet Halk Partisi", "org", "seed")
    await _mk_alias(db, "cumhuriyet halk partisi", "org", c, "seed")
    await _mk_alias(db, "chp", "org", c, "seed")

    # alias ile arama → canonical bulunur
    res = await list_canonical(admin=None, db=db, search="chp")  # type: ignore[arg-type]
    assert "Cumhuriyet Halk Partisi" in [r.canonical_name for r in res.data]

    # canonical adıyla arama da çalışır (regresyon)
    res2 = await list_canonical(admin=None, db=db, search="cumhuriyet")  # type: ignore[arg-type]
    assert "Cumhuriyet Halk Partisi" in [r.canonical_name for r in res2.data]

    # eşleşmeyen arama → boş
    res3 = await list_canonical(admin=None, db=db, search="zzz-yok")  # type: ignore[arg-type]
    assert all(r.canonical_name != "Cumhuriyet Halk Partisi" for r in res3.data)
