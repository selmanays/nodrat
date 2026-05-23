---
type: topic
title: "Phase 7b admin/rag/page.tsx — Mini-plan"
slug: "phase7b-admin-rag-mini-plan"
status: live
created: 2026-05-23
updated: 2026-05-23
sources:
  - "wiki/plans/modular-monolith-transition-master-plan.md§9"
  - "wiki/plans/modular-monolith-transition-master-plan.md§13"
  - "wiki/topics/phase7a-frontend-mini-plan.md"
tags: [phase7b, refactor, frontend, admin-rag, t6, mini-plan, done]
aliases: [phase7b-mini-plan, admin-rag-mini-plan]
---

> **Durum (2026-05-23 SON):** PR-7b-0..10 TAMAMLANDI (11/13). `page.tsx` 2356 → 143 LoC (~%94 küçülme, **thin router**). 9 tab dosyası + `_shared.tsx` + 10 PR merge edildi (#1226..#1236). Vitest 107/107 sabit. Production smoke (read-only 4-route) her PR sonrası ZERO error. **Kalan:** PR-7b-closure (bu PR — docs-only) + PR-7b-T6-close (sıradaki — Phase 5 retrieval sign-off + T6 #1085 close).

# Phase 7b — `apps/web/src/app/admin/rag/page.tsx` mini-plan

## TL;DR

`apps/web/src/app/admin/rag/page.tsx` **2356 LoC / 9 tab god-file**. T6 [#1085](https://github.com/selmanays/nodrat/issues/1085)'in 5 tracked god-file'ından biri ve Living Checklist 0/5 (faz hiç başlamadı). Phase 7a (api.ts 2041→580) precedenti ile **tab-by-tab behavior-preserving extraction**: 13 PR, her PR ≤ ~575 LoC değişiklik, ilk 7 PR state-changing ZERO. **Component test infra (RTL) bu turda eklenmez** (T6 closure'ı bloklamaz; ayrı future initiative). Inspector için 600+ LoC complexity gate; tetiklenirse 2-PR split. T6 closure path'inde son strict blokçu; Phase 5 retrieval alternate criteria sign-off + bu mini-plan + closure docs ile T6 #1085 kapatılabilir.

## Tanım / Bağlam

**Hedef god-file:** `apps/web/src/app/admin/rag/page.tsx`
- **LoC:** 2356 (83 KB)
- **9 tab:** Health, Benchmark, Citation, Rerank, Ner, Raptor, Inspector, Cache, Performance
- **39 useState + 10 useEffect** (tab seviyesinde izole; root sadece 1 tab key)
- **3 state-changing trigger:** `ragBenchmarkRun`, `ragRaptorTrigger`, `ragInspectQuery`
- **9 read-only GET:** ragHealth, ragBenchmarkHistory/Status, ragCitationStats, ragRerankStats, ragNerStats, ragCacheTelemetry, ragRaptorClusters, ragPipelineComparison
- **Source of truth:** Reality analizi 2026-05-23 (kullanıcı onayıyla bu mini-plan'a girdi)

**T6 #1085'teki yeri:** 5 tracked god-file'dan biri (Phase 7b etiketli). Living Checklist 0/5 (facade established / char test pack / internal split / snapshot diff 0 / legacy file deleted) — faz hiç başlamadı.

**Phase 7a precedent:** `api.ts` 2041→580 LoC, 24 PR, 110 mock-fetch char test, 0 regression, 33 docs-only deploy SKIP dogfooding. tsc + ESLint + Vitest + next build safety net **kanıtlı yeterli** (component test eklenmedi).

**Phase 6 PR-C+ precedent:** `_research_stream_body` BİLİNÇLİ taşınmadı; kapanış kriteri (ii) ("replay+helper yeterli safety net; full integration bilinçli deferred") deklarasyonu ile alt-track DONE sayıldı. Bu mini-plan için de benzer **alternate criteria** kullanılabilir: "tab'lar ayrı dosyalarda; page.tsx thin router olarak ~60 LoC'a düşer; legacy delete YOK."

## Karar / Kabul kapsamı

### Kararlar (kullanıcı 2026-05-23 onayı)

- **A1 — RTL infra eklenmez.** `@testing-library/react` + `@testing-library/jest-dom` + `@vitejs/plugin-react` + `setupTests.ts` bu turda kurulmaz. Component characterization atlanır; static analysis (tsc + ESLint + next build) + production read-only smoke + log scan safety net'i Phase 7a precedent ile sürdürülür. RTL ayrı future initiative — T6 closure'ı **bloklamaz**.
- **A2 — Inspector için 600+ LoC complexity gate.** PR-7b-10 (Inspector + RerankBadge) tek PR olarak başlar. Lokal pre-flight'ta diff 600+ LoC veya state ayrışması/review karmaşıklığı sinyali verirse → **PR-7b-10a (RerankBadge + Inspector-local helper extraction)** + **PR-7b-10b (Inspector body taşıma)** olarak otomatik split.
- **A3 — Bu tur yalnız `apps/web/src/app/admin/rag/page.tsx`.** Phase 7b umbrella'sında olan diğer kalemler (`admin/queue/page.tsx`, `admin/sft/page.tsx`, `src/components/research/*`) bu turda **dahil DEĞİL**; T6 kapatıldıktan sonra ayrı sıra. T6 yalnız admin/rag'i tracking ediyor.

### Hard kurallar (her PR için)

- **Behavior-preserving extraction.** Saf taşıma (function body kopyala-yapıştır + import path update + page.tsx re-export). Logic/render davranış değişikliği YOK.
- **Pre-flight 4-aşama:** `npm run type-check` + `npm run lint` + `npx vitest run` (107/107 PASS bekleniyor) + `npm run build`.
- **Production smoke read-only sınırlar:** `GET /admin/rag` (sayfa load — read-only GET'leri otomatik tetikler) + `GET /admin` + `GET /` + `GET /api/health`. Tıklama YOK; trigger button'a hiçbir koşulda **basılmaz**.
- **Trigger çağrısı YASAK** (production'da kullanıcı tarafından admin UI üzerinden tetiklenir; agent/smoke OTOMATIK ÇAĞIRMAZ): `ragBenchmarkRun`, `ragRaptorTrigger`, `ragInspectQuery`.
- **Auto-merge gate:** CI 10/10 SUCCESS + CLEAN. Squash merge (`--delete-branch` YOK — worktree/main checkout hatasını önler; remote branch ayrıca silinir).
- **Deploy reality:** `apps/web/**` değişikliği → **FULL 17-step deploy** (PR #1225 ile kanıtlandı). Docs-only → SKIP. Backend kodu DOKUNULMAZ.
- **DB / Redis / migration / provider / SSE / research stream / rechunk / reembed / manual task trigger YOK.**
- **import-linter contracts dokunulmaz** (frontend; backend contracts 13 kept / 0 broken aynı kalır).
- **Vitest test sayısı korunur (107/107).** Component test eklenmediği için test sayısı bu mini-plan boyunca artmaz; PR-7b-1..7b-10'da 107 PASS gibi gibi geçer.

## PR sırası (13 PR)

### Hedef dosya haritası (final)

```
apps/web/src/app/admin/rag/
├── page.tsx                  # AdminRagPage thin router (~60 satır)
├── _shared.tsx               # StatCard + KV + fmt + HINTS (~80 satır)
└── _tabs/
    ├── citation.tsx          # CitationTab + Skeleton (~95 satır)
    ├── rerank.tsx            # RerankTab + Skeleton (~115 satır)
    ├── cache.tsx             # CacheTab (~115 satır)
    ├── ner.tsx               # NerTab + Skeleton (~165 satır)
    ├── health.tsx            # HealthTab + Skeleton + FlagRow + Metric (~285 satır)
    ├── performance.tsx       # PerformanceTab + DeltaBadge + METRIC_KEYS (~285 satır)
    ├── raptor.tsx            # RaptorTab + ClusterRow (~140 satır; TRIGGER)
    ├── benchmark.tsx         # BenchmarkTab + benchmarkChartConfig (~340 satır; TRIGGER + polling)
    └── inspector.tsx         # InspectorTab + RerankBadge (~570 satır; TRIGGER; A2 gate)
```

`page.tsx` 2356 → ~60 LoC; her tab ≤ 570 satır.

### PR sequence (FINAL — 11/13 merged 2026-05-23)

| PR | İçerik | PR# | LoC değişim | Trigger? | Sonuç |
|---|---|---|---|---|---|
| **7b-0** | Mini-plan docs-only PR. | [#1226](https://github.com/selmanays/nodrat/pull/1226) | wiki/ | hayır | ✅ MERGED |
| **7b-1** | Shared helpers → `_shared.tsx` (HINTS, StatCard, KV, fmt). | [#1227](https://github.com/selmanays/nodrat/pull/1227) | +114 / -98 | hayır | ✅ MERGED |
| **7b-2** | `CitationTab` → `_tabs/citation.tsx` (129L). | [#1228](https://github.com/selmanays/nodrat/pull/1228) | +129 / -95 | hayır | ✅ MERGED |
| **7b-3** | `RerankTab` → `_tabs/rerank.tsx` (151L). | [#1229](https://github.com/selmanays/nodrat/pull/1229) | +151 / -120 | hayır | ✅ MERGED |
| **7b-4** | `CacheTab` → `_tabs/cache.tsx` (155L). | [#1230](https://github.com/selmanays/nodrat/pull/1230) | +155 / -127 | hayır | ✅ MERGED |
| **7b-5** | `NerTab` → `_tabs/ner.tsx` (217L). | [#1231](https://github.com/selmanays/nodrat/pull/1231) | +217 / -170 | hayır | ✅ MERGED |
| **7b-6** | `HealthTab + FlagRow + Metric` → `_tabs/health.tsx` (335L). | [#1232](https://github.com/selmanays/nodrat/pull/1232) | +335 / -287 | hayır | ✅ MERGED |
| **7b-7** | `PerformanceTab + DeltaBadge + METRIC_KEYS` → `_tabs/performance.tsx` (397L). | [#1233](https://github.com/selmanays/nodrat/pull/1233) | +397 / -340 | hayır | ✅ MERGED |
| **7b-8** | `RaptorTab + ClusterRow` → `_tabs/raptor.tsx` (187L). **TRIGGER:** `ragRaptorTrigger`. | [#1234](https://github.com/selmanays/nodrat/pull/1234) | +189 / -142 | **evet** | ✅ MERGED |
| **7b-9** | `BenchmarkTab + benchmarkChartConfig` → `_tabs/benchmark.tsx` (408L). **TRIGGER:** `ragBenchmarkRun` + 10s setInterval polling. | [#1235](https://github.com/selmanays/nodrat/pull/1235) | +412 / -355 | **evet** | ✅ MERGED |
| **7b-10** | `InspectorTab + RerankBadge` → `_tabs/inspector.tsx` (567L). **TRIGGER:** `ragInspectQuery`. A2 gate **tetiklenmedi** (567 LoC < 600). | [#1236](https://github.com/selmanays/nodrat/pull/1236) | +574 / -550 | **evet** | ✅ MERGED |
| **7b-closure** | Phase 7b admin/rag alt-track DONE deklarasyonu — bu PR. | _bu PR_ | wiki/ | hayır | 🟡 IN PROGRESS |
| **7b-T6-close** | T6 #1085 closure docs (Phase 5 retrieval sign-off + final close). | sıradaki | wiki/ + issue close | hayır | ⏳ pending |

### Toplam (final)

- **13 PR planlandı; 11 merge edildi; 2 closure işi kaldı.**
- 6 PR (7b-2..7b-7) state-changing **ZERO**.
- 3 PR (7b-8, 7b-9, 7b-10) trigger içerir → smoke "no click" disiplin korundu; trigger sembolleri byte-for-byte aktarıldı.
- **page.tsx: 2356 → 143 LoC** (-2213 net, ~%94 küçülme; **thin router** = imports + TabKey + TABS + AdminRagPage).
- **9 `_tabs/*.tsx` + 1 `_shared.tsx`** oluşturuldu.
- **Vitest 107/107 sabit** mini-plan boyunca (component test infra eklenmedi — A1 kararı korundu).
- **Production smoke**: her PR sonrası 4-route 200 + 13/13 container healthy + ZERO ERROR/Traceback/ImportError (6 dk pencere). Trigger butonlarına ASLA tıklanmadı.
- **A2 complexity gate** PR-7b-10'da tetiklenmedi: Inspector body 567 LoC < 600 threshold, helper bağımlılığı minimal (RerankBadge 8 satır), tek PR olarak güvenle uygulandı.

## Smoke disiplin (her PR için)

### İzin verilen (otomatik agent smoke)

- `GET https://nodrat.com/api/health` → 200
- `GET https://nodrat.com/` → 200
- `GET https://nodrat.com/admin` → 200
- `GET https://nodrat.com/admin/rag` → 200 (sayfa render eder; read-only GET'ler otomatik tetiklenir)

### YASAK (production state-changing)

- **HİÇBİR koşulda trigger button'a tıklama:**
  - Benchmark tab'da "Yeni benchmark başlat" → `ragBenchmarkRun(suite)` POST
  - Raptor tab'da "RAPTOR-Lite çalıştır" → `ragRaptorTrigger()` POST
  - Inspector tab'da "Sorguyu çalıştır" → `ragInspectQuery(query, k, …)` POST
- Authentication: Admin route, anonymous smoke (agent admin token görmez) → button binding'i görür ama action erişimi yok. Yine de "tıklama YOK" disiplini açık tutulmalı.
- **DB / Redis / migration / provider / SSE / research stream / rechunk / reembed / manual task trigger YOK.**

### Log scan kuralı (her PR post-deploy)

- VPS log scan: 7 container × ~6 dakika pencere
- Pattern: `ERROR|CRITICAL|Traceback|ModuleNotFoundError|ImportError`
- **0 gerçek hata bekleniyor** (INFO log içindeki `errors=0` field değerleri kelime eşleşmesi sayılmaz)
- Beklenen: container all `Up (healthy)`; natural Celery fire normal

## Risk matrisi

| Risk seviyesi | PR'lar | Etken | Mitigation |
|---|---|---|---|
| **Düşük** | 7b-0, 7b-1, 7b-2..7b-7 (6 read-only tab), 7b-closure, 7b-T6-close | Saf taşıma; behavior-preserving; static analysis + read-only smoke yeterli; trigger içermez | Phase 7a 24-PR safety net deseni; production smoke /admin/rag 200 + log scan ZERO |
| **Orta** | 7b-7 (Performance 245L), 7b-8 (Raptor trigger), 7b-9 (Benchmark trigger + setInterval polling) | LoC büyüklüğü; trigger binding doğru aktarımı; setInterval cleanup (`useEffect` return) sızıntı önlenmeli | Per-PR tsc + ESLint + next build + post-merge log scan; smoke trigger'a TIKLAMAZ; setInterval'i extraction sonrası izole gözle |
| **Yüksek** | 7b-10 (Inspector 502L; trigger; 6 useState; karmaşık form + RerankBadge iç içe) | En büyük tab; complex render tree; tek seferde taşıma review riski | **A2 complexity gate**: pre-flight diff 600+ LoC ⇒ 7b-10a (RerankBadge + Inspector-local helper) + 7b-10b (body) splitle; pre-flight 4-aşama hep birden; manuel admin UI smoke (kullanıcı tarafından) opsiyonel |
| **Cross-cutting (orta)** | Tüm Phase 7b | Component test infra YOK; runtime davranışı static analysis dışında doğrulanmaz | A1 kararı: RTL ayrı future initiative; Phase 7a precedent (24 PR / 0 regression) yeterli safety net kanıtı |
| **Trigger smoke breach (yüksek-impact, düşük olasılık)** | 7b-8, 7b-9, 7b-10 | Smoke'da yanlışlıkla trigger button tıklaması → DB write / provider call / state change | Sıkı kural: smoke yalnız 4 read-only GET (/admin/rag + /admin + / + /api/health). Hiçbir adımda `click()` / `fill()` / button etkileşimi YOK. Her PR closure raporunda "production endpoint çağrısı YOK" explicit beyan |

## A2 Complexity Gate (PR-7b-10 Inspector)

PR-7b-10 başlangıçta **tek PR** olarak planlanır. Pre-flight sırasında aşağıdaki tetikleyicilerden HERHANGİ BİRİ tespit edilirse **otomatik split**:

- **Diff 600+ LoC** (target threshold; A2 onaylanmış gate)
- **State ayrışması** — Inspector'ın 6 useState'i + form binding'leri + RerankBadge entegrasyonu net iki adıma ayrılıyorsa
- **Review karmaşıklığı** — diff GitHub'da rahat okunamayacak kadar karışıksa (yorum yorum etrafa dağılırsa; tek mantıksal değişiklik takip edilemiyorsa)

### Split deseni (gate tetiklenirse)

**PR-7b-10a — RerankBadge + Inspector helper extraction (orta risk):**
- `RerankBadge` (70 satır) → `_shared.tsx`'e taşı (RerankBadge artık Inspector-local değil; ileride başka tab kullanabilir)
- VEYA `RerankBadge` ile birlikte Inspector'ın iç pure helper'larını (ör. answer span parsing) `_tabs/_inspector_helpers.tsx`'e çıkar
- Inspector body `page.tsx`'te kalır
- Pre-flight 4-aşama + behavior-preserving

**PR-7b-10b — Inspector body extraction (yüksek risk):**
- `InspectorTab` body → `_tabs/inspector.tsx` taşı (helper'lar 10a ile zaten dışarda)
- Trigger button `ragInspectQuery` binding'i + form state aktarılır
- Pre-flight 4-aşama + behavior-preserving + manuel admin UI smoke (opsiyonel, kullanıcı tarafından)

## T6 #1085 closure path

Bu mini-plan tamamlandığında:

1. **7b-2..7b-10** = `admin/rag/page.tsx` 2356 → ~60 LoC (thin router); 9 tab + shared helpers ayrı dosyalarda. T6'nın `admin/rag/page.tsx` alt-kalemi **DONE (alternate criteria (ii))**.
2. **7b-closure** = Phase 7b admin/rag alt-track DONE deklarasyonu (master plan §13). Phase 7b umbrella'nın diğer kalemleri (queue, sft, research) AÇIK kalır; sayfası ayrı tracking edilir.
3. **7b-T6-close** = T6 closure docs:
   - Phase 5 retrieval (`core/retrieval.py` 1926 LoC) için **alternate criteria (ii) sign-off** (1 docs-only deklarasyon: "split + char yeterli safety net; legacy 1926 LoC kalır" + master plan §12.3 entry)
   - T6 #1085'in 5 tracked god-file'ı için final durum tablosu:
     | God-file | Final durum | Yöntem |
     |---|---|---|
     | `core/extractor.py` | ✅ legacy DELETED → `shared/extraction/` | Phase 4 PR-D2 |
     | `core/retrieval.py` | ✅ alternate criteria (ii) sign-off | 7b-T6-close docs |
     | `api/app_research_stream.py` | ✅ alternate criteria (ii); body taşınmadı | Phase 6 PR-C+ DONE |
     | `src/lib/api.ts` | ✅ Core + facade re-export (580 LoC stays) | Phase 7a #1095 CLOSED |
     | `src/app/admin/rag/page.tsx` | ✅ alternate criteria (ii); 9 tab ayrı dosyalarda; page.tsx ~60 LoC thin router | Phase 7b mini-plan 7b-1..7b-10 |
   - `#1085 close` (closure docs PR merge + dogfooding PASS sonrası)

T6 closure ulaşılabilirliği: **~13 PR sonrası**.

## İlişkiler

- **Faz:** Phase 7b ([#1096](https://github.com/selmanays/nodrat/issues/1096))
- **Tracking:** T6 ([#1085](https://github.com/selmanays/nodrat/issues/1085))
- **Önceki mini-plan:** [[phase7a-frontend-mini-plan]] (24 PR; api.ts 2041→580 LoC; #1095 CLOSED)
- **Paralel Phase 6 deseni:** [[phase6-sse-prc-plus-mini-plan]] (alternate criteria (ii); _research_stream_body BİLİNÇLİ taşınmadı)
- **Master plan:** [[modular-monolith-transition-master-plan]] §9 Phase 7b / §13 status board

## Kaynaklar

- [docs/engineering/refactor-playbook.md §3](../../docs/engineering/refactor-playbook.md)
- [wiki/decisions/god-file-facade-first.md](../decisions/god-file-facade-first.md)
- [wiki/plans/modular-monolith-transition-master-plan.md §9 Phase 7b](../plans/modular-monolith-transition-master-plan.md)
- [wiki/topics/phase7a-frontend-mini-plan.md](phase7a-frontend-mini-plan.md) (precedent)
- [wiki/topics/phase6-sse-prc-plus-mini-plan.md](phase6-sse-prc-plus-mini-plan.md) (alternate criteria precedent)
- Reality analysis (read-only) — kullanıcı onayı 2026-05-23 (bu mini-plan'ın temeli)

## Açık sorular / TODO

- (PR-7b-1 sonrası karar) `_shared.tsx`'in dosya konumu — `apps/web/src/app/admin/rag/_shared.tsx` mi yoksa `apps/web/src/modules/rag/admin/_shared.tsx` mi? Mini-plan başlangıçta `apps/web/src/app/admin/rag/` altında planlıyor (en kısa yol); modules/rag taşıma ayrı initiative (Phase 7b umbrella'nın bu mini-plan dışı kısmı).
- (PR-7b-9 öncesi) Benchmark setInterval polling cleanup deseni: `useEffect` return içinde `clearInterval` zaten var (L478); extraction'da bu deseni aynen taşı.
- (PR-7b-10 sonrası) Inspector tarafından kullanılan `formatTrDateTime` (`@/lib/format`) shared olarak `_shared.tsx`'e taşınsın mı? Mini-plan'da Inspector-local kalıyor; gerekirse 7b-closure'da hizalama.
- (A1 future initiative) RTL ne zaman eklensin? Önerilen: Phase 7b umbrella'nın diğer kalemleri (queue/sft/research) başlamadan önce ayrı PR (test-infra-only); T6 closure'dan SONRA.
