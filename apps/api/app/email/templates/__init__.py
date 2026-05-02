"""Email templates (#68).

Tüm template'ler:
- Türkçe (locale=tr-TR)
- HTML + plain text (multi-part)
- Inline CSS (email client kompatibilitesi)
- Link expiration süresi açıkça belirtilir
"""

from app.email.templates.password_reset import build_password_reset
from app.email.templates.verify import build_email_verify

__all__ = ["build_email_verify", "build_password_reset"]
