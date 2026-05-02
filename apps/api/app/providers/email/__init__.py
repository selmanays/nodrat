"""Email provider abstraction (#68).

Usage:
    from app.providers.email import get_email_provider

    provider = get_email_provider()
    message_id = await provider.send(
        to="user@example.com",
        sender="no-reply@nodrat.com",
        subject="...",
        html="<p>...</p>",
        text="...",
    )
"""

from app.providers.email.base import EmailProvider, EmailSendResult
from app.providers.email.factory import get_email_provider

__all__ = ["EmailProvider", "EmailSendResult", "get_email_provider"]
