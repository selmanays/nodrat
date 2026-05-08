"""Lemon Squeezy provider client (#53, Epic #448).

LS JSON:API client (https://docs.lemonsqueezy.com/api). MoR yapısı:
- Checkout URL üretimi (POST /checkouts)
- Customer Portal URL alma (signed URL)
- Subscription detay sorgusu (GET /subscriptions/:id)
- Subscription cancel/resume (PATCH /subscriptions/:id)

Webhook signature verify: HMAC SHA256 of body with signing_secret.

Configuration: LS hesabı henüz kurulmadıysa LS_NOT_CONFIGURED exception
fırlatır — endpoint'ler 503 döner.

Architecture A3 (provider abstraction): Bu client `LemonSqueezyProvider` adapter
olarak kullanılır. Paddle scaffold (#471) aynı interface'i implement eder.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from dataclasses import dataclass
from typing import Any

import httpx

from app.config import get_settings


logger = logging.getLogger(__name__)


class LSNotConfigured(Exception):
    """LS hesap kurulumu eksik (env vars boş)."""


class LSAPIError(Exception):
    """LS API call başarısız."""

    def __init__(self, status_code: int, body: Any) -> None:
        self.status_code = status_code
        self.body = body
        super().__init__(f"LS API {status_code}: {body}")


@dataclass
class CheckoutResult:
    """LS hosted checkout URL — frontend yeni tab'da açar."""

    checkout_url: str
    ls_variant_id: str
    expires_at: str | None = None


@dataclass
class SubscriptionStatus:
    """LS subscription detay — ana state alanları."""

    ls_subscription_id: str
    ls_customer_id: str
    ls_variant_id: str
    status: str  # 'on_trial', 'active', 'past_due', 'cancelled', 'expired', 'paused'
    trial_ends_at: str | None
    current_period_start: str | None
    current_period_end: str | None
    cancelled_at: str | None
    ends_at: str | None


def _ensure_configured() -> tuple[str, str, str]:
    """Env vars dolu mu kontrol — yoksa LSNotConfigured raise."""
    settings = get_settings()
    api_key = settings.lemonsqueezy_api_key.get_secret_value()
    store_id = settings.lemonsqueezy_store_id
    signing_secret = settings.lemonsqueezy_signing_secret.get_secret_value()

    if not api_key or not store_id or not signing_secret:
        raise LSNotConfigured(
            "Lemon Squeezy hesap kurulumu eksik. .env'de "
            "LEMONSQUEEZY_API_KEY, LEMONSQUEEZY_STORE_ID ve "
            "LEMONSQUEEZY_SIGNING_SECRET değerlerini doldurun."
        )
    return api_key, store_id, signing_secret


def is_configured() -> bool:
    """Sessiz kontrol — endpoint'lerde 503 öncesi check için."""
    try:
        _ensure_configured()
        return True
    except LSNotConfigured:
        return False


def verify_webhook_signature(body: bytes, signature_header: str) -> bool:
    """HMAC SHA256 webhook signature doğrulama.

    LS webhook header: `X-Signature` (hex digest).
    Signing secret: settings.lemonsqueezy_signing_secret
    """
    if not signature_header:
        return False
    settings = get_settings()
    secret = settings.lemonsqueezy_signing_secret.get_secret_value()
    if not secret:
        return False

    digest = hmac.new(
        secret.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(digest, signature_header.strip())


def _client(api_key: str) -> httpx.AsyncClient:
    """Authenticated httpx async client — JSON:API headers."""
    settings = get_settings()
    return httpx.AsyncClient(
        base_url=settings.lemonsqueezy_base_url,
        headers={
            "Accept": "application/vnd.api+json",
            "Content-Type": "application/vnd.api+json",
            "Authorization": f"Bearer {api_key}",
        },
        timeout=httpx.Timeout(30.0),
    )


async def create_checkout(
    *,
    variant_id: str,
    user_email: str,
    user_id: str,
    custom_data: dict[str, Any] | None = None,
) -> CheckoutResult:
    """LS hosted checkout session oluştur — kullanıcı bu URL'e yönlendirilir.

    custom_data: webhook payload'ında dönecek metadata (user_id eşleştirme için).
    """
    api_key, store_id, _ = _ensure_configured()
    settings = get_settings()

    payload: dict[str, Any] = {
        "data": {
            "type": "checkouts",
            "attributes": {
                "test_mode": settings.lemonsqueezy_test_mode,
                "checkout_data": {
                    "email": user_email,
                    "custom": {
                        "user_id": user_id,
                        **(custom_data or {}),
                    },
                },
                "checkout_options": {
                    "embed": False,
                    "media": True,
                    "logo": True,
                },
            },
            "relationships": {
                "store": {"data": {"type": "stores", "id": store_id}},
                "variant": {"data": {"type": "variants", "id": variant_id}},
            },
        }
    }

    async with _client(api_key) as client:
        response = await client.post("/checkouts", json=payload)
        if response.status_code != 201:
            raise LSAPIError(response.status_code, response.text)
        data = response.json()

    checkout_url = data["data"]["attributes"]["url"]
    return CheckoutResult(
        checkout_url=checkout_url,
        ls_variant_id=variant_id,
    )


async def get_subscription(ls_subscription_id: str) -> SubscriptionStatus:
    """LS subscription detayı — webhook'tan bağımsız doğrulama için."""
    api_key, _, _ = _ensure_configured()

    async with _client(api_key) as client:
        response = await client.get(f"/subscriptions/{ls_subscription_id}")
        if response.status_code != 200:
            raise LSAPIError(response.status_code, response.text)
        data = response.json()

    attrs = data["data"]["attributes"]
    return SubscriptionStatus(
        ls_subscription_id=str(data["data"]["id"]),
        ls_customer_id=str(attrs["customer_id"]),
        ls_variant_id=str(attrs["variant_id"]),
        status=attrs["status"],
        trial_ends_at=attrs.get("trial_ends_at"),
        current_period_start=attrs.get("renews_at"),
        current_period_end=attrs.get("renews_at"),
        cancelled_at=attrs.get("cancelled"),
        ends_at=attrs.get("ends_at"),
    )


async def cancel_subscription(ls_subscription_id: str) -> SubscriptionStatus:
    """LS subscription iptal et — kullanıcı dönem sonuna kadar erişim devam."""
    api_key, _, _ = _ensure_configured()

    payload = {
        "data": {
            "type": "subscriptions",
            "id": ls_subscription_id,
            "attributes": {"cancelled": True},
        }
    }
    async with _client(api_key) as client:
        response = await client.patch(f"/subscriptions/{ls_subscription_id}", json=payload)
        if response.status_code != 200:
            raise LSAPIError(response.status_code, response.text)

    return await get_subscription(ls_subscription_id)


async def get_customer_portal_url(ls_customer_id: str) -> str:
    """LS Customer Portal signed URL — cancel/update card/invoice list.

    LS API: GET /customers/:id → urls.customer_portal field.
    """
    api_key, _, _ = _ensure_configured()

    async with _client(api_key) as client:
        response = await client.get(f"/customers/{ls_customer_id}")
        if response.status_code != 200:
            raise LSAPIError(response.status_code, response.text)
        data = response.json()

    portal_url = data["data"]["attributes"].get("urls", {}).get("customer_portal")
    if not portal_url:
        raise LSAPIError(200, "customer_portal URL eksik")
    return portal_url
