---
type: topic
title: "Phase 7a Frontend Mini Plan — src/lib/api.ts split strategy"
slug: "phase7a-frontend-mini-plan"
category: "playbook"
status: "live"
created: "2026-05-21"
updated: "2026-05-22"
progress: "8 PR DONE (PR-7a-0/1/2/3 + PR-7a-4 verifyResend mini + PR-7a-5 admin-users + PR-7a-6 admin-audit + PR-7a-7 admin-system); 29 char test cumulative; api.ts -255 LoC (2041 → 1786); 7 facade doğrulama; PR-7a-8 scope analizi sırada; Research deferred"
sources:
  - "apps/web/src/lib/api.ts"
  - "wiki/plans/modular-monolith-transition-master-plan.md§13"
  - "wiki/topics/refactor-pr-checklist.md"
tags: [phase-7a, frontend, refactor, modular-monolith, characterization, t6]
aliases: ["frontend-api-ts-mini-plan", "phase-7a-mini-plan"]
---

# Phase 7a Frontend Mini Plan — `src/lib/api.ts` split strategy

> **TL;DR:** Phase 7a `apps/web/src/lib/api.ts` (2041 LoC / 199 export / 60 caller dosyası / 94 unique sembol) god-file'ını backward-compatible facade pattern ile domain-bazlı parçalama planı. Frontend runtime test altyapısı YOK → önce PR-7a-0 test infra bootstrap; sonra public search / disk gibi en küçük caller'lı domain'lerden başlayarak research section'a kadar artan boyutta extract; `apiFetch` + `ApiException` ortak core olarak korunur.

## Bağlam

Backend Phase 4-6 (god-file refactor; 11 PR, 124 characterization test) tamamlandıktan sonra T6 [#1085](https://github.com/selmanays/nodrat/issues/1085) tracking listesindeki Phase 7a frontend `api.ts` parçalama planı. PR #1170 (P6 PR-A8 marker chars) closure scope analizinde frontend reality checkpoint istendi; bu sayfa kalıcı playbook olarak Phase 7a başlama hazırlığını dökümante eder.

**Master plan §13** Phase 7a tracking için [#1095](https://github.com/selmanays/nodrat/issues/1095) (api.ts split) issue açık. Backend refactor zinciri (P3-P6) doğrulanmış facade pattern + characterization-first disiplini frontend'e adapte edilir.

## Ana içerik

### A. `src/lib/api.ts` reality (snapshot 2026-05-21, post-PR #1170)

| Metrik | Değer |
|---|---|
| LoC | **2041** |
| Export count | **199** (function/interface/type/class) |
| Caller dosya | **60** (`@/lib/api` import eden TS/TSX) |
| Unique imported sembol | **94** |
| Test infra | **YOK** — frontend runtime unit/E2E test framework kurulu değil |
| Safety net | ESLint + `tsc --noEmit` strict + `next build` (compile-time only) |

**7 major domain bloğu** (section header'lara göre):

| Bölüm | LoC range | Tahmini boyut | Caller tipi |
|---|---|---|---|
| Core (`apiFetch` + `ApiException` + token storage) | L1-185 | ~185 | **Ortak** (TÜM caller'lar) |
| Auth (login/register/logout) | L185-256 | ~70 | 5 auth page |
| Sources (admin) | L256-431 | ~175 | Admin-only |
| Selector test + Config versioning | L431-539 | ~108 | Admin-only |
| **Public search** | L539-567 | **~28** | **1 caller (`/ara`)** |
| Articles | L567-716 | ~149 | Karma (admin + app overlap) |
| **Research (#793 Perplexity-style)** | L733-1424 | **~691** | **EN BÜYÜK** — user-facing + research domain |
| Message feedback + Legal + Admin Users + Queue + Audit + Clusters + `/me` + Admin RAG + Pipeline + Settings + Media + System + **Disk** | L961-2041 | ~1080 | Çoğunlukla admin; `/me` user; **Disk = 36 LoC / 1 caller** |

### B. Caller surface (60 dosya, domain bucket'lar)

| Bucket | Caller dosya sayısı | Notlar |
|---|---|---|
| Admin pages (`/admin/*`) | **24** | sources, articles, users, queue, audit, RAG, clusters, settings, media, system, disk, sft, prompts, legal, login |
| User pages (`/app/*`) | **11** | research (×2), style-profiles (×3), me, billing (×4) |
| Auth pages | 5 | login (admin), register, verify-email, forgot, reset |
| Public (`/ara`) | 1 | Public search |
| Components | 14+ | research/*, consent/*, legal/*, dashboard blocks, email-verify-banner |

**Top 5 imported sembol:**
- `type` (57× — TypeScript type-only imports yaygın)
- `ApiException` (40×)
- `apiFetch` (12×)
- `listSources` (4×)
- `getSource` (3×)

Kalan **89 sembol** ≤3 caller — uzun kuyruk dağılımı.

### C. Önerilen hedef yapı (facade pattern)

```
src/lib/api/
├── index.ts          # facade — re-export wrapper (api.ts'in yeni rolü; backward-compat)
├── _core.ts          # ApiException, apiFetch, token storage (L1-185)
├── auth.ts           # login/register/logout (L185-256)
├── sources.ts        # admin sources + config + selector test (L256-539)
├── articles.ts       # articles (L567-716)
├── research.ts       # research/conversations (L733-1424) — EN SONA
├── admin/
│   ├── users.ts
│   ├── queue.ts
│   ├── audit.ts
│   ├── clusters.ts
│   ├── rag.ts
│   ├── pipeline.ts
│   ├── settings.ts
│   ├── media.ts
│   ├── system.ts
│   ├── disk.ts
│   ├── legal.ts
│   └── sft.ts
├── me.ts             # KVKK self-service (L1343-1423)
└── public.ts         # public search (L539-567)
```

`src/lib/api.ts` mevcut role'ü **facade**: `export * from "./api/_core"; export * from "./api/auth"; …`. 60 caller dosyası `@/lib/api`'den import etmeye devam eder, **0 import path değişimi**.

### D. PR sırası önerisi

| Sıra | PR | İçerik | Tahmini boyut | Caller etkisi | Risk | Durum |
|---|---|---|---|---|---|---|
| **0** | **PR-7a-0** | **Test infra bootstrap** (Vitest + jsdom + en kritik 3-5 helper char test: `ApiException`, token storage, `apiFetch` min mock) | ~150 yeni satır (test+config) | 0 caller change | **Düşük** — safety net foundation | ✅ **DONE** ([#1172](https://github.com/selmanays/nodrat/pull/1172), 5 char test, Vitest 2.1.8 + jsdom 25.0.1) |
| 1 | PR-7a-1 | **Public search extract** (`publicSearch` + tipler) → `src/lib/api/public.ts` re-export | ~28 LoC taşıma | 1 caller (`/ara`) | **Çok düşük** | ✅ **DONE** ([#1173](https://github.com/selmanays/nodrat/pull/1173), facade pattern proof-of-concept; cumulative 7 test) |
| 2 | PR-7a-2 | **Admin Disk extract** (L2005-2041) | ~36 LoC | 1 caller (`/admin/system/disk`) | **Çok düşük** | ✅ **DONE** ([#1174](https://github.com/selmanays/nodrat/pull/1174), 54 LoC, state-changing `adminDiskCleanup` smoke skipped; cumulative 9 test) |
| 3 | PR-7a-3 | **Auth extract** (login/register/logout) | ~70 LoC | 5 auth pages | Düşük | ✅ **DONE** ([#1175](https://github.com/selmanays/nodrat/pull/1175), ~95 LoC + TypeScript same-file type-ref edge case fix; cumulative 13 test; auth action TETİKLENMEDİ) |
| 4 | PR-7a-4 | **`requestVerifyResend` mini-extract** (auth-domain misplaced helper) → `api/auth.ts` | 12 LoC | 2 caller (`/login`, email-verify-banner) | Çok düşük | ✅ **DONE** ([#1177](https://github.com/selmanays/nodrat/pull/1177), 95 LoC dosya 107'ye çıktı; cumulative 16 test; auth/email action TETİKLENMEDİ) |
| 5 | PR-7a-5 | **Admin Users extract** | ~90 LoC | 3 caller (`/admin`, `/admin/users`, `/admin/users/[id]`) | Düşük | ✅ **DONE** ([#1178](https://github.com/selmanays/nodrat/pull/1178), 137 LoC dosya; `buildQuery` non-exported kopya; cumulative 22 test; state-changing TETİKLENMEDİ) |
| 6 | PR-7a-6 | **Admin Audit extract** (read-only) | ~41 LoC | 1 caller (`/admin/audit`) | Çok düşük | ✅ **DONE** ([#1180](https://github.com/selmanays/nodrat/pull/1180), 83 LoC dosya; `buildQuery` non-exported kopya 2.; cumulative 26 test; read-only, state-changing yok) |
| 7 | PR-7a-7 | **Admin /system extract** (read-only) | ~77 LoC | 1 caller (`/admin/observability`) | Çok düşük | ✅ **DONE** ([#1181](https://github.com/selmanays/nodrat/pull/1181), 110 LoC dosya; 11 interface; buildQuery GEREK YOK; cumulative 29 test; read-only) |
| 8 | PR-7a-8 | **Scope analizi sırada** — 8 aday karşılaştırma (Admin Media/Legal/Settings/Account-Me/Queue/Articles/Sources/RAG) | TBD | TBD | TBD | 🔄 **SIRADA** (closure docs v14 sonrası) |
| ... | ... | Artan boyutta domain bucket'ları | | | | |
| Son | PR-7a-N | **Research extract** (~691 LoC) | En büyük | 11+ caller (research/*, components) | Yüksek — son sıra | ⏳ **DEFERRED** (SSE client coupling; backend P6 PR-A8 ile bağ) |

### E. Hard kurallar (Phase 7a süresince)

- **`apiFetch` + `ApiException`** ortak core — `_core.ts` extract en SON yapılmalı veya hiç ayrılmamalı; backward-compat re-export ile facade'da kalabilir.
- **60 caller import path'leri DEĞİŞMEZ** — facade `@/lib/api` üzerinden re-export şart.
- **Auth/session/token refresh behavior** sadece test ile değiştirilebilir; karmaşık concurrent 401 koruması var (L70-180).
- **SSE streaming** (`streamResearchMessage`): client-side SSE handling research extract sırasında özel test gerektirir; backend Phase 6 SSE replay testleri (PR #1160-#1168) ile entegre.
- **Component-level api caller** patternları (örn. `research/MessageActions.tsx`) refactor scope'a girer.
- **Production behavior change YOK**, API contract değişmez.

### F. Phase 7a açık sorular / blocker'lar

1. **Articles overlap:** Articles section (L567-716) admin'de mi sadece kullanılıyor yoksa app/research'te de paylaşılıyor mu? Detaylı caller breakdown PR-7a-N planlamadan önce yapılmalı.
2. **Test framework seçimi:** Vitest + jsdom önerisi var; ama package.json'a göre alternatifler (React Testing Library vs Vitest Components, MSW for fetch mocking) PR-7a-0 reality check'inde değerlendirilecek.
3. **Token storage karmaşıklığı:** `localStorage`-based (production'da httpOnly cookie ihtimal; #71 backlog). Token storage testleri jsdom-only çalışır.
4. **Re-export type-only imports:** `export type { ... } from "./..."` — TypeScript-aware syntax dikkat edilmesi gereken nokta.

## Çıkarımlar

1. **Backend refactor disiplini frontend'e aynen uygulanır** — facade pattern + characterization-first; ancak frontend'de safety net YOK, bu yüzden test infra (PR-7a-0) ilk önkoşul.
2. **En küçük güvenli ekstrakt = Public search** (28 LoC, 1 caller). Facade pattern proof-of-concept için ideal.
3. **Research section en sona** (691 LoC, 11+ caller, SSE client coupling) — backend P6 PR-A1...A8 zinciri tamamlandı; frontend benzer derinlik gerektirir.
4. **`apiFetch` + `ApiException` ASLA ayrılmaz** — facade'da kalır; tüm caller'ların ortak bağımlılığı.

## İlişkiler

- **Beslediği plan:** [[modular-monolith-transition-master-plan]] §13 Phase 7a
- **İlgili topic:** [[refactor-pr-checklist]] (backend pattern; frontend uyarlaması Phase 7a süresince eklenir)
- **Tracking issue:** [#1095](https://github.com/selmanays/nodrat/issues/1095) — api.ts split
- **Referans:** Backend Phase 4 PR-A (`#1144` extractor characterization, 15 test), Phase 6 PR-A8 (`#1170` marker chars, 15 test) — pure helper characterization patternları

## Açık sorular / TODO

- Test framework seçimi (Vitest vs Jest vs Bun test) PR-7a-0 reality check'inde kararlaştırılır.
- Articles overlap (admin-only mu, app-side caller var mı) PR-7a-3 öncesi netleştirilir.
- Research SSE client coupling testi için strateji (production `streamResearchMessage` consumer pattern incelenmeli) PR-7a-N öncesi planlanır.
- Component-level api caller refactoring (research/MessageActions.tsx, dashboard blocks vb.) ayrı bir sub-plan gerektirebilir.

## Kaynaklar

- [apps/web/src/lib/api.ts](../../apps/web/src/lib/api.ts) — refactor hedefi
- [wiki/plans/modular-monolith-transition-master-plan.md](../plans/modular-monolith-transition-master-plan.md) §13 — Phase 7a tracking
- [[refactor-pr-checklist]] — backend pattern (facade + characterization disiplini)
- [#1095](https://github.com/selmanays/nodrat/issues/1095) — Phase 7a api.ts split tracking issue
