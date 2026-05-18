"""Rename provider 'deepseek_v3' → 'deepseek' (#720 followup)

DeepSeek V3 modeli yayından kalktı (#361, 2026-04-29). Registry routing key
'deepseek_v3' yanıltıcı çünkü provider artık `deepseek-v4-flash` modelini
servis ediyor. Bu migration:

  - generations.model_provider: 'deepseek_v3' → 'deepseek'
  - provider_call_logs.provider: 'deepseek_v3' → 'deepseek'

Provider name = sağlayıcı adı (model versiyon-agnostik) olmalı; model
versiyonu zaten ayrı kolonda (model_name / model) tutuluyor.

Ölçek (2026-05-12 prod): generations 231, provider_call_logs 21,371 row.
"""

from __future__ import annotations

from alembic import op

# revision identifiers
revision = "20260512_0100"
down_revision = "20260511_0200"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) generations.model_provider
    op.execute(
        "UPDATE generations SET model_provider = 'deepseek' WHERE model_provider = 'deepseek_v3'"
    )
    # 2) provider_call_logs.provider
    op.execute("UPDATE provider_call_logs SET provider = 'deepseek' WHERE provider = 'deepseek_v3'")


def downgrade() -> None:
    # Geri alımda eski rows'ları 'deepseek_v3' etiketine döndür.
    op.execute(
        "UPDATE generations SET model_provider = 'deepseek_v3' WHERE model_provider = 'deepseek'"
    )
    op.execute("UPDATE provider_call_logs SET provider = 'deepseek_v3' WHERE provider = 'deepseek'")
