"""Add source + article pipeline tables (Faz 1 + admin_audit_log)

docs/engineering/data-model.md §3.1, §3.2, §3.3, §3.4, §3.5, §3.6, §3.7, §4.1, §5.4

Tabloları:
  - sources, source_configs, source_health (Faz 1 source mgmt)
  - articles, article_images (Faz 1 article pipeline)
  - article_chunks (Faz 2 RAG hazır — vector(1024))
  - crawler_jobs, failed_jobs (worker queue ledger + DLQ)
  - admin_audit_log (Legal §8.3)

Closes #8 #13

Revision ID: 20260501_2100
Revises: 20260501_2000
Create Date: 2026-05-01 21:00:00 UTC

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID


# revision identifiers
revision: str = "20260501_2100"
down_revision: Union[str, None] = "20260501_2000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ============================================================
    # 1) sources
    # ============================================================
    op.create_table(
        "sources",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("slug", sa.String(80), nullable=False, unique=True),
        sa.Column("domain", sa.String(180), nullable=False),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("base_url", sa.Text, nullable=False),
        sa.Column("language", sa.String(10), nullable=False, server_default=sa.text("'tr'")),
        sa.Column("country", sa.String(8), nullable=False, server_default=sa.text("'TR'")),
        sa.Column("category", sa.String(80)),
        sa.Column("reliability_score", sa.Numeric(3, 2), nullable=False, server_default=sa.text("0.70")),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("FALSE")),
        sa.Column(
            "crawl_interval_minutes",
            sa.Integer,
            nullable=False,
            server_default=sa.text("30"),
        ),
        sa.Column("last_crawled_at", sa.DateTime(timezone=True)),
        # Compliance (Legal §4)
        sa.Column("robots_txt_check_at", sa.DateTime(timezone=True)),
        sa.Column("robots_txt_compliant", sa.Boolean),
        sa.Column("tos_acknowledged", sa.Boolean, nullable=False, server_default=sa.text("FALSE")),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.CheckConstraint("type IN ('rss', 'category_page', 'manual')", name="ck_sources_type"),
        sa.CheckConstraint(
            "reliability_score >= 0.0 AND reliability_score <= 1.0",
            name="ck_sources_reliability_range",
        ),
    )

    op.create_index(
        "idx_sources_active",
        "sources",
        ["is_active"],
        postgresql_where=sa.text("is_active = TRUE"),
    )
    op.create_index("idx_sources_type", "sources", ["type"])
    op.create_index("idx_sources_domain", "sources", ["domain"])

    # updated_at trigger
    op.execute(
        "CREATE TRIGGER trg_sources_updated_at BEFORE UPDATE ON sources "
        "FOR EACH ROW EXECUTE FUNCTION trg_set_updated_at();"
    )

    # ============================================================
    # 2) source_configs
    # ============================================================
    op.create_table(
        "source_configs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "source_id",
            UUID(as_uuid=True),
            sa.ForeignKey("sources.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("config_json", JSONB, nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("FALSE")),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.UniqueConstraint("source_id", "version", name="uq_source_configs_source_version"),
    )

    op.create_index(
        "idx_source_configs_active",
        "source_configs",
        ["source_id"],
        postgresql_where=sa.text("is_active = TRUE"),
    )
    # Sadece bir aktif config per source (partial unique)
    op.create_index(
        "uniq_source_configs_one_active",
        "source_configs",
        ["source_id"],
        unique=True,
        postgresql_where=sa.text("is_active = TRUE"),
    )

    # ============================================================
    # 3) source_health (1:1 latest)
    # ============================================================
    op.create_table(
        "source_health",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "source_id",
            UUID(as_uuid=True),
            sa.ForeignKey("sources.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("last_status", sa.String(16), nullable=False, server_default=sa.text("'unknown'")),
        sa.Column("last_success_at", sa.DateTime(timezone=True)),
        sa.Column("last_failure_at", sa.DateTime(timezone=True)),
        sa.Column("failure_count_24h", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("avg_fetch_ms", sa.Integer),
        sa.Column("avg_extract_confidence", sa.Numeric(3, 2)),
        sa.Column("last_error", sa.Text),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.CheckConstraint(
            "last_status IN ('green', 'yellow', 'red', 'unknown')",
            name="ck_source_health_status",
        ),
    )
    op.create_index("idx_source_health_status", "source_health", ["last_status"])

    # ============================================================
    # 4) articles
    # ============================================================
    op.create_table(
        "articles",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "source_id",
            UUID(as_uuid=True),
            sa.ForeignKey("sources.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("canonical_url", sa.Text, nullable=False),
        sa.Column("source_url", sa.Text, nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("subtitle", sa.Text),
        sa.Column("author", sa.String(180)),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("crawled_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("raw_html_storage_path", sa.Text),
        sa.Column("body_html", sa.Text),
        sa.Column("clean_text", sa.Text),
        sa.Column("language", sa.String(10), nullable=False, server_default=sa.text("'tr'")),
        # Dedupe
        sa.Column("content_hash", sa.CHAR(64), nullable=False),
        sa.Column("title_hash", sa.CHAR(64), nullable=False),
        sa.Column("extraction_confidence", sa.Numeric(3, 2)),
        sa.Column(
            "status",
            sa.String(16),
            nullable=False,
            server_default=sa.text("'discovered'"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.UniqueConstraint("canonical_url", name="uq_articles_canonical_url"),
        sa.UniqueConstraint("source_id", "content_hash", name="uq_articles_source_content_hash"),
        sa.CheckConstraint(
            "status IN ('discovered', 'fetched', 'cleaned', 'failed', 'archived')",
            name="ck_articles_status",
        ),
    )

    op.create_index(
        "idx_articles_source_published",
        "articles",
        ["source_id", sa.text("published_at DESC")],
    )
    op.create_index(
        "idx_articles_published_at",
        "articles",
        [sa.text("published_at DESC")],
        postgresql_where=sa.text("status = 'cleaned'"),
    )
    op.create_index(
        "idx_articles_status",
        "articles",
        ["status", sa.text("created_at DESC")],
    )
    op.create_index("idx_articles_title_hash", "articles", ["title_hash"])
    # Trigram indeksleri (pg_trgm extension init migration'da yüklenmiş)
    op.execute(
        "CREATE INDEX idx_articles_title_trgm ON articles USING gin (title gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX idx_articles_clean_text_trgm ON articles USING gin (clean_text gin_trgm_ops)"
    )

    # updated_at trigger
    op.execute(
        "CREATE TRIGGER trg_articles_updated_at BEFORE UPDATE ON articles "
        "FOR EACH ROW EXECUTE FUNCTION trg_set_updated_at();"
    )

    # ============================================================
    # 5) article_images
    # ============================================================
    op.create_table(
        "article_images",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "article_id",
            UUID(as_uuid=True),
            sa.ForeignKey("articles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source_id",
            UUID(as_uuid=True),
            sa.ForeignKey("sources.id"),
            nullable=False,
        ),
        sa.Column("original_url", sa.Text, nullable=False),
        sa.Column("storage_url", sa.Text),
        sa.Column("caption", sa.Text),
        sa.Column("alt_text", sa.Text),
        sa.Column("mime_type", sa.String(64)),
        sa.Column("width", sa.Integer),
        sa.Column("height", sa.Integer),
        sa.Column("file_size", sa.Integer),
        sa.Column("sha256_hash", sa.CHAR(64)),
        sa.Column("perceptual_hash", sa.CHAR(64)),
        sa.Column("discovered_from", sa.String(32)),
        sa.Column(
            "status",
            sa.String(16),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.CheckConstraint(
            "status IN ('pending', 'downloaded', 'failed', 'duplicate')",
            name="ck_article_images_status",
        ),
    )
    op.create_index("idx_article_images_article", "article_images", ["article_id"])
    op.create_index("idx_article_images_status", "article_images", ["status"])
    op.create_index(
        "uniq_article_images_hash",
        "article_images",
        ["sha256_hash"],
        unique=True,
        postgresql_where=sa.text("sha256_hash IS NOT NULL AND status = 'downloaded'"),
    )

    # ============================================================
    # 6) article_chunks (Faz 2 hazır)
    # ============================================================
    op.execute(
        """
        CREATE TABLE article_chunks (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            article_id      UUID NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
            source_id       UUID NOT NULL REFERENCES sources(id),
            chunk_index     INTEGER NOT NULL,
            chunk_text      TEXT NOT NULL,
            token_count     INTEGER NOT NULL,
            embedding       vector(1024),
            embedding_model VARCHAR(80),
            embedding_provider VARCHAR(80),
            published_at    TIMESTAMPTZ,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (article_id, chunk_index)
        );
        """
    )
    op.execute(
        "CREATE INDEX idx_article_chunks_embedding "
        "ON article_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);"
    )
    op.create_index("idx_article_chunks_article", "article_chunks", ["article_id"])
    op.create_index(
        "idx_article_chunks_published",
        "article_chunks",
        [sa.text("published_at DESC")],
        postgresql_where=sa.text("published_at IS NOT NULL"),
    )
    op.create_index(
        "idx_article_chunks_source_published",
        "article_chunks",
        ["source_id", sa.text("published_at DESC")],
    )

    # ============================================================
    # 7) crawler_jobs (queue ledger)
    # ============================================================
    op.create_table(
        "crawler_jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("job_type", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default=sa.text("'queued'")),
        sa.Column("priority", sa.SmallInteger, nullable=False, server_default=sa.text("50")),
        sa.Column("payload_json", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("attempt_count", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("max_attempts", sa.Integer, nullable=False, server_default=sa.text("3")),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("error_message", sa.Text),
        sa.Column(
            "source_id",
            UUID(as_uuid=True),
            sa.ForeignKey("sources.id", ondelete="CASCADE"),
        ),
        sa.Column(
            "article_id",
            UUID(as_uuid=True),
            sa.ForeignKey("articles.id", ondelete="CASCADE"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'dead')",
            name="ck_crawler_jobs_status",
        ),
    )

    op.create_index(
        "idx_crawler_jobs_status",
        "crawler_jobs",
        ["status", sa.text("priority DESC"), "scheduled_at"],
    )
    op.create_index("idx_crawler_jobs_type", "crawler_jobs", ["job_type", "status"])
    op.create_index(
        "idx_crawler_jobs_source",
        "crawler_jobs",
        ["source_id"],
        postgresql_where=sa.text("source_id IS NOT NULL"),
    )
    op.create_index(
        "idx_crawler_jobs_article",
        "crawler_jobs",
        ["article_id"],
        postgresql_where=sa.text("article_id IS NOT NULL"),
    )

    # ============================================================
    # 8) failed_jobs (DLQ)
    # ============================================================
    op.create_table(
        "failed_jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("original_job_id", UUID(as_uuid=True)),
        sa.Column("job_type", sa.String(64), nullable=False),
        sa.Column("payload_json", JSONB, nullable=False),
        sa.Column(
            "source_id",
            UUID(as_uuid=True),
            sa.ForeignKey("sources.id", ondelete="SET NULL"),
        ),
        sa.Column("article_url", sa.Text),
        sa.Column("error_message", sa.Text, nullable=False),
        sa.Column("stack_trace", sa.Text),
        sa.Column("retry_count", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("resolved_by", UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("resolution_note", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )

    op.create_index(
        "idx_failed_jobs_unresolved",
        "failed_jobs",
        [sa.text("created_at DESC")],
        postgresql_where=sa.text("resolved_at IS NULL"),
    )
    op.create_index(
        "idx_failed_jobs_source",
        "failed_jobs",
        ["source_id"],
        postgresql_where=sa.text("source_id IS NOT NULL"),
    )

    # ============================================================
    # 9) admin_audit_log (Legal §8.3)
    # ============================================================
    op.create_table(
        "admin_audit_log",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "actor_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("action", sa.String(80), nullable=False),
        sa.Column("target_type", sa.String(80)),
        sa.Column("target_id", UUID(as_uuid=True)),
        sa.Column("metadata", JSONB, server_default=sa.text("'{}'::jsonb")),
        sa.Column("ip_address", INET),
        sa.Column("user_agent", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )

    op.create_index(
        "idx_admin_audit_log_actor_created",
        "admin_audit_log",
        ["actor_id", sa.text("created_at DESC")],
    )
    op.create_index(
        "idx_admin_audit_log_action_created",
        "admin_audit_log",
        ["action", sa.text("created_at DESC")],
    )
    op.create_index(
        "idx_admin_audit_log_target",
        "admin_audit_log",
        ["target_type", "target_id"],
        postgresql_where=sa.text("target_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_table("admin_audit_log")
    op.drop_table("failed_jobs")
    op.drop_table("crawler_jobs")
    op.execute("DROP INDEX IF EXISTS idx_article_chunks_embedding")
    op.drop_table("article_chunks")
    op.drop_table("article_images")
    op.execute("DROP TRIGGER IF EXISTS trg_articles_updated_at ON articles")
    op.execute("DROP INDEX IF EXISTS idx_articles_title_trgm")
    op.execute("DROP INDEX IF EXISTS idx_articles_clean_text_trgm")
    op.drop_table("articles")
    op.drop_table("source_health")
    op.drop_table("source_configs")
    op.execute("DROP TRIGGER IF EXISTS trg_sources_updated_at ON sources")
    op.drop_table("sources")
