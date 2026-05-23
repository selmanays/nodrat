---
type: topic
title: "Phase 7b admin/sft/page.tsx — Mini-plan"
slug: "phase7b-admin-sft-mini-plan"
status: live
created: 2026-05-23
updated: 2026-05-23
sources:
  - "wiki/plans/modular-monolith-transition-master-plan.md§9"
  - "wiki/plans/modular-monolith-transition-master-plan.md§13"
  - "wiki/topics/phase7b-admin-queue-mini-plan.md"
  - "wiki/topics/phase7b-admin-rag-mini-plan.md"
tags: [phase7b, refactor, frontend, admin-sft, mini-plan, done]
aliases: [phase7b-sft-mini-plan, admin-sft-mini-plan]
---

> **Durum (2026-05-23 SON):** 3 PR (PR-7d-0..closure) TAMAMLANDI. `apps/web/src/app/admin/sft/page.tsx` 1026 → **896 LoC** (-130 net, ~%12.7 küçülme). 7 helper sembol `_shared.tsx` (180 LoC) dosyasına ayrıldı. Vitest 107/107 sabit. Production smoke 4-route 200 + 13/13 healthy + ZERO error. Section split DEFERRED (admin/queue ile aynı karar). **alt-track 3/4 DONE** — research components son alt-track.

# Phase 7b — `apps/web/src/app/admin/sft/page.tsx` mini-plan

## TL;DR

`apps/web/src/app/admin/sft/page.tsx` **1026 LoC / single AdminSftPage component**. T6 #1085 dışı; Phase 7b umbrella ([#1096](https://github.com/selmanays/nodrat/issues/1096)) admin/rag + admin/queue sonrası 3. alt-track. admin/queue ile aynı pattern: tek büyük component + paylaşılan state; section split DEFERRED. Behavior-preserving extraction kapsamı: 4 const (label dict + options + setting keys) + 2 saf presentational subcomponent (`StatCard` + `NumericSettingInput`) → `_shared.tsx`. Hedef küçülme: ~150-180 LoC (~%15-18). State-changing trigger envanteri: 5 endpoint (3 settings + 1 recompute + 1 triggerRun + 1 export) — production'da ASLA tetiklenmez.

## Tanım / Bağlam

**Hedef god-page:** `apps/web/src/app/admin/sft/page.tsx`
- **LoC:** 1026 (35 KB)
- **Single component** `AdminSftPage` (L135–L931 = 797 LoC body)
- **Top-level helpers** (L90–L133 = 44 LoC):
  - `EXCLUDED_LABEL` (label dict)
  - `TASK_TYPE_OPTIONS` (7-option array)
  - `SAMPLE_TYPE_LABEL` (label dict)
  - `SPLIT_OPTIONS` (4-option array)
  - `SFT_SETTING_KEYS` (3-key object)
- **Bottom-level helpers** (L932–L1026):
  - `StatCard({ title, value, hint })` ~30 LoC — saf presentational
  - `NumericSettingInput({ value, onSave, ... })` ~60 LoC — saf presentational, props-only
- **7 component handler** (`loadAll`, `handleToggleEnabled`, `handleSaveNumberSetting`, `handleResetSetting`, `handleRecompute`, `handleTriggerRun`, `handleExport`)
- **1 useEffect** (mount load)

**State-changing API çağrıları (production'da ASLA tetiklenmez):**

| Sembol | HTTP | Endpoint | Risk |
|---|---|---|---|
| `getSFTStats` | GET | `/admin/sft/stats?days=30` | Read-only |
| `getSFTConsentStats` | GET | `/admin/sft/consent-stats` | Read-only |
| `getSFTRecent` | GET | `/admin/sft/recent?limit=50` | Read-only |
| `adminSettingsList("sft")` | GET | `/admin/settings?group=sft` | Read-only |
| `adminSettingUpdate` | POST | `/admin/settings/{key}` | **State-changing** (DB write — pipeline ayarı kalıcı değişir) |
| `adminSettingReset` | DELETE | `/admin/settings/{key}` | **State-changing** (DB delete → default fallback) |
| `recomputeSFTEligibility` | POST | `/admin/sft/recompute-eligibility?days=30` | **State-changing** (job dispatch + DB re-eval) |
| `triggerSFTRun` | POST | `/admin/sft/run` | **State-changing** (MANUEL SFT pipeline run — prod'da ASLA tetiklenmez) |
| `downloadSFTExport` | POST | `/admin/sft/export` | **State-changing** (server-side büyük JSONL üretimi; bandwidth + zaman) |

## Karar / Kabul kapsamı

### Strateji — admin/queue deseni

admin/sft yapısı admin/queue ile **paralel**: tek büyük component + paylaşılan state (7 form input + 4 dialog state). Section split shared-state lift + Context gerektirir → **DEFERRED** (admin/queue ile aynı karar).

**Karar:** Behavior-preserving extraction yalnız:
- 4 const top-level helper (`EXCLUDED_LABEL`, `TASK_TYPE_OPTIONS`, `SAMPLE_TYPE_LABEL`, `SPLIT_OPTIONS`, `SFT_SETTING_KEYS`)
- 2 saf presentational subcomponent (`StatCard`, `NumericSettingInput`) — zaten ayrı function olarak bottom'da; sadece dosya yer değişimi.

Ana `AdminSftPage` + 7 handler + 1 useEffect + JSX body `page.tsx`'te kalır.

### Hard kurallar (her PR için)

- Pre-flight 4-aşama: `npm run type-check` + `npm run lint` + `npx vitest run src/lib/__tests__/api.test.ts` + `npm run build`.
- **Vitest 107/107 sabit**; RTL eklenmez (A1 admin/rag/queue kararı korunur).
- Production smoke read-only 4-route ONLY (`/`, `/admin`, `/admin/sft`, `/api/health`).
- **State-changing trigger butonlarına TIKLAMA YOK** (Save/Reset settings × 3 + "Yeniden Hesapla" + "Pipeline'ı Çalıştır" + "Dışa Aktar (JSONL)"). 5 state-changing endpoint manuel ASLA çağrılmaz.
- VPS log scan: ERROR/Traceback/ModuleNotFoundError/ImportError + symbol-specific (`AdminSftPage|admin/sft|StatCard|NumericSettingInput|sft/_shared`) → 0 hit beklenir.

## PR sırası (planlanan)

### Hedef dosya haritası (final)

```
apps/web/src/app/admin/sft/
├── page.tsx                       (~860 LoC; AdminSftPage main + 7 handler + useEffect + JSX body)
└── _shared.tsx                    (~165 LoC; 4 const + StatCard + NumericSettingInput)
```

### PR sequence (FINAL — 3/3 merged 2026-05-23)

| PR | İçerik | PR# | LoC değişim | Trigger? | Sonuç |
|---|---|---|---|---|---|
| **7d-0** | Mini-plan docs-only | [#1242](https://github.com/selmanays/nodrat/pull/1242) | wiki/ | hayır | ✅ MERGED |
| **7d-1** | Helpers → `_shared.tsx` | [#1243](https://github.com/selmanays/nodrat/pull/1243) | +190 / -140 | hayır | ✅ MERGED |
| **7d-closure** | alt-track 3/4 DONE — bu PR | _bu PR_ | wiki/ | hayır | 🟡 IN PROGRESS |

### Toplam (final)

- **3 PR** merge edildi.
- `page.tsx`: 1026 → **896 LoC** (-130 net, ~%12.7).
- `_shared.tsx`: 180 LoC (yeni; 7 helper sembol — 4 const + 2 interface + 2 saf subcomponent).
- Vitest 107/107 sabit.
- Production smoke 4-route 200 + 13/13 healthy + ZERO error.
- ESLint pre-flight 3 unused import yakaladı (RotateCcw + Save + Input) → fix sonrası temiz.
- Section split shared-state lift gerektirdiği için DEFERRED.

## Smoke disiplin (her PR için)

### İzin verilen

- GET `/` / `/admin` / `/admin/sft` / `/api/health` → 200
- VPS docker compose ps + log scan (6 dk)

### YASAK (production state-changing)

- 5 state-changing endpoint manuel çağrı
- Settings save/reset butonları (3 input)
- "Yeniden Hesapla" butonu
- "Pipeline'ı Çalıştır" butonu
- "Dışa Aktar (JSONL)" butonu
- Switch toggle (Enabled)

## Risk matrisi

| Risk | Etki | Mitigasyon |
|---|---|---|
| StatCard/NumericSettingInput taşıma sırasında prop type kayması | Düşük | Pre-flight tsc yakalar |
| Helpers extraction sırasında lucide-react / shadcn import surprise | Düşük | Pre-flight tsc + ESLint cross-tab usage yakalar |
| AdminSftPage main component dokunulmaz | Orta | Helper extraction yalnız L90-L133 + L932-L1026 bloklarına; orta blok L135-L931 DOKUNULMADI |
| State-changing handler signature kayması | Yüksek | Handler'lar page.tsx'te kalıyor; helpers extraction'da dokunulmaz |
| Section split denenirse | Yüksek | Mini-plan açıkça DEFERRED; admin/queue ile aynı karar |

## T6 dışı / Phase 7b alt-track

- **admin/rag DONE 2026-05-23** ([[phase7b-admin-rag-mini-plan]]; closure v36).
- **admin/queue DONE 2026-05-23** ([[phase7b-admin-queue-mini-plan]]; closure v39).
- **admin/sft (BU MİNİ-PLAN)** — alt-track 3/4.
- **research components** — alt-track 4 (8 component zaten ayrı; reality assessment yapılacak; muhtemelen extraction GEREKLİ DEĞİL — alternate criteria ile kabul).
- **Phase 7b umbrella closure docs** — tüm alt-track'ler sonrası; [#1096](https://github.com/selmanays/nodrat/issues/1096) status karar.

## İlişkiler

- [[phase7b-admin-queue-mini-plan]] — Phase 7b 2. alt-track (paralel pattern)
- [[phase7b-admin-rag-mini-plan]] — Phase 7b 1. alt-track (tab-by-tab pattern; SFT için uygulanmaz)
- [[modular-monolith-transition-master-plan]] §13 — Phase 7b umbrella status

## Kaynaklar

- [admin/sft/page.tsx](../../apps/web/src/app/admin/sft/page.tsx) — hedef god-page
- [lib/admin-sft-api.ts](../../apps/web/src/lib/admin-sft-api.ts) — SFT API client (Phase 7a kapsamı DIŞINDA; ayrı dosya zaten)
- Phase 7b admin/queue closure: PR #1239..#1241; docs v38+v39

## Açık sorular / TODO

- (PR-7d-1 sonrası) Dialog wrapper (Export Dialog L?-L?) presentational subcomponent olarak çıkarılabilir mi? Mevcut mini-plan kapsamı dışı; ileri initiative olarak değerlendirilebilir.
- (PR-7d-closure sonrası) Section split (shared-state lift + Context) admin/queue ile birleşik bir initiative olarak açılır mı? Mini-plan kapanışında karar.
