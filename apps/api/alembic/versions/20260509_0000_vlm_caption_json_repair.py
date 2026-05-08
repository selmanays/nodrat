"""Bozuk vlm_caption (raw JSON) kayıtlarını repair (#480)

Production tanı (2026-05-08 23:50 UTC):
  article_images.vlm_caption LIKE '{%' → 4 kayıt (~%0.2 oran)
  Sebep: NIM modeli bazen \\u00b (3 hex digit) gibi bozuk Unicode escape üretir;
  json.loads fail → eski parser fallback'a düşüp raw JSON'u caption alanına
  döker; ocr_text ve depicts boş kalır.

Bu migration mevcut 4 bozuk kaydı _safe_json_parse (yeni multi-fallback) ile
doğru alanlara dağıtır. Yeni gelen kayıtlar artık parser fix sayesinde sorunsuz
yazılır.

Revision ID: 20260509_0000
Revises: 20260508_2330
Create Date: 2026-05-08 23:50:00
"""

from __future__ import annotations

import json
import re

import sqlalchemy as sa
from alembic import op


revision = "20260509_0000"
down_revision = "20260508_2330"
branch_labels = None
depends_on = None


# Inline parser kopyası — migration'ın kendi modülünde olması için
# (app.providers.nim_vlm import migration runtime'da risksiz değil; alembic
# tek-dosya self-contained yaklaşımı).
_STRING_BODY = r'"((?:[^"\\]|\\.)*)"'


def _decode_escapes(s: str) -> str:
    replaced = (
        s.replace(r"\"", '"')
         .replace(r"\\", "\\")
         .replace(r"\n", "\n")
         .replace(r"\t", "\t")
    )
    def _u_sub(m: re.Match) -> str:
        try:
            return chr(int(m.group(1), 16))
        except (ValueError, OverflowError):
            return m.group(0)
    return re.sub(r"\\u([0-9a-fA-F]{4})", _u_sub, replaced)


def _safe_parse(text: str) -> dict | None:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    repaired = re.sub(
        r"\\u([0-9a-fA-F]{1,3})(?![0-9a-fA-F])",
        lambda m: r"\\u" + m.group(1),
        text,
    )
    if repaired != text:
        try:
            return json.loads(repaired)
        except json.JSONDecodeError:
            pass
    cap_m = re.search(r'"caption"\s*:\s*' + _STRING_BODY, text, re.DOTALL)
    ocr_m = re.search(r'"ocr_text"\s*:\s*' + _STRING_BODY, text, re.DOTALL)
    dep_m = re.search(r'"depicts"\s*:\s*\[([^\]]*)\]', text, re.DOTALL)
    if not (cap_m or ocr_m):
        return None
    depicts: list[str] = []
    if dep_m:
        depicts = re.findall(r'"((?:[^"\\]|\\.)*)"', dep_m.group(1))
    return {
        "caption": _decode_escapes(cap_m.group(1)) if cap_m else "",
        "ocr_text": _decode_escapes(ocr_m.group(1)) if ocr_m else "",
        "depicts": [_decode_escapes(d) for d in depicts][:20],
    }


def upgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            """
            SELECT id, vlm_caption FROM article_images
            WHERE status = 'processed' AND vlm_caption LIKE '{%'
            """
        )
    ).fetchall()

    for row in rows:
        parsed = _safe_parse(row.vlm_caption)
        if parsed is None:
            # Parse edilemediyse caption'ı bilgilendirici bir mesaja çevir;
            # raw JSON UI'da kalmasın.
            bind.execute(
                sa.text(
                    """
                    UPDATE article_images
                    SET vlm_caption = 'VLM yanıtı ayrıştırılamadı (eski parser hatası, #480)'
                    WHERE id = :id
                    """
                ),
                {"id": row.id},
            )
            continue

        caption = (parsed.get("caption") or "")[:5000].strip()
        ocr_text = (parsed.get("ocr_text") or "")[:10000].strip()
        depicts = parsed.get("depicts") or []
        if not isinstance(depicts, list):
            depicts = []
        depicts_clean = [str(d)[:200] for d in depicts[:20]]

        bind.execute(
            sa.text(
                """
                UPDATE article_images
                SET vlm_caption = :cap,
                    ocr_text = COALESCE(NULLIF(:ocr, ''), ocr_text),
                    depicts = CAST(:depicts AS jsonb)
                WHERE id = :id
                """
            ),
            {
                "id": row.id,
                "cap": caption,
                "ocr": ocr_text,
                "depicts": json.dumps(depicts_clean),
            },
        )


def downgrade() -> None:
    # Geri alma yok — orijinal raw JSON elde tutulmadı.
    pass
