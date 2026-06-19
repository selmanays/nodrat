"""training_samples küme/artefakt şekli — schema sanity (Faz 1a).

DB-bağımsız. Additive kolonlar (artifact_id/artifact_revision_seq/cluster_id) +
idempotency index ORM'de mevcut + alembic check parity. Runtime davranışı
integration testte (tests/migration/test_training_samples_kume_shape.py).
"""

from __future__ import annotations


def test_new_columns_present():
    from app.models import TrainingSample

    cols = TrainingSample.__table__.c
    assert "artifact_id" in cols
    assert "artifact_revision_seq" in cols
    assert "cluster_id" in cols
    # additive → hepsi nullable (historical satırlar NULL)
    assert cols["artifact_id"].nullable is True
    assert cols["artifact_revision_seq"].nullable is True
    assert cols["cluster_id"].nullable is True


def test_artifact_fk_set_null():
    """artifact_id → SET NULL: artefakt silinse de training snapshot korunur."""
    from app.models import TrainingSample

    fk = next(iter(TrainingSample.__table__.c.artifact_id.foreign_keys))
    assert fk.ondelete == "SET NULL"
    assert fk.column.table.name == "artifacts"


def test_cluster_id_is_soft_ref_no_fk():
    """cluster_id hard FK taşımaz (history-safety, immutable snapshot)."""
    from app.models import TrainingSample

    assert len(TrainingSample.__table__.c.cluster_id.foreign_keys) == 0


def test_artifact_idempotency_partial_unique_index():
    from app.models import TrainingSample

    idx = {i.name: i for i in TrainingSample.__table__.indexes}
    assert "uq_training_samples_artifact" in idx
    target = idx["uq_training_samples_artifact"]
    assert target.unique is True
    assert [c.name for c in target.columns] == [
        "artifact_id",
        "artifact_revision_seq",
        "task_type",
        "sample_type",
    ]
    # partial (WHERE artifact_id IS NOT NULL) — NULL artefaktlı eski satırları etkilemez
    assert target.dialect_options["postgresql"]["where"] is not None


def test_cluster_index_present():
    from app.models import TrainingSample

    idx = {i.name: i for i in TrainingSample.__table__.indexes}
    assert "idx_training_samples_cluster" in idx


def test_message_path_unchanged():
    """Mevcut message yolu (Faz 1a'da DEĞİŞMEZ) korunur."""
    from app.models import TrainingSample

    cols = TrainingSample.__table__.c
    assert "message_id" in cols
    msg_fk = next(iter(cols["message_id"].foreign_keys))
    assert msg_fk.ondelete == "CASCADE"  # KVKK — değişmedi
    idx = {i.name for i in TrainingSample.__table__.indexes}
    assert "uq_training_samples_message_task_sample" in idx
