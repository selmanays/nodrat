"""SQLAlchemy modeller — Alembic autogenerate için tek noktadan import.

Yeni model eklediğinde buraya ekle ki Alembic schema'da görsün.
"""

from app.models.article import Article, ArticleImage
from app.models.job import AdminAuditLog, CrawlerJob, FailedJob
from app.models.source import Source, SourceConfig, SourceHealth
from app.models.user import Session, User

__all__ = [
    "AdminAuditLog",
    "Article",
    "ArticleImage",
    "CrawlerJob",
    "FailedJob",
    "Session",
    "Source",
    "SourceConfig",
    "SourceHealth",
    "User",
]
