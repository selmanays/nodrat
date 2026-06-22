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


async def _wikidata_owner_map(db: Any, pairs: set[tuple[str, str]]) -> dict[tuple[str, str], str]:
    """(canonical_normalized, entity_type) → onu sahiplenen wikidata/admin canonical id.

    #1725/#1726 — build_canonical'ın wikidata otoritesine DEFER etmesi için: bir norm
    zaten bir wikidata/admin canonical'ın canonical'ı VEYA alias'ıysa, builder o norm için
    YENİ (daha düşük otoriteli) seed/token_subset canonical AÇMAZ, mevcut W'ye yönlendirir.
    Aksi halde builder her turda enrich_wikidata merge'ini geri bozar (salınım → ~30dk/6h
    görünür dup; teşhis: 15-16 Haziran + YÖK/AK Parti). Authority: admin > wikidata > seed."""
    if not pairs:
        return {}
    by_type: dict[str, list[str]] = {}
    for norm, et in pairs:
        by_type.setdefault(et, []).append(norm)
    out: dict[tuple[str, str], str] = {}
    for et, norms in by_type.items():
        owner_rows = (
            (
                await db.execute(
                    sa_text(
                        """
                        SELECT canonical_normalized AS norm, id::text AS cid
                        FROM canonical_entities
                        WHERE source IN ('wikidata', 'admin') AND entity_type = :t
                          AND canonical_normalized = ANY(:norms)
                        UNION
                        SELECT a.alias_normalized AS norm, a.canonical_id::text AS cid
                        FROM entity_aliases a
                        JOIN canonical_entities c
                          ON c.id = a.canonical_id AND c.source IN ('wikidata', 'admin')
                        WHERE a.entity_type = :t AND a.alias_normalized = ANY(:norms)
                        """
                    ),
                    {"t": et, "norms": norms},
                )
            )
            .mappings()
            .all()
        )
        for row in owner_rows:
            out[(row["norm"], et)] = row["cid"]
    return out


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
        # seed/unvan-soyma eşleşmelerini topla (owner-lookup batch; seed_matched dry-run'da da dolar)
        seed_hits: list[tuple[str, str, Any]] = []
        for r in rows:
            match = resolve_canonical(r["norm"], r["etype"])
            if match is None:
                continue
            matched += 1
            seed_matched.add((r["norm"], r["etype"]))
            seed_hits.append((r["norm"], r["etype"], match))

        if not dry_run:
            # #1726: seed canonical'ları da wikidata/admin otoritesine DEFER (seed bölümü de
            # salınıyordu: enrich seed'i wikidata'ya yükseltir, builder seed'i geri yaratırdı).
            seed_owner = await _wikidata_owner_map(
                db, {(m.canonical_normalized, m.entity_type) for _, _, m in seed_hits}
            )
            for norm, etype, match in seed_hits:
                key = (match.canonical_normalized, match.entity_type)
                cid = canon_cache.get(key)
                if cid is None:
                    wid = seed_owner.get(key)
                    if wid is not None:
                        canon_cache[key] = wid  # wikidata canonical'a yönlendir, seed AÇMA
                    else:
                        new_id = (
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
                        canon_cache[key] = str(new_id)
                        n_canon += 1
                    cid = canon_cache[key]

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
                    {"alias": norm, "etype": etype, "cid": cid, "src": match.source},
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
            # #1725: wikidata/admin OTORİTESİNE DEFER — bir grubun üyesi/canonical'ı zaten bir
            # wikidata/admin canonical'ın canonical'ı veya alias'ıysa, build_canonical YENİ
            # token_subset canonical AÇMAZ; grubu o wikidata canonical'a (W) yönlendirir. Aksi
            # halde build_canonical her turda enrich_wikidata'nın merge'ini geri bozardı
            # (token_subset varyantı + alias'ları yeniden yaratır → salınım, #1725 kökü).
            all_norms = set(groups.keys()) | set(groups.values())
            owner_map = await _wikidata_owner_map(db, {(n, etype) for n in all_norms})
            owner = {norm: cid for (norm, _et), cid in owner_map.items()}

            # canonical_norm → canonical_id (yüzey biçimi mode entity_text)
            for canonical_norm in set(groups.values()):
                key = (canonical_norm, etype)
                if key in canon_cache:
                    continue
                members = [m for m, c in groups.items() if c == canonical_norm]
                wid = next((owner[n] for n in (canonical_norm, *members) if n in owner), None)
                if wid is not None:
                    # grup zaten wikidata/admin canonical'a ait → W'ye yönlendir, YENİ açma
                    canon_cache[key] = wid
                    continue
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
                        WHERE entity_aliases.source NOT IN ('admin', 'wikidata')
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
