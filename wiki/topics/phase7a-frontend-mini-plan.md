---
type: topic
title: "Phase 7a Frontend Mini Plan — src/lib/api.ts split strategy"
slug: "phase7a-frontend-mini-plan"
category: "playbook"
status: "live"
created: "2026-05-21"
updated: "2026-05-22"
progress: "20 PR DONE (PR-7a-0..16c + PR-7a-17 admin-clusters); 84 char test cumulative; api.ts -934 LoC (2041 → 1107, ~%46); 17 facade doğrulama; küçük read-only domain'ler bitti; api/admin/clusters.ts (2 if + listClusters read-only); kalan: Admin RAG (#189 ~377 LoC) 18a read-only + 18b trigger split + Research+feedback+SSE (EN SONA) + createConfig cleanup; PR-7a-18a Admin RAG read-only sırada; Research deferred"
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
| 8 | PR-7a-8 | **Admin Media extract** (1 state-changing smoke-skip) | ~70 LoC | 1 caller (`/admin/media`) | Düşük | ✅ **DONE** ([#1183](https://github.com/selmanays/nodrat/pull/1183), 112 LoC dosya; reprocessMedia VLM trigger smoke-skip; cumulative 33 test) |
| 9 | PR-7a-9 | **buildQuery shared `_query.ts` housekeeping** | +42/-61 | 4 import site (api.ts + 3 admin) | Çok düşük | ✅ **DONE** ([#1184](https://github.com/selmanays/nodrat/pull/1184), 4 kopya → 1 leaf helper; +0 test; pure refactor) |
| 10 | PR-7a-10 | **Legal admin extract** (1 state-changing smoke-skip) | ~71 LoC | 3 caller | Orta (legal compliance) | ✅ **DONE** ([#1186](https://github.com/selmanays/nodrat/pull/1186), 103 LoC dosya; updateTakedownRequest smoke-skip; buildQuery shared'ı tüketen ilk extract; cumulative 41 test) |
| 11 | PR-7a-11 | **Admin Articles extract** (1 state-changing smoke-skip) | ~149 LoC | 3 admin caller | Düşük | ✅ **DONE** ([#1187](https://github.com/selmanays/nodrat/pull/1187), 198 LoC dosya; 11 interface + 1 type + 6 fonksiyon; reprocessArticle smoke-skip; getMyQuota DOKUNULMADI; cumulative 44 test) |
| 12 | PR-7a-12 | **getMyQuota mini-extract** → YENİ `api/account.ts` | ~12 LoC | 1 app caller | Çok düşük | ✅ **DONE** ([#1189](https://github.com/selmanays/nodrat/pull/1189), 40 LoC dosya; read-only `/app/quota`; cumulative 46 test) |
| 13 | PR-7a-13 | **Account/Me extract** → mevcut `api/account.ts` (birleşik) | ~68 LoC | 1 caller (`/app/me`) | Orta-düşük (deleteMe/exportMe smoke-skip) | ✅ **DONE** ([#1190](https://github.com/selmanays/nodrat/pull/1190), 4 interface + 4 fonksiyon; updateMe/exportMe/deleteMe smoke-skip; PII/deletion YOK; cumulative 52 test) |
| 14 | PR-7a-14 | **Admin Settings extract** (2 state-changing smoke-skip) | ~85 LoC | admin settings caller | Düşük (runtime config) | ✅ **DONE** ([#1192](https://github.com/selmanays/nodrat/pull/1192), 85 LoC dosya; adminSettingUpdate/adminSettingReset smoke-skip; **adminSettingReset DELETE method** korundu (scope POST varsayımı düzeltildi); runtime config canlı DEĞİŞMEDİ; cumulative 56 test) |
| 15 | PR-7a-15 | **Admin Queue extract** (5 state-changing smoke-skip) | ~145 LoC | 2 caller (`/admin`, `/admin/queue`) | Düşük (manuel task trigger smoke-skip) | ✅ **DONE** ([#1194](https://github.com/selmanays/nodrat/pull/1194), 178 LoC dosya; 9 interface + 8 fonksiyon; 3 read-only + 5 state-changing; **`runMaintenanceNow` manuel maintenance task trigger** + retry/bulk/resolve smoke-skip; buildQuery shared; cumulative 65 test) |
| 16a | PR-7a-16a | **Admin Sources core extract** (Part 1/3; 3 state-changing + 2 dış-çağrı smoke-skip) | ~164 LoC | 6 caller (`/admin`, sources list/new/[id]/test-selectors/configs) | Düşük | ✅ **DONE** ([#1196](https://github.com/selmanays/nodrat/pull/1196), YENİ `api/admin/sources.ts` 200 LoC; 11 type/if + 7 fn — listSources/getSource read-only + createSource/activateSource/updateSource state-changing + testFeed/robotsCheck dış-çağrı smoke-skip; selector+config+`createConfig` inline; buildQuery shared; cumulative 73 test) |
| 16b | PR-7a-16b | **Admin Sources selector test extract** (Part 2/3) → mevcut `api/admin/sources.ts` | ~62 LoC | 1-2 caller (`/admin/sources/[id]/test-selectors`) | Düşük (testListing dış-çağrı smoke-skip) | ✅ **DONE** ([#1198](https://github.com/selmanays/nodrat/pull/1198), 4 interface + 2 fonksiyon → sources.ts 200→267 LoC; `testListing` POST outbound + `sourceExtractionStats` GET read-only; testListing smoke-skip; cumulative 77 test) |
| 16c | PR-7a-16c | **Admin Sources config versioning extract** (Part 3/3, son) → mevcut `api/admin/sources.ts` | ~44 LoC | 1 caller (`/admin/sources/[id]/configs`) | Düşük | ✅ **DONE** ([#1200](https://github.com/selmanays/nodrat/pull/1200), 2 interface + 3 fonksiyon; `listConfigs` read-only + `createConfig` 0-caller dead-code KORUNDU + `rollbackConfig` DB write; create/rollback smoke-skip; **Admin Sources TAM** → sources.ts 321 LoC / 12 fn; cumulative 81 test) |
| 17 | PR-7a-17 | **Admin clusters extract** (#1028; saf read-only) | ~33 LoC | 1 caller (`/admin/clusters`) | Çok düşük | ✅ **DONE** ([#1202](https://github.com/selmanays/nodrat/pull/1202), YENİ `api/admin/clusters.ts` 57 LoC; 2 interface + `listClusters` GET; buildQuery shared; state-changing yok; cumulative 84 test) |
| 18a | PR-7a-18a | **Admin RAG read-only observability extract** (#189 Part 1/2) → YENİ `api/admin/rag.ts` | ~250 LoC | 1 caller (`/admin/rag`) | Düşük | 🔄 **SIRADA** (closure docs v23 sonrası; 9 read-only GET fn + ~24 if; trigger'lar 18b) |
| 18b | PR-7a-18b | **Admin RAG trigger/pipeline extract** (#189 Part 2/2) → `api/admin/rag.ts` | ~130 LoC | 1 caller | Düşük (3 trigger smoke-skip) | ⏳ **PLANLI** (`ragBenchmarkRun`/`ragRaptorTrigger`/`ragInspectQuery` — benchmark/RAPTOR/pipeline; prod'da TETİKLENMEZ) |
| Son | PR-7a-N | **Research + message-feedback + `streamResearchMessage` SSE cluster** (~225 LoC) | En son | 6 caller (research/* + feedback) | Yüksek — son sıra | ⏳ **DEFERRED** (SSE client coupling / ReadableStream; backend P6 PR-A8 ile bağ; sona yaklaşıldı) |

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
