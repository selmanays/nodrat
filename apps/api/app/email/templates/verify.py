"""Email verification template (#68)."""

from __future__ import annotations

from dataclasses import dataclass

from app.email.templates._layout import cta_button, html_layout


@dataclass
class EmailVerifyContent:
    subject: str
    html: str
    text: str


def build_email_verify(*, verify_url: str, ttl_hours: int = 24) -> EmailVerifyContent:
    """Email doğrulama mesajı oluştur.

    Args:
        verify_url: Tam URL (örn. https://nodrat.com/auth/verify?token=...)
        ttl_hours: Token geçerlilik süresi (subject'e yazılır)
    """
    subject = "Nodrat — e-posta doğrulama"

    body_html = f"""
<h2 style="margin: 0 0 16px 0; font-size: 20px; font-weight: 600;">
  E-posta adresini doğrula
</h2>
<p style="margin: 0 0 12px 0;">
  Nodrat hesabını oluşturduğun için teşekkürler. Devam etmek için aşağıdaki düğmeye tıklayarak
  e-posta adresini doğrula.
</p>
{cta_button("E-posta adresimi doğrula", verify_url)}
<p style="margin: 16px 0 0 0; font-size: 14px; color: #6b7280;">
  Düğme çalışmazsa şu bağlantıyı tarayıcına kopyala:
</p>
<p style="margin: 4px 0 0 0; font-size: 13px; word-break: break-all; color: #1a3d5c;">
  {verify_url}
</p>
<p style="margin: 24px 0 0 0; font-size: 13px; color: #9ca3af;">
  Bu bağlantı <strong>{ttl_hours} saat</strong> içinde geçersiz olur.
  Süre dolduysa hesap ayarlarından yeni bir doğrulama e-postası talep edebilirsin.
</p>
"""

    text = f"""Nodrat — e-posta doğrulama

Hesabını oluşturduğun için teşekkürler. Devam etmek için aşağıdaki bağlantıya tıklayarak
e-posta adresini doğrula:

{verify_url}

Bu bağlantı {ttl_hours} saat içinde geçersiz olur.

Bu e-postayı yanlışlıkla aldıysan görmezden gelebilirsin.

—
Nodrat Ekibi
support@nodrat.com
"""

    return EmailVerifyContent(
        subject=subject,
        html=html_layout(title=subject, body_html=body_html),
        text=text,
    )
