"""Admin source yönetimi endpoint'leri.

docs/engineering/api-contracts.md §4.1
docs/legal/opinion-integration.md §3.4 (5-item compliance checklist)
docs/legal/scraping-policy.md §3.3 (robots.txt zero tolerance)

Endpoints:
    POST   /admin/sources                 — Yeni kaynak ekle (RSS/manual)
    GET    /admin/sources                 — Kaynak listesi
    GET    /admin/sources/{id}            — Detay
    PATCH  /admin/sources/{id}            — Güncelle
    POST   /admin/sources/{id}/activate   — 5-item checklist + robots check + activate
    POST   /admin/sources/test-feed       — RSS feed test (DB'ye yazmadan)

Compliance:
    - Yeni kaynak default is_active=FALSE
    - 5 checkbox TRUE + robots.txt compliant olmadan activate edilemez
    - Tüm değişiklikler admin_audit_log'a yazılır
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from pydantic import BaseModel, Field, HttpUrl, field_validator
from sqlalchemy import select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import get_client_ip, require_admin
from app.core.extractor import extract_listing_cards
from app.core.http_client import fetch_text
from app.core.robots import (
    RobotsDisallowed,
    RobotsReport,
    enforce_or_raise,
    fetch_robots,
)
from app.core.rss import FeedReport, fetch_feed
from app.models.job import AdminAuditLog
from app.models.source import Source, SourceConfig
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter()


# =============================================================================
# Pydantic schemas
# =============================================================================

SourceTypeT = Literal["rss", "category_page", "manual"]


SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$")


class SourceCreateRequest(BaseModel):
    """Yeni kaynak ekleme — is_active otomatik FALSE.

    5-item compliance checklist activate akışında zorunlu (POST /activate).
    """

    name: str = Field(min_length=2, max_length=120)
    slug: str = Field(min_length=2, max_length=80)
    domain: str = Field(min_length=4, max_length=180)
    type: SourceTypeT
    base_url: HttpUrl
    language: str = Field(default="tr", min_length=2, max_length=10)
    country: str = Field(default="TR", min_length=2, max_length=8)
    category: str | None = Field(default=None, max_length=80)
    crawl_interval_minutes: int = Field(default=30, ge=5, le=1440)
    config_json: dict | None = None
    """RSS field maps / selectors / pagination — type'a göre."""

    @field_validator("slug")
    @classmethod
    def slug_format(cls, v: str) -> str:
        v = v.lower().strip()
        if not SLUG_RE.fullmatch(v):
            raise ValueError("slug only lowercase alnum + hyphen, no leading/trailing hyphen")
        return v

    @field_validator("domain")
    @classmethod
    def domain_format(cls, v: str) -> str:
        v = v.lower().strip()
        if "/" in v or " " in v or v.startswith("http"):
            raise ValueError("domain must be bare host (e.g. 'example.com')")
        return v


class ComplianceChecklist(BaseModel):
    """5-item compliance checklist — activate öncesi admin bilgisi gerekli.

    Legal opinion §3.4: 5'i de TRUE olmadan is_active=TRUE olamaz.
    """

    robots_txt_checked: bool
    """robots.txt otomatik kontrol edildi (sistem set eder)."""

    not_paywalled: bool
    """Paywall arkasında değil — admin onayı."""

    tos_allows_scraping: bool
    """Kullanım Şartları scraping'i yasaklamıyor — admin onayı."""

    publicly_accessible: bool
    """Kamuya açık sayfalardan oluşuyor — admin onayı."""

    commercial_risk_assessed: bool
    """Ticari kullanım riski değerlendirildi — admin onayı."""

    def all_true(self) -> bool:
        return all(
            (
                self.robots_txt_checked,
                self.not_paywalled,
                self.tos_allows_scraping,
                self.publicly_accessible,
                self.commercial_risk_assessed,
            )
        )


class ActivateRequest(BaseModel):
    """Activate request — 5-item checklist payload."""

    checklist: ComplianceChecklist
    note: str | None = Field(default=None, max_length=500)


class TestFeedRequest(BaseModel):
    """Test endpoint — DB'ye yazmadan feed parse + örnek itemlar döner."""

    feed_url: HttpUrl


class SourcePublic(BaseModel):
    """Source response payload."""

    id: UUID
    name: str
    slug: str
    domain: str
    type: str
    base_url: str
    language: str
    country: str
    category: str | None
    reliability_score: float
    is_active: bool
    crawl_interval_minutes: int
    robots_txt_compliant: bool | None
    tos_acknowledged: bool
    # Realtime polling (#565 Faz 0+1) — adaptive tier foundation
    realtime_enabled: bool = False
    polling_tier: str = "normal"
    # Adaptive tier shadow mode (#578 Faz 2)
    would_be_tier: str | None = None
    tier_changed_at: datetime | None = None
    tier_metadata: dict | None = None
    consecutive_unchanged: int = 0

    model_config = {"from_attributes": True}


class SourceUpdateRequest(BaseModel):
    """Patch payload — sadece runtime tunable alanlar (#565).

    `slug`, `domain`, `type`, `base_url` immutable (kaynak kimliği değişemez).
    `is_active` ayrı endpoint (POST /activate) — compliance checklist zorunluluğu
    bypass edilmesin diye.
    """

    crawl_interval_minutes: int | None = Field(default=None, ge=5, le=1440)
    realtime_enabled: bool | None = None
    name: str | None = Field(default=None, min_length=2, max_length=120)
    category: str | None = Field(default=None, max_length=80)


class FeedReportPublic(BaseModel):
    """Test feed response."""

    feed_url: str
    fetched: bool
    status_code: int
    error: str | None = None
    feed_title: str = ""
    feed_description: str = ""
    feed_language: str | None = None
    item_count: int = 0
    sample_items: list[dict] = Field(default_factory=list)


class RobotsReportPublic(BaseModel):
    """Robots check response."""

    domain: str
    robots_url: str
    fetched: bool
    status_code: int
    base_url_allowed: bool
    crawl_delay_sec: float
    sitemaps: list[str]
    error: str | None = None


# =============================================================================
# Helpers
# =============================================================================


async def _audit(
    db: AsyncSession,
    *,
    actor_id: UUID,
    action: str,
    target_type: str,
    target_id: UUID,
    metadata: dict | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
) -> None:
    """admin_audit_log insert helper. Caller commit eder."""
    audit = AdminAuditLog(
        actor_id=actor_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        event_metadata=metadata or {},
        ip_address=ip,
        user_agent=user_agent,
    )
    db.add(audit)


# =============================================================================
# Endpoints
# =============================================================================


@router.post(
    "",
    response_model=SourcePublic,
    status_code=status.HTTP_201_CREATED,
    summary="Yeni kaynak ekle (default inactive)",
)
async def create_source(
    payload: SourceCreateRequest,
    request: Request,
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Source:
    """Yeni kaynak ekle. is_active default FALSE (activate ile aktif olur).

    Robots.txt otomatik kontrol edilir — Disallow varsa 422 döner (admin override yok).
    """
    # 1) robots.txt zero-tolerance check
    try:
        report = await enforce_or_raise(str(payload.base_url))
    except RobotsDisallowed as e:
        logger.warning("source.create blocked by robots url=%s reason=%s", e.url, e.reason)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "ROBOTS_DISALLOWED",
                "title": "robots.txt bu kaynağa erişimi engelliyor",
                "detail": e.reason,
                "url": e.url,
            },
        ) from None

    # 2) Insert source
    source = Source(
        name=payload.name.strip(),
        slug=payload.slug,
        domain=payload.domain,
        type=payload.type,
        base_url=str(payload.base_url),
        language=payload.language,
        country=payload.country,
        category=payload.category,
        crawl_interval_minutes=payload.crawl_interval_minutes,
        is_active=False,  # always start inactive
        robots_txt_compliant=report.base_url_allowed,
        robots_txt_check_at=None,  # SQL default NOW()'a eşit set ederiz aşağıda
        tos_acknowledged=False,
        created_by=admin.id,
    )
    # robots_txt_check_at için DB-side NOW() yerine Python tarafı set
    from datetime import UTC
    from datetime import datetime as _dt

    source.robots_txt_check_at = _dt.now(UTC)

    db.add(source)
    try:
        await db.flush()
    except IntegrityError as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "SLUG_EXISTS",
                "title": "Bu slug zaten kullanımda",
            },
        ) from e

    # 3) Source config — versiyonlu
    if payload.config_json:
        cfg = SourceConfig(
            source_id=source.id,
            config_json=payload.config_json,
            version=1,
            is_active=True,
            created_by=admin.id,
        )
        db.add(cfg)

    # 4) Audit
    await _audit(
        db,
        actor_id=admin.id,
        action="source.create",
        target_type="source",
        target_id=source.id,
        metadata={
            "name": source.name,
            "domain": source.domain,
            "type": source.type,
            "robots_txt_compliant": report.base_url_allowed,
        },
        ip=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )

    await db.commit()
    await db.refresh(source)
    return source


@router.get(
    "",
    response_model=list[SourcePublic],
    summary="Kaynak listesi (admin)",
)
async def list_sources(
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    is_active: bool | None = Query(None, description="Filter by active status"),
    type: SourceTypeT | None = Query(None, description="Filter by type"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[Source]:
    """Tüm kaynakları listele (admin). is_active + type filtresi."""
    stmt = select(Source).order_by(Source.created_at.desc()).limit(limit).offset(offset)
    if is_active is not None:
        stmt = stmt.where(Source.is_active.is_(is_active))
    if type is not None:
        stmt = stmt.where(Source.type == type)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get(
    "/{source_id}",
    response_model=SourcePublic,
    summary="Kaynak detay",
)
async def get_source(
    source_id: Annotated[UUID, Path()],
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Source:
    source = await db.get(Source, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail={"code": "SOURCE_NOT_FOUND"})
    return source


@router.post(
    "/{source_id}/activate",
    response_model=SourcePublic,
    summary="Kaynağı aktif et — 5-item compliance checklist zorunlu",
)
async def activate_source(
    source_id: Annotated[UUID, Path()],
    payload: ActivateRequest,
    request: Request,
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Source:
    """Kaynağı aktif et — 5'i de TRUE olmadan is_active=TRUE olamaz.

    Akış:
      1. Source exists?
      2. Re-check robots.txt
      3. 5-item checklist all_true()
      4. is_active=TRUE + tos_acknowledged=TRUE
      5. Audit log
    """
    source = await db.get(Source, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail={"code": "SOURCE_NOT_FOUND"})

    # 1) Re-check robots.txt (compliance — periyodik kontrol policy)
    try:
        report = await enforce_or_raise(source.base_url)
    except RobotsDisallowed as e:
        # Robots değişmiş olabilir → kaynak deactive kalır
        from datetime import UTC
        from datetime import datetime as _dt

        source.robots_txt_compliant = False
        source.robots_txt_check_at = _dt.now(UTC)
        source.is_active = False
        await _audit(
            db,
            actor_id=admin.id,
            action="source.activate_blocked",
            target_type="source",
            target_id=source.id,
            metadata={"reason": "robots_disallowed", "detail": e.reason},
            ip=get_client_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "ROBOTS_DISALLOWED",
                "title": "Aktif edilemedi — robots.txt değişti, erişim engelli",
                "detail": e.reason,
            },
        ) from None

    # 2) Compliance checklist
    if not payload.checklist.all_true():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "COMPLIANCE_INCOMPLETE",
                "title": "5 madde compliance checklist tamamlanmadan aktif edilemez",
            },
        )

    # 3) Activate
    from datetime import UTC
    from datetime import datetime as _dt

    source.is_active = True
    source.tos_acknowledged = True
    source.robots_txt_compliant = report.base_url_allowed
    source.robots_txt_check_at = _dt.now(UTC)

    # 4) Audit
    await _audit(
        db,
        actor_id=admin.id,
        action="source.activate",
        target_type="source",
        target_id=source.id,
        metadata={
            "checklist": payload.checklist.model_dump(),
            "note": payload.note,
        },
        ip=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    await db.commit()
    await db.refresh(source)
    return source


@router.patch(
    "/{source_id}",
    response_model=SourcePublic,
    summary="Kaynak runtime alanlarını güncelle (interval, realtime, name, category)",
)
async def update_source(
    source_id: Annotated[UUID, Path()],
    payload: SourceUpdateRequest,
    request: Request,
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Source:
    """Runtime tunable alanları güncelle (#565).

    İzinli alanlar: crawl_interval_minutes, realtime_enabled, name, category.
    Slug/domain/type/base_url **immutable** — kaynak kimliği değişemez.
    is_active ayrı endpoint (POST /activate) — compliance checklist bypass yok.
    """
    source = await db.get(Source, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail={"code": "SOURCE_NOT_FOUND"})

    update_dict = payload.model_dump(exclude_unset=True)
    if not update_dict:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "EMPTY_PATCH", "title": "En az bir alan gönderilmeli"},
        )

    # Snapshot — audit için sadece değişen alanlar
    changes: dict[str, dict] = {}
    for key, new_value in update_dict.items():
        old_value = getattr(source, key)
        if old_value != new_value:
            changes[key] = {"from": old_value, "to": new_value}
            setattr(source, key, new_value)

    if not changes:
        # No-op patch — yine de 200 döner (idempotent), audit gereksiz
        return source

    await _audit(
        db,
        actor_id=admin.id,
        action="source.update",
        target_type="source",
        target_id=source.id,
        metadata={"changes": changes},
        ip=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    await db.commit()
    await db.refresh(source)
    return source


@router.post(
    "/test-feed",
    response_model=FeedReportPublic,
    summary="RSS feed test — DB'ye yazmadan parse",
)
async def test_feed(
    payload: TestFeedRequest,
    admin: Annotated[User, Depends(require_admin)],
) -> FeedReportPublic:
    """RSS / Atom feed URL'sini test et.

    Returns:
        feed metadata + ilk 5 entry örneği (admin source ekleme UI'sında preview).
    """
    report: FeedReport = await fetch_feed(str(payload.feed_url))
    sample = [
        {
            "title": item.title,
            "link": item.link,
            "summary": item.summary[:200] if item.summary else "",
            "author": item.author,
            "published_at": item.published_at.isoformat() if item.published_at else None,
            "image_url": item.image_url,
        }
        for item in report.items[:5]
    ]
    return FeedReportPublic(
        feed_url=report.feed_url,
        fetched=report.fetched,
        status_code=report.status_code,
        error=report.error,
        feed_title=report.feed_title,
        feed_description=report.feed_description,
        feed_language=report.feed_language,
        item_count=report.item_count,
        sample_items=sample,
    )


@router.get(
    "/{source_id}/robots-check",
    response_model=RobotsReportPublic,
    summary="Robots.txt re-check (manuel admin tetikli)",
)
async def robots_check(
    source_id: Annotated[UUID, Path()],
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RobotsReportPublic:
    """Robots.txt'i yeniden fetch et + DB güncelle. Endpoint admin için diagnostik."""
    source = await db.get(Source, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail={"code": "SOURCE_NOT_FOUND"})

    report: RobotsReport = await fetch_robots(source.base_url)

    from datetime import UTC
    from datetime import datetime as _dt

    source.robots_txt_compliant = report.base_url_allowed if report.fetched else False
    source.robots_txt_check_at = _dt.now(UTC)

    # Compliance düştüyse otomatik deactivate
    if not source.robots_txt_compliant and source.is_active:
        source.is_active = False
        logger.warning("source auto-deactivated by robots check id=%s", source.id)

    await db.commit()

    return RobotsReportPublic(
        domain=report.domain,
        robots_url=report.robots_url,
        fetched=report.fetched,
        status_code=report.status_code,
        base_url_allowed=report.base_url_allowed,
        crawl_delay_sec=report.crawl_delay_sec,
        sitemaps=report.sitemaps,
        error=report.error,
    )


# =============================================================================
# Selector test endpoints (#70 — R-OPS-01 mitigation)
# =============================================================================


class TestListingRequest(BaseModel):
    """Listing/category sayfası selector test isteği.

    selectors → {card, title, link, image, date}. card zorunlu, diğerleri opsiyonel.
    """

    url: HttpUrl
    """Test edilecek listing/kategori sayfa URL'si."""

    selectors: dict[str, str] = Field(default_factory=dict)
    """CSS selectors. card zorunlu (container), title/link/image/date opsiyonel."""

    @field_validator("selectors")
    @classmethod
    def card_required(cls, v: dict[str, str]) -> dict[str, str]:
        if "card" not in v or not v["card"].strip():
            raise ValueError("'card' selector zorunlu (container CSS selector)")
        return v


class TestListingCard(BaseModel):
    """Tek listing card preview."""

    title: str | None = None
    link: str | None = None
    image_url: str | None = None
    date: str | None = None


class TestListingResponse(BaseModel):
    """Listing test sonucu — admin UI preview için."""

    url: str
    fetch_status: int
    """HTTP status code. 0 = network error."""
    fetch_error: str | None = None
    card_count: int
    cards: list[TestListingCard]
    warnings: list[str]
    """Field eksikleri vb. uyarılar (örn. '3/12 card görsel eksik')."""


# #904 — TestDetail* (kaynağa özel DETAY selector testi) KALDIRILDI.
# Detay extraction artık generic (Tier-0 JSON-LD → density → fallback);
# per-domain çıkarım sağlığı /extraction-stats ile izlenir. test-listing
# (category_page keşfi) KORUNUR.


class ExtractionStatsBucket(BaseModel):
    day: str
    avg: float
    cleaned: int
    miss: int


class SourceExtractionStatsResponse(BaseModel):
    """#904 — per-domain çıkarım telemetrisi (kaynak detay sayfası)."""

    avg_confidence: float
    quarantine_rate: float
    cleaned_7d: int
    miss_7d: int
    buckets: list[ExtractionStatsBucket]


@router.post(
    "/{source_id}/test-listing",
    response_model=TestListingResponse,
    summary="Listing/category sayfa selector canlı test (R-OPS-01)",
)
async def test_listing(
    source_id: Annotated[UUID, Path()],
    payload: TestListingRequest,
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TestListingResponse:
    """Admin listing selector'ları gerçek HTML'e karşı test eder (DB'ye yazmaz).

    R-OPS-01 mitigation: Selector kırıldığında 2 saat hedefiyle hızlı düzeltme.
    Sonuç max 50 card preview + warnings (eksik field rapor).
    """
    source = await db.get(Source, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail={"code": "SOURCE_NOT_FOUND"})

    url_str = str(payload.url)
    status_code, body, _headers = await fetch_text(url_str, timeout=20.0)
    if not body or status_code >= 400:
        return TestListingResponse(
            url=url_str,
            fetch_status=status_code,
            fetch_error=f"HTTP {status_code}" if status_code else "network error",
            card_count=0,
            cards=[],
            warnings=[],
        )

    cards_raw, warnings = extract_listing_cards(
        body, url=url_str, selectors=payload.selectors
    )
    cards = [
        TestListingCard(
            title=c.title, link=c.link, image_url=c.image_url, date=c.date
        )
        for c in cards_raw
    ]
    return TestListingResponse(
        url=url_str,
        fetch_status=status_code,
        card_count=len(cards),
        cards=cards,
        warnings=warnings,
    )


@router.get(
    "/{source_id}/extraction-stats",
    response_model=SourceExtractionStatsResponse,
    summary="Per-domain çıkarım telemetrisi (#904 — R-OPS-01 gate)",
)
async def source_extraction_stats(
    source_id: Annotated[UUID, Path()],
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SourceExtractionStatsResponse:
    """#904 — kaynak detay sayfasında gösterilen 7g çıkarım sağlığı.

    avg_confidence: cleaned son 7g ortalama extraction_confidence.
    quarantine_rate: miss / (cleaned+miss) son 7g (miss = quarantine+discarded).
    < %70 ⇒ recompute_extract_health 'red' + warning DLQ alarmı (R-OPS-01).
    """
    source = await db.get(Source, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail={"code": "SOURCE_NOT_FOUND"})

    rows = (
        await db.execute(
            text(
                """
                SELECT
                  to_char(date_trunc('day',
                    COALESCE(a.cleaned_at, a.updated_at)), 'YYYY-MM-DD') AS day,
                  AVG(a.extraction_confidence)
                    FILTER (WHERE a.status='cleaned') AS avg_conf,
                  COUNT(*) FILTER (WHERE a.status='cleaned') AS cleaned,
                  COUNT(*) FILTER (
                    WHERE a.status IN ('quarantine','discarded')) AS miss
                FROM articles a
                WHERE a.source_id = :sid
                  AND a.status IN ('cleaned','quarantine','discarded')
                  AND COALESCE(a.cleaned_at, a.updated_at)
                      >= now() - interval '7 days'
                GROUP BY 1 ORDER BY 1
                """
            ),
            {"sid": str(source_id)},
        )
    ).all()

    buckets: list[ExtractionStatsBucket] = []
    tot_cleaned = 0
    tot_miss = 0
    conf_sum = 0.0
    conf_n = 0
    for day, avg_conf, cleaned, miss in rows:
        c = int(cleaned or 0)
        m = int(miss or 0)
        avg = round(float(avg_conf), 3) if avg_conf is not None else 0.0
        buckets.append(
            ExtractionStatsBucket(day=day, avg=avg, cleaned=c, miss=m)
        )
        tot_cleaned += c
        tot_miss += m
        if avg_conf is not None and c:
            conf_sum += float(avg_conf) * c
            conf_n += c

    denom = tot_cleaned + tot_miss
    return SourceExtractionStatsResponse(
        avg_confidence=round(conf_sum / conf_n, 3) if conf_n else 0.0,
        quarantine_rate=round(tot_miss / denom, 3) if denom else 0.0,
        cleaned_7d=tot_cleaned,
        miss_7d=tot_miss,
        buckets=buckets,
    )


# =============================================================================
# Source config versioning (#75)
# =============================================================================


class SourceConfigPublic(BaseModel):
    """SourceConfig liste / rollback response."""

    id: UUID
    source_id: UUID
    version: int
    is_active: bool
    config_json: dict
    created_at: str
    created_by: UUID | None = None

    model_config = {"from_attributes": True}


class ConfigCreateRequest(BaseModel):
    """Yeni config version oluştur — önceki aktifi pasifleştirir."""

    config_json: dict
    note: str | None = Field(default=None, max_length=200)


class ConfigListResponse(BaseModel):
    """Config version listesi."""

    items: list[SourceConfigPublic]
    active_version: int | None
    total: int


def _config_to_public(cfg: SourceConfig) -> SourceConfigPublic:
    return SourceConfigPublic(
        id=cfg.id,
        source_id=cfg.source_id,
        version=cfg.version,
        is_active=cfg.is_active,
        config_json=cfg.config_json or {},
        created_at=cfg.created_at.isoformat() if cfg.created_at else "",
        created_by=cfg.created_by,
    )


@router.get(
    "/{source_id}/configs",
    response_model=ConfigListResponse,
    summary="Source config version listesi (#75)",
)
async def list_configs(
    source_id: Annotated[UUID, Path()],
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ConfigListResponse:
    """Tüm version'ları listele (en yeni → en eski). Aktif version highlight."""
    src = await db.get(Source, source_id)
    if src is None:
        raise HTTPException(status_code=404, detail={"code": "SOURCE_NOT_FOUND"})

    q = await db.execute(
        select(SourceConfig)
        .where(SourceConfig.source_id == source_id)
        .order_by(SourceConfig.version.desc())
    )
    rows = list(q.scalars().all())
    items = [_config_to_public(c) for c in rows]
    active_version = next((c.version for c in rows if c.is_active), None)
    return ConfigListResponse(
        items=items, active_version=active_version, total=len(items)
    )


@router.post(
    "/{source_id}/configs",
    response_model=SourceConfigPublic,
    status_code=status.HTTP_201_CREATED,
    summary="Yeni config version oluştur (#75)",
)
async def create_config(
    source_id: Annotated[UUID, Path()],
    payload: ConfigCreateRequest,
    request: Request,
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SourceConfigPublic:
    """Önceki aktif config pasifleşir, yeni version=max+1 ile aktif olur.

    Source crawl bir sonraki tetiklemede yeni config'i kullanır.
    """
    src = await db.get(Source, source_id)
    if src is None:
        raise HTTPException(status_code=404, detail={"code": "SOURCE_NOT_FOUND"})

    # Mevcut max version
    max_q = await db.execute(
        select(SourceConfig.version)
        .where(SourceConfig.source_id == source_id)
        .order_by(SourceConfig.version.desc())
        .limit(1)
    )
    current_max = max_q.scalar() or 0

    # Aktif config'i pasifleştir (partial unique constraint için)
    await db.execute(
        update(SourceConfig)
        .where(
            SourceConfig.source_id == source_id,
            SourceConfig.is_active.is_(True),
        )
        .values(is_active=False)
    )

    new_cfg = SourceConfig(
        source_id=source_id,
        config_json=payload.config_json,
        version=current_max + 1,
        is_active=True,
        created_by=admin.id,
    )
    db.add(new_cfg)
    await db.flush()

    await _audit(
        db,
        actor_id=admin.id,
        action="source.config.create",
        target_type="source_config",
        target_id=new_cfg.id,
        metadata={
            "source_id": str(source_id),
            "version": new_cfg.version,
            "previous_max": current_max,
            "note": payload.note,
        },
        ip=get_client_ip(request),
    )
    await db.commit()
    await db.refresh(new_cfg)
    logger.info(
        "source config v%d created source=%s by=%s",
        new_cfg.version, src.slug, admin.email,
    )
    return _config_to_public(new_cfg)


@router.post(
    "/{source_id}/configs/{version}/rollback",
    response_model=SourceConfigPublic,
    summary="Bu version'i tekrar aktif et — rollback (#75)",
)
async def rollback_config(
    source_id: Annotated[UUID, Path()],
    version: Annotated[int, Path(ge=1)],
    request: Request,
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SourceConfigPublic:
    """Belirtilen version'i is_active=TRUE yap, diğerlerini FALSE.

    Yeni version oluşturmaz — mevcut version'i toggle eder. Audit log'a
    kayıt geçilir (eski active version, yeni active version).
    """
    src = await db.get(Source, source_id)
    if src is None:
        raise HTTPException(status_code=404, detail={"code": "SOURCE_NOT_FOUND"})

    target_q = await db.execute(
        select(SourceConfig).where(
            SourceConfig.source_id == source_id,
            SourceConfig.version == version,
        )
    )
    target = target_q.scalar_one_or_none()
    if target is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "CONFIG_VERSION_NOT_FOUND", "version": version},
        )

    if target.is_active:
        # Zaten aktif — no-op
        return _config_to_public(target)

    # Eski aktif version'i kaydet (audit için)
    prev_q = await db.execute(
        select(SourceConfig.version)
        .where(
            SourceConfig.source_id == source_id,
            SourceConfig.is_active.is_(True),
        )
        .limit(1)
    )
    prev_active = prev_q.scalar()

    # Tüm config'leri pasifleştir, target'i aktif et
    await db.execute(
        update(SourceConfig)
        .where(
            SourceConfig.source_id == source_id,
            SourceConfig.is_active.is_(True),
        )
        .values(is_active=False)
    )
    target.is_active = True
    await db.flush()

    await _audit(
        db,
        actor_id=admin.id,
        action="source.config.rollback",
        target_type="source_config",
        target_id=target.id,
        metadata={
            "source_id": str(source_id),
            "rolled_back_to_version": version,
            "previous_active_version": prev_active,
        },
        ip=get_client_ip(request),
    )
    await db.commit()
    await db.refresh(target)
    logger.info(
        "source config rollback source=%s prev=v%s now=v%d by=%s",
        src.slug, prev_active, version, admin.email,
    )
    return _config_to_public(target)
