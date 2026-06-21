"""Celery: Wikidata canonical-etiket zenginleştirme (#1710 Faz 1).

`entities`'ten df ≥ min_freq + henüz-çözülmemiş yüzey formlarını toplar; mevcut
`WikipediaProvider` zinciriyle (full-text → DOĞRU sayfa → wikibase_item kesin QID →
wbgetentities) Wikipedia TR canonical başlığı + TR alias'ları çözer; **tip-gate**
(P31 ↔ NER tipi) geçerse `canonical_entities` (source='wikidata') + `entity_aliases`
(korpus yüzey + Wikidata alias'ları) upsert eder. Her deneme — çözülsün/çözülmesin —
`wikidata_entity_resolutions`'a 'denendi' yazılır (#1602 sonsuz-döngü guard).

Authority: admin > **wikidata** > seed > token_subset (alias ON CONFLICT guard'ı
admin+wikidata korur; build_canonical de bu ikisini ezmez). `entities` YALNIZ okunur.
Flag `entities.wikidata_enrich.enabled` (default OFF). ner_queue → worker_ner.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text as sa_text

from app.core.research_clustering import GENERIC_ANCHOR_MAX
from app.modules.entities.tasks.entities import _normalize_entity
from app.modules.entities.wikidata_match import (
    select_canonical_label,
    strip_event_edition,
    type_matches,
)
from app.providers.wikipedia import WikipediaProvider, get_wikipedia_provider
from app.shared.runtime_config.settings_store import settings_store
from app.shared.workers.db_session import _get_session_factory, _run_async
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

_FLAG = "entities.wikidata_enrich.enabled"

# #1716 — jenerik-kavram guard: çözülen Wikipedia başlığı korpusta çok-entity'nin
# BİLEŞENİ ise (jenerik kavram, ör. "merkez bankası" N=57, "yapay zeka" N=50) çapa
# olamaz. Kapitalizasyon/P279 ayırmıyor (MediaWiki ilk-harfi büyütür; TR cümle-düzeni;
# spesifik takım da P279'a sahip) → corpus-N (#1705 sinyali, eşik GENERIC_ANCHOR_MAX)
# tek güvenilir ayrım. Spesifik özel-ad ~0 (ABD=10<15 korunur).
_GENERIC_N_SQL = sa_text(
    "SELECT count(DISTINCT entity_normalized) FROM entities "
    "WHERE entity_normalized LIKE '%' || :t || '%' AND entity_normalized <> :t"
)


async def _corpus_generic_count(db, norm: str) -> int:
    """norm'u BİLEŞEN olarak içeren FARKLI entity sayısı (#1705/#1716 jenerik sinyali)."""
    if not norm:
        return 0
    return int((await db.execute(_GENERIC_N_SQL, {"t": norm})).scalar() or 0)


async def _resolve_one(
    provider: WikipediaProvider, query_title: str, ner_type: str
) -> tuple[str, str | None, str | None, list[str], list[str]]:
    """Yüzey form → (status, qid, canonical_title, aliases, p31).

    #997 güvenilir zinciri: full-text arama DOĞRU sayfayı bulur → o sayfanın
    sitelink-deterministik QID'si → wbgetentities meta. Çıplak-keyword wbsearchentities
    disambiguation YOK. Tip-gate yanlış sayfayı (kişi→takvim/yer) eler.

    #1714 evergreen: (a) EN-fallback — search tr→en düşerse QID o makalenin diliyle
    çözülür (labels.tr ile TR karşılığı, LLM'siz); (b) event yıl/sıra-öneki sıyrılır
    (birincil = jenerik taban, spesifik form alias). Status: resolved | no_match |
    type_mismatch. (Jenerik-kavram guard'ı çağıran loop'ta — corpus-N, DB gerektirir.)
    """
    articles = await provider.search(query_title, top_k=1)
    if not articles:
        return ("no_match", None, None, [], [])
    art = articles[0]
    # EN-fallback: makale TR değilse (lang_priority tr→en) QID o dille çözülür.
    qid = await provider.wikidata_qid_for_title(art.title, lang=art.lang)
    if not qid:
        return ("no_match", None, None, [], [])
    meta = await provider.wikidata_entity_meta(qid, lang="tr")
    if meta is None:
        return ("no_match", qid, None, [], [])
    if not type_matches(ner_type, meta.p31):
        return ("type_mismatch", qid, meta.trwiki_title, [], meta.p31)
    title = select_canonical_label(meta.trwiki_title, meta.label_tr)
    if not title:
        return ("no_match", qid, None, [], meta.p31)
    extra_aliases = list(meta.aliases_tr)
    # event yıl/sıra-öneki → jenerik taban birincil etiket; spesifik form alias kalır
    if ner_type == "event":
        base, edition = strip_event_edition(title)
        if edition:
            extra_aliases.append(title)  # "49. G7 zirvesi" / "2026 …" → alias
            title = base
    # NOT: jenerik-kavram guard (corpus-N) çağıran loop'ta (DB gerektirir, _resolve_one saf-provider).
    return ("resolved", qid, title, extra_aliases, meta.p31)


async def _enrich_wikidata_async(
    *,
    min_freq: int = 3,
    limit: int = 50,
    refresh_days: int = 30,
    dry_run: bool = False,
) -> dict[str, Any]:
    """entities → Wikipedia-canonical etiket + alias zenginleştirme (batch, idempotent)."""
    factory = _get_session_factory()
    summary: dict[str, Any] = {
        "status": "unknown",
        "scanned": 0,
        "resolved": 0,
        "no_match": 0,
        "type_mismatch": 0,
        "generic": 0,
        "error": 0,
        "canonical_upserts": 0,
        "alias_upserts": 0,
        "dry_run": dry_run,
    }

    async with factory() as db:
        if not dry_run and not await settings_store.get_bool(db, _FLAG, False):
            summary["status"] = "disabled"
            return summary

        rows = (
            (
                await db.execute(
                    sa_text(
                        """
                        SELECT e.entity_normalized AS norm, e.entity_type AS etype,
                               COUNT(DISTINCT e.article_id) AS freq,
                               mode() WITHIN GROUP (ORDER BY e.entity_text) AS sample_text
                        FROM entities e
                        WHERE e.entity_type IN ('person','org','place','event')
                        GROUP BY e.entity_normalized, e.entity_type
                        HAVING COUNT(DISTINCT e.article_id) >= :min_freq
                           AND NOT EXISTS (
                               SELECT 1 FROM wikidata_entity_resolutions r
                               WHERE r.entity_normalized = e.entity_normalized
                                 AND r.entity_type = e.entity_type
                                 AND r.attempted_at > now() - make_interval(days => :refresh_days)
                           )
                        ORDER BY freq DESC
                        LIMIT :limit
                        """
                    ),
                    {"min_freq": min_freq, "refresh_days": refresh_days, "limit": limit},
                )
            )
            .mappings()
            .all()
        )
        summary["scanned"] = len(rows)
        if not rows:
            summary["status"] = "no_candidates"
            return summary

        provider = await get_wikipedia_provider()
        n_canon = 0
        n_alias = 0
        for r in rows:
            norm = r["norm"]
            etype = r["etype"]
            query_title = (r["sample_text"] or norm or "").strip()
            try:
                status, qid, title, aliases, p31 = await _resolve_one(provider, query_title, etype)
            except Exception as exc:  # pragma: no cover — ağ/parse; guard yine yazılır
                status, qid, title, aliases, p31 = ("error", None, None, [], [])
                logger.warning("wikidata enrich resolve failed %r: %s", query_title, exc)

            # #1716 — jenerik-kavram guard (corpus-N): çözülen başlık korpusta çok-entity'nin
            # bileşeniyse (jenerik kavram, ör. "merkez bankası") çapa OLAMAZ → 'generic' (yazma yok).
            if (
                status == "resolved"
                and title
                and (await _corpus_generic_count(db, _normalize_entity(title)))
                >= GENERIC_ANCHOR_MAX
            ):
                status = "generic"

            summary[status] = summary.get(status, 0) + 1

            if not dry_run:
                # 'denendi' guard — her deneme (çözülsün/çözülmesin) yazılır (#1602)
                await db.execute(
                    sa_text(
                        """
                        INSERT INTO wikidata_entity_resolutions
                            (entity_normalized, entity_type, status, wikidata_qid,
                             canonical_title, p31, attempted_at, updated_at)
                        VALUES (:norm, :etype, :status, :qid, :title, :p31, now(), now())
                        ON CONFLICT (entity_normalized, entity_type) DO UPDATE
                            SET status = EXCLUDED.status,
                                wikidata_qid = EXCLUDED.wikidata_qid,
                                canonical_title = EXCLUDED.canonical_title,
                                p31 = EXCLUDED.p31,
                                attempted_at = now(),
                                updated_at = now()
                        """
                    ),
                    {
                        "norm": norm,
                        "etype": etype,
                        "status": status,
                        "qid": qid,
                        "title": title,
                        "p31": ",".join(p31) if p31 else None,
                    },
                )

            if status != "resolved" or dry_run:
                continue

            # canonical_entities upsert — Wikidata otorite (admin korunur)
            cnorm = _normalize_entity(title)
            if not cnorm:
                continue
            cid = (
                await db.execute(
                    sa_text(
                        """
                        INSERT INTO canonical_entities
                            (canonical_name, entity_type, canonical_normalized, source)
                        VALUES (:name, :etype, :cnorm, 'wikidata')
                        ON CONFLICT (canonical_normalized, entity_type) DO UPDATE
                            SET canonical_name = CASE
                                    WHEN canonical_entities.source = 'admin'
                                    THEN canonical_entities.canonical_name
                                    ELSE EXCLUDED.canonical_name END,
                                source = CASE
                                    WHEN canonical_entities.source = 'admin'
                                    THEN canonical_entities.source
                                    ELSE 'wikidata' END,
                                updated_at = now()
                        RETURNING id
                        """
                    ),
                    {"name": title, "etype": etype, "cnorm": cnorm},
                )
            ).scalar()
            n_canon += 1

            # alias'lar: korpus yüzey formu + canonical_normalized + Wikidata TR alias'ları
            alias_norms = {norm, cnorm}
            for a in aliases:
                an = _normalize_entity(a)
                if an:
                    alias_norms.add(an)
            for an in alias_norms:
                await db.execute(
                    sa_text(
                        """
                        INSERT INTO entity_aliases
                            (alias_normalized, entity_type, canonical_id, confidence, source)
                        VALUES (:alias, :etype, :cid, 0.950, 'wikidata')
                        ON CONFLICT (alias_normalized, entity_type) DO UPDATE
                            SET canonical_id = EXCLUDED.canonical_id, source = 'wikidata'
                            WHERE entity_aliases.source <> 'admin'
                        """
                    ),
                    {"alias": an, "etype": etype, "cid": cid},
                )
                n_alias += 1

        if not dry_run:
            await db.execute(
                sa_text(
                    """
                    UPDATE canonical_entities c
                    SET alias_count = (
                        SELECT count(*) FROM entity_aliases a WHERE a.canonical_id = c.id
                    )
                    WHERE c.source = 'wikidata'
                    """
                )
            )
            await db.commit()

        summary["canonical_upserts"] = n_canon
        summary["alias_upserts"] = n_alias
        summary["status"] = "dry_run" if dry_run else "enriched"
        logger.info(
            "wikidata enrich: scanned=%s resolved=%s no_match=%s type_mismatch=%s "
            "generic=%s canon=%s alias=%s dry=%s",
            summary["scanned"],
            summary["resolved"],
            summary["no_match"],
            summary["type_mismatch"],
            summary["generic"],
            n_canon,
            n_alias,
            dry_run,
        )
        return summary


@celery_app.task(name="tasks.entities.enrich_wikidata", bind=True)
def enrich_wikidata(  # type: ignore[no-untyped-def]
    self,
    min_freq: int = 3,
    limit: int = 50,
    refresh_days: int = 30,
    dry_run: bool = False,
) -> dict:
    """entities → Wikidata canonical-etiket zenginleştirme (flag-gated, batch)."""
    return _run_async(
        _enrich_wikidata_async(
            min_freq=min_freq, limit=limit, refresh_days=refresh_days, dry_run=dry_run
        )
    )
