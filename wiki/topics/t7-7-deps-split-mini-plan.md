---
type: topic
title: "T7-7 Deps Split Mini-Plan"
slug: "t7-7-deps-split-mini-plan"
status: planned
created: "2026-05-29"
updated: "2026-05-29"
github_issue: "https://github.com/selmanays/nodrat/issues/1086"
sources:
  - "wiki/topics/t7-cost-tracker-core-consumer-cleanup-mini-plan.md§T7-7"
  - "wiki/topics/t8-model-relocation-mini-plan.md"
  - "wiki/topics/refactor-pr-checklist.md"
  - "wiki/plans/modular-monolith-transition-master-plan.md§13"
tags: ["t7", "deps", "core-consumer-cleanup", "accounts", "sub-pr-split", "modular-monolith", "auth"]
aliases: ["T7-7 deps split", "core/deps relocation", "accounts/deps"]
---

## TL;DR

**T7-7 = `app/core/deps.py` (FastAPI auth dependency'leri) → `app/modules/accounts/deps.py`.** T7 core-consumer cleanup'ın son + en büyük PR'ı (**24 import-site / 29 dosya**). Amacı: `core/deps.py:20 from app.models.user import User` edge'ini core/'dan çıkarmak → **T8-21 (User+Session → accounts/models.py) unblock** (deps, User'ı import eden TEK kalan core/ dosyası; diğeri cost_tracker→ProviderCallLog = T7-6). **İki sert problem:** (P1) **relocation atomiktir** (core→modules re-export stub yasak) → **re-export shim** (accounts→core LEGAL) ile çok-PR geçiş; (P2) **sources→accounts FORBIDDEN** (kernel strict-forbidden) ama `sources/admin/routes.py` `require_admin` (User'a bağlı auth gate) kullanıyor → raw-SQL'lenemez → **mimari karar** (R2 önerilen: contract refine). Behavior-preserving; auth enforcement birebir; veri/migration/schema DEĞİŞMEZ.

## 1. Problem + amaç

`core/deps.py` (159 satır) Nodrat'ın auth/role kernel'i: `get_current_user`, `require_admin`, `require_foreign_transfer_consent`, `get_client_ip`, `bearer_scheme`, `CURRENT_CONSENT_VERSION`. Tek model bağımlılığı **satır 20 `from app.models.user import User`** (get_current_user `select(User)` + döner `User`; require_admin `user.role` kontrol).

**T8-21 blocker zinciri:** T8-21 User+Session'ı `app/models/user.py` → `app/modules/accounts/models.py`'ye taşır. Sonra `app/models/user.py` facade olur (`from app.modules.accounts.models import Session, User`). O an `core/deps.py:20 → app.models.user (facade) → app.modules.accounts` zinciri oluşur → **`core/* must not import modules/*` İHLALİ**. (Submodule leaf import bugün GEÇİYOR çünkü `app.models.user` gerçek leaf model; facade'leşince zincir uzar — T8-21 sonrası kırılır.)

**Çözüm:** deps.py'yi core/'dan accounts/'a taşı → `from app.modules.accounts.models import User` **intra-module** (LEGAL). core/ artık User import etmez → T8-21 serbest.

**Audit (2026-05-29, main `a7d4985`):** core/ kalan `app.models` importları yalnız 2: `cost_tracker.py:35→ProviderCallLog` (T7-6 ayrı track; T8-7 ops modelleri unblock) + `deps.py:20→User` (bu PR). → **T7-7 tek başına T8-21'i tam unblock eder.**

## 2. Caller envanteri (24 import-site / 29 dosya)

### 2.1 `app/api/*` — 16 dosya (api → accounts LEGAL)

`admin_audit`, `admin_billing`, `admin_clusters`, `admin_dashboard`, `admin_queue`, `admin_rag`, `admin_system`, `admin_users`, `app_consent`, `app_me`, `app_research`, `app_research_stream`, `auth` (fonksiyon-içi import satır 213), `auth_2fa`, `billing`, `public_search`. İçe aktarılan: `require_admin` / `get_current_user` / `get_client_ip` / `require_foreign_transfer_consent` / `CURRENT_CONSENT_VERSION` kombinasyonları.

### 2.2 `app/modules/*` — 8 dosya

| Caller | import | accounts contract | Durum |
|---|---|---|---|
| `articles/admin/routes.py:30` | get_client_ip, require_admin | articles→accounts LEGAL | DIRECT flip |
| `legal/routes.py:34` | get_client_ip, require_admin | legal→accounts LEGAL | DIRECT flip |
| `media/admin/routes.py:28` | require_admin | media→accounts LEGAL | DIRECT flip |
| `prompts_admin/routes.py:30` | get_client_ip, require_admin | prompts_admin→accounts LEGAL | DIRECT flip |
| `settings_admin/routes.py:30` | get_client_ip, require_admin | settings_admin→accounts LEGAL | DIRECT flip |
| `sft/admin/routes.py:33` | get_client_ip, require_admin | sft→accounts LEGAL | DIRECT flip |
| `style_profiles/routes.py:31` | get_current_user | style_profiles→accounts LEGAL | DIRECT flip |
| `sources/admin/routes.py:36` | get_client_ip, require_admin | **sources→accounts FORBIDDEN** ⚠️ | **P2 — mimari karar** |

### 2.3 `tests/*` — 5 dosya

- **`tests/unit/test_module_init_lazy.py`** ⚠️ — `app.core.deps`'i **canary** olarak kullanıyor (`test_module_init_does_not_pull_core_deps`: modül paket-init'i eager `from .routes import router` ile auth zincirini yükledi mi?). **Relocation sonrası canary string `app.core.deps` → `app.modules.accounts.deps`** güncellenmeli (davranış-koruyan; A-grup laziness guard'ın özü). NOT: `_purge_cached_modules` `*.models` muafiyeti (v93) `…accounts.deps`'i etkilemez (`.deps` ≠ `.models`).
- `tests/unit/test_research_stream_{async_helpers,followups,helpers,tracked_chat_generate}.py` — sadece **açıklayıcı yorum** (`# app.api.app_research_stream → app.core.deps → app.core.security`). Kozmetik güncelleme (fonksiyonel patch YOK).

## 3. P1 — atomik relocation split mekaniği (re-export shim)

Relocation **atomiktir**: `core/deps.py` silinince tüm caller aynı anda kırılır; `core/deps.py`'de `from app.modules.accounts.deps import *` re-export stub'ı **`core/* must not import modules/*` ihlali** (yasak). Çözüm — **ters yön shim**: `accounts/deps.py` geçişte `core/deps.py`'den re-export eder (**accounts→core LEGAL**; hiçbir contract modules→core yasaklamaz). Caller'lar ≤8 batch'te accounts.deps'e flip edilir (davranış birebir — shim aynı objeleri re-export); final PR'da gerçek kod core→accounts taşınır + shim gerçeğe döner + core/deps.py silinir.

> **Shim contract kontrolü:** `accounts/deps.py → core.deps → app.models.user (leaf) + app.core.{db,security}`. accounts→core LEGAL; accounts→app.models.user LEGAL (business-modül değil; leaf). lint-imports 16/16 korunur.

## 4. P2 — sources→accounts contract blocker (mimari karar)

`sources/admin/routes.py` `require_admin` (5 route) + `get_client_ip` (4 yer) kullanıyor. `require_admin` → `get_current_user` → `select(User)` → User'a bağlı **auth gate**; T8-12a'daki count-query gibi raw-SQL'lenemez (FastAPI `Depends()` + dönüş tipi `User`). `sources → app.modules.accounts` **strict-forbidden** (kernel "any other domain" listesinde accounts var).

**Çözüm seçenekleri:**

| Opt | Yaklaşım | Artı | Eksi |
|---|---|---|---|
| **R1** | require_admin'i concrete User'dan decouple et, core/'da model-free auth surface bırak | contract dokunulmaz | get_current_user `select(User)` + dönüş `User` → ORM decouple çok zor; DI/registry = T7-6-tarzı redesign (HIGH) |
| **R2 (ÖNERİLEN)** | `app.modules.accounts`'ı sources strict-forbidden listesinden çıkar (yalnız accounts; business domain'ler yasak kalır) | temiz; master-plan-aligned (accounts "parallel" auth katmanı; business→accounts doğal yön); auth=cross-cutting infra, business-logic değil; tüm modüller admin route'unu in-module tutar | CI-enforced architectural contract refinement (security-adjacent; auth ENFORCEMENT değişmez) |
| **R3** | `sources/admin/routes.py`'yi `app/api/`'ye taşı (api→accounts LEGAL) | sources kernel saflığı korunur; contract dokunulmaz | sources'ı özel-vaka yapar (diğer modüller admin'i in-module tutuyor); routing refactor + main.py + canary modül listesi |

**Önerilen: R2.** Gerekçe (closure'da yazılacak): sources strict-forbidden contract'ı sources'ı **business domain**'lerden (articles/rag/generations) izole etmek için var — auth/identity katmanından değil. accounts master-plan'da "parallel" katman; her router'ın (kernel admin router'ları dahil) ihtiyaç duyduğu `require_admin` cross-cutting altyapıdır. accounts'ı yalnız sources-forbidden listesinden çıkarmak (business domain'ler yasak kalır) kernel-saflık niyetini korur (sources hâlâ business'a bağlanamaz) + auth'un cross-cutting doğasını kabul eder. **Auth enforcement birebir korunur** (require_admin super_admin gate aynen). → ayrı [[modular-monolith-boundary|boundary]] decision güncellemesi (mimari karar = ayrı decision sayfası).

> **Hard-stop:** R2 contract değişikliği yalnız **T7-7e (final sub-PR)** kapsamındadır. T7-7a..T7-7d (shim + 23 non-sources caller flip) contract'a dokunmaz — %100 otonom-güvenli ilerler. T7-7e'de R2 decision sayfası + rationale yazılır; eğer security-sınırı aşıyorsa kullanıcıya tek-soru olarak sunulur (data/schema/security/prod-health/irreversible guardrail).

## 5. Sub-PR sıralaması (≤8 dosya/PR)

| Sub-PR | Scope | Dosya | Risk |
|---|---|---|---|
| **T7-7a** ✅ **DONE v100** | `accounts/deps.py` re-export shim (`from app.core.deps import …`) | 1 dosya | **TAMAMLANDI** PR [#1357](https://github.com/selmanays/nodrat/pull/1357) `54b5f92`; 6 public sembol re-export (accounts/__init__ dokunulmadı — shim __init__ değişikliği gerektirmedi); lint-imports 16/16 (accounts→core LEGAL); shim identity 6/6; module_init 9/9 (canary etkilenmez); mapper 3/3; TAM 1186; FULL deploy GREEN + SSH 13/13. |
| **T7-7b** | api/admin_* caller flip → accounts.deps (admin_audit/billing/clusters/dashboard/queue/rag/system/users) | 8 | LOW (api→accounts LEGAL; shim davranış birebir) |
| **T7-7c** | api/ app+auth caller flip (app_consent/app_me/app_research/app_research_stream/auth/auth_2fa/billing/public_search) | 8 | LOW |
| **T7-7d** | non-sources modül caller flip (articles/legal/media/prompts_admin/settings_admin/sft/style_profiles) | 7 | LOW (hepsi →accounts LEGAL) |
| **T7-7e** | **FINAL:** gerçek kod core→accounts taşı (shim→real) + **R2 contract refine** + sources/admin flip + core/deps.py SİL + **canary test güncelle** (`app.core.deps`→`app.modules.accounts.deps`) + research_stream yorum güncelle | ~6-9 | **MED-HIGH** (P2 mimari karar; canary guard; atomik delete) |

> Toplam ~5 sub-PR. T7-7a..d (23/24 caller) otonom; T7-7e P2/contract/canary'yi taşır. Her PR sonrası FULL deploy + SSH smoke + lint-imports tekrar.

## 6. Pre-flight matrisi (her sub-PR)

ruff + format / 5-form stale grep (`app.core.deps` import — T7-7e'de 0 olmalı) / **lint-imports 16/16** (T7-7e: sources→accounts R2 sonrası temiz; accounts→core LEGAL) / mapper_resolution 3/3 / **module_init_lazy 9/9** (T7-7e canary güncellemesi sonrası) / admin_rag collect / **TAM `pytest tests/unit/` 1186** / branch-CI-gated merge → FULL deploy watcher → SSH smoke → vNN closure.

## 7. Hard-stop kuralları (T7-7 boyunca)

- import-linter 16/16 bozulursa DUR (T7-7a..d shim/flip sırasında AYNEN korunmalı; yalnız T7-7e R2 ile sources→accounts açılır).
- **Auth davranışı değişirse DUR** — require_admin (super_admin gate) + get_current_user (401/403 case'leri) + foreign_transfer_consent (KVKK m.9 gate) birebir korunur; behavior-preserving relocation.
- `_purge_cached_modules` canary (`test_module_init_lazy`) bozulursa DUR — T7-7e'de string güncellemesi + 9/9 doğrula.
- ignore_imports YASAK (P2 çözümü R2 contract refine = boundary tanımı, per-line suppress değil; veya R1/R3 behavior-preserving).
- Caller flip sonrası lint-imports TEKRAR (T8-11 dersi).
- get_client_ip (model-free) accounts/deps'e taşınır (R2 kapsar) veya shared/'a alınabilir — basitlik için accounts/deps.

## İlişkiler

- [[t7-cost-tracker-core-consumer-cleanup-mini-plan]] — T7 ana planı (T7-7 satırı; bu mini-plan onu süpersede eder: sources blocker + atomik split eklendi)
- [[t8-model-relocation-mini-plan]] — T8-21 (User+Session) bu PR ile unblock olur
- [[refactor-pr-checklist]] — pre-flight + canary + caller-flip dersleri
- [[modular-monolith-boundary]] — R2 contract refine decision (T7-7e'de güncellenecek)
- [[modular-monolith-transition-master-plan]] §13 — milestone

## Kaynaklar

- `apps/api/app/core/deps.py` (159 satır; auth/role kernel; satır 20 User import)
- `apps/api/pyproject.toml` `[[tool.importlinter.contracts]]` (sources strict-forbidden + accounts forbidden + core→modules)
- `apps/api/tests/unit/test_module_init_lazy.py` (`app.core.deps` canary)
- docs/engineering/threat-model.md §2 (authn/z) + docs/engineering/api-contracts.md §0/§16.3

## Açık sorular / TODO

- **P2 R2 onayı (T7-7e):** sources strict-forbidden listesinden `app.modules.accounts` çıkarımı — security-adjacent contract refinement; T7-7e'de decision sayfası + rationale; gerekirse tek-soru ask.
- T7-7e sonrası **T8-21** (User+Session → accounts/models.py) artık unblock — ayrı PR (28 caller potansiyeli; kendi pre-PR audit'i; relationship User↔Session kontrolü).
- `get_client_ip` nihai konum: accounts/deps (R2 kapsar) vs shared/http util — basitlik için accounts; gerekirse sonradan shared'a.
