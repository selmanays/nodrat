"""SQLAlchemy modeller — Alembic autogenerate için tek noktadan import.

Yeni model eklediğinde buraya ekle ki Alembic schema'da görsün.
"""

from app.models.agenda import AgendaCard
from app.models.article import Article, ArticleImage
from app.models.event import EventArticle, EventCluster
from app.models.generation import Generation, SavedGeneration, UsageEvent
from app.models.job import AdminAuditLog, CrawlerJob, FailedJob
from app.models.provider_log import ProviderCallLog
from app.models.source import Source, SourceConfig, SourceHealth
from app.models.user import Session, User

__all__ = [
    "AdminAuditLog",
    "AgendaCard",
    "Article",
    "ArticleImage",
    "CrawlerJob",
    "EventArticle",
    "EventCluster",
    "FailedJob",
    "Generation",
    "ProviderCallLog",
    "SavedGeneration",
    "Session",
    "Source",
    "SourceConfig",
    "SourceHealth",
    "UsageEvent",
    "User",
]
