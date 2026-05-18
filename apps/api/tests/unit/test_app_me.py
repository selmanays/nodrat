"""KVKK self-service endpoint smoke tests (#80).

DB integration testleri testcontainers (#43) ile gelir; burada router register +
Pydantic schema validation + request/response invariantları doğrulanır.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

# ---------------------------------------------------------------------------
# Router wiring
# ---------------------------------------------------------------------------


def test_router_registered_app_me_paths():
    """main.app /app/me ailesi mount edilmiş mi?"""
    from app.main import app

    paths = {route.path for route in app.routes}  # type: ignore[attr-defined]
    assert "/app/me" in paths
    assert "/app/me/export" in paths


def test_router_methods_per_endpoint():
    """GET, PATCH, DELETE /app/me + GET /app/me/export tanımlı mı?"""
    from app.main import app

    methods_by_path: dict[str, set[str]] = {}
    for route in app.routes:  # type: ignore[attr-defined]
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None)
        if path and methods:
            methods_by_path.setdefault(path, set()).update(methods)

    assert {"GET", "PATCH", "DELETE"}.issubset(methods_by_path["/app/me"])
    assert "GET" in methods_by_path["/app/me/export"]


# ---------------------------------------------------------------------------
# Schema invariants
# ---------------------------------------------------------------------------


def test_profile_update_request_no_forbidden_fields():
    """PATCH payload schema'sı sadece self-service alanlarını taşır.

    YASAK: email, role, tier, is_active, deleted_at, kvkk_acknowledgment vb.
    """
    from app.api.app_me import ProfileUpdateRequest

    fields = set(ProfileUpdateRequest.model_fields.keys())
    forbidden = {
        "email",
        "role",
        "tier",
        "is_active",
        "deleted_at",
        "password",
        "password_hash",
        "kvkk_acknowledgment",
        "data_processing_consent",
        "foreign_transfer_consent",
        "totp_secret",
    }
    leaked = fields & forbidden
    assert not leaked, f"PATCH şemasında yasaklı alan: {leaked}"
    # Öte yandan beklenen alanlar var mı?
    assert {"full_name", "locale", "marketing_consent"}.issubset(fields)


def test_profile_update_request_locale_min_length():
    """locale en az 2 karakter olmalı."""
    from app.api.app_me import ProfileUpdateRequest

    # Geçerli
    ProfileUpdateRequest(full_name=None, locale="tr-TR", marketing_consent=False)

    # Çok kısa locale → ValidationError
    with pytest.raises(ValidationError):
        ProfileUpdateRequest(locale="t")


def test_account_delete_request_confirmation_required():
    """DELETE confirmation kelimesi zorunlu (boş kabul edilmez)."""
    from app.api.app_me import AccountDeleteRequest

    # Boş confirmation → ValidationError (min_length=1)
    with pytest.raises(ValidationError):
        AccountDeleteRequest(confirmation="")

    # Geçerli
    payload = AccountDeleteRequest(confirmation="SIL")
    assert payload.confirmation == "SIL"


def test_export_response_excludes_sensitive_fields():
    """ExportResponse user payload'ında sensitive alanlar OLMAMALI."""
    from app.api.app_me import (
        ExportResponse,
        ExportSession,
        ExportUsageEvent,
        UserMePublic,
    )

    user_fields = set(UserMePublic.model_fields.keys())
    forbidden = {"password_hash", "totp_secret", "token_hash"}
    leaked = user_fields & forbidden
    assert not leaked, f"UserMePublic'te sensitive alan: {leaked}"

    # ExportSession token_hash içermemeli
    sess_fields = set(ExportSession.model_fields.keys())
    assert "token_hash" not in sess_fields

    # ExportResponse top-level shape — S1B (#800) chat-only sonrası:
    # generations/saved_generations DROP; conversations + messages eklendi
    # (app_me.py ExportResponse docstring'inde belgeli).
    er_fields = set(ExportResponse.model_fields.keys())
    expected_top = {
        "user",
        "conversations",
        "usage_events",
        "sessions",
        "exported_at",
        "note",
    }
    assert expected_top.issubset(er_fields)
    # #800 regresyon-guard: eski generation-çağı alanları GERİ GELMEMELİ
    assert "generations" not in er_fields
    assert "saved_generations" not in er_fields

    # UsageEvent metadata alanı dahil
    assert "metadata" in set(ExportUsageEvent.model_fields.keys())


def test_account_delete_response_shape():
    """Response status / deletion_at / retention_until / sessions_revoked taşır."""
    from app.api.app_me import AccountDeleteResponse

    r = AccountDeleteResponse(
        status="soft_deleted",
        deletion_at=datetime(2026, 5, 1, tzinfo=UTC),
        retention_until=datetime(2026, 5, 31, tzinfo=UTC),
        ticket_id="TKD-2026-000123",
        sessions_revoked=3,
    )
    assert r.status == "soft_deleted"
    assert r.ticket_id == "TKD-2026-000123"
    assert r.sessions_revoked == 3
    # retention 30 günlük pencere (deletion_at + 30 gün)
    delta = (r.retention_until - r.deletion_at).days
    assert delta == 30


def test_user_me_public_includes_created_at_and_consent_timestamps():
    """UserMePublic response'unda created_at ve KVKK timestamp'leri olmalı."""
    from app.api.app_me import UserMePublic

    fields = set(UserMePublic.model_fields.keys())
    assert "created_at" in fields
    assert "kvkk_acknowledgment_at" in fields
    assert "data_processing_consent_at" in fields
    assert "foreign_transfer_consent_at" in fields
    assert "marketing_consent_at" in fields


def test_export_constants_caps_are_sensible():
    """Export limitleri privacy + payload size sınırına bağlı.

    S1B (#800) chat-only göçü: EXPORT_GENERATIONS_LIMIT/EXPORT_SAVED_LIMIT
    DROP → EXPORT_CONVERSATIONS_LIMIT + EXPORT_MESSAGES_PER_CONV_LIMIT
    (app_me.py:56 yorumunda belgeli).
    """
    from app.api import app_me

    assert app_me.EXPORT_CONVERSATIONS_LIMIT == 100
    assert app_me.EXPORT_MESSAGES_PER_CONV_LIMIT == 50
    assert app_me.EXPORT_USAGE_EVENTS_LIMIT == 100
    assert app_me.EXPORT_SESSIONS_LIMIT == 50
    assert app_me.HARD_DELETE_RETENTION_DAYS == 30
    # #800 regresyon-guard: eski generation-çağı sabitleri GERİ GELMEMELİ
    assert not hasattr(app_me, "EXPORT_GENERATIONS_LIMIT")
    assert not hasattr(app_me, "EXPORT_SAVED_LIMIT")
