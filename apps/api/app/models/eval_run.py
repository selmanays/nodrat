"""EvalRun ORM model — RAG benchmark history (#190).

docs/engineering/data-model.md (admin RAG observability)
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import DateTime, Index, Integer, Numeric, String, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class EvalRun(Base):
    """RAG retrieval benchmark sonucu (PR-A #179 + admin #190)."""

    __tablename__ = "eval_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    golden_set: Mapped[str] = mapped_column(String(120), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    n_queries: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    top_k: Mapped[int] = mapped_column(Integer, nullable=False, default=20)

    ndcg_10: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    map_5: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    mrr_10: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    recall_20: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    p_5: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    latency_ms_p50: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    latency_ms_p95: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))

    config_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    triggered_by: Mapped[str | None] = mapped_column(String(80))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("idx_eval_runs_created", text("created_at DESC")),
        Index(
            "idx_eval_runs_golden_set",
            "golden_set",
            text("created_at DESC"),
        ),
    )
