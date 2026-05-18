"""Email provider factory (#68).

Production: Resend (RESEND_API_KEY varsa)
Test/dev: Noop (sadece log)
"""

from __future__ import annotations

import logging
from functools import lru_cache

from app.config import get_settings
from app.providers.email.base import EmailProvider
from app.providers.email.noop import NoopEmailProvider
from app.providers.email.resend import ResendProvider

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_email_provider() -> EmailProvider:
    """Settings'e göre email provider seç.

    - RESEND_API_KEY (re_...) varsa → ResendProvider
    - Aksi halde → NoopEmailProvider (warning log)
    """
    settings = get_settings()

    raw_key = settings.resend_api_key.get_secret_value() if settings.resend_api_key else ""
    api_key = raw_key.strip()
    if api_key.startswith("re_"):
        logger.info("email_provider.init", extra={"provider": "resend"})
        return ResendProvider(api_key=api_key)

    logger.warning(
        "email_provider.fallback_noop",
        extra={"reason": "RESEND_API_KEY not configured"},
    )
    return NoopEmailProvider()
