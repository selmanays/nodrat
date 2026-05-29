---
type: topic
title: "T8-21 User+Session Split Mini-Plan"
slug: "t8-21-user-session-split-mini-plan"
status: planned
created: "2026-05-29"
updated: "2026-05-29"
github_issue: "https://github.com/selmanays/nodrat/issues/1087"
sources:
  - "wiki/topics/t8-model-relocation-mini-plan.md"
  - "wiki/topics/t7-7-deps-split-mini-plan.md"
  - "wiki/topics/refactor-pr-checklist.md"
  - "wiki/plans/modular-monolith-transition-master-plan.md§13"
tags: ["t8", "accounts", "user", "session", "model-relocation", "sub-pr-split", "modular-monolith"]
aliases: ["T8-21 user split", "User Session relocation"]
---

## TL;DR

**T8-21 = `User` + `Session` ORM `app/models/user.py` → `app/modules/accounts/models.py`.** T8 milestone closure'ın ilk + en büyük relocation'ı (**~27 DIRECT caller > 8** → shim-split). T7-7 (deps→accounts) ile **unblocked** (core/ artık User import etmez; accounts modülü auth/identity evi → models burada toplanır, deps.py yanına). **relationship `User.sessions ↔ Session.user`** (back_populates) → 2 class **birlikte** taşınır (mapper-safe; T8-10/T8-11 kanıtlı). **Split mekaniği:** `app/models/user.py` re-export **shim** (T7-7 paterni) → ≤8 batch DIRECT flip → shim sil. **R2 sinerjisi:** T7-7e'de `sources→accounts` açıldı → tüm modül caller'ları (sources/admin dahil) zaten LEGAL. Behavior-preserving; veri/migration/schema DEĞİŞMEZ.

## 1. Problem + amaç

`User` (auth/identity ana modeli; 150+ satır, KVKK consent alanları, TOTP, role/tier) + `Session` (refresh token oturumları; FK `users.id` CASCADE). T8 milestone closure'da `app/models/user.py` → `app/modules/accounts/models.py` (accounts modülü auth/identity kanonik evi; T7-7 ile `accounts/deps.py` zaten orada). Bu, accounts modülünü **deps + models** ile tamamlar.

**T7-7 ile unblocked:** Eskiden `core/deps.py` User import ediyordu → User taşınırsa `core/* must not import modules/*` ihlali. T7-7 deps'i accounts'a taşıdı + core/deps.py'yi sildi → core/ artık User'a bağlı değil. **Artık User serbestçe accounts'a taşınabilir.**

**Audit (2026-05-29, main `0cebc13`):**
- **Model:** `User` (CITEXT email unique; INET consent IP'leri; ARRAY totp_backup_codes; role/tier/locale) + `Session` (FK `users.id` CASCADE). **relationship `User.sessions` ↔ `Session.user`** (back_populates) → 2 class birlikte taşınır → mapper-safe. Vector YOK.
- **Hedef:** `modules/accounts/models.py` (accounts A-grubu değil ama `*.models` purge muafiyeti v93 `.models`'i kapsar → duplicate-registration riski yok).

## 2. Caller analizi (~27 DIRECT + facade)

**DIRECT path (`from app.models.user import`) — taşıma sonrası kırılır → flip gerek:**

| Grup | Dosyalar | Sayı |
|---|---|---|
| **api/admin** | admin_audit, admin_billing, admin_clusters, admin_dashboard, admin_queue, admin_rag, admin_system, admin_users (Session+User) | 8 |
| **api/app+auth** | _research_stream_context, app_consent, app_me (Session+User), app_research, app_research_stream, auth (Session+User), auth_2fa (Session+User), billing | 8 |
| **modules** | articles/admin/routes, billing/services/plan_features, legal/routes, media/admin/routes, prompts_admin/routes, settings_admin/routes, sft/admin/routes, sft/tasks/sft_curator, sources/admin/routes, style_profiles/routes | 10 |
| **legacy top-level** | email/service.py | 1 |
| **facade** | app/models/__init__.py (relocation PR'da flip) | 1 |
| **intra-module** | accounts/deps.py (relocation PR'da intra-module flip) | 1 |

**Contract durumu (DIRECT flip `→ app.modules.accounts.models`):** api→accounts LEGAL; **modules→accounts LEGAL** (accounts "parallel"; hiçbir modülün forbidden listesinde accounts yok — **sources dahil: T7-7e R2 ile sources strict-forbidden'dan çıkarıldı**); email/ legacy top-level (contract-dışı) LEGAL. → **Tüm flip'ler LEGAL.** Yalnız Session importu 4 caller'da (admin_users, app_me, auth, auth_2fa).

## 3. Split mekaniği — `app/models/user.py` re-export shim (T7-7 paterni)

Model relocation atomiktir (git mv user.py → accounts/models.py → eski dosya gider → 27 caller aynı anda kırılır). Caller>8 (≤8 sub-PR kuralı) için **shim**: `app/models/user.py` re-export edilir (`from app.modules.accounts.models import Session, User`). Bu LEGAL (app.models legacy facade katmanı zaten app.modules.*'tan re-export ediyor — poisoned __init__; per-file shim de aynı katman). Caller'lar shim üzerinden çalışır; ≤8 batch DIRECT flip → final PR shim'i siler.

> **Neden facade-path flip DEĞİL:** caller'ları `from app.models import User` (facade __init__) yapmak modül caller'ları için POISONED-transitive ihlal doğurur (sources/style_profiles → app.models → rag/generations YASAK; v78/T8-11). DIRECT (`from app.modules.accounts.models`) güvenli. Shim ise `app.models.user` (per-file, poisoned-__init__ TETİKLEMEZ — submodule) → tüm caller'lar için legal geçiş yolu.

## 4. Sub-PR sıralaması (≤8 dosya/PR)

| Sub-PR | Scope | Dosya | Risk |
|---|---|---|---|
| **T8-21a** ✅ **DONE v107** | git mv user.py → accounts/models.py + `app/models/user.py` re-export shim + facade __init__ flip + accounts/deps.py intra-module flip | 4 | **TAMAMLANDI** PR [#1370](https://github.com/selmanays/nodrat/pull/1370) `c4f5484`; User+Session+relationship birlikte; facade identity 3-path (facade/shim/direct=tek class); mapper User↔Session resolve; lint 16/16 (accounts→core.db Base LEGAL); module_init 9/9; TAM 1186; FULL deploy GREEN + SSH 13/13 + api healthy (auth import OK). **T8 16→17/22.** Shim sayesinde ~27 caller kırılmadı. |
| **T8-21b** ✅ **DONE v108** | api/admin ×8 DIRECT flip | 8 | **TAMAMLANDI** PR [#1372](https://github.com/selmanays/nodrat/pull/1372) `a5f4657`; mekanik flip (ruff --fix 8 I001); lint 16/16; 8 modül import OK; TAM 1186; FULL deploy GREEN + SSH 13/13. |
| **T8-21c** ✅ **DONE v109** | api/app+auth ×8 DIRECT flip | 8 | **TAMAMLANDI** PR [#1374](https://github.com/selmanays/nodrat/pull/1374) `326eb67`; mekanik flip (ruff --fix 6 I001); lint 16/16; 8 import OK; TAM 1186; FULL deploy GREEN. **16 api caller (b+c) TAM.** |
| **T8-21d** ✅ **DONE v110** | modules ×8 DIRECT flip (articles/admin, billing/plan_features, legal, media/admin, prompts_admin, settings_admin, sft/admin, sft/curator) | 8 | **TAMAMLANDI** PR [#1376](https://github.com/selmanays/nodrat/pull/1376) `d068d54`; hepsi →accounts LEGAL; ruff --fix 6 I001; lint 16/16; module_init 9/9; TAM 1186; FULL deploy GREEN. **23/27 caller flip TAM; kalan: sources/admin + style_profiles + email (T8-21e).** |
| **T8-21e** ✅ **DONE v111** | **FINAL:** kalan modules ×2 (sources/admin [R2 LEGAL], style_profiles) + email/service flip + `app/models/user.py` shim SİL | 6 | **TAMAMLANDI** PR [#1378](https://github.com/selmanays/nodrat/pull/1378) `6621179`; 3 flip + accounts/deps docstring + articles/README doc-ref + shim git rm; **5-form grep `app.models.user`=0** (import); lint 16/16; facade identity (shim YOK); mapper; module_init 9/9; TAM 1186; FULL deploy GREEN + SSH 11 healthy + container'da SHIM_YOK. **🏁 T8-21 TAM (5/5); accounts domain deps+models KOMPLE.** |

> Toplam ~5 sub-PR. T8-21a relocation+shim (substantive; milestone 16→17/22); b/c/d/e flip+cleanup. Her PR sonrası FULL deploy + SSH smoke + lint-imports.

## 5. relationship + mapper + veri güvenliği guard

- **relationship `User.sessions` ↔ `Session.user`** (back_populates, cascade): 2 class birlikte taşınır → mapper resolution korunur (T8-10 Conv+Message, T8-11 Source family kanıtlı; mapper_resolution 3/3 ön-şart).
- **Behavior-preserving:** pure ORM declaration move; **no migration, no schema change** (users/sessions tabloları + index + FK + CITEXT/INET/ARRAY tipleri AYNEN). raw-SQL caller'lar (varsa) tablo-adı-sabit → etkilenmez. **Veri YOK silme/truncate.**
- **facade identity:** `app.models.User is app.modules.accounts.models.User` (+ Session) → tek mapper instance.

## 6. Pre-flight matrisi (her sub-PR)

ruff + format / 5-form stale grep (`app.models.user` — T8-21e'de 0) / **lint-imports 16/16** / **mapper_resolution 3/3** (User↔Session relationship) / module_init 9/9 / **facade identity** (User+Session) / admin_rag collect / **TAM `pytest tests/unit/` 1186** / branch-CI-gated merge → FULL deploy watcher → SSH smoke → vNN closure. **Deploy public-smoke false-fail tekrarı (T7-7e/T8-15) → SSH ile health doğrula (functional success).**

## 7. Hard-stop kuralları

- import-linter 16/16 bozulursa DUR.
- relationship/mapper resolution bozulursa DUR (User↔Session birlikte taşınmalı).
- Veri/migration/schema değişimi ihtimali → DUR (yalnız ORM declaration move).
- ignore_imports YASAK.
- Caller flip sonrası lint-imports + ruff isort TEKRAR (T8-11/T7-7 dersi).
- Auth davranışı (User.role, consent alanları, Session FK) birebir korunur.

## İlişkiler

- [[t8-model-relocation-mini-plan]] — ana T8 planı (T8-21 satırı)
- [[t7-7-deps-split-mini-plan]] — T7-7 deps split (T8-21'i unblock etti; shim + R2 paterni)
- [[modular-monolith-boundary]] — R2 (sources→accounts) → T8-21 modül flip'lerini de açar
- [[refactor-pr-checklist]] — pre-flight + caller-flip + shim dersleri
- [[modular-monolith-transition-master-plan]] §13 — milestone

## Kaynaklar

- `apps/api/app/models/user.py` (User + Session; relationship; CITEXT/INET/ARRAY)
- `apps/api/app/modules/accounts/` (deps.py T7-7'de; models.py T8-21'de eklenir)
- `apps/api/pyproject.toml` `[[tool.importlinter.contracts]]` (accounts forbidden one-way; sources→accounts R2 ile açık)

## Açık sorular / TODO

- T8-21 sonrası accounts modülü **deps + models TAM** (auth/identity domain modülü tamamlanır).
- email (EmailVerificationToken/PasswordResetToken/EmailLog) da accounts'a → T8-21'den SONRA ayrı PR (auth-related; Base relocation gerekmez).
- accounts/__init__.py lazy (empty docstring) korunur; models.py `*.models` purge-muaf (v93).
