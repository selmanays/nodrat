"""Resend email provider (#68).

API: https://resend.com/docs/api-reference/emails/send-email
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.providers.email.base import EmailSendResult

logger = logging.getLogger(__name__)


RESEND_API_URL = "https://api.resend.com/emails"


class ResendProvider:
    """Resend.com transactional email provider."""

    name: str = "resend"

    def __init__(self, api_key: str, timeout_sec: float = 10.0) -> None:
        if not api_key or not api_key.startswith("re_"):
            raise ValueError("Invalid Resend API key (must start with 're_')")
        self._api_key = api_key
        self._timeout = timeout_sec

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
        """POST https://api.resend.com/emails."""

        payload: dict[str, Any] = {
            "from": sender,
            "to": [to],
            "subject": subject,
            "html": html,
            "text": text,
        }
        if reply_to:
            payload["reply_to"] = reply_to

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    RESEND_API_URL,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                )

            if resp.status_code == 200:
                body = resp.json()
                message_id = body.get("id")
                logger.info(
                    "resend.send.ok",
                    extra={
                        "to": to,
                        "subject": subject[:80],
                        "message_id": message_id,
                    },
                )
                return EmailSendResult(message_id=message_id, success=True)

            # Error path
            try:
                err_body = resp.json()
                err_msg = err_body.get("message") or str(err_body)
            except Exception:
                err_msg = resp.text[:500]

            logger.warning(
                "resend.send.fail",
                extra={
                    "to": to,
                    "status": resp.status_code,
                    "error": err_msg[:200],
                },
            )
            return EmailSendResult(
                message_id=None,
                success=False,
                error=f"HTTP {resp.status_code}: {err_msg[:200]}",
            )

        except httpx.HTTPError as exc:
            logger.exception("resend.send.exception", extra={"to": to})
            return EmailSendResult(
                message_id=None, success=False, error=f"HTTPError: {exc}"
            )
