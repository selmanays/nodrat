"""AppSetting ORM model — admin runtime config (#263, MVP-1.2).

docs/engineering/data-model.md (admin settings panel)
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class AppSetting(Base):
    """Runtime-tunable application settings (#262 Epic).

    Hardcoded `config.py` değerlerinin DB'ye taşınmış hali. Admin paneli
    `PUT /admin/settings/{key}` üzerinden günceller; SettingsStore
    Redis pub/sub ile tüm container'lara bildirir.
    """

    __tablename__ = "app_settings"
    __table_args__ = (
        CheckConstraint(
            "type IN ('float','int','bool','string','json')",
            name="app_settings_type_check",
        ),
        Index("idx_app_settings_group", "group_name"),
    )

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[Any] = mapped_column(JSONB, nullable=False)
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    group_name: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    min_value: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    max_value: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    allowed_values: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    requires_restart: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
