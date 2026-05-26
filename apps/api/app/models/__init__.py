"""SQLAlchemy modeller — Alembic autogenerate için tek noktadan import.

Yeni model eklediğinde buraya ekle ki Alembic schema'da görsün.
"""

from app.models.agenda import AgendaCard
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
from app.models.research_cluster import MessageCluster, ResearchCluster
from app.models.source import Source, SourceConfig, SourceHealth
from app.models.style_profile import StyleProfile, StyleSample
from app.models.user import Session, User
from app.modules.legal.models import TakedownRequest
from app.modules.prompts_admin.models import AppPrompt, AppPromptHistory  # T8-2: moved 2026-05-26
from app.modules.rag.models import EvalRun
from app.modules.settings_admin.models import (
    AppSetting,  # T8-1 v2: moved 2026-05-26 (T8-PRE-1 v2 koruması altında)
)
from app.modules.sft.models import TrainingSample

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
    "EvalRun",
    "EventArticle",
    "EventCluster",
    "FailedJob",
    "Invoice",
    "Message",
    "MessageCluster",
    "PasswordResetToken",
    "Plan",
    "ProviderCallLog",
    "ResearchCacheTelemetry",
    "ResearchCluster",
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
