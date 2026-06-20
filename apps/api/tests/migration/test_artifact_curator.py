"""Integration — Faz 3c/1b SFT artefakt-curator (testcontainers).

curate_artifacts eligible artefakt HEAD'lerini SFT örneği olarak yazar. Eligibility:
model_improvement_consent + review-buffer + effective_query + PII-temiz. Idempotent
(uq_training_samples_artifact). Head ≠ initial → head içeriği örneklenir.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.modules.sft.tasks.artifact_curator import curate_artifacts
from sqlalchemy import text

pytestmark = pytest.mark.integration


async def _user(db, *, consent: bool = True, revoked: bool = False) -> uuid.UUID:
    uid = uuid.uuid4()
    await db.execute(
        text("INSERT INTO users (id, email, password_hash) VALUES (:id, :e, 'x')"),
        {"id": uid, "e": f"u-{uid.hex[:8]}@test.local"},
    )
    if consent:
        await db.execute(
            text(
                "UPDATE users SET model_improvement_consent_at = NOW(), "
                "model_improvement_consent_revoked_at = :rev WHERE id = :id"
            ),
            {"id": uid, "rev": datetime.now(UTC) if revoked else None},
        )
    return uid


async def _cluster(db) -> uuid.UUID:
    cid = uuid.uuid4()
    await db.execute(
        text(
            "INSERT INTO research_clusters (id, cluster_key, cluster_type, canonical_name) "
            "VALUES (:id, :k, 'topic', 'Asgari Ücret')"
        ),
        {"id": cid, "k": f"topic:{cid.hex[:10]}"},
    )
    return cid


async def _seed_artifact(
    db,
    cid: uuid.UUID,
    uid: uuid.UUID,
    *,
    effective_query: str | None = "asgari ücret 2026 ne olacak",
    initial_content: str = "İlk taslak içerik [1].",
    sources: list | None = None,
    days_ago: int = 10,
    head_content: str | None = None,
    head_intent: str = "quick_shorter",
) -> tuple[uuid.UUID, int]:
    """Artefakt + initial revizyon (+ opsiyonel head revizyon). Dönüş: (artifact_id, head_seq)."""
    if sources is None:
        sources = [{"title": "Komisyon takvimi", "source_name": "ANKA"}]
    aid = uuid.uuid4()
    rev1 = uuid.uuid4()
    head_seq = 1
    created = datetime.now(UTC) - timedelta(days=days_ago)
    await db.execute(
        text(
            "INSERT INTO artifacts (id, cluster_id, user_id, artifact_type, head_revision_id, created_at) "
            "VALUES (:id, :c, :u, 'post', :head, :created)"
        ),
        {"id": aid, "c": cid, "u": uid, "head": rev1, "created": created},
    )
    await db.execute(
        text(
            "INSERT INTO artifact_revisions "
            "(id, artifact_id, revision_seq, revision_intent, content, sources_used, effective_query) "
            "VALUES (:id, :a, 1, 'initial', :content, :src, :eq)"
        ),
        {
            "id": rev1,
            "a": aid,
            "content": initial_content,
            "src": json.dumps(sources),
            "eq": effective_query,
        },
    )
    if head_content is not None:
        rev2 = uuid.uuid4()
        await db.execute(
            text(
                "INSERT INTO artifact_revisions "
                "(id, artifact_id, revision_seq, parent_revision_id, revision_intent, content, sources_used) "
                "VALUES (:id, :a, 2, :parent, :intent, :content, :src)"
            ),
            {
                "id": rev2,
                "a": aid,
                "parent": rev1,
                "intent": head_intent,
                "content": head_content,
                "src": json.dumps(sources),
            },
        )
        await db.execute(
            text("UPDATE artifacts SET head_revision_id = :h WHERE id = :a"), {"h": rev2, "a": aid}
        )
        head_seq = 2
    return aid, head_seq


async def _samples(db, aid):
    return (
        (
            await db.execute(
                text(
                    "SELECT artifact_revision_seq, task_type, sample_type, cluster_id, user_id, "
                    "input_payload, output_payload, quality_signals, sft_split "
                    "FROM training_samples WHERE artifact_id = :a ORDER BY artifact_revision_seq"
                ),
                {"a": aid},
            )
        )
        .mappings()
        .all()
    )


async def test_curate_creates_sft_sample(test_db_session):
    db = test_db_session
    uid = await _user(db)
    cid = await _cluster(db)
    aid, head_seq = await _seed_artifact(db, cid, uid, head_content="Kısa içerik [1].")

    summary = await curate_artifacts(db, daily_max=100, prompt_version="2.0.0")
    assert summary["ingested_sft"] == 1
    assert summary["scanned"] == 1

    rows = await _samples(db, aid)
    assert len(rows) == 1
    s = rows[0]
    assert s["artifact_revision_seq"] == head_seq == 2  # HEAD örneklenir, initial değil
    assert s["task_type"] == "research_answer"  # REUSE
    assert s["sample_type"] == "sft"
    assert str(s["cluster_id"]) == str(cid)
    assert str(s["user_id"]) == str(uid)
    assert s["output_payload"]["content"] == "Kısa içerik [1]."  # head içeriği
    assert "asgari ücret" in s["input_payload"]["messages"][0]["content"]  # effective_query
    assert s["quality_signals"]["source"] == "artifact"
    assert s["quality_signals"]["head_intent"] == "quick_shorter"
    assert s["sft_split"] in {"train", "val", "test"}


async def test_idempotent(test_db_session):
    db = test_db_session
    uid = await _user(db)
    cid = await _cluster(db)
    aid, _ = await _seed_artifact(db, cid, uid)

    s1 = await curate_artifacts(db, daily_max=100, prompt_version="2.0.0")
    assert s1["ingested_sft"] == 1
    s2 = await curate_artifacts(db, daily_max=100, prompt_version="2.0.0")
    assert s2["ingested_sft"] == 0  # NOT EXISTS → 2. run boş
    assert s2["scanned"] == 0
    assert len(await _samples(db, aid)) == 1


async def test_no_consent_skipped(test_db_session):
    db = test_db_session
    uid = await _user(db, consent=False)
    cid = await _cluster(db)
    aid, _ = await _seed_artifact(db, cid, uid)

    summary = await curate_artifacts(db, daily_max=100, prompt_version="2.0.0")
    assert summary["scanned"] == 0  # consent yok → aday değil
    assert len(await _samples(db, aid)) == 0


async def test_revoked_consent_skipped(test_db_session):
    db = test_db_session
    uid = await _user(db, consent=True, revoked=True)
    cid = await _cluster(db)
    aid, _ = await _seed_artifact(db, cid, uid)

    summary = await curate_artifacts(db, daily_max=100, prompt_version="2.0.0")
    assert summary["scanned"] == 0
    assert len(await _samples(db, aid)) == 0


async def test_review_buffer_skipped(test_db_session):
    db = test_db_session
    uid = await _user(db)
    cid = await _cluster(db)
    # 1 gün önce oluşturulmuş → 7-gün buffer içinde → aday değil
    aid, _ = await _seed_artifact(db, cid, uid, days_ago=1)

    summary = await curate_artifacts(db, daily_max=100, prompt_version="2.0.0")
    assert summary["scanned"] == 0
    assert len(await _samples(db, aid)) == 0


async def test_no_effective_query_skipped(test_db_session):
    db = test_db_session
    uid = await _user(db)
    cid = await _cluster(db)
    aid, _ = await _seed_artifact(db, cid, uid, effective_query=None)

    summary = await curate_artifacts(db, daily_max=100, prompt_version="2.0.0")
    assert summary["scanned"] == 1
    assert summary["skipped_no_query"] == 1
    assert summary["ingested_sft"] == 0
    assert len(await _samples(db, aid)) == 0


async def test_pii_skipped(test_db_session):
    db = test_db_session
    uid = await _user(db)
    cid = await _cluster(db)
    # head içeriğinde email → PII secondary scan hit
    aid, _ = await _seed_artifact(
        db, cid, uid, head_content="İletişim: gizli@example.com üzerinden [1]."
    )

    summary = await curate_artifacts(db, daily_max=100, prompt_version="2.0.0")
    assert summary["scanned"] == 1
    assert summary["skipped_pii"] == 1
    assert summary["ingested_sft"] == 0
    assert len(await _samples(db, aid)) == 0


async def test_manual_edit_creates_dpo_pair(test_db_session):
    """Manuel-edit head (freetext) + anlamlı değişim → sft + dpo_chosen + dpo_rejected."""
    db = test_db_session
    uid = await _user(db)
    cid = await _cluster(db)
    aid, head_seq = await _seed_artifact(
        db,
        cid,
        uid,
        initial_content="LLM'in ürettiği uzun ve hatalı ilk taslak, gereksiz detaylarla dolu [1].",
        head_content="Kullanıcının elle yazdığı net ve doğru sürüm [1].",
        head_intent="freetext",
    )

    summary = await curate_artifacts(db, daily_max=100, prompt_version="2.0.0")
    assert summary["ingested_sft"] == 1
    assert summary["ingested_dpo_chosen"] == 1
    assert summary["ingested_dpo_rejected"] == 1

    rows = await _samples(db, aid)
    by_type = {(r["artifact_revision_seq"], r["sample_type"]): r for r in rows}
    assert (head_seq, "sft") in by_type  # head = SFT
    assert (head_seq, "dpo_chosen") in by_type  # head = chosen
    assert (1, "dpo_rejected") in by_type  # parent (initial, seq=1) = rejected
    # chosen = head içeriği, rejected = parent içeriği
    assert by_type[(head_seq, "dpo_chosen")]["output_payload"]["content"].startswith("Kullanıcının")
    assert by_type[(1, "dpo_rejected")]["output_payload"]["content"].startswith("LLM'in")
    # chosen ve rejected aynı input'u paylaşır (DPO contract)
    assert (
        by_type[(head_seq, "dpo_chosen")]["input_payload"]
        == by_type[(1, "dpo_rejected")]["input_payload"]
    )
    # pair link
    assert by_type[(1, "dpo_rejected")]["quality_signals"]["dpo_pair_with"] == str(aid)


async def test_dpo_retried_when_sft_exists_but_dpo_missing(test_db_session):
    """SFT var ama DPO yok (transient fail simülasyonu) → genişletilmiş NOT EXISTS
    artefaktı yeniden dahil eder; DPO pair oluşur, SFT ON CONFLICT no-op."""
    db = test_db_session
    uid = await _user(db)
    cid = await _cluster(db)
    aid, _ = await _seed_artifact(
        db,
        cid,
        uid,
        initial_content="LLM'in uzun hatalı ilk taslağı gereksiz detaylarla [1].",
        head_content="Kullanıcının net elle düzeltilmiş sürümü [1].",
        head_intent="freetext",
    )
    s1 = await curate_artifacts(db, daily_max=100, prompt_version="2.0.0")
    assert s1["ingested_dpo_chosen"] == 1
    # DPO satırlarını sil (transient kayıp simülasyonu), SFT kalsın
    await db.execute(
        text(
            "DELETE FROM training_samples WHERE artifact_id=:a "
            "AND sample_type IN ('dpo_chosen','dpo_rejected')"
        ),
        {"a": aid},
    )
    s2 = await curate_artifacts(db, daily_max=100, prompt_version="2.0.0")
    assert s2["scanned"] == 1  # SFT var ama dpo_chosen yok → yeniden aday
    assert s2["ingested_dpo_chosen"] == 1
    assert s2["ingested_dpo_rejected"] == 1
    assert s2["skipped_duplicate"] == 1  # SFT ON CONFLICT no-op
    assert {r["sample_type"] for r in await _samples(db, aid)} == {
        "sft",
        "dpo_chosen",
        "dpo_rejected",
    }


async def test_dpo_parent_is_immediate_not_initial(test_db_session):
    """Derin zincir (head=seq3 freetext, parent=seq2 quick_shorter): DPO rejected =
    immediate parent (seq2), initial (seq1) DEĞİL."""
    db = test_db_session
    uid = await _user(db)
    cid = await _cluster(db)
    aid = uuid.uuid4()
    r1, r2, r3 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    created = datetime.now(UTC) - timedelta(days=10)
    await db.execute(
        text(
            "INSERT INTO artifacts (id, cluster_id, user_id, artifact_type, head_revision_id, created_at) "
            "VALUES (:i,:c,:u,'post',:h,:cr)"
        ),
        {"i": aid, "c": cid, "u": uid, "h": r3, "cr": created},
    )
    await db.execute(
        text(
            "INSERT INTO artifact_revisions (id, artifact_id, revision_seq, revision_intent, content, effective_query) "
            "VALUES (:i,:a,1,'initial',:ct,:eq)"
        ),
        {"i": r1, "a": aid, "ct": "seq1 initial taslak [1]", "eq": "asgari ücret 2026 ne olacak"},
    )
    await db.execute(
        text(
            "INSERT INTO artifact_revisions (id, artifact_id, revision_seq, parent_revision_id, revision_intent, content) "
            "VALUES (:i,:a,2,:p,'quick_shorter',:ct)"
        ),
        {"i": r2, "a": aid, "p": r1, "ct": "seq2 kısa LLM sürümü hâlâ gereksiz detaylı [1]"},
    )
    await db.execute(
        text(
            "INSERT INTO artifact_revisions (id, artifact_id, revision_seq, parent_revision_id, revision_intent, content) "
            "VALUES (:i,:a,3,:p,'freetext',:ct)"
        ),
        {"i": r3, "a": aid, "p": r2, "ct": "seq3 kullanıcının elle yazdığı net final [1]"},
    )

    summary = await curate_artifacts(db, daily_max=100, prompt_version="2.0.0")
    assert summary["ingested_dpo_rejected"] == 1
    rejected = [r for r in await _samples(db, aid) if r["sample_type"] == "dpo_rejected"]
    assert len(rejected) == 1
    assert rejected[0]["artifact_revision_seq"] == 2  # immediate parent (seq2), initial DEĞİL
    assert rejected[0]["output_payload"]["content"].startswith("seq2")


async def test_quick_action_head_no_dpo(test_db_session):
    """Quick-action head (stilistik) → SADECE sft, DPO YOK."""
    db = test_db_session
    uid = await _user(db)
    cid = await _cluster(db)
    aid, _ = await _seed_artifact(
        db, cid, uid, head_content="Kısaltılmış sürüm [1].", head_intent="quick_shorter"
    )

    summary = await curate_artifacts(db, daily_max=100, prompt_version="2.0.0")
    assert summary["ingested_sft"] == 1
    assert summary["ingested_dpo_chosen"] == 0
    assert summary["ingested_dpo_rejected"] == 0
    rows = await _samples(db, aid)
    assert {r["sample_type"] for r in rows} == {"sft"}


async def test_minor_edit_no_dpo(test_db_session):
    """Manuel-edit ama küçük tweak (similarity > 0.95) → parent 'rejected' DEĞİL, DPO yok."""
    db = test_db_session
    uid = await _user(db)
    cid = await _cluster(db)
    base_txt = "Asgari ücret komisyonu kasım ortasında toplanmak üzere takvim açıkladı [1]."
    await _seed_artifact(
        db,
        cid,
        uid,
        initial_content=base_txt,
        head_content=base_txt + " ",  # neredeyse aynı (typo/whitespace düzeyi)
        head_intent="edit",
    )

    summary = await curate_artifacts(db, daily_max=100, prompt_version="2.0.0")
    assert summary["ingested_sft"] == 1
    assert summary["ingested_dpo_chosen"] == 0  # değişim < %5 → DPO yok
    assert summary["ingested_dpo_rejected"] == 0


async def test_terminal_manual_edit_not_rescanned_second_run(test_db_session):
    """#5 starvation fix: DPO-terminal manuel-edit (eşik-altı değişim →
    dpo_applicable=false) İKİNCİ run'da YENİDEN TARANMAZ.

    Önceki OR-dalı yalnız dpo_chosen-yokluğuna bakıyordu → terminal head'ler
    (parent-yok/eşik-altı/PII) her gece sonsuza dek yeniden seçilip daily_max
    slot tüketiyor + boşa PII-rescan yapıyordu (NER-backfill sınıfı döngü)."""
    db = test_db_session
    uid = await _user(db)
    cid = await _cluster(db)
    base_txt = "Asgari ücret komisyonu kasım ortasında toplanmak üzere takvim açıkladı [1]."
    await _seed_artifact(
        db,
        cid,
        uid,
        initial_content=base_txt,
        head_content=base_txt + " ",  # eşik-altı (typo/whitespace → terminal)
        head_intent="edit",
    )
    s1 = await curate_artifacts(db, daily_max=100, prompt_version="2.0.0")
    assert s1["ingested_sft"] == 1
    assert s1["ingested_dpo_chosen"] == 0  # terminal → dpo_applicable=false
    # İkinci run: SFT zaten var + dpo_applicable=false → YENİDEN ADAY DEĞİL.
    s2 = await curate_artifacts(db, daily_max=100, prompt_version="2.0.0")
    assert s2["scanned"] == 0  # starvation yok (eski kodda 1 olurdu)


async def test_multiple_artifacts_one_run(test_db_session):
    """Tek run'da birden çok eligible artefakt → hepsi ingest (ON CONFLICT atomik;
    bir satır diğerlerini zehirlemez — begin_nested-poison regresyon guard'ı)."""
    db = test_db_session
    uid = await _user(db)
    cid = await _cluster(db)
    aids = []
    for i in range(3):
        aid, _ = await _seed_artifact(db, cid, uid, effective_query=f"sorgu {i} ne olacak")
        aids.append(aid)

    summary = await curate_artifacts(db, daily_max=100, prompt_version="2.0.0")
    assert summary["ingested_sft"] == 3
    assert summary["errors"] == 0
    total = (
        await db.execute(
            text("SELECT count(*) FROM training_samples WHERE artifact_id = ANY(:ids)"),
            {"ids": aids},
        )
    ).scalar()
    assert total == 3


async def test_single_revision_artifact_curated(test_db_session):
    """Tek revizyonlu artefakt (head=initial, seq=1) de örneklenir."""
    db = test_db_session
    uid = await _user(db)
    cid = await _cluster(db)
    aid, _ = await _seed_artifact(db, cid, uid, head_content=None)  # yalnız initial

    summary = await curate_artifacts(db, daily_max=100, prompt_version="2.0.0")
    assert summary["ingested_sft"] == 1
    rows = await _samples(db, aid)
    assert rows[0]["artifact_revision_seq"] == 1
    assert rows[0]["output_payload"]["content"] == "İlk taslak içerik [1]."
