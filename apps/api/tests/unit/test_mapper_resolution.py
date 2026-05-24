"""Phase 8 PR-8b-3 — Mapper resolution boot check.

Validates that every SQLAlchemy mapper in `app.models` registers correctly
and that `configure_mappers()` resolves the full relationship graph without
errors. Catches:

- Typos in `back_populates="..."`
- Missing relationship counterparts
- ForeignKey references to non-existent tables/columns
- String-form `relationship("ClassName")` references that don't resolve
- Mapper classes missing `__tablename__`
- T8 precondition 3 (mapper resolution) regression

Pure unit test — no DB connection, no Docker, no testcontainers. Imports
all models from `app.models` (triggers __init__.py registration), then
runs `configure_mappers()` which is the same internal SQLAlchemy step that
fires implicitly on the first ORM query / `Base.metadata.create_all()`.
Forcing it at test time surfaces config errors immediately instead of at
prod boot.

Marker: `unit` — runs in `api-unit-tests` CI job (no docker dep).
"""

from __future__ import annotations

import pytest


@pytest.mark.unit
def test_configure_mappers_succeeds() -> None:
    """`sqlalchemy.orm.configure_mappers()` resolves the full mapper graph.

    Raises `sqlalchemy.exc.ArgumentError` (or related) if any relationship's
    `back_populates`, `secondary=`, or string-form class ref is broken.
    """
    # Import all models — this populates Base.registry via app.models.__init__.
    import app.models  # noqa: F401
    from sqlalchemy.orm import configure_mappers

    configure_mappers()


@pytest.mark.unit
def test_all_mapped_classes_have_tablename() -> None:
    """Every registered mapper exposes a non-empty `__tablename__`.

    Defensive check that catches accidental abstract-only classes or
    forgotten `__tablename__` overrides that would silently break Alembic
    autogenerate later.
    """
    import app.models  # noqa: F401
    from app.core.db import Base

    missing: list[str] = []
    for mapper in Base.registry.mappers:
        cls = mapper.class_
        tablename = getattr(cls, "__tablename__", None)
        if not tablename:
            missing.append(cls.__name__)

    assert not missing, f"Mappers missing __tablename__: {missing}"


@pytest.mark.unit
def test_mapper_count_covers_known_models() -> None:
    """Sanity: at least N mappers register (catches regression of missing __init__ imports).

    Set lower bound conservatively — 25 — well below the current count (~35);
    intended to flag if `app.models.__init__` loses imports en-masse
    (PR-8b-1 #1251 surfaced exactly this kind of bug for 3 models).
    """
    import app.models  # noqa: F401
    from app.core.db import Base

    mapper_count = len(list(Base.registry.mappers))
    assert mapper_count >= 25, (
        f"Expected ≥25 registered mappers, found {mapper_count}. "
        "Check app/models/__init__.py for missing model imports."
    )
