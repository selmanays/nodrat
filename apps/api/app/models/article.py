"""Article + ArticleImage + ArticleChunk modelleri (Faz 1 + Faz 2 ready).

docs/engineering/data-model.md §3.4, §3.5, §4.1
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CHAR,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class Article(Base):
    """Haber makalesi — canonical_url + content_hash UNIQUE.

    State machine: discovered → fetched → cleaned → archived (or failed).
    """

    __tablename__ = "articles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sources.id", ondelete="RESTRICT"),
        nullable=False,
    )

    canonical_url: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    subtitle: Mapped[str | None] = mapped_column(Text)
    author: Mapped[str | None] = mapped_column(String(180))

    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    crawled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    raw_html_storage_path: Mapped[str | None] = mapped_column(Text)
    body_html: Mapped[str | None] = mapped_column(Text)
    clean_text: Mapped[str | None] = mapped_column(Text)

    language: Mapped[str] = mapped_column(
        String(10), nullable=False, server_default=text("'tr'")
    )

    content_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    title_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)

    extraction_confidence: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))

    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'discovered'")
    )
    """'discovered' | 'fetched' | 'cleaned' | 'failed' | 'archived'"""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Cold tier (#219 MVP-1.5 PR-4) — 30+ gün eski raw_html Contabo OS'a taşınır
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    """NOT NULL ise raw_html cold storage'da; MinIO'dan silinmiş."""

    cold_storage_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    """Contabo OS bucket key (örn: cold/2026/04/abc.html.gz). archived_at varsa dolu."""

    images: Mapped[list[ArticleImage]] = relationship(
        back_populates="article", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("canonical_url", name="uq_articles_canonical_url"),
        UniqueConstraint(
            "source_id", "content_hash", name="uq_articles_source_content_hash"
        ),
        CheckConstraint(
            "status IN ('discovered', 'fetched', 'cleaned', 'failed', 'archived')",
            name="ck_articles_status",
        ),
    )


class ArticleImage(Base):
    """Görsel metadata kaydı — VLM caption + OCR (#300 MVP-1.4 process & discard).

    Bytes asla persistent storage'a yazılmaz; download geçici, NIM VLM ile
    işlenir, sonuç bu tabloya yazılır, bytes silinir.
    """

    __tablename__ = "article_images"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    article_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("articles.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sources.id"),
        nullable=False,
    )

    original_url: Mapped[str] = mapped_column(Text, nullable=False)
    """Haber kaynağındaki orijinal URL (linking için kullanılır, biz host etmiyoruz)."""

    caption: Mapped[str | None] = mapped_column(Text)
    """HTML <figcaption> orijinal metni."""
    alt_text: Mapped[str | None] = mapped_column(Text)
    """HTML <img alt='...'> orijinal metni."""

    # #300 MVP-1.4 — VLM pipeline output (NIM Llama 4 Maverick)
    vlm_caption: Mapped[str | None] = mapped_column(Text)
    """NIM VLM tarafından üretilen Türkçe akıllı caption (1-2 cümle)."""
    ocr_text: Mapped[str | None] = mapped_column(Text)
    """Görseldeki metin (NIM VLM OCR çıktısı)."""
    depicts: Mapped[list | None] = mapped_column(JSONB)
    """Tasvir edilen kişi/obje listesi (string array). Verified label Faz 4 #60."""
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    """VLM call tamamlanma zamanı. NULL = işlenmedi."""

    position: Mapped[int | None] = mapped_column(Integer)
    """DOM order — article body içindeki görsel sırası (0-based)."""

    discovered_from: Mapped[str | None] = mapped_column(String(32))
    """'rss' | 'listing' | 'detail' | 'opengraph' | 'gallery' (legacy, body kullanılır)"""

    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'pending'")
    )
    """'pending' | 'processed' | 'failed' | 'skipped'"""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    article: Mapped[Article] = relationship(back_populates="images")

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'processed', 'failed', 'skipped')",
            name="ck_article_images_status",
        ),
        Index("idx_article_images_article", "article_id"),
        Index("idx_article_images_status", "status"),
        Index("idx_article_images_processed_at", "processed_at"),
    )
