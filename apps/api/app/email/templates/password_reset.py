"""Password reset template (#68)."""

from __future__ import annotations

from dataclasses import dataclass

from app.email.templates._layout import cta_button, html_layout


@dataclass
class PasswordResetContent:
    subject: str
    html: str
    text: str


def build_password_reset(
    *, reset_url: str, ttl_hours: int = 1, request_ip: str | None = None
) -> PasswordResetContent:
    """Şifre sıfırlama mesajı oluştur.

    Args:
        reset_url: Tam URL (örn. https://nodrat.com/auth/reset?token=...)
        ttl_hours: Token geçerlilik süresi
        request_ip: İsteğin geldiği IP (kullanıcıya bilgi)
    """
    subject = "Nodrat — şifre sıfırlama isteği"

    ip_note = ""
    if request_ip:
        ip_note = (
            f'<p style="margin: 16px 0 0 0; font-size: 13px; color: #9ca3af;">'
            f"Bu istek <strong>{request_ip}</strong> IP adresinden alındı."
            f"</p>"
        )

    body_html = f"""
<h2 style="margin: 0 0 16px 0; font-size: 20px; font-weight: 600;">
  Şifre sıfırlama
</h2>
<p style="margin: 0 0 12px 0;">
  Hesabın için şifre sıfırlama talebi aldık. Yeni şifre belirlemek için aşağıdaki düğmeye tıkla.
</p>
{cta_button("Yeni şifre belirle", reset_url)}
<p style="margin: 16px 0 0 0; font-size: 14px; color: #6b7280;">
  Düğme çalışmazsa şu bağlantıyı tarayıcına kopyala:
</p>
<p style="margin: 4px 0 0 0; font-size: 13px; word-break: break-all; color: #1a3d5c;">
  {reset_url}
</p>
<p style="margin: 24px 0 0 0; font-size: 13px; color: #9ca3af;">
  Bu bağlantı <strong>{ttl_hours} saat</strong> içinde geçersiz olur.
</p>
<p style="margin: 12px 0 0 0; font-size: 13px; color: #ef4444;">
  <strong>Bu talebi sen oluşturmadıysan</strong> bu e-postayı görmezden gelebilirsin —
  şifren değişmedi. Şüphelendiğin durumlarda
  <a href="mailto:support@nodrat.com" style="color: #ef4444;">support@nodrat.com</a> adresine yaz.
</p>
{ip_note}
"""

    text_ip_note = f"\nBu istek {request_ip} IP adresinden alındı.\n" if request_ip else ""

    text = f"""Nodrat — şifre sıfırlama isteği

Hesabın için şifre sıfırlama talebi aldık. Yeni şifre belirlemek için aşağıdaki bağlantıya tıkla:

{reset_url}

Bu bağlantı {ttl_hours} saat içinde geçersiz olur.

⚠ Bu talebi sen oluşturmadıysan bu e-postayı görmezden gelebilirsin — şifren değişmedi.
Şüphelendiğin durumlarda support@nodrat.com adresine yaz.
{text_ip_note}

—
Nodrat Ekibi
support@nodrat.com
"""

    return PasswordResetContent(
        subject=subject,
        html=html_layout(title=subject, body_html=body_html),
        text=text,
    )
