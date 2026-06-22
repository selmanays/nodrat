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
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy import text as sa_text

from app.modules.entities.tasks.entities import _normalize_entity
from app.modules.entities.wikidata_match import (
    select_canonical_label,
    strip_event_edition,
    type_matches,
)
from app.providers.registry import bootstrap_default_providers, registry
from app.providers.wikipedia import WikipediaProvider, get_wikipedia_provider
from app.shared.runtime_config.settings_store import settings_store
from app.shared.workers.db_session import _get_session_factory, _run_async
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

_FLAG = "entities.wikidata_enrich.enabled"
# #1720 canonical-katman merge'i ayrı kapı: deploy davranışı DEĞİŞTİRMESİN (DELETE içerir →
# canary). dry_run bu flag'i baypas eder (salt-okunur önizleme). Default OFF.
_CANON_FLAG = "entities.wikidata_enrich.canon_layer.enabled"

# NOT (#1717): jenerik-kavram OTO-tespiti GERİ ÇEKİLDİ. Denenen 3 sinyal de güvenilir
# DEĞİL: (a) kapitalizasyon — MediaWiki başlık ilk harfini DAİMA büyütür + TR cümle-
# düzeni; (b) Wikidata P279 — spesifik takımlar da subclass; (c) corpus-N (#1716) —
# prominent özel-adlar (Türkiye/İstanbul/NATO/Erdoğan) çok-bileşik-entity'de geçtiği
# için yüksek-N → 232 MEŞRU canonical'ı yanlış sildi (geri yüklendi). Sonuç: jenerik
# kavram (merkez bankası) canonical katmanında zararsız kalır; KÜME ÇAPASI olması zaten
# [[global-research-cluster-model]] #1705 genericlik-reddiyle engellenir. Nadir görünür
# yanlış-eşleme → admin Varlık Birleştirme (insan kararı).


async def _llm_confirm_same_entity(query: str, title: str, summary: str) -> bool:
    """v4-flash precision gate (#1720): Wikipedia maddesi haber-varlığının TAM karşılığı mı?

    Full-text arama event/prosedür adlarında ~%50 konu-kayması üretiyor (dry-run
    kanıtı): token-örtüşmesi hem akronimi (YKS↔Yükseköğretim Kurumları Sınavı) hem
    fuzzy'yi (15-16 Haziran Direnişi↔15-16 Haziran olayları) bozduğu için deterministik
    ayrım yapılamıyor → anlamsal doğrulama. Tek ucuz çağrı (free-tier=DeepSeek v4-flash),
    cost-log'lu. Hata/belirsizlik → False (muhafazakâr: doğrulanamayan merge edilmez)."""
    try:
        from app.providers.base import Message as _PMsg

        provider = registry.route_for_tier(operation="chat", tier="free")
        _sys = (
            "Sen bir varlık-eşleştirme denetçisisin. Sana bir HABER VARLIĞI adı ve bir "
            "WIKIPEDIA maddesi (başlık + özet) verilir. Wikipedia maddesi bu haber "
            "varlığının TAM ve DOĞRU karşılığı mı (aynı gerçek-dünya nesnesi/olayı/"
            "kurumu) yoksa yalnızca konu olarak yakın ya da alakasız bir madde mi? "
            "Yıl/sıra farkı (ör. '2026 X Şampiyonası' ↔ 'X Şampiyonası') ve akronim/"
            "çeviri (ör. 'YKS' ↔ 'Yükseköğretim Kurumları Sınavı', 'İtalya Kupası' ↔ "
            "'Coppa Italia') AYNI sayılır. Farklı bir nesne/olay/kurum/yapım ise AYNI "
            "DEĞİL. Yalnızca tek kelime yanıtla: EVET veya HAYIR."
        )
        _usr = (
            f"HABER VARLIĞI: {query}\n"
            f"WIKIPEDIA BAŞLIK: {title}\n"
            f"WIKIPEDIA ÖZET: {(summary or '')[:400]}"
        )
        res = await provider.generate_text(
            messages=[
                _PMsg(role="system", content=_sys),
                _PMsg(role="user", content=_usr),
            ],
            max_tokens=4,
            temperature=0.0,
        )
        try:  # best-effort cost log (akışı bozmaz; ayrı session — #1604 deseni)
            from app.core.db import get_session_factory
            from app.shared.observability.cost_tracker import track_provider_call

            _f = get_session_factory()
            async with _f() as _db_log:
                async with track_provider_call(
                    db=_db_log, provider=provider.name, operation="wikidata_verify"
                ) as _tr:
                    _tr.record(
                        input_tokens=res.input_tokens,
                        output_tokens=res.output_tokens,
                        cached_tokens=getattr(res, "cached_input_tokens", 0),
                        model=res.model,
                        cost_usd=res.cost_usd,
                    )
                await _db_log.commit()
        except Exception:  # noqa: S110 — best-effort cost log
            pass
        return (res.text or "").strip().lower().startswith("evet")
    except Exception as exc:  # pragma: no cover — ağ/provider; muhafazakâr red
        logger.warning("llm verify failed %r→%r: %s", query, title, exc)
        return False


async def _resolve_one(
    provider: WikipediaProvider,
    query_title: str,
    ner_type: str,
    verifier: Callable[[str, str, str], Awaitable[bool]] | None = None,
) -> tuple[str, str | None, str | None, list[str], list[str]]:
    """Yüzey form → (status, qid, canonical_title, aliases, p31).

    #997 güvenilir zinciri: full-text arama DOĞRU sayfayı bulur → o sayfanın
    sitelink-deterministik QID'si → wbgetentities meta. Çıplak-keyword wbsearchentities
    disambiguation YOK. Tip-gate yanlış sayfayı (kişi→takvim/yer) eler.

    #1714 evergreen: (a) EN-fallback — search tr→en düşerse QID o makalenin diliyle
    çözülür (labels.tr ile TR karşılığı, LLM'siz); (b) event yıl/sıra-öneki sıyrılır
    (birincil = jenerik taban, spesifik form alias). Status: resolved | no_match |
    type_mismatch | llm_reject.

    #1720 precision: `verifier` verilirse (canonical-katman), tip-gate sonrası anlamsal
    doğrulama yapılır (full-text konu-kayması ~%50 → token-gate yetersiz, bkz.
    `_llm_confirm_same_entity`). Doğrulanmazsa → llm_reject (merge yok). verifier=None
    (entity pass + unit test) → davranış değişmez.
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
    # #1720 anlamsal precision kapısı (tip-gate sonrası → yalnız tip-doğru adaylarda LLM)
    if verifier is not None and not await verifier(query_title, art.title, art.summary or ""):
        return ("llm_reject", qid, meta.trwiki_title, [], meta.p31)
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


# --- alias upsert (W'ye re-point / ekle) — admin+wikidata korunur ---
_ALIAS_UPSERT_SQL = sa_text(
    """
    INSERT INTO entity_aliases
        (alias_normalized, entity_type, canonical_id, confidence, source)
    VALUES (:alias, :etype, :cid, 0.950, 'wikidata')
    ON CONFLICT (alias_normalized, entity_type) DO UPDATE
        SET canonical_id = EXCLUDED.canonical_id, source = 'wikidata'
        WHERE entity_aliases.source <> 'admin'
    """
)

# --- wikidata canonical upsert (admin adı/source'u korur) ---
_CANON_UPSERT_SQL = sa_text(
    """
    INSERT INTO canonical_entities
        (canonical_name, entity_type, canonical_normalized, source)
    VALUES (:nm, :et, :cn, 'wikidata')
    ON CONFLICT (canonical_normalized, entity_type) DO UPDATE
        SET canonical_name = CASE WHEN canonical_entities.source = 'admin'
                THEN canonical_entities.canonical_name ELSE EXCLUDED.canonical_name END,
            source = CASE WHEN canonical_entities.source = 'admin'
                THEN canonical_entities.source ELSE 'wikidata' END,
            updated_at = now()
    RETURNING id
    """
)


async def _apply_canonical_merge(
    db: Any, *, cid: str, cn: str, et: str, title: str, extra_aliases: list[str]
) -> str | None:
    """token_subset/seed canonical C'yi wikidata canonical W'ye (title) uygula.

    Aynı normalized → yerinde-yükseltme ('upgraded'); farklı → merge ('merged':
    C'nin alias'ları + C.normalized W'ye re-point, orphan C DELETE). extra_aliases =
    Wikipedia alias'ları (canonical-pass'te dolu; self-heal'de boş — cache'den merge).
    tnorm boşsa None. COMMIT YAPMAZ (çağıran transaction'ı yönetir)."""
    tnorm = _normalize_entity(title)
    if not tnorm:
        return None
    wid = (await db.execute(_CANON_UPSERT_SQL, {"nm": title, "et": et, "cn": tnorm})).scalar()
    if str(wid) == cid:
        outcome = "upgraded"
    else:
        caliases = (
            (
                await db.execute(
                    sa_text("SELECT alias_normalized FROM entity_aliases WHERE canonical_id = :c"),
                    {"c": cid},
                )
            )
            .scalars()
            .all()
        )
        for an in set(caliases) | {cn}:
            await db.execute(_ALIAS_UPSERT_SQL, {"alias": an, "etype": et, "cid": wid})
        # orphan C sil (alias'lar W'ye taşındı; research_clusters FK SET NULL)
        await db.execute(sa_text("DELETE FROM canonical_entities WHERE id = :c"), {"c": cid})
        outcome = "merged"
    for a in extra_aliases:
        an = _normalize_entity(a)
        if an:
            await db.execute(_ALIAS_UPSERT_SQL, {"alias": an, "etype": et, "cid": wid})
    return outcome


async def _enrich_canonical_layer(
    db: Any,
    provider: WikipediaProvider,
    *,
    limit: int,
    refresh_days: int,
    dry_run: bool,
    verifier: Callable[[str, str, str], Awaitable[bool]] | None = _llm_confirm_same_entity,
) -> dict[str, int]:
    """#1720 — token_subset/seed CANONICAL'larını Wikipedia'ya doğrula → wikidata'ya merge.

    token_subset canonical'ları düşük-df entity varyantlarını AGGREGATE eder (ör.
    "15-16 Haziran Direnişi" + "15-16 Haziran Büyük İşçi Direnişi"); tek tek
    df < min_freq olduğu için entity-df taraması (`_enrich_wikidata_async`) onları
    kaçırır — ama agregat Wikipedia'da var ("15-16 Haziran olayları"). Bu pass
    canonical_name'i çözer; çözülürse wikidata canonical (W) upsert + alias'lar W'ye
    re-point + orphan token_subset/seed canonical DELETE (admin liste status
    filtrelemez → orphan kalmamalı). Cluster retro-fit GEREKMEZ: bunlar entity-
    canonicalization katmanı; küme çapaları ayrı resolver'da canonical-aware (#1712)
    ve yeni sorguda W'ye bağlanır. 'denendi' guard (canonical_normalized keyed)
    sonsuz-retry önler (#1602). Authority: admin > wikidata (re-point/DELETE
    admin'e dokunmaz).
    """
    out = {
        "canon_scanned": 0,
        "canon_resolved": 0,
        "canon_merged": 0,
        "canon_upgraded": 0,
        "canon_no_match": 0,
        "canon_llm_reject": 0,
    }
    rows = (
        (
            await db.execute(
                sa_text(
                    """
                    SELECT id::text AS id, canonical_name AS nm, entity_type AS et,
                           canonical_normalized AS cn
                    FROM canonical_entities ce
                    WHERE ce.source IN ('token_subset', 'seed') AND ce.status = 'active'
                      AND NOT EXISTS (
                          SELECT 1 FROM wikidata_entity_resolutions r
                          WHERE r.entity_normalized = ce.canonical_normalized
                            AND r.entity_type = ce.entity_type
                            AND r.attempted_at > now() - make_interval(days => :rd)
                      )
                    ORDER BY ce.alias_count DESC, ce.canonical_name
                    LIMIT :lim
                    """
                ),
                {"rd": refresh_days, "lim": limit},
            )
        )
        .mappings()
        .all()
    )
    out["canon_scanned"] = len(rows)
    for r in rows:
        cid, nm, et, cn = r["id"], r["nm"], r["et"], r["cn"]
        try:
            status, qid, title, aliases, p31 = await _resolve_one(provider, nm, et, verifier)
        except Exception as exc:  # pragma: no cover — ağ/parse
            logger.warning("canon enrich resolve failed %r: %s", nm, exc)
            continue

        if dry_run:
            if status == "resolved":
                out["canon_resolved"] += 1
                logger.info("canon dry-run: %r (%s) → %r", nm, et, title)
            elif status == "llm_reject":
                out["canon_llm_reject"] += 1
                logger.info("canon dry-run LLM-RED: %r (%s) ✗→ %r", nm, et, title)
            else:
                out["canon_no_match"] += 1
            continue

        try:
            await db.execute(
                sa_text(
                    """
                    INSERT INTO wikidata_entity_resolutions
                        (entity_normalized, entity_type, status, wikidata_qid,
                         canonical_title, p31, attempted_at, updated_at)
                    VALUES (:n, :t, :s, :q, :ti, :p, now(), now())
                    ON CONFLICT (entity_normalized, entity_type) DO UPDATE
                        SET status = EXCLUDED.status, wikidata_qid = EXCLUDED.wikidata_qid,
                            canonical_title = EXCLUDED.canonical_title, p31 = EXCLUDED.p31,
                            attempted_at = now(), updated_at = now()
                    """
                ),
                {
                    "n": cn,
                    "t": et,
                    "s": status,
                    "q": qid,
                    "ti": title,
                    "p": ",".join(p31) if p31 else None,
                },
            )
            if status != "resolved":
                out["canon_llm_reject" if status == "llm_reject" else "canon_no_match"] += 1
                await db.commit()
                continue

            outcome = await _apply_canonical_merge(
                db, cid=cid, cn=cn, et=et, title=title, extra_aliases=aliases
            )
            if outcome is None:
                await db.commit()
                continue
            out["canon_resolved"] += 1
            out["canon_upgraded" if outcome == "upgraded" else "canon_merged"] += 1
            await db.commit()  # canonical-başına commit: merge atomik + blast-radius sınırlı
        except Exception as exc:  # pragma: no cover
            await db.rollback()
            logger.warning("canon enrich merge failed %r: %s", nm, exc)
            continue

    if not dry_run:
        await db.execute(
            sa_text(
                "UPDATE canonical_entities c SET alias_count = "
                "(SELECT count(*) FROM entity_aliases a WHERE a.canonical_id = c.id) "
                "WHERE c.source = 'wikidata'"
            )
        )
        await db.commit()
    return out


async def _reheal_canonical_layer(db: Any, *, limit: int, dry_run: bool) -> dict[str, int]:
    """#1725 self-heal — build_canonical'ın yeniden-yarattığı token_subset/seed canonical'ı,
    guard'da zaten 'resolved' (önbellek) varsa Wikipedia/LLM ÇAĞIRMADAN yeniden merge eder.

    build_canonical fix'i (#1725) salınımı önler ama enrich'ten ÖNCE çalıştığı turda taze
    bir varyant geçici token_subset canonical olarak doğabilir; ayrıca enrich guard'ı
    (refresh_days) yeniden-resolve'u 30 gün engeller. Bu pass, çözümü zaten bilinen
    (cache'li canonical_title) canonical'ları SIFIR LLM maliyetiyle W'ye geri katlar →
    gerçek evergreen yapışkanlık. Sadece canonical-katman flag'i açıkken çağrılır."""
    out = {"reheal_scanned": 0, "reheal_merged": 0}
    rows = (
        (
            await db.execute(
                sa_text(
                    """
                    SELECT ce.id::text AS id, ce.canonical_name AS nm, ce.entity_type AS et,
                           ce.canonical_normalized AS cn, r.canonical_title AS title
                    FROM canonical_entities ce
                    JOIN wikidata_entity_resolutions r
                      ON r.entity_normalized = ce.canonical_normalized
                     AND r.entity_type = ce.entity_type
                    WHERE ce.source IN ('token_subset', 'seed') AND ce.status = 'active'
                      AND r.status = 'resolved' AND r.canonical_title IS NOT NULL
                    ORDER BY ce.alias_count DESC, ce.canonical_name
                    LIMIT :lim
                    """
                ),
                {"lim": limit},
            )
        )
        .mappings()
        .all()
    )
    out["reheal_scanned"] = len(rows)
    for r in rows:
        cid, nm, et, cn, title = r["id"], r["nm"], r["et"], r["cn"], r["title"]
        # cache'li başlık zaten bu canonical'ın kendisi (normalized eşit) → onarılacak bir şey yok
        if _normalize_entity(title) == cn:
            continue
        if dry_run:
            out["reheal_merged"] += 1
            logger.info("canon reheal dry-run: %r (%s) → %r [cache]", nm, et, title)
            continue
        try:
            outcome = await _apply_canonical_merge(
                db, cid=cid, cn=cn, et=et, title=title, extra_aliases=[]
            )
            if outcome == "merged":
                out["reheal_merged"] += 1
            await db.commit()
        except Exception as exc:  # pragma: no cover
            await db.rollback()
            logger.warning("canon reheal failed %r: %s", nm, exc)
            continue
    if not dry_run and out["reheal_merged"]:
        await db.execute(
            sa_text(
                "UPDATE canonical_entities c SET alias_count = "
                "(SELECT count(*) FROM entity_aliases a WHERE a.canonical_id = c.id) "
                "WHERE c.source = 'wikidata'"
            )
        )
        await db.commit()
    return out


async def _reverify_wikidata_aliases(
    db: Any,
    provider: WikipediaProvider,
    *,
    limit: int,
    dry_run: bool,
    verifier: Callable[[str, str, str], Awaitable[bool]] = _llm_confirm_same_entity,
) -> dict[str, int]:
    """#1729/#1730 cleanup — gate'siz entity-pass'in (Pass 1) ürettiği YANLIŞ wikidata
    alias'larını **yeniden çözümleyerek** doğrular (özet'li gate → bağlamsal).

    Hedef: 'resolved' guard'lı (yüzey-formundan çözülmüş) + bir wikidata canonical'a bağlı +
    canonical'ın kendisi OLMAYAN alias'lar. Her alias `_resolve_one` (search → QID → wbget
    meta → tip-gate → **özet'li LLM gate**) ile YENİDEN çözülür:
      - AYNI canonical'a çözülürse → doğru, dokunma.
      - FARKLI (geçerli) canonical'a çözülürse → yanlış-eşlenmiş → doğru W'ye **re-point**.
      - Çözülemez/reddedilirse → drift (ör. "kemal irmak"→Atatürk) → **sil** + guard llm_reject.
    Bağlamsal olduğu için akronim/tarihsel-ad/sponsor-ad (KESK, Dersim, RAMS Park) KORUNUR;
    context-free karşılaştırma bunları yanlışlıkla siliyordu (#1729 dry-run dersi). Standalone
    one-time cleanup (beat'e bağlı DEĞİL). dry_run hiçbir şey YAZMAZ (ama re-resolve LLM çağırır)."""
    out = {"reverify_scanned": 0, "reverify_deleted": 0, "reverify_repointed": 0}
    rows = (
        (
            await db.execute(
                sa_text(
                    """
                    SELECT a.alias_normalized AS alias, a.entity_type AS et,
                           a.canonical_id::text AS cid, c.canonical_name AS cname,
                           c.canonical_normalized AS cn
                    FROM entity_aliases a
                    JOIN canonical_entities c
                      ON c.id = a.canonical_id AND c.source = 'wikidata' AND c.status = 'active'
                    JOIN wikidata_entity_resolutions r
                      ON r.entity_normalized = a.alias_normalized AND r.entity_type = a.entity_type
                    WHERE a.source = 'wikidata' AND r.status = 'resolved'
                      AND a.alias_normalized <> c.canonical_normalized
                    ORDER BY a.entity_type, a.alias_normalized
                    LIMIT :lim
                    """
                ),
                {"lim": limit},
            )
        )
        .mappings()
        .all()
    )
    out["reverify_scanned"] = len(rows)
    for r in rows:
        alias, et, cid, cname, cn = r["alias"], r["et"], r["cid"], r["cname"], r["cn"]
        try:
            status, _qid, title, _aliases, _p31 = await _resolve_one(provider, alias, et, verifier)
        except Exception as exc:  # pragma: no cover — ağ/parse; muhafazakâr: dokunma
            logger.warning("reverify resolve failed %r: %s", alias, exc)
            continue
        tnorm = _normalize_entity(title) if title else None
        if status == "resolved" and tnorm == cn:
            continue  # aynı canonical'a çözüldü → doğru, dokunma

        if dry_run:
            if status == "resolved" and tnorm:
                out["reverify_repointed"] += 1
                logger.info("reverify dry-run REPOINT: %r (%s) %r→%r", alias, et, cname, title)
            else:
                out["reverify_deleted"] += 1
                logger.info(
                    "reverify dry-run SİL: %r (%s) ✗→ %r [eski:%r]", alias, et, status, cname
                )
            continue
        try:
            if status == "resolved" and tnorm:
                # yanlış-eşlenmiş → doğru W'ye re-point (ON CONFLICT mevcut alias'ı günceller)
                wid = (
                    await db.execute(_CANON_UPSERT_SQL, {"nm": title, "et": et, "cn": tnorm})
                ).scalar()
                await db.execute(_ALIAS_UPSERT_SQL, {"alias": alias, "etype": et, "cid": wid})
                out["reverify_repointed"] += 1
                logger.info("reverify REPOINT: %r (%s) %r→%r", alias, et, cname, title)
            else:
                # drift / çözülemez → sil + guard llm_reject (gürültü, retry yok)
                await db.execute(
                    sa_text(
                        "DELETE FROM entity_aliases WHERE alias_normalized = :a "
                        "AND entity_type = :t AND canonical_id = :c"
                    ),
                    {"a": alias, "t": et, "c": cid},
                )
                await db.execute(
                    sa_text(
                        "UPDATE wikidata_entity_resolutions SET status = 'llm_reject', "
                        "updated_at = now() WHERE entity_normalized = :a AND entity_type = :t"
                    ),
                    {"a": alias, "t": et},
                )
                out["reverify_deleted"] += 1
                logger.info("reverify SİLİNDİ: %r (%s) ✗→ %r", alias, et, cname)
            await db.commit()
        except Exception as exc:  # pragma: no cover
            await db.rollback()
            logger.warning("reverify apply failed %r: %s", alias, exc)
    if not dry_run and (out["reverify_deleted"] or out["reverify_repointed"]):
        await db.execute(
            sa_text(
                "UPDATE canonical_entities c SET alias_count = "
                "(SELECT count(*) FROM entity_aliases a WHERE a.canonical_id = c.id) "
                "WHERE c.source = 'wikidata'"
            )
        )
        await db.commit()
    return out


async def _enrich_wikidata_async(
    *,
    min_freq: int = 3,
    limit: int = 50,
    refresh_days: int = 30,
    canon_limit: int = 30,
    dry_run: bool = False,
) -> dict[str, Any]:
    """entities → Wikipedia-canonical etiket + alias zenginleştirme (batch, idempotent).

    İki pass: (1) entity-df taraması (yüzey formlar); (2) canonical-katman (#1720) —
    token_subset/seed canonical'larını Wikipedia'ya doğrula → wikidata'ya merge."""
    # Celery worker registry'yi otomatik bootstrap ETMEZ (yalnız app.main lifespan);
    # canonical-katman LLM precision gate registry'ye ihtiyaç duyar → idempotent kayıt
    # (agenda/embedding/raptor task deseni; build_local lazy → bge-m3 yüklenmez). (#1720)
    bootstrap_default_providers()
    factory = _get_session_factory()
    summary: dict[str, Any] = {
        "status": "unknown",
        "scanned": 0,
        "resolved": 0,
        "no_match": 0,
        "type_mismatch": 0,
        "error": 0,
        "canonical_upserts": 0,
        "alias_upserts": 0,
        "canon_scanned": 0,
        "canon_resolved": 0,
        "canon_merged": 0,
        "canon_upgraded": 0,
        "canon_no_match": 0,
        "canon_llm_reject": 0,
        "reheal_scanned": 0,
        "reheal_merged": 0,
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
        provider = await get_wikipedia_provider()
        n_canon = 0
        n_alias = 0
        for r in rows:
            norm = r["norm"]
            etype = r["etype"]
            query_title = (r["sample_text"] or norm or "").strip()
            try:
                # #1729: entity-pass de LLM precision gate kullanır (Pass 2 ile aynı). Aksi halde
                # full-text drift + zayıf person tip-gate ("herhangi bir insan") farklı kişiyi
                # ünlüye bağlar (ör. "kemal irmak" → Atatürk). HAYIR → llm_reject (alias yok).
                status, qid, title, aliases, p31 = await _resolve_one(
                    provider, query_title, etype, _llm_confirm_same_entity
                )
            except Exception as exc:  # pragma: no cover — ağ/parse; guard yine yazılır
                status, qid, title, aliases, p31 = ("error", None, None, [], [])
                logger.warning("wikidata enrich resolve failed %r: %s", query_title, exc)

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

        # Pass 2 (#1720): canonical-katman — token_subset/seed → Wikipedia doğrula + merge.
        # Gerçek merge ayrı flag arkasında (DELETE içerir → canary); dry_run baypas eder.
        canon_enabled = dry_run or await settings_store.get_bool(db, _CANON_FLAG, False)
        if canon_limit > 0 and canon_enabled:
            canon = await _enrich_canonical_layer(
                db,
                provider,
                limit=canon_limit,
                refresh_days=refresh_days,
                dry_run=dry_run,
            )
            summary.update(canon)
            # #1725 self-heal: build_canonical'ın geri-bozduğu (cache'li resolved) canonical'ları
            # LLM'siz yeniden W'ye katla → enrich↔builder yapışkanlığı kalıcı.
            reheal = await _reheal_canonical_layer(
                db, limit=max(canon_limit * 4, 100), dry_run=dry_run
            )
            summary.update(reheal)

        summary["status"] = "dry_run" if dry_run else "enriched"
        logger.info(
            "wikidata enrich: scanned=%s resolved=%s no_match=%s type_mismatch=%s "
            "canon=%s alias=%s | canon-layer scanned=%s resolved=%s merged=%s "
            "upgraded=%s llm_reject=%s | reheal scanned=%s merged=%s dry=%s",
            summary["scanned"],
            summary["resolved"],
            summary["no_match"],
            summary["type_mismatch"],
            n_canon,
            n_alias,
            summary["canon_scanned"],
            summary["canon_resolved"],
            summary["canon_merged"],
            summary["canon_upgraded"],
            summary["canon_llm_reject"],
            summary["reheal_scanned"],
            summary["reheal_merged"],
            dry_run,
        )
        return summary


@celery_app.task(name="tasks.entities.enrich_wikidata", bind=True)
def enrich_wikidata(  # type: ignore[no-untyped-def]
    self,
    min_freq: int = 3,
    limit: int = 50,
    refresh_days: int = 30,
    canon_limit: int = 30,
    dry_run: bool = False,
) -> dict:
    """entities → Wikidata canonical-etiket zenginleştirme (flag-gated, batch).

    Pass 2 (#1720) token_subset/seed canonical'larını da Wikipedia'ya doğrulayıp
    wikidata'ya merge eder (canon_limit=0 ile kapatılır)."""
    return _run_async(
        _enrich_wikidata_async(
            min_freq=min_freq,
            limit=limit,
            refresh_days=refresh_days,
            canon_limit=canon_limit,
            dry_run=dry_run,
        )
    )
