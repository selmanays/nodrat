"""No-op email provider — test + dev (#68).

Email göndermez, sadece log'a yazar. Production'da kullanılmaz."""

from __future__ import annotations

import logging
import uuid

from app.providers.email.base import EmailSendResult

logger = logging.getLogger(__name__)


class NoopEmailProvider:
    """Dev/test fallback — email API çağrısı yapmaz."""

    name: str = "noop"

    async def send(
        self,
        *,
        to: str,
        sender: str,
        subject: str,
        html: str,
        text: str,
        reply_to: str | None = None,
    ) -> EmailSendResult:
        fake_id = f"noop-{uuid.uuid4().hex[:12]}"
        logger.info(
            "noop_email.send",
            extra={
                "to": to,
                "sender": sender,
                "subject": subject[:120],
                "text_preview": text[:200],
                "message_id": fake_id,
            },
        )
        return EmailSendResult(message_id=fake_id, success=True)
