"""Legal takedown endpoint smoke tests (#35).

DB integration testleri testcontainers ile gelir; burada router register +
Pydantic schema validation kontrol edilir.
"""

from __future__ import annotations

from datetime import UTC

import pytest
from pydantic import ValidationError


def test_router_registered():
    from app.main import app

    paths = {route.path for route in app.routes}  # type: ignore[attr-defined]
    assert "/legal/abuse" in paths
    assert "/legal/takedown" in paths
    assert "/legal/copyright" in paths
    assert "/legal/privacy-request" in paths
    assert "/admin/legal/requests" in paths


def test_admin_router_path():
    from app.main import app

    paths = {route.path for route in app.routes}  # type: ignore[attr-defined]
    assert "/admin/legal/requests/{ticket_id}" in paths


def test_takedown_submission_min_description():
    from app.api.legal import TakedownSubmission

    # < 20 char açıklama → ValidationError
    with pytest.raises(ValidationError):
        TakedownSubmission(
            requester_email="x@y.com",
            description="kısa",
        )


def test_takedown_submission_max_evidence():
    """evidence_urls 10'dan fazla geçemez."""
    from app.api.legal import TakedownSubmission

    too_many = [f"https://x.com/{i}" for i in range(15)]
    with pytest.raises(ValidationError):
        TakedownSubmission(
            requester_email="x@y.com",
            description="x" * 30,
            evidence_urls=too_many,
        )


def test_takedown_submission_valid():
    from app.api.legal import TakedownSubmission

    s = TakedownSubmission(
        requester_email="ali@example.com",
        requester_name="Ali Veli",
        authority_claim="telif sahibiyim",
        subject_url="https://nodrat.com/foo",
        description="Bu içerik telif hakkımı ihlal ediyor çünkü...",
        evidence_urls=["https://veriumdeposu.com/orijinal"],
    )
    assert s.requester_email == "ali@example.com"
    assert len(s.evidence_urls) == 1


def test_evidence_url_validation_strips_invalid():
    """_validate_evidence_urls sadece http(s) URL kabul."""
    from app.api.legal import _validate_evidence_urls

    result = _validate_evidence_urls(
        [
            "https://valid.com",
            "http://also-valid.com",
            "ftp://invalid.com",
            "javascript:alert(1)",
            "not a url",
            "",
        ]
    )
    assert len(result) == 2
    assert all(u.startswith(("http://", "https://")) for u in result)


def test_request_type_message_localized():
    from app.api.legal import _request_type_message

    for t in ["abuse", "takedown", "copyright", "privacy_request"]:
        msg = _request_type_message(t)
        assert msg
        # Türkçe karakter kontrolü
        assert any(c in msg for c in "şçğıöüİ")


def test_overdue_logic():
    from datetime import datetime, timedelta
    from unittest.mock import MagicMock

    from app.api.legal import _is_overdue

    # Resolved → never overdue
    req = MagicMock(
        status="action_taken",
        sla_due_at=datetime.now(UTC) - timedelta(hours=1),
    )
    assert _is_overdue(req) is False

    # Submitted + past due → overdue
    req2 = MagicMock(
        status="submitted",
        sla_due_at=datetime.now(UTC) - timedelta(hours=1),
    )
    assert _is_overdue(req2) is True

    # Submitted + future due → not overdue
    req3 = MagicMock(
        status="submitted",
        sla_due_at=datetime.now(UTC) + timedelta(hours=1),
    )
    assert _is_overdue(req3) is False
