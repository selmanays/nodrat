"""SQLAlchemy modeller — Alembic autogenerate için tek noktadan import.

Yeni model eklediğinde buraya ekle ki Alembic schema'da görsün.
"""

from app.models.agenda import AgendaCard
from app.models.app_setting import AppSetting
from app.models.article import Article, ArticleImage
from app.models.email import EmailLog, EmailVerificationToken, PasswordResetToken
from app.models.event import EventArticle, EventCluster
from app.models.generation import Generation, SavedGeneration, UsageEvent
from app.models.job import AdminAuditLog, CrawlerJob, FailedJob
from app.models.provider_log import ProviderCallLog
from app.models.source import Source, SourceConfig, SourceHealth
from app.models.takedown import TakedownRequest
from app.models.user import Session, User

__all__ = [
    "AdminAuditLog",
    "AgendaCard",
    "AppSetting",
    "Article",
    "ArticleImage",
    "CrawlerJob",
    "EmailLog",
    "EmailVerificationToken",
    "EventArticle",
    "EventCluster",
    "FailedJob",
    "Generation",
    "PasswordResetToken",
    "ProviderCallLog",
    "SavedGeneration",
    "Session",
    "Source",
    "SourceConfig",
    "SourceHealth",
    "TakedownRequest",
    "UsageEvent",
    "User",
]
