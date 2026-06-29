---
type: plan
title: "Otomasyon Stüdyosu — Master Plan (Faz 5)"
slug: automation-studio-master-plan
status: live
created: 2026-06-27
updated: 2026-06-27
sources:
  - "wiki/decisions/global-research-cluster-model.md"
  - "wiki/decisions/import-direction-rules.md"
  - "wiki/topics/architecture-final-state-2026-05.md§3"
tags:
  - automation
  - kume-abonelik
  - master-plan
  - faz5
  - social-sharing
  - kvkk
aliases:
  - otomasyon-studyosu
  - automation-studio
  - faz-5
---

# Otomasyon Stüdyosu — Master Plan (Faz 5)

> **TL;DR:** Founder vizyon merdiveninin **tepe basamağı**: _sor → küme abonesi ol → **otomasyona ekle**_. Kullanıcı abone olduğu **kümeye** bir **kural** koyar; küme `breaking`/`developing` trend-state'ine girince → **oto-kaynaklı artefakt** üretilir → **onay kuyruğu** → (opsiyonel) **sosyal paylaşım**. 6 alt-faza bölünmüş: **5.0 şema ✅** (iskele) → **5.1 tetik+kuyruk ✅** (ayrı beat) → **5.2 oto-içerik ✅** (5.2a research_runner çekirdek + 5.2b içerik işlemcisi; ikisi de no-op) → **5.3 stüdyo UI+onay ✅** (5.3a API + 5.3b frontend) → 5.4 sosyal OAuth+paylaşım (**en son, en sıkı kapı**). Her faz **additive + flag-gated default OFF → deploy = no-op**. 5.2 founder kararı **B: paylaşılan bileşenler** (canlı SSE research yolu DEĞİŞMEZ; runner aynı yapı-taşlarını çağırır). **5.3 sonrası: backend + UI TAM, yalnız sosyal-paylaşım (5.4) + canary kaldı.**

## Bağlam

Bu plan [[global-research-cluster-model|küme-abonelik modeli]] merdiveninin son halkasıdır. Ayrı bir "kural motoru" gerekmez: **trend-state'in kendisi tetikleyicidir** (mevcut [[trend-unit-entity-centered|trend-intelligence]] altyapısı `breaking`/`developing` tespitini abone kümeler için zaten yapıyor — [[trend-intelligence-admin-overview-2026-06|trend-intelligence]]). Otomasyon = aynı tespit → kullanıcının `automation_rules`'ı varsa kuyruğa koşum ekle.

Otomasyon **üst-katman orkestratör**dür: `generations` (artefakt) + `trends` (trend-state) + `clusters` + abonelik okur, ama **kimse onu import etmez** (ops deseni). Bunu [[import-direction-rules]] **17. contract** zorlar (`domain → automation` forbidden).

## Founder ilkeleri (kilitli)

- **Onay kuyruğu VARSAYILAN** — `mode='approval_queue'`. Tam-otomatik (`full_auto`) **opt-in** + çoklu-kapı.
- **Kaynaksız ASLA oto-paylaşma** — 0-cited yanıtta artefakt üretilmez/paylaşılmaz (#1754 invariant'ının otomasyona taşınması).
- **Sosyal paylaşım + OAuth = en son faz + en sıkı kapı** (Claude-güvenlik: public-post + OAuth = açık-izin sınıfı).
- **KVKK:** token Fernet-şifreli + revocable; user→CASCADE soft-delete; veri-export kapsamı.

### Açık kararlar — founder yanıtları (2026-06-26, kilitli)

| Karar | Yanıt |
|---|---|
| Oto-içerik üretim yolu | **A: `research_runner` refactor** (mevcut research pipeline'ını paylaşılır servise çıkar; #1754 kaynak-disiplini korunur) |
| Tam-otomatik (`full_auto`) | **Yeteneği kur, default KAPALI** (build-but-OFF; flag + opt-in) |
| Kota | **Kotaya tabi** (otomasyon koşumları generation kotasını tüketir; mevcut `quota.py enforce_quota` deseni) |
| İlk sosyal platform | **X (Twitter)** ilk (`provider='x'`; genişletilebilir) |
| Tetik koşulu | **breaking-only** (ilk sürümde yalnız `breaking`; `developing` sonra) |

## Fazlar

| Faz | Başlık | Teslim | Flag (default OFF) | Deploy no-op gerekçe | Durum |
|---|---|---|---|---|---|
| **5.0** | **Şema iskelesi** | 3 tablo (`social_accounts`, `automation_rules`, `automation_runs`) + 17. import contract + master flag | `automation.enabled` | Hiçbir okuyucu/yazıcı kod yok; tablolar boş; flag OFF | ✅ **CANLI** (#1779/[#1780](https://github.com/selmanays/nodrat/pull/1780)) |
| **5.1** | **Tetik + kuyruk** | **AYRI** automation beat (boundary: `trends→automation` yasak → hook değil): aktif kural × kümesi `breaking` → idempotent `automation_runs` enqueue (`queued`) | `automation.triggers.enabled` | Çift flag-gate (master + triggers) default OFF + 0 kural → beat erken-return, yazmaz | ✅ **CANLI** (#1782/[#1783](https://github.com/selmanays/nodrat/pull/1783)) |
| **5.2** | **Oto-içerik** | **B: paylaşılan bileşenler** (canlı SSE yolu değişmez). **5.2a ✅** (#1785): `research_runner.py` non-streaming çekirdek. **5.2b ✅** (#1788): `content.py` işlemci — queued koşum claim (FOR UPDATE SKIP LOCKED + kural-revalidation) → consent/kota kapıları → runner → kaynaksız→`skipped_no_sources` → artefakt `origin='automation'`→`pending` | `automation.content.enabled` (**davranış-canary**) | çift flag OFF + 0 kural → no-op | ✅ **CANLI** (flag-flip canary founder onayı bekler) |
| **5.3** | **Stüdyo UI + onay** | **5.3a ✅** (#1791): `app/me/automation/*` API (kural CRUD + onay-kuyruğu approve/reject) + feed-gizleme. **5.3b ✅** (PR#1794): `/app/automation` UI — kural-kurucu + onay-kuyruğu (Next.js/shadcn Tabs/Select), flag-off→"henüz aktif değil"; nav linki canary'de | `automation.studio.enabled` | flag OFF → 403/UI gizli; nav linki yok | ✅ **CANLI** (canary founder onayı bekler) |
| 5.4 | Sosyal OAuth + paylaşım | X OAuth bağlama (token Fernet) + onaylı koşumu paylaş; rate-limit + audit; kaynaksız-asla hard-invariant | `automation.social.enabled` | Ayrı epic + docs/legal; bağlı hesap yokken no-op | 🔜 planlı (**en sıkı kapı**, ayrı epic) |

> Her faz bağımlılığı bir öncekine. 5.4'ten önce 5.0-5.3 zincirinin tamamı + ayrı KVKK/güvenlik review'i şart.

## Faz 5.0 şeması (canlı)

`app/modules/automation/models.py` — model ownership modül içinde. FK sırası `social_accounts → automation_rules → automation_runs`.

- **`social_accounts`** (5.4'e kadar BOŞ): `id`, `user_id→users CASCADE`, `provider CHECK('x')`, `provider_user_id`, `handle`, `access_token`/`refresh_token` (**LargeBinary, Fernet**), `token_expires_at`, `scopes`, `status CHECK(connected/revoked/error)`, zaman damgaları, `revoked_at`. Partial-unique `(user_id, provider) WHERE revoked_at IS NULL` (tek canlı hesap/sağlayıcı).
- **`automation_rules`**: `id`, `user_id→users CASCADE`, `cluster_id→research_clusters RESTRICT`, `trigger_config JSONB`, `action_config JSONB`, `mode CHECK(approval_queue/full_auto)` default `approval_queue`, `social_account_id→social_accounts SET NULL`, `status CHECK(active/paused/disabled)`, `enabled` default `false`, `last_triggered_at`, soft-delete `deleted_at`. Partial-unique `(user_id, cluster_id) WHERE deleted_at IS NULL` (**küme başına tek canlı kural**).
- **`automation_runs`**: `id`, `rule_id→automation_rules CASCADE`, `cluster_id→research_clusters RESTRICT`, `status CHECK(queued/pending/skipped_no_sources/skipped_quota/skipped_no_consent/posted/rejected/failed)`, `artifact_id→artifacts SET NULL`, `dedupe_key UNIQUE` (idempotency: rule+küme+gün), `error`, `triggered_at`, `reviewed_at`. Index `(rule_id, created_at DESC)`.

FK ondelete mantığı: `user→CASCADE` (KVKK), `cluster→RESTRICT` (paylaşımlı global düğüm korunur — [[global-research-cluster-model]]), `social_account→SET NULL`, `artifact→SET NULL` (run izi kalır).

**Prod doğrulaması (2026-06-27):** alembic head `20260626_0100`; 3 tablo var + **0 satır**; 6 CHECK/unique + 3 partial/expression index; api image swap MODULE_OK; no-op (yalnız `app/models/__init__.py` kaydı).

## Faz 5.1 — tetik beat'i (canlı)

`app/modules/automation/tasks/triggers.py` — `dispatch_automation_triggers` celery beat (saatlik dk:45, `event_queue`; aggregate :20 + alerts :35 sonrası).

**Mimari:** import-linter 17. contract `trends → automation` YASAK → trend-alert beat'ine hook takılamaz; bu **AYRI** bir automation beat (`automation → trends` OKUR). trend-state **CANLI** okunur (`trend_metrics_for_clusters` — [[trend-intelligence-admin-overview-2026-06|alerts]] ile aynı yol; snapshot worker flag'inden bağımsız).

**Çekirdek (`_dispatch_for_session`):** aktif kuralları (`enabled AND status='active' AND deleted_at IS NULL`, kümesi `deprecated_at IS NULL`) çek → kuralları `trigger_config.window_seconds`'a göre grupla → pencere başına tek `trend_metrics_for_clusters` → kümenin `trend_state ∈ trigger_config.states` (default `{breaking}` — founder breaking-only) ise `automation_runs`'a `queued` koşum (`INSERT ... ON CONFLICT (dedupe_key) DO NOTHING`). dedupe_key `<rule>:<cluster>:<gün-UTC>` (rule+küme+gün başına tek). **Günlük cap** (`DAILY_CAP_PER_USER=50`) — beat-yerel değil GERÇEK günlük: `per_user` bugünkü koşumlardan tohumlanır (saatlik beat'ler arası maliyet tavanı). Koşum üretilince `last_triggered_at` güncellenir.

**Çift flag-gate (`_dispatch_async`):** `automation.enabled` (master) + `automation.triggers.enabled` (operasyonel), ikisi de default OFF → beat erken-return (`skipped`), DB'ye yazmaz. Kural-kurma UI'ı (5.3) henüz yok → 0 kural → zaten no-op.

**Durum-makinesi:** `queued` (bu beat) → [5.2 oto-içerik] `pending` (onay kuyruğu) → [5.3 onay] `posted` | `rejected` | `skipped_*` | `failed`.

**13-ajan 3-mercek çekişmeli review:** 7 doğrulanan bulgu (hepsi low/test-gap; correctness bug yok) → DAILY_CAP gerçek-günlük yapıldı + 4 test boşluğu kapatıldı (paused/çoklu-pencere/m-is-None/günlük-cap).

**Prod doğrulaması (2026-06-27):** triggers modülü image'da; beat `dispatch-automation-triggers` kayıtlı (crontab `45 * * * *`); route `tasks.automation.*`→event_queue; iki flag yok (default OFF); `automation_runs`=0; /health 200 → **no-op**.

## Faz 5.2 — oto-içerik (canlı)

Founder kararı **B: paylaşılan bileşenler** (6-ajan keşif + risk-kararı çekişmeli sunumu) — canlı SSE orkestratörü `_research_stream_body` (~900 satır, ürünün kalbi) **DEĞİŞMEZ**.

- **5.2a `app/modules/generations/research_runner.py`** (#1785): `run_cluster_research(db,*,user,query,now)` non-streaming çekirdek; canlı yolla AYNI yapı-taşları (`SEARCH_NEWS_TOOL`+`execute_search_news` retrieval kalite makinesi · `_tracked_chat_generate` LLM+cost-log · `_cited_numbers` cited-only). Kompakt tek-tur-zorlamalı tool-loop; KAYNAKSIZ→`skipped_no_sources`. Artefakt/kota/consent YOK.
- **5.2b `app/modules/automation/tasks/content.py`** (#1788): `process_automation_content` beat (saatlik dk:50). Tek-koşum **atomik claim** (`FOR UPDATE OF r SKIP LOCKED` → at-most-once) + **kural-revalidation** (enabled+active+deleted_at IS NULL + rc.deprecated_at; triggers paritesi) + **consent** (claim-anında taze, KVKK) → **kota** (`get_quota_status.exceeded`) → research_runner → kaynaksız→`skipped_no_sources` → artefakt `origin='automation'` + `record_usage` → koşum `pending`. research+artefakt **savepoint-izole** (hata kısmi işi geri alır, claim'i değil); per-koşum commit.
- **`artifacts.origin`** kolonu (`'interactive'`|`'automation'`, additive `20260627_0100`, CHECK NOT VALID+VALIDATE zero-downtime).
- **22-ajan 4-mercek çekişmeli review** (17 bulgu; medium'lar giderildi: kural-revalidation · consent-TOCTOU · claim-lock · zero-downtime CHECK · flag-gate testi).
- Skip durumları: `skipped_no_consent` · `skipped_quota` · `skipped_no_sources` · `failed`.

**Prod doğrulaması (2026-06-27):** head `20260627_0100`; origin kolonu+CHECK, 41 satır backfill `interactive`; content beat kayıtlı (dk:50); çift flag OFF; automation_runs=0, automation-origin artefakt=0; /health 200 → **no-op**.

## Güvenlik invariantları (sonraki fazlarda zorlanır)

1. **Kaynaksız asla** — 0-cited artefakt üretilmez/paylaşılmaz.
2. **Onay-kuyruğu varsayılan** — full-auto opt-in + çoklu-kapı.
3. **Token gizli** — Fernet-şifreli `bytea`; plaintext saklanmaz/loglanmaz; revocable.
4. **User-scoped + soft-delete** — KVKK opt-out izi; user silinince CASCADE.
5. **Küme bütünlüğü** — `cluster_id RESTRICT`; paylaşımlı küme silinemez.
6. **Idempotency** — `dedupe_key` UNIQUE; aynı rule+küme+gün tek koşum.
7. **Sosyal paylaşım = açık-izin sınıfı** — OAuth kullanıcının sağlayıcı UI'ında; rate-limit + audit; en son faz.

## Reuse noktaları (5.1+)

- Trend tetik: `app/modules/trends/` `detect_trend_alerts` beat + `trend_state` ([[trend-intelligence-admin-overview-2026-06|trend-intelligence]]).
- Abonelik: `app/modules/generations/subscriptions.py` (`user_cluster_subscriptions`).
- Artefakt: `app/modules/generations/artifacts.py` (`create_artifact_with_revision`) + `followup.py`/`artifact_quick_actions.py` (v4-flash + best-effort cost-log).
- Altyapı: celery beat, `settings_store` + `SETTING_REGISTRY` (admin UI), KVKK desenleri (consent, soft-delete).

## İlişkiler

- **Üst vizyon:** [[global-research-cluster-model|küme-abonelik modeli]] (merdivenin tepesi)
- **Boundary:** [[import-direction-rules]] (17. contract) · [[modular-monolith-boundary]] · [[architecture-final-state-2026-05]]
- **Tetik altyapısı:** [[trend-intelligence-admin-overview-2026-06|trend-intelligence]] · [[trend-unit-entity-centered]]
- **Küme modeli:** [[global-research-cluster-model]]
- **Kaynak-disiplini:** [[research-cited-only-hard-invariant]] / #1754

## Kaynaklar

- [apps/api/app/modules/automation/models.py](../../apps/api/app/modules/automation/models.py) — 3 ORM model
- [apps/api/alembic/versions/20260626_0100_automation_scaffold.py](../../apps/api/alembic/versions/20260626_0100_automation_scaffold.py) — Faz 5.0 migration
- [apps/api/pyproject.toml](../../apps/api/pyproject.toml) `[tool.importlinter]` — 17. contract
- GitHub: [#1779](https://github.com/selmanays/nodrat/issues/1779) · PR [#1780](https://github.com/selmanays/nodrat/pull/1780)
