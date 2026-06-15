---
type: topic
title: "Trend Intelligence — Admin Overview (Faz 1+2)"
slug: "trend-intelligence-admin-overview-2026-06"
status: live
created: 2026-06-15
updated: 2026-06-15
sources:
  - "apps/api/app/api/admin_trends.py"
  - "apps/web/src/app/admin/trends/page.tsx"
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
- **momentum:** `(cur-prev)/prev`; `prev=0 & cur>0 → null` ("yeni"/breaking).
- **source_diversity:** basit v1 proxy = `benzersiz_kaynak / toplam_haber` (clamp [0,1]).
- **credibility_score:** pencere içi `AVG(sources.reliability_score)`.
- **novelty_score:** recency, `0.5 ** (yaş_saat / 12)` (yarı-ömür 12sa).
- **trend_state:** deterministik `breaking | developing | stable | fading` (momentum + cur/prev). velocity-driven; `event_clusters.status` (lifecycle-driven) yalnız okunur, **asla yazılmaz** — tamamlayıcı.
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

## Faz 3+ (deferred)

Merge/split admin feedback + signal inbox (Faz 3), demand (search_arg_telemetry → topic) + watchlist (Faz 4), user-facing trend cards (Faz 5), public/sellable API (Faz 6). Master plan §7. Algoritma iyileştirme: centroid cosine matching (v1 entity-only), incremental centroid refine, LLM topic label/özet.

## İlişkiler

- [[data-pipelines]] — Pipeline-3 (event_clusters + agenda_cards) bu fazın veri substratı.
- [[realtime-rss-polling]] — tazelik altyapısı (trend kalitesi için).
- Kaynak kod: `apps/api/app/api/admin_trends.py`, `apps/web/src/app/admin/trends/page.tsx`.

## Kaynaklar

- **Faz 1:** PR [#1503](https://github.com/selmanays/nodrat/pull/1503) · Issue [#1500](https://github.com/selmanays/nodrat/issues/1500) · main `c2f0b67`.
- **Faz 2:** Issue [#1505](https://github.com/selmanays/nodrat/issues/1505) (CLOSED) · PR [#1506](https://github.com/selmanays/nodrat/pull/1506) (migration) + [#1511](https://github.com/selmanays/nodrat/pull/1511) (worker) + [#1512](https://github.com/selmanays/nodrat/pull/1512) (read-path) · deploy.yml fix [#1508](https://github.com/selmanays/nodrat/pull/1508).
- Kod: `app/modules/trends/` (models/aggregation/topic_assignment/tasks) · `app/api/admin_trends.py`.
- Master plan: `~/.claude/plans/nodrat-i-in-kaynak-haberlerden-dazzling-walrus.md` §4/§5/§7 (Faz 2 data model + algoritma + rollout).
