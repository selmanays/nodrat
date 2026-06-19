"""Article + ArticleImage + ArticleChunk modelleri (Faz 1 + Faz 2 ready).

T8-12b (2026-05-28): `app/models/article.py`'den buraya taşındı (articles domain).
T8-12a ile sources→articles decouple (raw SQL) yapılmıştı → relocation contract-temiz.
relationship() internal (Article.images ↔ ArticleImage.article cascade); 2 class
birlikte → mapper-safe. Vector(1024) summary_embedding ORM declaration KONUMU değişir;
tablo `articles` / ivfflat index / migration `20260511_0100` / raw-SQL write+read
path'leri (tablo adına bağlı) DEĞİŞMEZ — embedding/RAG/index VERİSİNE dokunulmaz.

docs/engineering/data-model.md §3.4, §3.5, §4.1

articles.summary_embedding (vector(1024)) Phase 8.2 PR-8.2-12'de ORM'e tanımlandı.
Migration: 20260511_0100_article_summary_embedding.py `sa.Column("summary_embedding",
Vector(1024), nullable=True)` ile yaratıldı (#661 Faz 5.2 article-level tema match).
Write path: `app/modules/embedding/tasks/embedding.py:532` raw SQL
`UPDATE articles SET summary_embedding = :vec WHERE id = :aid`.
Read path: `app/core/retrieval.py:1148-1153` raw SQL cosine similarity
`<=> (:vec)::vector` + `WHERE summary_embedding IS NOT NULL`.
ORM attribute access (`.summary_embedding`) YOK — Mapped declaration sadece
alembic autogenerate metadata için.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pgvector.sqlalchemy import Vector
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
    external_article_id: Mapped[str | None] = mapped_column(Text)
    """#496 — Kaynak sitenin haber ID'si (URL'den extract edilir).

    Pattern örnekleri: Evrensel /haber/{id}/, AA /tr/.../{id}. Slug değişikliği
    nedeniyle aynı haber farklı URL'le iki kez INSERT edilmesin diye dedup
    anahtarı. Aynı (source_id, external_article_id) tekil — partial unique
    index `uq_articles_source_external_id`.
    """
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

    body_html: Mapped[str | None] = mapped_column(Text)
    clean_text: Mapped[str | None] = mapped_column(Text)

    language: Mapped[str] = mapped_column(String(10), nullable=False, server_default=text("'tr'"))

    content_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    title_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)

    extraction_confidence: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))

    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'discovered'")
    )
    """#904: 'discovered' | 'fetched' | 'cleaned' | 'failed'
    | 'quarantine' (extraction-miss, GÖRÜNÜR + retryable)
    | 'discarded' (gerçek kalıcı: true soft_404/duplicate/invalid — TEK terminal).

    ESKİ 'archived' status DEĞERİ kaldırıldı (#483 overload çözüldü)."""

    extract_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    """#904 — fetch_detail deneme sayacı. retry_failed yaş-tabanlı
    (`created_at`) yerine deneme-tabanlı: extract_attempts < max → retry,
    >= max & quarantine → discarded."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # #513 — pipeline state-machine geçiş timestamp'i (admin chart için)
    cleaned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    """status 'cleaned' geçişinde set edilir; sadece bu geçiş etkiler.

    `updated_at` çok-amaçlı (her UPDATE'te değişir — status, body_html drop,
    dedup migration, ext_id backfill, vb.). Chart 'Temizlenen içerikler'
    yığılmasını önlemek için ayrı field. Aynı pattern image_vlm.processed_at
    için kullanılır (#479).
    """

    # #1602 — NER 'denendi' işareti. extract_article_entities başarılı LLM çağrısı
    # sonunda (entity bulunsun/bulunmasın) set edilir; backfill `IS NULL` ile
    # entity-üretmeyen (gürültü) makaleleri eler → sonsuz NER döngüsü kırılır.
    # Aynı pattern cleaned_at / image_vlm.processed_at.
    entities_extracted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    """NOT NULL ise NER en az bir kez başarıyla çalıştı (entity bulunmasa da)."""

    # Phase 8.2 PR-8.2-12: pgvector Vector(1024) ORM declaration
    # Migration: 20260511_0100_article_summary_embedding.py
    # `sa.Column("summary_embedding", Vector(1024), nullable=True)` — explicit nullable=True.
    # Writer: app/modules/embedding/tasks/embedding.py:532 raw SQL
    #   `UPDATE articles SET summary_embedding = :vec WHERE id = :aid`.
    # Reader: app/core/retrieval.py:1148-1153 raw SQL `<=> (:vec)::vector` cosine
    #   + `WHERE summary_embedding IS NOT NULL`.
    # ORM accessor YOK — Mapped declaration sadece alembic metadata için.
    # #661 Faz 5.2 — article-level tema match (chunk-level RAPTOR ile complement).
    summary_embedding: Mapped[list[float] | None] = mapped_column(Vector(1024), nullable=True)

    images: Mapped[list[ArticleImage]] = relationship(
        back_populates="article", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("canonical_url", name="uq_articles_canonical_url"),
        UniqueConstraint("source_id", "content_hash", name="uq_articles_source_content_hash"),
        CheckConstraint(
            "status IN ('discovered', 'fetched', 'cleaned', 'failed', 'quarantine', 'discarded')",
            name="ck_articles_status",
        ),
        # Partial UQ — RSS source-bazlı external_article_id deduplication
        # Migration: 20260509_0500_articles_external_id_dedup.py §6
        # NULL external_article_id'ler kısıtlanmaz (Tier-2 manuel scrape).
        Index(
            "uq_articles_source_external_id",
            "source_id",
            "external_article_id",
            unique=True,
            postgresql_where=text("external_article_id IS NOT NULL"),
        ),
        # ============================================================
        # Phase 8.2 PR-8.2-3: 8 Index drift — DB'de zaten mevcut
        # Migration: 20260501_2100_add_sources_articles.py (5 index)
        #          + 20260509_0800_articles_cleaned_at.py (1 index)
        # (#1634: 20260506_1500 idx_articles_archive_candidate kaldırıldı — cold-tier sökümü)
        # ============================================================
        Index(
            "idx_articles_source_published",
            "source_id",
            text("published_at DESC"),
        ),
        Index(
            "idx_articles_published_at",
            text("published_at DESC"),
            postgresql_where=text("status = 'cleaned'"),
        ),
        Index(
            "idx_articles_status",
            "status",
            text("created_at DESC"),
        ),
        Index("idx_articles_title_hash", "title_hash"),
        # GIN trigram indexes — full-text fuzzy search (pg_trgm extension)
        Index(
            "idx_articles_title_trgm",
            "title",
            postgresql_using="gin",
            postgresql_ops={"title": "gin_trgm_ops"},
        ),
        Index(
            "idx_articles_clean_text_trgm",
            "clean_text",
            postgresql_using="gin",
            postgresql_ops={"clean_text": "gin_trgm_ops"},
        ),
        # Chart query hot path — cleaned_at sort with partial WHERE
        Index(
            "idx_articles_cleaned_at_status",
            "cleaned_at",
            postgresql_where=text("status = 'cleaned' AND cleaned_at IS NOT NULL"),
        ),
        # Phase 8.2 PR-8.2-12: pgvector ivfflat index ORM declaration
        # Migration: 20260511_0100_article_summary_embedding.py L25-29
        # `CREATE INDEX IF NOT EXISTS idx_articles_summary_emb ON articles
        # USING ivfflat (summary_embedding vector_cosine_ops) WITH (lists = 100)`
        # NOT: lists=100 (agenda/event lists=50'den farklı; daha büyük table)
        Index(
            "idx_articles_summary_emb",
            "summary_embedding",
            postgresql_using="ivfflat",
            postgresql_ops={"summary_embedding": "vector_cosine_ops"},
            postgresql_with={"lists": 100},
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

    error_message: Mapped[str | None] = mapped_column(Text)
    """#477 — fail nedeni (status='failed' olduğunda doldurulur).

    Örnekler: 'vlm: NIM error: status=403' (auth fail), 'NIM_API_KEY missing',
    'rejected: image too large', 'rejected: invalid mime'. Admin media sayfasında
    "Başarısız" badge yanında gösterilir; eskiden Celery result backend'inde
    saklanıyordu, UI'dan erişilemiyordu.
    """

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
