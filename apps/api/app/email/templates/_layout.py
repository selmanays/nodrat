"""Email layout — ortak HTML wrapper (#68).

Tüm template'ler bu layout'u kullanır. Inline CSS (email client uyumu)."""

from __future__ import annotations


_BRAND_PRIMARY = "#1a3d5c"  # brand-700
_TEXT_DARK = "#1f2937"
_TEXT_MUTED = "#6b7280"
_BG_SOFT = "#f9fafb"


def html_layout(*, title: str, body_html: str, footer_html: str = "") -> str:
    """Ortak HTML email layout.

    Args:
        title: Email konusu (alt-text + browser tab).
        body_html: Ana içerik (zaten HTML).
        footer_html: Footer'a ek HTML (opsiyonel).
    """
    base_footer = (
        '<p style="margin: 16px 0 0 0; font-size: 12px; color: #9ca3af;">'
        "Bu e-postayı yanlışlıkla aldıysanız görmezden gelebilirsiniz. "
        "İletişim: <a href='mailto:support@nodrat.com' "
        "style='color: #6b7280;'>support@nodrat.com</a>"
        "</p>"
        '<p style="margin: 8px 0 0 0; font-size: 11px; color: #9ca3af;">'
        "Nodrat — gündemi kaynaklı X içeriklerine dönüştüren editör aracı."
        "</p>"
    )

    return f"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
</head>
<body style="margin: 0; padding: 0; background: {_BG_SOFT}; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
  <table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="background: {_BG_SOFT}; padding: 32px 16px;">
    <tr>
      <td align="center">
        <table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="max-width: 560px; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.08);">
          <!-- Header -->
          <tr>
            <td style="background: {_BRAND_PRIMARY}; padding: 20px 32px;">
              <h1 style="margin: 0; color: white; font-size: 22px; font-weight: 600; letter-spacing: -0.01em;">
                Nodrat
              </h1>
            </td>
          </tr>
          <!-- Body -->
          <tr>
            <td style="padding: 32px; color: {_TEXT_DARK}; font-size: 15px; line-height: 1.6;">
              {body_html}
            </td>
          </tr>
          <!-- Footer -->
          <tr>
            <td style="padding: 0 32px 24px 32px; color: {_TEXT_MUTED}; font-size: 13px;">
              {footer_html}
              {base_footer}
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def cta_button(text: str, url: str) -> str:
    """Standart eylem düğmesi (HTML)."""
    return f"""
<table role="presentation" cellpadding="0" cellspacing="0" style="margin: 24px 0;">
  <tr>
    <td style="border-radius: 6px; background: {_BRAND_PRIMARY};">
      <a href="{url}"
         style="display: inline-block; padding: 12px 28px; color: white; text-decoration: none; font-weight: 600; font-size: 15px; border-radius: 6px;">
        {text}
      </a>
    </td>
  </tr>
</table>
"""
