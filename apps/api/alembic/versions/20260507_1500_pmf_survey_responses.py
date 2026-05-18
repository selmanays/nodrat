"""PMF survey responses scaffold (#55, MVP-2 Dalga 5)

Sean Ellis testi — 30g aktif user'a sorulur:
"Nodrat olmasaydı nasıl hissederdin?"
  - very_disappointed (hedef ≥%40)
  - somewhat_disappointed
  - not_disappointed
  - already_left

Tablo:
    pmf_survey_responses (id, user_id, response, comment, submitted_at)
    UNIQUE(user_id) — her user 1 kez yanıt verir

Settings flag: pmf_survey.enabled (admin_settings.py'da default false).
Endpoint: POST /app/me/pmf-survey (auth req).
30g aktif user check: app/me/pmf-survey/eligibility GET.

Revision ID: 20260507_1500
Revises: 20260506_1830
Create Date: 2026-05-07 15:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260507_1500"
down_revision = "20260506_1830"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pmf_survey_responses",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "response",
            sa.String(32),
            nullable=False,
            comment="very_disappointed | somewhat_disappointed | not_disappointed | already_left",
        ),
        sa.Column(
            "comment",
            sa.Text(),
            nullable=True,
            comment="Opsiyonel kullanıcı yorumu (max 500 char UI'da limit)",
        ),
        sa.Column(
            "submitted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    # response value check
    op.create_check_constraint(
        "ck_pmf_response_value",
        "pmf_survey_responses",
        sa.text(
            "response IN ('very_disappointed', 'somewhat_disappointed', "
            "'not_disappointed', 'already_left')"
        ),
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_pmf_response_value", "pmf_survey_responses", type_="check"
    )
    op.drop_table("pmf_survey_responses")
