---
type: topic
title: "Trend Intelligence — Admin Overview (Faz 1+2 + Entity Pivot)"
slug: "trend-intelligence-admin-overview-2026-06"
status: live
created: 2026-06-15
updated: 2026-06-16
sources:
  - "apps/api/app/api/admin_trends.py"
  - "apps/api/app/api/admin_entities.py"
  - "apps/web/src/app/admin/trends/page.tsx"
  - "apps/web/src/app/admin/trends/[key]/page.tsx"
  - "apps/web/src/app/admin/entities/canonical/page.tsx"
  - "apps/api/app/modules/trends/ (models + aggregation + topic_assignment + tasks)"
  - "apps/api/app/modules/settings_admin/routes.py (SETTING_REGISTRY: trends.*)"
tags: [trends, admin, observability, gundem]
aliases: ["Trend Overview", "Gündem Trendleri Faz 1", "trend-intelligence-faz1"]
---

# Trend Intelligence — Admin Overview (Faz 1)

## TL;DR

GDELT-benzeri "trend intelligence" katmanının **Faz 1**'i: admin panelde `/admin/trends` altında **transient / read-only** Trend Overview. Backend mevcut `event_clusters` / `event_articles` / `sources` verisinden **CANLI SQL** ile konu trend metrikleri hesaplar — **persistence yok, worker yok, LLM yok, migration yok**. Flag `trends.enabled` default **OFF** → endpoint no-op (prod davranışı değişmez). Mevcut RAG/search pipeline'a dokunulmaz. PR [#1503](https://github.com/selmanays/nodrat/pull/1503) (issue [#1500](https://github.com/selmanays/nodrat/issues/1500)), main `c2f0b67`, FULL deploy success + prod no-op doğrulandı.

## Bağlam / neden

Sistem zaten bir trend altyapısının yarısına sahipti: `event_clusters` saatlik refresh'te `importance_score`/`freshness_score`'u **yerinde overwrite** ediyordu — tarihsel ölçüm yapılmıyordu. Bu fazın amacı, mevcut kümeleme verisinden **transient** (anlık hesaplanan, kaydedilmeyen) trend metriklerini admin gözlemine açmak; kalıcı kimlik (topics) + zaman-serisi (snapshots) Faz 2'ye bırakılır. Master plan: `~/.claude/plans/nodrat-i-in-kaynak-haberlerden-dazzling-walrus.md`. İlgili veri-akışı: [[data-pipelines]] (Pipeline-3 Clustering+Agenda).

## Endpoint + sözleşme

`GET /admin/trends?window=&sort=&limit=&offset=` (`require_admin`, read-only, audit yok).

- **window:** `1h | 6h | 24h | 7d` (verilmezse `trends.overview.window_default`, default `24h`).
- **sort:** `momentum | article_count | source_count | novelty | credibility`.
- **pagination:** `limit` (≤200), `offset`.
- **Flag OFF (default):** ağır SQL çalışmaz → `{enabled:false, data:[], total:0}` no-op envelope.

Her satır: `cluster_id, title, status, trend_state, article_count, previous_article_count, momentum (null=yeni), unique_source_count, source_diversity, credibility_score, novelty_score, first_seen_at, last_seen_at, sparkline[]`.

## Metrik formülleri (v0, saf SQL + Python, deterministik)

- **article_count / previous_article_count:** seçili pencere `[now-W, now]` ve önceki `[now-2W, now-W]` içinde `event_articles.published_at` sayımı (cluster başına FILTER agregasyonu).
- **momentum:** ham `(cur-prev)/prev`; `prev=0 & cur>0 → null`. ⚠️ **#1566 ile düzeltildi:** ham momentum korpus büyümesini trend sanıyordu → artık `relative_momentum` (korpus-normalize, aşağıdaki "#1566" bölümü) asıl sinyal; ham yalnız referans.
- **source_diversity:** basit v1 proxy = `benzersiz_kaynak / toplam_haber` (clamp [0,1]).
- **credibility_score:** pencere içi `AVG(sources.reliability_score)`.
- **novelty_score:** recency, `0.5 ** (yaş_saat / 12)` (yarı-ömür 12sa).
- **trend_state:** `breaking | developing | stable | fading`. ⚠️ **#1566 ile yeniden tasarlandı:** artık `relative_momentum` (korpus gate) + `burst_z` (pencere-içi grafik yönü) ile hesaplanır → rozet sparkline ile hizalı. (Eski "momentum+cur/prev" eşiği "her şey patlıyor" üretiyordu.) `event_clusters.status` yalnız okunur, **asla yazılmaz**.
- **sparkline:** pencereye göre bucketed sayım (1h→6×10dk, 6h→6×1sa, 24h→12×2sa, 7d→7×1gün).

## Mimari + boundary

- Kod `app/api/admin_trends.py` aggregator katmanında: cross-domain ORM/tablo okuma serbest (import-linter yalnız `core→modules` / `shared→modules` vb. yasaklar; `api→modules` serbest — [[admin_clusters.py pattern]]). **lint-imports 16/16 KEPT.**
- **PostgreSQL gotcha:** momentum `ORDER BY` ifadesi output-alias kullandığından (`(cur_count-prev_count)/NULLIF(prev_count,0)`) subquery-dışına alındı; düz ORDER BY içinde alias → "column does not exist". Integration test bunu asyncpg'de doğrular.
- **Perf:** `event_articles.published_at` üzerinde index YOK (yalnız event_id, article_id) → pencere taraması seq-scan; v1 ölçeğinde kabul. Korpus büyürse `(event_id, published_at)` index'i Faz 2 migration'da değerlendirilir (bu PR'da migration YOK).

## Frontend

`/admin/trends` sayfası ([[admin-clusters page]] list deseni): window toggle + özet kartları + tablo + sparkline (Recharts) + loading/empty(flag-OFF "kapalı" mesajı)/error state, tr-TR format. Sidebar **Gözlem** grubuna "Trendler" (TrendingUp). Bloklar: `trend-status-badge`, `trend-sparkline`, `trend-window-toggle`. Settings UI'da `trends` grubu (flag açma).

## Deploy + prod assert (2026-06-15)

- main CI 11/11 ✓. Deploy attempt-1 **transient SSH-broken-pipe** (runner→VPS, api image export sırasında; `up -d` skipped → prod dokunulmadı). Re-run (attempt-2) **success**: build ✓ · up -d ✓ · alembic verify-at-head ✓ (migration yok → no-op) · smoke /health ✓.
- Prod assert (SSH): 13/13 container running · api'de `admin_trends.py` var · `app_settings` `trends.*` override **0 satır → flag default OFF** · api log temiz · `/api/admin/trends` 401 (auth-gate) · `/health` 200 · mevcut `/api/admin/clusters` 401 → RAG/admin yüzeyi etkilenmedi. **Prod no-op doğrulandı.**

## Faz 2 — kalıcı persistence (IMPLEMENTED 2026-06-15)

3-PR split (issue [#1505](https://github.com/selmanays/nodrat/issues/1505); kararlar: tam ORM modeli · entity-anchored seed · retention 180g · bucket 1h):

- **PR-2a** [#1506](https://github.com/selmanays/nodrat/pull/1506) (main `cb29984`) — **migration + ORM modelleri.** 4 tablo: `topics` (kalıcı kimlik; slug/label/topic_kind/anchor_entity/centroid_embedding ivfflat/status) · `topic_clusters` (topic↔event_cluster; `event_cluster_id` **hard FK YOK**) · `trend_snapshots` (zaman-serisi; **UNIQUE(subject_type,subject_id,bucket_start,algo_version)** idempotency; `subject_id` FK YOK — history subject'i aşar) · `trend_signals` (burst). Tam ORM `app/modules/trends/models.py` + `app/models/__init__.py` kayıt. **alembic check 0-diff parity** (event_clusters PR-8.2-11 ivfflat deseni). 3 flag default OFF: `trends.snapshots.enabled` · `trends.assignment.enabled` · `trends.retention.enabled`.
- **PR-2b** [#1511](https://github.com/selmanays/nodrat/pull/1511) (main `a1e3f36`) — **aggregation worker.** `aggregation.py` (paylaşılan scoring + burst z-score) · `topic_assignment.py` (**entity-tabanlı** cluster→topic: baskın person/org/event entity match → recur eden konu tek kimlikte; eşik yoksa entity-anchored seed; centroid cluster'dan in-DB kopya — vektör round-trip yok; tümü raw SQL) · `tasks/aggregate.py` Celery: `aggregate_trends` (beat :20 → assign + snapshot, kapanmış saat bucket) + `backfill_snapshots(range)` + `prune_snapshots` (180g). **İdempotent upsert** ON CONFLICT → re-run identical. maintenance_tracker (admin manuel-trigger).
- **PR-2c** [#1512](https://github.com/selmanays/nodrat/pull/1512) (main `d96f518`, **Closes #1505**) — **read-path snapshot switch + scoring dedup.** `admin_trends`: `trends.snapshots.enabled` ON + pencerede topic snapshot'ı varsa kalıcı store'dan **topic-tabanlı** trendler (response `source="snapshot"`); yoksa **canlı cluster SQL fallback** (Faz 1 davranışı korunur). compute_* → `aggregation`'dan import (tek kaynak).

**Worker açma (canary, ayrı karar):** `trends.assignment.enabled` + `trends.snapshots.enabled` ON → beat :20 topic atama + saatlik snapshot birikir → admin topic trendlerini snapshot'tan okur. Flag OFF iken (mevcut prod) worker no-op + read-path canlı fallback = Faz 1. Prod assert (her PR): flag OFF, tablolar boş, /health 200, Faz1/RAG değişmedi.

> **Deploy dersi (önemli):** PR-2a deploy "Alembic migrate + verify at head" SUCCESS dedi ama migration uygulanMADI (force-recreate image-timing → drift-assert eski container'a koştu, `current==heads(eski)` ile sahte geçti); manuel `alembic upgrade head` ile düzeltildi. Fix: deploy.yml [#1508](https://github.com/selmanays/nodrat/pull/1508) — assert artık **deployed-repo'nun beklediği head**'e bağlı (container heads'ine değil) + stale-image guard + retry. Ayrıca [#1510] SSH keepalive (uzun build runner→VPS pipe-drop). **Migration içeren deploy'lar SSH ile `alembic current==head` + `to_regclass` doğrulanmalı; "success" yetmez.**

## Entity-merkezli pivot (#1516/#1518/#1520, 2026-06-15) — GÜNCEL DAVRANIŞ

Worker canary açıldığında (assignment+snapshots ON, 48s backfill) UI'nin **ham haber başlığı trendi** gösterdiği tespit edildi. Kök neden: `topics.label = event_clusters.canonical_title = articles.title` + **event_clusters ~%93 singleton** (7g'de bile cluster başına en fazla 2 haber) → cluster/topic birimi anlamlı trend üretemiyor. Çözüm = birimi **entity**'ye taşımak. Karar: [[trend-unit-entity-centered]] (LOCKED).

- **Quick-fix** [#1516](https://github.com/selmanays/nodrat/issues/1516) / PR [#1517](https://github.com/selmanays/nodrat/pull/1517) (main `f38a9c9`): read-path **evidence gate** (`trends.gate.min_articles`/`min_sources`, int default 2, 0=kapalı) + breaking eşik (`prev=0→cur≥3`) + HTML decode (`html.unescape`). Migration yok. Worker yazımı kapatıldı (`assignment`+`snapshots` OFF; 227 topic silinmedi — dormant).
- **Entity MVP** [#1518](https://github.com/selmanays/nodrat/issues/1518) / PR [#1519](https://github.com/selmanays/nodrat/pull/1519) (main `04f683c`): `admin_trends._read_entity_trends` (`entities ⋈ articles`, label=`mode() entity_text`, gate) + `aggregation.compute_trend_score` birleşik skor (0.40 volume + 0.25 momentum + 0.20 diversity + 0.10 recency + 0.05 reliability; novelty tie-breaker). FE entity-type rozeti + Skor sütunu. Prod: gate-geçen 6s=66/24s=403/7g=796; top20 = "Türkiye/ABD/İran/Donald Trump/Hürmüz Boğazı" (temiz entity adı).
- **Cluster path kaldırma** [#1520](https://github.com/selmanays/nodrat/issues/1520) / PR [#1521](https://github.com/selmanays/nodrat/pull/1521) (main `98dcfda`): `subject` param + cluster/snapshot okuma yolu (`_read_topic_trends` + canlı cluster SQL + `_SORT_SQL`/`_SNAPSHOT_SORT_SQL`) + UI toggle **tamamen silindi** (net −788/+73). Entity tek okuma yolu; `source="entity"`.

> **Sözleşme güncellemesi (#1518/#1520):** endpoint artık entity-merkezli; `sort` whitelist'ine `score` (varsayılan) eklendi; `subject` param **yok**. Satıra `entity_type` + `trend_score` alanları eklendi; `cluster_id` artık entity subject anahtarı (`"type:normalized"`). Bkz. [api-contracts §6b](../../docs/engineering/api-contracts.md) + [data-model §13c](../../docs/engineering/data-model.md).
>
> **Bilinen risk:** jenerik yer entity baskınlığı (place tipi listeyi domine eder) — stoplist/down-weight ileri faz.

## Pipeline tazelik + canonicalization (2026-06-16)

**NER decouple (#1531/PR#1532) — kısa pencere tazeliği.** Kısa trend pencereleri (1h/6h) boştu; teşhis: NER (entity extraction, DeepSeek LLM) `chunk_article` (embedding zinciri) İÇİNDEN dispatch ediliyordu → embedding throughput'una zincirli, prod **clean→entity median 248 dk** (crawl→clean yalnız 5.7 dk). NER'in embedding'e bağımlılığı yok (sadece clean_text). Fix: NER'i temizleme task'ından **bağımsız** dispatch + adanmış `ner_queue`+`worker_ner` (concurrency 4) + `backfill-entities` beat (30dk güvenlik ağı). **Prod: clean→entity 248dk→3dk.** Kalan: keşif gecikmesi pub→crawl ~6.4s (kaynak-RSS bağlı, Fix C deferred).

**NER cost logging (#1533/PR#1534).** NER `provider_call_logs`'a hiç yazmıyordu → `track_provider_call(operation='ner')` ile loglandı; NER ~$0.27/gün (toplam LLM ~$0.78/gün).

**Entity canonicalization Faz 1 (#1540).** Aynı varlığın varyantları (CHP↔Cumhuriyet Halk Partisi, Cumhurbaşkanı Erdoğan↔Recep Tayyip Erdoğan) ayrı gruplanıyordu → `canonical_entities`+`entity_aliases` katmanı + flag `trends.canonical_entities.enabled`. Builder deterministik (seed + unvan-soyma + ilk-ad guard). Prod: 58 alias/26 canonical; Erdoğan 6+ parça→tek 131 haber, CHP 124+17→130. Karar: [[entity-canonicalization-faz1]]. (PR-A #1541 migration + PR-B #1543.)

**Token-altküme merge (#1548/PR#1549).** Faz 1'in jenerik (seed-siz) genişlemesi: yalnız `event` tipi, `build_subset_groups` union-find ile "2026 FIFA Dünya Kupası"↔"2026 Dünya Kupası" gibi token-altküme varyantları birleşir. Belirsiz vaka (birden çok üst-küme) birleştirilmez → admin'e bırakılır. Prod: 386 eşleşme / 148 event grubu. Detay: [[entity-canonicalization-faz1]] madde 2.

**Trend detail drill-down (#1552/PR#1553).** Trend satırına tıklayınca entity bazlı **detay sayfası** (`GET /admin/trends/detail?key=&window=`, read-only): pencere içi haberler (kaynak+yayın), kaynak dağılımı, birleştirilen **varyant yüzey biçimleri** (canonical ise alias seti), sparkline. FE `/admin/trends/[key]` + liste satırı clickable. Prod container'da route canlı doğrulandı.

**Admin canonical merge/split (#1554/PR#1555).** Deterministik builder'ın çözemediği belirsiz vakaları admin elle yönetir: `/admin/entities` (birleştir/ayır/manuel alias/yeni canonical; hepsi `require_admin`+`AdminAuditLog`). **Builder koruması:** admin mutation'ları `source='admin'` → builder alias upsert'ü `WHERE source <> 'admin'` ile bunları ezmez (CI testcontainers invariant testi yeşil). FE `/admin/entities/canonical` yönetim sayfası + "Varlık Birleştirme" nav. Belirsiz token-altküme vakalarının (örn. "2026 Dünya Kupası"→FIFA) insan-onaylı çözüm yolu. Karar: [[entity-canonicalization-faz1]] madde 5-6.

**Alias-aware liste araması (#1558/PR#1559).** Yönetim sayfasının araması yalnız `canonical_normalized`'ı tarıyordu → bir canonical alias'ıyla bulunamıyordu ("chp" → "Cumhuriyet Halk Partisi" gelmiyordu, chp = alias). `list_canonical` search'ü canonical adı **VEYA** bağlı alias eşleşince satırı döndürür (EXISTS). Prod doğrulandı: "chp" araması artık "Cumhuriyet Halk Partisi"yi getiriyor; testcontainers testi (`test_list_search_matches_alias`) yeşil.

**Merge-aday seçici de alias-aware (#1562/PR#1563).** Detay diyalogdaki "Başka grubu bu gruba kat" seçicisi client-side `allRows` (yüklü ≤100 satır) üzerinde yalnız `canonical_normalized.includes` ile süzüyordu → alias'ları kapsamıyordu + tüm veriyi taramıyordu. FE-only fix: seçici artık sunucu-taraflı `listCanonical({search, entity_type, limit})` (yukarıdaki #1558 alias-aware endpoint) ile debounce'lu arar; aynı tip + kendini eler. Backend değişmedi (mevcut search yeterli). Prod: web container recreate, yeni FE canlı.

**Korpus-normalize + grafik-hizalı trend_state (#1566/PR#1567).** Listede **her satır "Patlıyor"** çıkıyor + sparkline'lar rozetle uyuşmuyordu. **Kök neden (prod kanıtı):** ham `momentum=(cur-prev)/prev` korpus-geneli hacim büyümesini trend sanıyordu — korpus pencereler-arası ~3× büyümüş (entity'li haber cur 1904/prev 609 = +%213); her entity bu baseline'dan pay alıp +%50 breaking eşiğini aşıyordu. Ayrıca `trend_state` pencere-üstü momentum'dan, sparkline pencere-içi dağılımdan → farklı şey ölçüyor (rozet≠grafik). Skor da tavanlara çarpıp ~0.983'te doyuyordu. **Çözüm (A+B+D):**
- **A — korpus-normalize relatif momentum** (`compute_relative_momentum`): `(cur/prev)/(corpus_cur/corpus_prev)-1` → entity yalnız korpustan hızlı büyürse pozitif. Confound kökten silinir.
- **B — canlı pencere-içi burst z-score** (`compute_window_burst`): son üçte-bir vs entity'nin kendi baseline'ı, sparkline bucket serisinden (snapshot worker GEREKMEZ).
- **D — rozet=grafik:** `trend_state` = rel (korpus gate) + burst (grafik yönü): düşüş→fading · yükseliş∧korpus-üstü→breaking · yükseliş→developing · düz→stable.
- Skor momentum bileşeni + `sort=momentum` artık rel kullanır → doygunluk kırılır. Response'a `relative_momentum`+`burst_z`; FE Momentum kolonu rel gösterir.

**Prod kanıtı (önce/sonra):** top 12 entity'nin ham momentum'u +%58…+%2340 (eski: 12/12 "Patlıyor"); korpus-normalize sonrası yalnız **3/12 breaking-aday** (chp +%27, anadolu ajansı +%680, dünya kupası +%37); abd/iran/türkiye/trump vb. korpus dalgasına binmiş (rel ≈0/negatif) → artık developing/stable/fading. CI: pure unit (prod sayılarıyla) + integration (testcontainers: korpus-rider breaking olmaz, gerçek spike olur) yeşil. Worker (dormant) yeni imzada rel=None (kendi robust snapshot burst'ü). Bilinen follow-up: org-as-source gürültüsü (haber ajansı adı entity olarak).

## Faz 3+ (deferred)

~~Merge/split admin feedback~~ **(✅ #1554 ile yapıldı)** + signal inbox (Faz 3), demand (search_arg_telemetry → topic) + watchlist (Faz 4), user-facing trend cards (Faz 5), public/sellable API (Faz 6). Master plan §7. Algoritma iyileştirme: generic-entity stoplist/down-weight, entity snapshot persistence (kalıcı zaman-serisi), LLM entity özet/"neden trend", canonicalization Faz 2 (LLM toplu öneri → admin merge UI'ya besle).

## İlişkiler

- [[trend-unit-entity-centered]] — entity-merkezli birim kararı (LOCKED, #1518/#1520).
- [[entity-canonicalization-faz1]] — varyant birleştirme kararı (#1540); trend listesini canonical bazında gruplar.
- [[data-pipelines]] — Pipeline-3 (event_clusters + agenda_cards) bu fazın veri substratı; entities (NER) entity trend birimi.
- [[realtime-rss-polling]] — tazelik altyapısı (trend kalitesi için).
- Kaynak kod: `apps/api/app/api/admin_trends.py`, `apps/web/src/app/admin/trends/page.tsx`.

## Kaynaklar

- **Faz 1:** PR [#1503](https://github.com/selmanays/nodrat/pull/1503) · Issue [#1500](https://github.com/selmanays/nodrat/issues/1500) · main `c2f0b67`.
- **Faz 2:** Issue [#1505](https://github.com/selmanays/nodrat/issues/1505) (CLOSED) · PR [#1506](https://github.com/selmanays/nodrat/pull/1506) (migration) + [#1511](https://github.com/selmanays/nodrat/pull/1511) (worker) + [#1512](https://github.com/selmanays/nodrat/pull/1512) (read-path) · deploy.yml fix [#1508](https://github.com/selmanays/nodrat/pull/1508).
- **Entity pivot:** quick-fix [#1516](https://github.com/selmanays/nodrat/issues/1516)/[#1517](https://github.com/selmanays/nodrat/pull/1517) · entity MVP [#1518](https://github.com/selmanays/nodrat/issues/1518)/[#1519](https://github.com/selmanays/nodrat/pull/1519) · cluster path kaldırma [#1520](https://github.com/selmanays/nodrat/issues/1520)/[#1521](https://github.com/selmanays/nodrat/pull/1521) · karar [[trend-unit-entity-centered]].
- **Canonicalization + admin:** token-altküme [#1549](https://github.com/selmanays/nodrat/pull/1549) (#1548) · trend detail [#1553](https://github.com/selmanays/nodrat/pull/1553) (#1552) · admin merge/split [#1555](https://github.com/selmanays/nodrat/pull/1555) (#1554) · karar [[entity-canonicalization-faz1]].
- **Docs:** [api-contracts §6b](../../docs/engineering/api-contracts.md) + [data-model §13c](../../docs/engineering/data-model.md) (#1522).
- Kod: `app/modules/trends/` (models/aggregation/topic_assignment/tasks) · `app/api/admin_trends.py` (+ `/detail`) · `app/api/admin_entities.py` · FE `admin/trends/[key]` + `admin/entities/canonical`.
- Master plan: `~/.claude/plans/nodrat-i-in-kaynak-haberlerden-dazzling-walrus.md` §4/§5/§7 (Faz 2 data model + algoritma + rollout).
