"""Admin sources router + schema unit tests (#565).

Schema-only (no DB) — `SourceUpdateRequest` validation + router wiring
kontrolü. Integration tests testcontainers ile gelir (#43).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

# ---------------------------------------------------------------------------
# Router wiring — PATCH endpoint mount edilmiş mi
# ---------------------------------------------------------------------------


def test_admin_sources_routes_registered():
    """Beklenen path'ler mount edilmiş mi?"""
    from app.main import app

    paths = {route.path for route in app.routes}  # type: ignore[attr-defined]
    assert "/admin/sources" in paths
    assert "/admin/sources/{source_id}" in paths
    assert "/admin/sources/{source_id}/activate" in paths


def test_admin_sources_detail_methods_include_patch():
    """{source_id} endpoint GET + PATCH destekler."""
    from app.main import app

    methods_by_path: dict[str, set[str]] = {}
    for route in app.routes:  # type: ignore[attr-defined]
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None)
        if path and methods:
            methods_by_path.setdefault(path, set()).update(methods)

    assert {"GET", "PATCH"}.issubset(methods_by_path["/admin/sources/{source_id}"])


# ---------------------------------------------------------------------------
# SourceUpdateRequest — Pydantic schema invariants
# ---------------------------------------------------------------------------


def test_update_request_all_fields_optional():
    """Boş payload da geçerli (validation level)."""
    from app.api.admin_sources import SourceUpdateRequest

    req = SourceUpdateRequest()
    # exclude_unset boş dict döner — handler 422 EMPTY_PATCH atar
    assert req.model_dump(exclude_unset=True) == {}


def test_update_request_immutable_fields_absent():
    """slug/domain/type/base_url/is_active/id — değiştirilemez."""
    from app.api.admin_sources import SourceUpdateRequest

    fields = set(SourceUpdateRequest.model_fields.keys())
    forbidden = {"slug", "domain", "type", "base_url", "is_active", "id"}
    leaked = fields & forbidden
    assert not leaked, f"PATCH şemasında değiştirilemez alan: {leaked}"


def test_update_request_allowed_fields_only():
    """İzinli alanlar: crawl_interval_minutes, realtime_enabled, name, category."""
    from app.api.admin_sources import SourceUpdateRequest

    fields = set(SourceUpdateRequest.model_fields.keys())
    expected = {"crawl_interval_minutes", "realtime_enabled", "name", "category"}
    assert fields == expected, f"unexpected fields: {fields ^ expected}"


def test_update_request_crawl_interval_range():
    """5 ≤ crawl_interval_minutes ≤ 1440."""
    from app.api.admin_sources import SourceUpdateRequest

    # Valid edges
    SourceUpdateRequest(crawl_interval_minutes=5)
    SourceUpdateRequest(crawl_interval_minutes=1440)
    SourceUpdateRequest(crawl_interval_minutes=60)

    # Invalid
    with pytest.raises(ValidationError):
        SourceUpdateRequest(crawl_interval_minutes=4)
    with pytest.raises(ValidationError):
        SourceUpdateRequest(crawl_interval_minutes=1441)
    with pytest.raises(ValidationError):
        SourceUpdateRequest(crawl_interval_minutes=0)


def test_update_request_realtime_enabled_bool():
    """realtime_enabled bool olmalı."""
    from app.api.admin_sources import SourceUpdateRequest

    SourceUpdateRequest(realtime_enabled=True)
    SourceUpdateRequest(realtime_enabled=False)


def test_update_request_partial_payload():
    """Alanlardan biri verilebilir, diğerleri default unset kalır."""
    from app.api.admin_sources import SourceUpdateRequest

    req = SourceUpdateRequest(realtime_enabled=True)
    dumped = req.model_dump(exclude_unset=True)
    assert dumped == {"realtime_enabled": True}


# ---------------------------------------------------------------------------
# SourcePublic — yeni alanlar exposed
# ---------------------------------------------------------------------------


def test_source_public_exposes_realtime_fields():
    """API client'lar realtime_enabled + polling_tier alanlarını görmeli."""
    from app.api.admin_sources import SourcePublic

    fields = set(SourcePublic.model_fields.keys())
    assert "realtime_enabled" in fields
    assert "polling_tier" in fields


def test_source_public_exposes_tier_shadow_fields():
    """#578 Faz 2: would_be_tier + tier_changed_at + tier_metadata + consecutive_unchanged."""
    from app.api.admin_sources import SourcePublic

    fields = set(SourcePublic.model_fields.keys())
    expected = {"would_be_tier", "tier_changed_at", "tier_metadata", "consecutive_unchanged"}
    missing = expected - fields
    assert not missing, f"SourcePublic eksik alanlar: {missing}"
