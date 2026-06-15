"""Trend ORM modelleri — kayıt + metadata sanity (Faz 2 PR-2a, #1505).

DB-bağımsız. alembic check'in görmesi için modeller `app/models/__init__.py`'ye
kayıtlı + Base.metadata'da olmalı (PR-8b-1'deki __init__ omission regresyonunu
önler). Tablo varlığı/constraint integration testte (test_trend_tables.py).
"""

from __future__ import annotations

from app.core.db import Base


def test_trend_models_importable_from_app_models():
    from app.models import Topic, TopicCluster, TrendSignal, TrendSnapshot

    assert Topic.__tablename__ == "topics"
    assert TopicCluster.__tablename__ == "topic_clusters"
    assert TrendSnapshot.__tablename__ == "trend_snapshots"
    assert TrendSignal.__tablename__ == "trend_signals"


def test_trend_models_in_all():
    import app.models as m

    for name in ("Topic", "TopicCluster", "TrendSnapshot", "TrendSignal"):
        assert name in m.__all__, f"{name} app.models.__all__ içinde değil"


def test_trend_tables_in_metadata():
    """env.py `from app.models import *` → Base.metadata; alembic bu tabloları görür."""
    for tbl in ("topics", "topic_clusters", "trend_snapshots", "trend_signals"):
        assert tbl in Base.metadata.tables, f"{tbl} Base.metadata'da yok"


def test_snapshot_idempotency_unique_constraint():
    from app.models import TrendSnapshot

    uniques = {
        c.name
        for c in TrendSnapshot.__table__.constraints
        if c.__class__.__name__ == "UniqueConstraint"
    }
    assert "uq_trend_snapshots_subject_bucket_algo" in uniques
    # idempotency key kolonları
    uq = next(
        c
        for c in TrendSnapshot.__table__.constraints
        if getattr(c, "name", None) == "uq_trend_snapshots_subject_bucket_algo"
    )
    assert [col.name for col in uq.columns] == [
        "subject_type",
        "subject_id",
        "bucket_start",
        "algo_version",
    ]


def test_topics_centroid_ivfflat_index_declared():
    """centroid_embedding ivfflat index ORM'de (alembic check parity)."""
    from app.models import Topic

    idx = {i.name: i for i in Topic.__table__.indexes}
    assert "idx_topics_centroid" in idx
    assert idx["idx_topics_centroid"].dialect_options["postgresql"]["using"] == "ivfflat"


def test_subject_id_has_no_foreign_key():
    """trend_snapshots.subject_id ve topic_clusters.event_cluster_id hard FK YOK."""
    from app.models import TopicCluster, TrendSnapshot

    assert len(TrendSnapshot.__table__.c.subject_id.foreign_keys) == 0
    assert len(TopicCluster.__table__.c.event_cluster_id.foreign_keys) == 0
    # topic_id ise gerçek FK
    assert len(TopicCluster.__table__.c.topic_id.foreign_keys) == 1
