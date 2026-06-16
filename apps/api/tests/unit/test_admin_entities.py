"""Admin Canonical Entities — router wiring + helper birim testleri (#1554).

DB-bağımsız: path/method kaydı + `_norm` yardımcısı + tip allowlist. SQL
davranış invariant'ları (builder admin-alias ezmez, merge/split) testcontainers
ile `tests/integration/test_canonical_admin_sql.py`'de.
"""

from __future__ import annotations

from app.api.admin_entities import _TYPES, _norm


def test_router_registered_admin_entities_path():
    from app.main import app

    paths = {route.path for route in app.routes}  # type: ignore[attr-defined]
    assert "/admin/entities/canonical" in paths


def test_router_has_merge_and_alias_subpaths():
    from app.main import app

    paths = {route.path for route in app.routes}  # type: ignore[attr-defined]
    assert "/admin/entities/canonical/{cid}/merge" in paths
    assert "/admin/entities/canonical/{cid}/aliases" in paths
    assert "/admin/entities/canonical/{cid}/aliases/{alias}" in paths


def test_methods_registered():
    from app.main import app

    methods_by_path: dict[str, set[str]] = {}
    for route in app.routes:  # type: ignore[attr-defined]
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None)
        if path and methods:
            methods_by_path.setdefault(path, set()).update(methods)

    assert "GET" in methods_by_path["/admin/entities/canonical"]
    assert "POST" in methods_by_path["/admin/entities/canonical"]
    assert "POST" in methods_by_path["/admin/entities/canonical/{cid}/merge"]
    assert "DELETE" in methods_by_path["/admin/entities/canonical/{cid}/aliases/{alias}"]


def test_norm_lower_trim():
    assert _norm("  Recep Tayyip ERDOĞAN ") == "recep tayyip erdoğan"
    assert _norm("CHP") == "chp"


def test_entity_types_allowlist():
    assert set(_TYPES) == {"person", "org", "place", "event"}
