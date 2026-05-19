"""SQLAlchemy modeller — Alembic autogenerate için tek noktadan import.

Yeni model eklediğinde buraya ekle ki Alembic schema'da görsün.
"""

from app.models.agenda import AgendaCard
from app.models.app_prompt import AppPrompt, AppPromptHistory
from app.models.app_setting import AppSetting
from app.models.article import Article, ArticleImage
from app.models.billing import (
    AgencySeat,
    Invoice,
    Plan,
    Subscription,
    WebhookEvent,
)
from app.models.conversation import Conversation, Message
from app.models.email import EmailLog, EmailVerificationToken, PasswordResetToken
from app.models.event import EventArticle, EventCluster
from app.models.generation import UsageEvent  # #800 S1B — Generation+SavedGeneration DROP
from app.models.job import AdminAuditLog, FailedJob
from app.models.provider_log import ProviderCallLog
from app.models.research_cache_telemetry import ResearchCacheTelemetry
from app.models.source import Source, SourceConfig, SourceHealth
from app.models.style_profile import StyleProfile, StyleSample
from app.models.takedown import TakedownRequest
from app.models.training_sample import TrainingSample
from app.models.user import Session, User

__all__ = [
    "AdminAuditLog",
    "AgencySeat",
    "AgendaCard",
    "AppPrompt",
    "AppPromptHistory",
    "AppSetting",
    "Article",
    "ArticleImage",
    "Conversation",
    "EmailLog",
    "EmailVerificationToken",
    "EventArticle",
    "EventCluster",
    "FailedJob",
    "Invoice",
    "Message",
    "PasswordResetToken",
    "Plan",
    "ProviderCallLog",
    "ResearchCacheTelemetry",
    "Session",
    "Source",
    "SourceConfig",
    "SourceHealth",
    "StyleProfile",
    "StyleSample",
    "Subscription",
    "TakedownRequest",
    "TrainingSample",
    "UsageEvent",
    "User",
    "WebhookEvent",
]
