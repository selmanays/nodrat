"""Celery: entity canonicalization builder (Faz 1, #1540).

`entities` tablosundaki distinct (entity_normalized, entity_type) kümesini tarar,
deterministik seed + unvan-soyma ile (canonicalization.resolve_canonical) canonical
eşleşmeleri bulur, `canonical_entities` + `entity_aliases` tablolarına idempotent
upsert eder. `entities` tablosu YALNIZ okunur (dokunulmaz). Eşleşmeyen entity ham
kalır (trend read'de kendi entity_normalized'ıyla gruplanır).

Periyodik beat + admin manuel-trigger (maintenance_tracker). ner_queue → worker_ner.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text as sa_text

from app.modules.entities.canonicalization import (
    SUBSET_TYPES,
    build_subset_groups,
    resolve_canonical,
)
from app.shared.workers.db_session import _get_session_factory, _run_async
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


async def _build_canonical_async(*, min_freq: int = 2, dry_run: bool = False) -> dict[str, Any]:
    """entities'i tara → seed/unvan-soyma eşleşmelerini alias tablosuna yaz."""
    factory = _get_session_factory()
    summary: dict[str, Any] = {
        "status": "unknown",
        "scanned": 0,
        "matched": 0,
        "canonical_upserts": 0,
        "alias_upserts": 0,
        "dry_run": dry_run,
    }

    async with factory() as db:
        rows = (
            (
                await db.execute(
                    sa_text(
                        """
                        SELECT e.entity_normalized AS norm, e.entity_type AS etype,
                               COUNT(DISTINCT e.article_id) AS freq
                        FROM entities e
                        WHERE e.entity_type IN ('person','org','place','event')
                        GROUP BY e.entity_normalized, e.entity_type
                        HAVING COUNT(DISTINCT e.article_id) >= :min_freq
                        """
                    ),
                    {"min_freq": min_freq},
                )
            )
            .mappings()
            .all()
        )
        summary["scanned"] = len(rows)

        canon_cache: dict[tuple[str, str], str] = {}
        seed_matched: set[tuple[str, str]] = set()
        matched = 0
        n_canon = 0
        n_alias = 0
        for r in rows:
            match = resolve_canonical(r["norm"], r["etype"])
            if match is None:
                continue
            matched += 1
            seed_matched.add((r["norm"], r["etype"]))
            if dry_run:
                continue

            key = (match.canonical_normalized, match.entity_type)
            cid = canon_cache.get(key)
            if cid is None:
                cid = (
                    await db.execute(
                        sa_text(
                            """
                            INSERT INTO canonical_entities
                                (canonical_name, entity_type, canonical_normalized, source)
                            VALUES (:name, :etype, :cnorm, 'seed')
                            ON CONFLICT (canonical_normalized, entity_type)
                            DO UPDATE SET updated_at = now()
                            RETURNING id
                            """
                        ),
                        {
                            "name": match.canonical_name,
                            "etype": match.entity_type,
                            "cnorm": match.canonical_normalized,
                        },
                    )
                ).scalar()
                canon_cache[key] = str(cid)
                n_canon += 1

            await db.execute(
                sa_text(
                    """
                    INSERT INTO entity_aliases
                        (alias_normalized, entity_type, canonical_id, confidence, source)
                    VALUES (:alias, :etype, :cid, 1.000, :src)
                    ON CONFLICT (alias_normalized, entity_type)
                    DO UPDATE SET canonical_id = EXCLUDED.canonical_id,
                                  source = EXCLUDED.source
                    WHERE entity_aliases.source NOT IN ('admin', 'wikidata')
                    """
                ),
                {"alias": r["norm"], "etype": r["etype"], "cid": cid, "src": match.source},
            )
            n_alias += 1

        # ---- #1548: token-altküme birleştirmesi (event) — seed dışı varyantlar -----
        # "2026 dünya kupası"/"fifa dünya kupası" → "2026 fifa dünya kupası" (tek
        # minimal üst-küme). canonical_name = en sık üyenin yüzey biçimi (mode entity_text).
        subset_total = 0
        for etype in SUBSET_TYPES:
            items = [
                (r["norm"], int(r["freq"]))
                for r in rows
                if r["etype"] == etype and (r["norm"], r["etype"]) not in seed_matched
            ]
            groups = build_subset_groups(items)  # {member_norm: canonical_norm}
            subset_total += len(set(groups.values()))
            if dry_run:
                matched += len(groups)
                continue
            # canonical_norm → canonical_id (yüzey biçimi mode entity_text)
            for canonical_norm in set(groups.values()):
                key = (canonical_norm, etype)
                cid = canon_cache.get(key)
                if cid is None:
                    display = (
                        await db.execute(
                            sa_text(
                                "SELECT mode() WITHIN GROUP (ORDER BY entity_text) "
                                "FROM entities WHERE entity_normalized = :n AND entity_type = :t"
                            ),
                            {"n": canonical_norm, "t": etype},
                        )
                    ).scalar() or canonical_norm
                    cid = (
                        await db.execute(
                            sa_text(
                                """
                                INSERT INTO canonical_entities
                                    (canonical_name, entity_type, canonical_normalized, source)
                                VALUES (:name, :etype, :cnorm, 'token_subset')
                                ON CONFLICT (canonical_normalized, entity_type)
                                DO UPDATE SET updated_at = now()
                                RETURNING id
                                """
                            ),
                            {"name": display, "etype": etype, "cnorm": canonical_norm},
                        )
                    ).scalar()
                    canon_cache[key] = str(cid)
                    n_canon += 1
            for member_norm, canonical_norm in groups.items():
                cid = canon_cache[(canonical_norm, etype)]
                await db.execute(
                    sa_text(
                        """
                        INSERT INTO entity_aliases
                            (alias_normalized, entity_type, canonical_id, confidence, source)
                        VALUES (:alias, :etype, :cid, 0.900, 'token_subset')
                        ON CONFLICT (alias_normalized, entity_type)
                        DO UPDATE SET canonical_id = EXCLUDED.canonical_id,
                                      source = EXCLUDED.source
                        WHERE entity_aliases.source <> 'admin'
                        """
                    ),
                    {"alias": member_norm, "etype": etype, "cid": cid},
                )
                n_alias += 1
            matched += len(groups)
        summary["subset_canonical"] = subset_total

        summary["matched"] = matched
        if not dry_run:
            # alias_count denormalize
            await db.execute(
                sa_text(
                    """
                    UPDATE canonical_entities c
                    SET alias_count = (
                        SELECT count(*) FROM entity_aliases a WHERE a.canonical_id = c.id
                    )
                    """
                )
            )
            await db.commit()
        summary["canonical_upserts"] = n_canon
        summary["alias_upserts"] = n_alias
        summary["status"] = "dry_run" if dry_run else "built"
        logger.info(
            "canonical build: scanned=%s matched=%s canon=%s alias=%s dry=%s",
            summary["scanned"],
            matched,
            n_canon,
            n_alias,
            dry_run,
        )
        return summary


@celery_app.task(name="tasks.entities.build_canonical", bind=True)
def build_canonical(  # type: ignore[no-untyped-def]
    self,
    min_freq: int = 2,
    dry_run: bool = False,
) -> dict:
    """entities → canonical/alias builder (deterministik seed + unvan-soyma)."""
    return _run_async(_build_canonical_async(min_freq=min_freq, dry_run=dry_run))
