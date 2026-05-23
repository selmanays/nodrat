---
type: topic
title: "Phase 7b admin/queue/page.tsx — Mini-plan"
slug: "phase7b-admin-queue-mini-plan"
status: live
created: 2026-05-23
updated: 2026-05-23
sources:
  - "wiki/plans/modular-monolith-transition-master-plan.md§9"
  - "wiki/plans/modular-monolith-transition-master-plan.md§13"
  - "wiki/topics/phase7b-admin-rag-mini-plan.md"
tags: [phase7b, refactor, frontend, admin-queue, mini-plan]
aliases: [phase7b-queue-mini-plan, admin-queue-mini-plan]
---

# Phase 7b — `apps/web/src/app/admin/queue/page.tsx` mini-plan

## TL;DR

`apps/web/src/app/admin/queue/page.tsx` **1035 LoC / single AdminQueuePage component**. T6 #1085 dışı; Phase 7b umbrella ([#1096](https://github.com/selmanays/nodrat/issues/1096)) admin/rag (DONE) sonrası 2. alt-track. admin/rag'den **farkı:** doğal "tab" sınırı YOK — tek büyük component + 5 JSX section (queue summary / filter / bulk toolbar / failed jobs table / maintenance) + 13 handler + 4 useEffect (initial load + 2 polling + filter reset) + paylaşılan state. **Strateji:** behavior-preserving extraction'ı saf presentational helper + label dict + badge bileşenlerine sınırla; ana `AdminQueuePage` `page.tsx` içinde kalır (shared state lift gerektirmez). Hedef: ~200-300 LoC çıkarma (admin/rag ~%94 küçülmesinin aksine; god-page DEĞİL daha çok housekeeping). State-changing trigger envanteri: 5 POST + 1 DELETE — production smoke'da ASLA tetiklenmez.

## Tanım / Bağlam

**Hedef god-page:** `apps/web/src/app/admin/queue/page.tsx`
- **LoC:** 1035 (38 KB)
- **Tek component** `AdminQueuePage` (L229–L1035 = 807 LoC body)
- **Top-level helpers** (L72–L227 = 156 LoC):
  - `ISTIPI_ETIKETI`, `KUYRUK_ETIKETI` (label dicts; 28+12 entries)
  - `isTipiniBicimle`, `kuyrukAdiniBicimle`, `hataAciklamasi` (3 pure formatter fn)
  - `DurumRozeti`, `SeverityRozeti` (2 saf presentational badge)
  - `SAYFA_BOYUTLARI`, `SayfaBoyutu` (pagination const + type)
- **5 JSX section** (AdminQueuePage body içinde):
  - Kuyruk özeti — 4-card pipeline-aligned (L511)
  - Filtre + yenile bar (L585)
  - Bulk toolbar (#462) (L652)
  - Başarısız işler tablosu + per-row dropdown actions (L683)
  - Bakım görevleri kartları (#468) (L899)
- **13 component-level handler** (veriYukle, bakimYukle, bakimSimdiCalistir, tekrarDene, olarakKapat, secimDegistir, tumSayfaSec, secimiTemizle, topluTekrarDene, topluKapat + pure compute'lar)
- **4 useEffect**: initial load + bakim 30s polling + filter reset (sayfa=1) + auto-refresh 10s

**State-changing API çağrıları (production'da ASLA tetiklenmez):**

| Sembol | HTTP | Endpoint | Risk |
|---|---|---|---|
| `getQueueOverview` | GET | `/admin/queue/overview` | Read-only |
| `listFailedJobs` | GET | `/admin/queue/failed?...` | Read-only |
| `listMaintenanceTasks` | GET | `/admin/queue/maintenance` | Read-only |
| `retryFailedJob` | POST | `/admin/queue/jobs/{id}/retry` | **State-changing** (Celery re-enqueue / manual task) |
| `resolveFailedJob` | DELETE | `/admin/queue/failed/{id}` | **State-changing** (DB write) |
| `bulkRetryFailedJobs` | POST | `/admin/queue/failed/bulk-retry` | **State-changing** (bulk Celery re-enqueue) |
| `bulkResolveFailedJobs` | POST | `/admin/queue/failed/bulk-resolve` | **State-changing** (bulk DB write) |
| `runMaintenanceNow` | POST | `/admin/queue/maintenance/{name}/run-now` | **State-changing** (MANUEL MAINTENANCE TASK TRIGGER — prod'da ASLA tetiklenmez) |

## Karar / Kabul kapsamı

### Strateji — admin/rag deseninden farkı

admin/rag tab-by-tab split mümkündü çünkü her tab kendi state'i + kendi API çağrılarına sahip izole component'di. **admin/queue böyle DEĞİL**:
- 5 JSX section paylaşılan state'i (cozulmemis, secilenIds, sayfa, isTipiFiltresi, …) kullanır.
- veriYukle handler aynı anda `getQueueOverview` + `listFailedJobs` çağırır (Promise.all).
- bulk toolbar + failed jobs table aynı `secilenIds` Set'ini paylaşır.
- Section'lar component olarak ayrılırsa **prop drilling** veya **Context API** gerekir → behavior değişikliği riski.

**Karar:** Behavior-preserving extraction yalnız aşağıdakilere sınırlanır:
- **Saf presentational helper'lar** (DurumRozeti, SeverityRozeti) → state'siz, props-only
- **Label dict + formatter fn'leri** (ISTIPI_ETIKETI, KUYRUK_ETIKETI, isTipiniBicimle, kuyrukAdiniBicimle, hataAciklamasi) → pure
- **Pagination const** (SAYFA_BOYUTLARI, SayfaBoyutu)

Ana `AdminQueuePage` component'i + 13 handler + 4 useEffect + 5 JSX section `page.tsx`'te kalır (~800 LoC). Cumulative küçülme tahmini: -150 ila -200 LoC (~%15-20).

### Hard kurallar (her PR için)

- Pre-flight 4-aşama: `npm run type-check` + `npm run lint` + `npx vitest run src/lib/__tests__/api.test.ts` + `npm run build`.
- **Vitest 107/107 sabit**; component test infra (RTL) **eklenmez** (admin/rag A1 kararının uzantısı).
- Production smoke read-only 4-route ONLY (`/`, `/admin`, `/admin/queue`, `/api/health`).
- **Trigger butonlarına TIKLAMA YOK**: "Tekrar Dene", "Çözüldü Olarak Kapat", "Topluca Tekrar Dene", "Topluca Çöz", "Şimdi Çalıştır" (maintenance) → production'da ASLA tıklanmaz.
- 5 POST + 1 DELETE state-changing endpoint manuel ASLA çağrılmaz.
- VPS log scan: ERROR/Traceback/ModuleNotFoundError/ImportError + symbol-specific (`AdminQueuePage|admin/queue|DurumRozeti|SeverityRozeti`) → 0 hit beklenir.
- Behavior-preserving: handler body, useEffect dependency array, polling interval (30s/10s) byte-for-byte korunur.

## PR sırası (planlanan)

### Hedef dosya haritası (final)

```
apps/web/src/app/admin/queue/
├── page.tsx                       (~800 LoC; AdminQueuePage main component)
└── _shared.tsx                    (~155 LoC; 2 label dict + 3 formatter fn + 2 badge component + pagination const)
```

### PR sequence

| PR | İçerik | LoC değişim tahmini | Trigger? | Risk |
|---|---|---|---|---|
| **7c-0** | **Bu mini-plan docs-only PR.** Yeni `phase7b-admin-queue-mini-plan.md` + master plan §13 + log + index. App code YOK. | wiki/ | hayır | düşük |
| **7c-1** | Helpers extraction → `_shared.tsx`: 2 label dict (`ISTIPI_ETIKETI`, `KUYRUK_ETIKETI`) + 3 formatter (`isTipiniBicimle`, `kuyrukAdiniBicimle`, `hataAciklamasi`) + 2 badge (`DurumRozeti`, `SeverityRozeti`) + pagination const/type (`SAYFA_BOYUTLARI`, `SayfaBoyutu`). `page.tsx` import path update. | ~+155 / -155 | hayır | düşük |
| **7c-closure** | Phase 7b admin/queue alt-track DONE deklarasyonu — page.tsx ~800 LoC kaldı (god-page değil; helpers ayrıldı); ileri component split shared-state lift gerektireceği için DEFERRED (ayrı initiative). Log + master plan + index. | wiki/ | hayır | düşük |

### Toplam

- **3 PR** (1 mini-plan + 1 helpers + 1 closure)
- 0 PR state-changing kod
- Her PR ≤ ~160 LoC değişiklik
- Cumulative küçülme: page.tsx 1035 → ~880 LoC (-155 net, ~%15)

## Smoke disiplin (her PR için)

### İzin verilen (otomatik agent smoke)

- GET `/` → 200
- GET `/admin` → 200
- GET `/admin/queue` → 200 (varsayılan render; tablo + cards görünür)
- GET `/api/health` → 200
- VPS docker compose ps + log scan (6 dk)

### YASAK (production state-changing)

- POST/DELETE endpoint manuel çağrı (5 endpoint)
- "Tekrar Dene" / "Çözüldü Olarak Kapat" satır butonları
- "Topluca Tekrar Dene" / "Topluca Çöz" bulk butonları
- "Şimdi Çalıştır" maintenance task butonları
- Auto-refresh polling'i manuel tetikleme

### Log scan kuralı (her PR post-deploy)

- web + api containers, son 6 dk
- Pattern: `ERROR|CRITICAL|Traceback|ModuleNotFoundError|ImportError`
- Symbol-specific: `AdminQueuePage|admin/queue|DurumRozeti|SeverityRozeti|queue/_shared`
- Beklenti: ZERO hit

## Risk matrisi

| Risk | Etki | Mitigasyon |
|---|---|---|
| Helpers extraction sırasında cn() / formatTrDate / cn import surprise | Düşük | Pre-flight tsc + ESLint cross-tab usage yakalar (PR-7b-6 dersi) |
| Polling cleanup regression | Düşük | Helpers extraction sadece pure fn; useEffect/setInterval DOKUNULMAZ |
| Trigger handler signature kayması | Yüksek (state-changing) | Handler'lar page.tsx'te kalıyor; helpers extraction'da dokunulmaz |
| Section split denenirse (mini-plan dışı) | Yüksek | Mini-plan açıkça DEFERRED; shared-state lift ayrı initiative |
| _shared.tsx + page.tsx LoC dengesi yanıltıcı | Düşük | Cumulative metric raporlarda hem dosya hem net diff |

## T6 dışı / Phase 7b alt-track

- **admin/rag DONE 2026-05-23** ([[phase7b-admin-rag-mini-plan]]; closure v36).
- **admin/queue (BU MİNİ-PLAN)** — alt-track 2.
- **admin/sft** — alt-track 3 (ayrı mini-plan; ~1026 LoC).
- **research components** — alt-track 4 (8 component zaten ayrı; reality assessment yapılacak; muhtemelen extraction GEREKLİ DEĞİL — alternate criteria ile kabul).
- **Phase 7b umbrella closure docs** — tüm alt-track'ler sonrası; [#1096](https://github.com/selmanays/nodrat/issues/1096) status karar.

## İlişkiler

- [[phase7b-admin-rag-mini-plan]] — Phase 7b 1. alt-track (precedent)
- [[phase7a-frontend-mini-plan]] — Phase 7a precedent (api.ts split)
- [[modular-monolith-transition-master-plan]] §13 — Phase 7b umbrella status
- [[shadcn-customization-policy]] — UI component customization kuralları (kalır)

## Kaynaklar

- [admin/queue/page.tsx](../../apps/web/src/app/admin/queue/page.tsx) — hedef god-page
- [api/admin/queue.ts](../../apps/web/src/lib/api/admin/queue.ts) — Admin Queue API client (Phase 7a PR-7a-15 #1194 ile çıkarıldı; bu mini-plan dışı)
- Phase 7b admin/rag closure: PR #1226..#1237; docs v36

## Açık sorular / TODO

- (PR-7c-1 sonrası karar) `_shared.tsx`'in dosya konumu — `apps/web/src/app/admin/queue/_shared.tsx` (admin/rag deseni) mi yoksa modules/queue ortak alanı mı? Mini-plan başlangıçta admin/rag deseniyle aynı konum kullanır (admin route'a yakın).
- (PR-7c-closure sonrası karar) Section split (shared-state lift + Context) ayrı initiative olarak açılacak mı yoksa accepted-as-is mi? Mini-plan kapanışında karar verilir.
- (P7b umbrella closure) admin/queue page sonrası kalan iki alt-track (sft + research components) ayrı mini-plan'larda mı ele alınacak, yoksa bir hub mini-plan'da mı? Önerilen: ayrı mini-plan'lar (admin/sft ve research için), sonrası umbrella closure tek docs PR.
