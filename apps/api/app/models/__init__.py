"""SQLAlchemy modeller — Alembic autogenerate için tek noktadan import.

Yeni model eklediğinde buraya ekle ki Alembic schema'da görsün.
"""

from app.models.job import AdminAuditLog, FailedJob  # T8-7b: cross-cutting exception (flat kalır)
from app.modules.accounts.models import (  # T8: email relocated  # T8-21: User+Session relocated
    EmailLog,
    EmailVerificationToken,
    PasswordResetToken,
    Session,
    User,
)
from app.modules.agenda.models import AgendaCard  # T8-10: moved 2026-05-28
from app.modules.articles.models import Article, ArticleImage
from app.modules.billing.models import (
    AgencySeat,
    Invoice,
    Plan,
    Subscription,
    UsageEvent,  # T8-17: moved 2026-05-28 (#800 S1B post-cleanup)
    WebhookEvent,
)
from app.modules.clusters.models import EventArticle, EventCluster  # T8-8: moved 2026-05-28
from app.modules.conversations.models import Conversation, Message
from app.modules.generations.models import (  # T8-9/T8-15: moved 2026-05-28
    Artifact,  # Faz 0: küme-merkezli abonelik vizyonu
    ArtifactCluster,  # #1762 Faz 2: çoklu-küme üyeliği
    ArtifactRevision,
    MessageCluster,
    ResearchCacheTelemetry,
    ResearchCluster,
    UserClusterSubscription,
)
from app.modules.legal.models import TakedownRequest
from app.modules.ops.models import ProviderCallLog  # T8-7a: moved 2026-05-30
from app.modules.prompts_admin.models import AppPrompt, AppPromptHistory  # T8-2: moved 2026-05-26
from app.modules.rag.models import EvalRun
from app.modules.settings_admin.models import (
    AppSetting,  # T8-1 v2: moved 2026-05-26 (T8-PRE-1 v2 koruması altında)
)
from app.modules.sft.models import TrainingSample
from app.modules.sources.models import Source, SourceConfig, SourceHealth
from app.modules.style_profiles.models import StyleProfile, StyleSample
from app.modules.trends.models import (  # #1505 Faz 2 PR-2a: trend persistence
    Topic,
    TopicCluster,
    TrendSignal,
    TrendSnapshot,
)

__all__ = [
    "AdminAuditLog",
    "AgencySeat",
    "AgendaCard",
    "AppPrompt",
    "AppPromptHistory",
    "AppSetting",
    "Article",
    "ArticleImage",
    "Artifact",
    "ArtifactCluster",
    "ArtifactRevision",
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
    "Topic",
    "TopicCluster",
    "TrainingSample",
    "TrendSignal",
    "TrendSnapshot",
    "UsageEvent",
    "User",
    "UserClusterSubscription",
    "WebhookEvent",
]
