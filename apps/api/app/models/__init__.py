"""SQLAlchemy modeller — Alembic autogenerate için tek noktadan import.

Yeni model eklediğinde buraya ekle ki Alembic schema'da görsün.
"""

from app.models.article import Article, ArticleImage
from app.models.conversation import Conversation, Message
from app.models.email import EmailLog, EmailVerificationToken, PasswordResetToken
from app.models.job import AdminAuditLog, FailedJob
from app.models.provider_log import ProviderCallLog
from app.models.user import Session, User
from app.modules.agenda.models import AgendaCard  # T8-10: moved 2026-05-28
from app.modules.billing.models import (
    AgencySeat,
    Invoice,
    Plan,
    Subscription,
    UsageEvent,  # T8-17: moved 2026-05-28 (#800 S1B post-cleanup)
    WebhookEvent,
)
from app.modules.clusters.models import EventArticle, EventCluster  # T8-8: moved 2026-05-28
from app.modules.generations.models import (  # T8-9/T8-15: moved 2026-05-28
    MessageCluster,
    ResearchCacheTelemetry,
    ResearchCluster,
)
from app.modules.legal.models import TakedownRequest
from app.modules.prompts_admin.models import AppPrompt, AppPromptHistory  # T8-2: moved 2026-05-26
from app.modules.rag.models import EvalRun
from app.modules.settings_admin.models import (
    AppSetting,  # T8-1 v2: moved 2026-05-26 (T8-PRE-1 v2 koruması altında)
)
from app.modules.sft.models import TrainingSample
from app.modules.sources.models import Source, SourceConfig, SourceHealth
from app.modules.style_profiles.models import StyleProfile, StyleSample

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
