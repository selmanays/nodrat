"""Küme abonelik + artefakt ORM modelleri — kayıt + metadata sanity (Faz 0).

DB-bağımsız. alembic check'in görmesi için modeller `app/models/__init__.py`'ye
kayıtlı + Base.metadata'da olmalı (trend modellerindeki __init__ omission
regresyonunu önler). Tablo varlığı/constraint runtime davranışı integration
testte (tests/migration/test_kume_subscription_artifacts.py).
"""

from __future__ import annotations

from app.core.db import Base

_TABLES = ("user_cluster_subscriptions", "artifacts", "artifact_revisions")


def test_kume_models_importable_from_app_models():
    from app.models import Artifact, ArtifactRevision, UserClusterSubscription

    assert UserClusterSubscription.__tablename__ == "user_cluster_subscriptions"
    assert Artifact.__tablename__ == "artifacts"
    assert ArtifactRevision.__tablename__ == "artifact_revisions"


def test_kume_models_in_all():
    import app.models as m

    for name in ("UserClusterSubscription", "Artifact", "ArtifactRevision"):
        assert name in m.__all__, f"{name} app.models.__all__ içinde değil"


def test_kume_tables_in_metadata():
    """env.py `from app.models import *` → Base.metadata; alembic bu tabloları görür."""
    for tbl in _TABLES:
        assert tbl in Base.metadata.tables, f"{tbl} Base.metadata'da yok"


def test_subscription_live_partial_unique_index():
    """Bir kullanıcı bir küme için en fazla TEK canlı abonelik (unsubscribed IS NULL)."""
    from app.models import UserClusterSubscription

    idx = {i.name: i for i in UserClusterSubscription.__table__.indexes}
    assert "uq_user_cluster_sub_live" in idx
    assert idx["uq_user_cluster_sub_live"].unique is True
    assert [c.name for c in idx["uq_user_cluster_sub_live"].columns] == [
        "user_id",
        "cluster_id",
    ]


def test_subscription_fk_ondelete():
    """user_id → CASCADE (KVKK), cluster_id → RESTRICT (global düğüm korunur)."""
    from app.models import UserClusterSubscription

    user_fk = next(iter(UserClusterSubscription.__table__.c.user_id.foreign_keys))
    cluster_fk = next(iter(UserClusterSubscription.__table__.c.cluster_id.foreign_keys))
    assert user_fk.ondelete == "CASCADE"
    assert cluster_fk.ondelete == "RESTRICT"


def test_artifact_revision_seq_unique_constraint():
    from app.models import ArtifactRevision

    uniques = {
        c.name
        for c in ArtifactRevision.__table__.constraints
        if c.__class__.__name__ == "UniqueConstraint"
    }
    assert "uq_artifact_revision_seq" in uniques
    uq = next(
        c
        for c in ArtifactRevision.__table__.constraints
        if getattr(c, "name", None) == "uq_artifact_revision_seq"
    )
    assert [col.name for col in uq.columns] == ["artifact_id", "revision_seq"]


def test_soft_refs_have_no_foreign_key():
    """Soft ref deseni (history-safety): hard FK YOK."""
    from app.models import Artifact, ResearchCluster

    # küme → kanonik varlık anchor (canonical_entities raw-SQL-only)
    assert len(ResearchCluster.__table__.c.canonical_entity_id.foreign_keys) == 0
    # artefakt → en güncel revizyon işaretçisi (circular-FK önlenir)
    assert len(Artifact.__table__.c.head_revision_id.foreign_keys) == 0


def test_artifact_origin_message_fk_set_null():
    """Legacy mesaj köprüsü → SET NULL (mesaj silinse de artefakt kalır)."""
    from app.models import Artifact

    fk = next(iter(Artifact.__table__.c.origin_message_id.foreign_keys))
    assert fk.ondelete == "SET NULL"
