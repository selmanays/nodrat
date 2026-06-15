"""#1498 — kaynak robots auto-deactivation: GEÇİCİ fetch hatası vs GERÇEK disallow.

Üretim-fatal davranış: aktif kaynaklar robots.txt o an çekilemediğinde
(network/timeout/5xx/4xx-forbidden) kalıcı engel sayılıp sessizce deactive
ediliyordu; iz bırakmıyor, sonraki healthcheck robots bayrağını healliyor ama
kaynağı açmıyordu (Hürriyet 9 Haz, ~10 kaynak 19 May sessizce kapandı).

Bu testler şunu kilitler:
  - GEÇİCİ fetch hatası canlı kaynağı KAPATMAZ (robots_txt_compliant korunur).
  - GERÇEK disallow kaynağı kapatır + FailedJob izi bırakır (24h dedupe).
  - reactivate_dormant_sources: robots re-check'li güvenli + idempotent recovery.

Test_sft_curator.py'deki Docker'sız fake-session + _get_session_factory patch
pattern'i ile koşar (gerçek FailedJob/RobotsReport ORM/dataclass kullanılır).
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from app.modules.sources.tasks import sources as src_tasks
from app.shared.crawl.robots import RobotsReport


# ---------------------------------------------------------------------------
# Fake async session — str(stmt) ile yönlendiren minimal mock
# ---------------------------------------------------------------------------
class _Result:
    def __init__(self, *, scalar=None, scalar_one=None, rows=None):
        self._scalar = scalar
        self._scalar_one = scalar_one
        self._rows = rows or []

    def scalar(self):
        return self._scalar

    def scalar_one_or_none(self):
        return self._scalar_one

    def scalars(self):
        return SimpleNamespace(all=lambda: list(self._rows))


class _Session:
    """db.get / db.execute / db.add / db.commit'i sahteleyen async session."""

    def __init__(self, *, sources=None, existing_failed=0, existing_health=None):
        self._sources = {s.id: s for s in (sources or [])}
        self.existing_failed = existing_failed
        self.existing_health = existing_health
        self.added: list = []
        self.commits = 0
        self.updates: list[str] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, _model, pk):
        return self._sources.get(pk)

    async def execute(self, stmt):
        s = str(stmt).lower()
        if s.startswith("update") and "failed_jobs" in s:
            self.updates.append(s)
            return _Result()
        if "failed_jobs" in s and "count" in s:
            return _Result(scalar=self.existing_failed)
        if "source_health" in s:
            return _Result(scalar_one=self.existing_health)
        if "from sources" in s:
            return _Result(rows=list(self._sources.values()))
        return _Result()

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1


def _factory(session: _Session):
    def _make():
        return session

    return _make


def _make_source(**over):
    base = {
        "id": uuid4(),
        "name": "Test Kaynak",
        "slug": "test-kaynak",
        "domain": "example.com",
        "base_url": "https://example.com/feed",
        "is_active": True,
        "robots_txt_compliant": True,
        "robots_txt_check_at": None,
        "tos_acknowledged": True,
    }
    base.update(over)
    return SimpleNamespace(**base)


def _report(*, fetched, allowed=True, status_code=200, error=None):
    return RobotsReport(
        domain="example.com",
        robots_url="https://example.com/robots.txt",
        fetched=fetched,
        status_code=status_code,
        base_url_allowed=allowed,
        error=error,
    )


def _run_healthcheck(session, source_id):
    with patch.object(src_tasks, "_get_session_factory", lambda: _factory(session)):
        return asyncio.run(src_tasks._healthcheck_source_async(source_id))


# ===========================================================================
# Healthcheck — GEÇİCİ fetch hatası
# ===========================================================================
def test_transient_fetch_failure_does_not_deactivate():
    """robots.txt çekilemedi (network/timeout) → kaynak AÇIK kalır, bayrak korunur."""
    source = _make_source(is_active=True, robots_txt_compliant=True)
    session = _Session(sources=[source])
    with patch.object(
        src_tasks,
        "fetch_robots",
        AsyncMock(return_value=_report(fetched=False, status_code=0, error="fetch failed")),
    ):
        out = _run_healthcheck(session, source.id)

    assert source.is_active is True, "geçici hata canlı kaynağı KAPATMAMALI"
    assert source.robots_txt_compliant is True, "önceki iyi bayrak EZİLMEMELİ"
    assert out["status"] == "yellow"
    assert out.get("robots_transient_error") is True
    assert out.get("auto_deactivated") is None
    # Hiçbir FailedJob (auto_deactivated) eklenmemeli
    assert not [a for a in session.added if getattr(a, "job_type", "") == "source.auto_deactivated"]


def test_transient_5xx_does_not_deactivate():
    source = _make_source(is_active=True, robots_txt_compliant=True)
    session = _Session(sources=[source])
    with patch.object(
        src_tasks,
        "fetch_robots",
        AsyncMock(return_value=_report(fetched=False, status_code=503, error="upstream error 503")),
    ):
        out = _run_healthcheck(session, source.id)
    assert source.is_active is True
    assert out["status"] == "yellow"


# ===========================================================================
# Healthcheck — GERÇEK disallow
# ===========================================================================
def test_genuine_disallow_deactivates_and_records():
    """robots çekildi ama base_url disallow → deactivate + FailedJob izi."""
    source = _make_source(is_active=True, robots_txt_compliant=True)
    session = _Session(sources=[source], existing_failed=0)
    with patch.object(
        src_tasks,
        "fetch_robots",
        AsyncMock(return_value=_report(fetched=True, allowed=False, status_code=200)),
    ):
        out = _run_healthcheck(session, source.id)

    assert source.is_active is False, "gerçek disallow kaynağı KAPATMALI"
    assert source.robots_txt_compliant is False
    assert out["status"] == "red"
    assert out.get("auto_deactivated") is True
    recs = [a for a in session.added if getattr(a, "job_type", "") == "source.auto_deactivated"]
    assert len(recs) == 1, "görünür FailedJob izi bırakılmalı"
    assert recs[0].severity == "warning"
    assert recs[0].source_id == source.id


def test_genuine_disallow_dedupe_within_24h():
    """24h içinde açık kayıt varsa yeni FailedJob YAZILMAZ (spam önleme)."""
    source = _make_source(is_active=True)
    session = _Session(sources=[source], existing_failed=1)
    with patch.object(
        src_tasks,
        "fetch_robots",
        AsyncMock(return_value=_report(fetched=True, allowed=False)),
    ):
        _run_healthcheck(session, source.id)
    assert source.is_active is False
    assert not [a for a in session.added if getattr(a, "job_type", "") == "source.auto_deactivated"]


def test_allowed_keeps_active_green():
    source = _make_source(is_active=True, robots_txt_compliant=False)
    session = _Session(sources=[source])
    with patch.object(
        src_tasks,
        "fetch_robots",
        AsyncMock(return_value=_report(fetched=True, allowed=True)),
    ):
        out = _run_healthcheck(session, source.id)
    assert source.is_active is True
    assert source.robots_txt_compliant is True
    assert out["status"] == "green"


# ===========================================================================
# Recovery — reactivate_dormant_sources
# ===========================================================================
def _run_recovery(session, *, can_fetch_ret, dry_run=False):
    with (
        patch.object(src_tasks, "_get_session_factory", lambda: _factory(session)),
        patch.object(src_tasks, "can_fetch", AsyncMock(return_value=can_fetch_ret)),
    ):
        return asyncio.run(src_tasks._reactivate_dormant_sources_async(dry_run=dry_run))


def test_recovery_reactivates_allowed_source():
    source = _make_source(is_active=False, tos_acknowledged=True)
    session = _Session(sources=[source])
    out = _run_recovery(session, can_fetch_ret=(True, _report(fetched=True, allowed=True)))

    assert source.slug in out["reactivated"]
    assert source.is_active is True
    assert source.robots_txt_compliant is True
    # açık auto_deactivated kayıtları resolve eden update çağrıldı
    assert any("failed_jobs" in u for u in session.updates)
    assert session.commits >= 1


def test_recovery_skips_genuine_disallow():
    source = _make_source(is_active=False, tos_acknowledged=True)
    session = _Session(sources=[source])
    out = _run_recovery(session, can_fetch_ret=(False, _report(fetched=True, allowed=False)))

    assert source.slug in out["skipped_disallow"]
    assert source.is_active is False, "gerçekten disallow kaynak AÇILMAMALI"


def test_recovery_skips_transient():
    source = _make_source(is_active=False, tos_acknowledged=True)
    session = _Session(sources=[source])
    out = _run_recovery(
        session, can_fetch_ret=(False, _report(fetched=False, status_code=0, error="timeout"))
    )
    assert source.slug in out["skipped_transient"]
    assert source.is_active is False


def test_recovery_skips_no_tos():
    """tos_acknowledged=False → onboard edilmemiş, değerlendirilmez."""
    source = _make_source(is_active=False, tos_acknowledged=False)
    session = _Session(sources=[source])
    out = _run_recovery(session, can_fetch_ret=(True, _report(fetched=True, allowed=True)))
    assert source.slug in out["skipped_no_tos"]
    assert out["evaluated"] == 0
    assert source.is_active is False


def test_recovery_dry_run_no_writes():
    source = _make_source(is_active=False, tos_acknowledged=True)
    session = _Session(sources=[source])
    out = _run_recovery(
        session, can_fetch_ret=(True, _report(fetched=True, allowed=True)), dry_run=True
    )
    assert source.slug in out["reactivated"]
    assert out["dry_run"] is True
    assert source.is_active is False, "dry_run hiçbir şey yazmamalı"
    assert session.commits == 0


# ===========================================================================
# Task registry
# ===========================================================================
def test_reactivate_task_registered():
    from app.workers.celery_app import celery_app

    assert "tasks.sources.reactivate_dormant_sources" in celery_app.tasks
