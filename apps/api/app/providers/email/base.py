"""Email provider Protocol + types (#68)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class EmailSendResult:
    """Provider'dan dönen gönderim sonucu."""

    message_id: str | None
    """Provider message ID — bounce/complaint webhook için. None ise no-op."""

    success: bool
    error: str | None = None


class EmailProvider(Protocol):
    """Transactional email provider interface.

    Implementations:
        - ResendProvider (production, real Resend API)
        - NoopProvider (test/dev, sadece log'lar — gerçek email göndermez)
    """

    name: str
    """Provider tanımlayıcı (email_log.provider'a yazılır)."""

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
        """Email gönder.

        Args:
            to: Alıcı email adresi.
            sender: Gönderici (örn. 'no-reply@nodrat.com').
            subject: Email konusu.
            html: HTML body (zorunlu).
            text: Plain text fallback (zorunlu — bazı clientlar HTML render etmez).
            reply_to: Reply-To header (örn. 'support@nodrat.com').

        Returns:
            EmailSendResult — message_id + success.

        Raises:
            asla raise etmez — error EmailSendResult.error'da döner.
            Caller email_log'a göre status set eder.
        """
        ...
