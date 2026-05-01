"""Admin user management endpoint smoke tests (#69).

DB integration testleri testcontainers (#43) ile gelir; burada router register +
Pydantic schema validation + locked vocab / immutable fields kontrol edilir.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError


# ---------------------------------------------------------------------------
# Router wiring
# ---------------------------------------------------------------------------


def test_router_registered_admin_users_paths():
    """main.app /admin/users ailesi mount edilmiş mi?"""
    from app.main import app

    paths = {route.path for route in app.routes}  # type: ignore[attr-defined]
    assert "/admin/users" in paths
    assert "/admin/users/stats" in paths
    assert "/admin/users/{user_id}" in paths
    assert "/admin/users/{user_id}/restore" in paths


def test_methods_per_endpoint():
    """GET list, GET stats, GET/PATCH detail, POST restore."""
    from app.main import app

    methods_by_path: dict[str, set[str]] = {}
    for route in app.routes:  # type: ignore[attr-defined]
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None)
        if path and methods:
            methods_by_path.setdefault(path, set()).update(methods)

    assert "GET" in methods_by_path["/admin/users"]
    assert "GET" in methods_by_path["/admin/users/stats"]
    assert {"GET", "PATCH"}.issubset(methods_by_path["/admin/users/{user_id}"])
    assert "POST" in methods_by_path["/admin/users/{user_id}/restore"]


# ---------------------------------------------------------------------------
# Schema invariants — locked vocabulary
# ---------------------------------------------------------------------------


def test_patch_request_locked_role_vocab():
    """role sadece super_admin / user olabilir."""
    from app.api.admin_users import AdminUserPatchRequest

    # Geçerli
    AdminUserPatchRequest(role="super_admin")
    AdminUserPatchRequest(role="user")

    # Geçersiz
    with pytest.raises(ValidationError):
        AdminUserPatchRequest(role="moderator")  # type: ignore[arg-type]


def test_patch_request_locked_tier_vocab():
    """tier sadece free / starter / pro / agency_seat olabilir."""
    from app.api.admin_users import AdminUserPatchRequest

    for tier in ("free", "starter", "pro", "agency_seat"):
        AdminUserPatchRequest(tier=tier)  # type: ignore[arg-type]

    with pytest.raises(ValidationError):
        AdminUserPatchRequest(tier="enterprise")  # type: ignore[arg-type]


def test_patch_request_immutable_fields_absent():
    """Email, password, KVKK consent admin'den DEĞİŞTİRİLEMEZ."""
    from app.api.admin_users import AdminUserPatchRequest

    fields = set(AdminUserPatchRequest.model_fields.keys())
    forbidden = {
        "email",
        "password",
        "password_hash",
        "kvkk_acknowledgment",
        "data_processing_consent_at",
        "foreign_transfer_consent_at",
        "totp_secret",
        "deleted_at",
        "id",
    }
    leaked = fields & forbidden
    assert not leaked, f"PATCH şemasında değiştirilemez alan: {leaked}"


def test_summary_excludes_password_hash():
    """AdminUserSummary password_hash / token_hash içermez."""
    from app.api.admin_users import AdminUserDetail, AdminUserSummary

    summary_fields = set(AdminUserSummary.model_fields.keys())
    assert "password_hash" not in summary_fields
    assert "token_hash" not in summary_fields

    detail_fields = set(AdminUserDetail.model_fields.keys())
    assert "password_hash" not in detail_fields
    assert "token_hash" not in detail_fields
    # Detail KVKK timestamp'leri dahil
    assert "kvkk_acknowledgment_at" in detail_fields
    assert "data_processing_consent_at" in detail_fields
    assert "foreign_transfer_consent_at" in detail_fields


def test_stats_response_shape():
    """AdminUserStatsResponse shape kontrolü."""
    from app.api.admin_users import (
        AdminUserStatsResponse,
        RoleStat,
        TierStat,
    )

    r = AdminUserStatsResponse(
        total=10,
        active=7,
        inactive=2,
        deleted=1,
        email_verified=6,
        by_tier=[
            TierStat(tier="free", count=8),
            TierStat(tier="pro", count=2),
        ],
        by_role=[
            RoleStat(role="user", count=9),
            RoleStat(role="super_admin", count=1),
        ],
    )
    assert r.total == 10
    assert r.deleted == 1
    assert sum(s.count for s in r.by_tier) == 10
    assert sum(s.count for s in r.by_role) == 10


def test_list_response_pagination_shape():
    """AdminUserListResponse data + total + limit + offset."""
    from app.api.admin_users import AdminUserListResponse

    r = AdminUserListResponse(data=[], total=0, limit=50, offset=0)
    assert r.total == 0
    assert r.limit == 50
    assert r.offset == 0


def test_summary_to_dict_carries_required_fields():
    """AdminUserSummary id/email/role/tier/is_active/created_at zorunlu alanlar."""
    from app.api.admin_users import AdminUserSummary

    s = AdminUserSummary(
        id=uuid4(),
        email="x@y.com",
        full_name=None,
        role="user",
        tier="free",
        locale="tr-TR",
        email_verified=False,
        is_active=True,
        totp_enabled=False,
        last_login_at=None,
        created_at=datetime.now(timezone.utc),
        deleted_at=None,
    )
    assert s.role == "user"
    assert s.tier == "free"
    assert s.is_active is True


def test_allowed_vocab_constants():
    """ALLOWED_ROLES + ALLOWED_TIERS Data Model §2.1 ile eşleşiyor."""
    from app.api.admin_users import ALLOWED_ROLES, ALLOWED_TIERS

    assert set(ALLOWED_ROLES) == {"super_admin", "user"}
    assert set(ALLOWED_TIERS) == {"free", "starter", "pro", "agency_seat"}


def test_restore_request_only_takes_note():
    """AdminUserRestoreRequest sadece note alır — başka alan yasak."""
    from app.api.admin_users import AdminUserRestoreRequest

    fields = set(AdminUserRestoreRequest.model_fields.keys())
    assert fields == {"note"}

    # Geçerli
    AdminUserRestoreRequest()
    AdminUserRestoreRequest(note="Yanlışlıkla silinmiş, kullanıcı talep etti.")

    # 500+ char → ValidationError
    with pytest.raises(ValidationError):
        AdminUserRestoreRequest(note="x" * 501)
