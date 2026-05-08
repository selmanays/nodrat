---
type: topic
title: "MVP roadmap — MVP-1 → 2 → 3 → 4+ timeline"
slug: "mvp-roadmap"
category: "timeline"
status: "live"
created: "2026-05-08"
updated: "2026-05-08"
sources:
  - "docs/strategy/risk-register.md§5"
  - "INDEX.md§5b"
  - "README.md§Milestone durumu"
  - "CHANGELOG.md"
tags: ["roadmap", "milestone", "mvp", "timeline", "synthesis"]
aliases: ["mvp-timeline", "milestone-roadmap"]
---

# MVP roadmap

> **TL;DR:** MVP-1 ✅ → MVP-1.1/1.2/1.3/1.4/1.5/1.6 ✅ → MVP-2 ✅ (-19 hafta erken) → MVP-3 hedef 2026-11-30 (KS-2 acceptance + Faz 5/6) → MVP-4+ planning. Bu topic her milestone için: hedef tarih, gerçekleşen tarih, kapsam, çıktılar, KS noktası, sonraki faz tetikleyicileri.

## Bağlam

Nodrat roadmap'i [docs/strategy/risk-register.md §5](../../docs/strategy/risk-register.md) içinde tanımlı. Bu topic onu güncel durum + KS noktaları + cross-link bilgileriyle zenginleştirir.

## Timeline overview

```
2026 ─────────────────────────────────────────────────────────
   Q1: MVP-1 production launch
   Q2: MVP-1.1 → 1.6 hardening (eval, settings, UI, VLM, infra, observability)
   Q2: MVP-2 delivered (Mayıs — 19 hafta erken!)
   Q3: KS-2 acceptance window (#385-#389) → MVP-3 başlangıcı
   Q4: MVP-3 paid launch (Kasım hedefli)
2027:
   Q1+: MVP-4+ — comparison mode tam, Faz 4 görsel, Faz 5 stil, EN dil
```

## MVP-1 — "Çalışan minimum" ✅

```text
Hedef:        2026-07-31 (8-12 hafta) → ERKENVERELDİ Q1
Gerçekleşen:  Production launch (https://nodrat.com)
Kapsam:       PRD Faz 0+1+2+3 (cut-list §4.9 birebir)
                12 sayfa, 12 tablo, ~20 endpoint
                3 RSS kaynak, current mode, X post output
                LLM: DeepSeek V3 only
                Embedding: NIM bge-m3
KS-1:         ⚠️ Resmi acceptance retro pending (bkz. [[kill-switch]])
                ✅ Discovery validation (27 görüşme)
                ✅ Avukat ToS/Privacy review
                [ ] Extraction ≥%70 — post-hoc kontrol
                [ ] Alpha 5+ olumlu — post-hoc
                [ ] Halü <%5 — eval framework MVP-1.1'de eklendi
                [ ] Maliyet <$0.01/gen — provider_call_logs
```

## MVP-1.1 — Production Hardening ✅ (2026-05-15)

```text
Hedef → Gerçekleşen: 2026-05-15
Eklenenler:
  ✅ Eval framework (golden test set + LLM-as-judge)
  ✅ Citation validator (#180 — embedding-bazlı kanıt eşleme, cosine ≥0.55)
  ✅ Cross-encoder reranker (#181 — NDCG@10 0.6153 → 0.6905)
  ✅ RAPTOR-Lite haftalık özet kart üretimi (#182)
  ✅ Geographic filter
  ✅ Importance scoring
  ✅ Summary output (multi-item bullet, NotebookLM-benzeri, #173)
  ✅ Intent classifier (multi_summary | single_post | thread)
  ✅ Time-aware retrieval ("son N" hybrid)

Sebep: KS-1 halü <%5 + citation %100 hedefleri için MVP-1 base'i tek başına yeterli değildi.
```

## MVP-1.2 — Admin Settings Panel ✅ (2026-05-31, Epic #262)

```text
Eklenenler:
  ✅ 42 admin setting (10 grup) — UI'dan tunable
  ✅ 3 LLM prompt runtime-tunable
  ✅ SettingsStore (versioned + audit)
  ✅ PromptsStore
  ✅ Redis pub/sub (cluster-wide config update)

Sebep: Operasyonel verimlilik — config değişiklikleri için container rebuild gerekmemesi.
Sapma not: MVP-1 cut-list'te yoktu; "MVP-1.2 hardening" olarak eklendi.
```

## MVP-1.3 — UI Modernization (shadcn) ✅ (2026-06-07, Epic #275)

```text
Eklenenler:
  ✅ Admin paneli shadcn radix-luma preset
  ✅ Sidebar primitive
  ✅ Auth + legal + app layout senkron

Sebep: UX polish + tasarım borcu temizleme.
Sapma not: Cut-list dışıydı.
```

## MVP-1.4 — Image Pipeline (VLM) ✅ (2026-05-06, Epic #300)

```text
Eklenenler:
  ✅ Process & discard mimarisi (bytes saklanmaz, sadece metadata)
  ✅ NIM Llama 4 Maverick VLM (caption + OCR + depicts)
  ✅ Site profile sistemi (BBC/Habertürk/Evrensel/AA/TRT/Yeşil Gazete)
  ✅ Reklam/logo/öneri haber filter
  ✅ suggest_image generation entegrasyonu

Çıktı:
  Storage 5 TB/yıl → 90 GB/yıl (98% azalma)
  R-OPS-05 ✅ ÇÖZÜLDÜ

Sebep: Storage cost mitigation. Faz 4 plan-dışı erken eklendi (kontrollü).
```

## MVP-1.5 — Infrastructure Migration ✅ (2026-05-06, Epic #215)

```text
Eklenenler (PR-1..PR-10):
  ✅ Contabo Cloud VPS 10 → Cloud VPS 40 yükseltme (4 vCPU/8 GB → 12 vCPU/47 GB/484 GB)
     — bkz. [[contabo-vps-hosting]] locked decision; production hep Contabo, sadece plan upgrade
  ✅ Backblaze B2 → Contabo Object Storage (restic backend swap, #330 / `714d5b2`)
  ✅ Local BAAI/bge-m3 embedding adapter (#345/#346/#350,
  ✅ Production migration: pg_dump + MinIO + apps rsync, DNS cutover
  ✅ Cold tier retention task (30+ gün raw_html → Contabo OS)
     — [[hot-cold-tier]]
  ✅ body_html drop policy (24h sonrası NULL)
  ✅ pgvector binary quantization (1024 float32 → bit(1024), 31x sıkışma)
     — [[binary-quantization]]
  ✅ Local bge-m3 + Dockerfile preload (~2.3 GB)
  ✅ Local bge-reranker-v2-m3 + Dockerfile preload (~568 MB)
  ✅ Doc senkron (architecture, unit-economics, ropa, INDEX, CHANGELOG)

Deferred:
  ⏭️  PR-7 #222 Chunk dedup (canonical_url 0 dup yakaladı)

Spawn issues (sonraki MVP'lere):
  #345 — NIM → local bge-m3 embedding re-embed migration
  #347 — Local rerank eval gate (NDCG@10 NIM vs Local)
  #331 — LE cert kontrolü
```

## MVP-1.6 — Admin Observability + UI Polish ✅ (2026-05-07, Epic #352)

```text
Eklenenler:
  ✅ Admin observability dashboard
  ✅ UI polish + #299 landing redesign

Sebep: Operasyonel + GTM polish.
```

## MVP-2 — "Kullanılabilir SaaS" ✅ DELIVERED (2026-05-07)

```text
Hedef:        2026-09-29 (Hafta 20)
Gerçekleşen:  2026-05-07 (-19 hafta erken!)
Sonuç:        12 issue + 17 PR, milestone closed

Eklenenler:
  ✅ Selector test UI (#70 — R-OPS-01 admin operasyon)
  ✅ Category page kaynak desteği (#71 — 3 pagination type)
  ✅ Source config versioning + rollback UI (#75)
  ✅ X thread + summary + headline output type (#73)
  ✅ Tone (8) + length (3) variations (#74)
  ✅ Comparison mode feature flag + telemetry (#51)
  ✅ Search-as-a-Service Phase A backend + Phase B /ara UI (#261)
  ✅ Landing redesign — hero/features/pricing (#299)
  ✅ PMF survey scaffold (#55)
  ✅ DeepSeek v4-flash thinking-disabled fix
  ✅ asyncpg pool tune + max_connections=300 (#256)
  ✅ Cloudflare Origin CA + Full(strict) (#331)
  ✅ Provider HTTP timeout runtime tunable (#273)
  ✅ Email pipeline production e2e smoke (#243)
  ✅ Web healthcheck localhost IPv4 fix (#294)

Trial flow:
  ⚠️ Anonim üretim KALDIRILDI (#72 refactor) — paid plan card-required (MVP-3)

KS-2 acceptance — MVP-3 cut-over'a taşındı:
  #385 — alpha test (5-10 closed beta, D7 retention)
  #386 — eval suite production runner (halü <%2)
  #387 — 25 persona görüşmesi
  #388 — load test sustained 50→200 RPS (k6 + p95)
  #389 — KS-2 final acceptance + release notes

Bilinçli ertelenmiş:
  • Phase C (publisher widget + advanced SEO) → #384 (MVP-3)
  • Weekly mode UI (query planner zaten destekliyor)
```

## MVP-2.1 — Pipeline Performance Optimization ✅ DELIVERED (2026-05-08)

```text
Hedef:        2026-05-28 → bitti 2026-05-08 (3 hafta erken)
Açıldı:       2026-05-08
Durum:        ✅ DELIVERED (3 PR, 7/7 sub-issue)
Milestone:    GitHub #14
Epic:         #391

Kapsam (7 sub-issue, 3 PR):
  PR #411 (#394 + #395 + #397): citation batch + settings paralel + normalize tek nokta
  PR #416 (#396 + #398): short query candidate_pool + citation embedding reuse
  PR #418 (#392 + #393): DeepSeek prompt prefix stability + content top_k 10→5

Hedef metrikler (baseline → tracking):
  Input token / req:  5,800 → 3,800   (-%34)
  P95 latency:        4-8s → 3-6s     (-1s)
  $/req (DeepSeek):   $0.0036 → $0.0027  (-%25)

Sebep: R-FIN-01 (LLM cost runaway) M7 mitigation. /app/generate içerik
       üretim hattında fark edilen verimsizlikler (prompt prefix dynamic,
       context şişkin, citation per-post embedding, settings DB hit yığını).
       /ara endpoint'i ayrı (Search-as-a-Service); retrieval altyapı
       paylaşımı dışında bu epic /app/generate'e özgü.

Kalite gate (her PR öncesi):
  Halü <%2, citation accuracy ≥%95, JSON parse error <%1 (R-PRD-01)

Önemli: Yeni feature DEĞİL, refactor + optimization. Pre-MVP-3 paid
        launch öncesi ideal landing window — hedef tarihten 3 hafta önce
        bitti, kullanıcı hızlı iterasyon ile.

Baseline + tracking: [[pipeline-performance-baseline]] (token/latency/$
        snapshot 2026-05-08; her PR sonrası tracking tablosu güncellenir).
```

## MVP-3 — "Ücretli launch" ⏳ HEDEF 2026-11-30

```text
Kapsam:
  + Faz 6 ödeme entegrasyonu (Iyzico TL, #53)
  + e-Arşiv fatura
  + Plan / subscription tabloları
  + Multi-seat agency (P1B persona şart)
  + Claude Haiku premium ([[claude-haiku-4-5]] aktivasyon)
  + Stil profili (Faz 5 #62/#63/#64)
  + 2FA admin (#56)
  + /admin/plans + /app/billing UI (#76/#77)
  + KS-2 acceptance ölçümleri (#384-#389)
  + Public launch

KS-3 acceptance:
  [ ] Free → paid conversion ≥ %3
  [ ] Trial → free conversion ≥ %20
  [ ] Pro tier en az 5 paid user (mock onboarding)
  [ ] Cost per user < tier maliyet limiti

No-go:
  Conversion <%1 → pricing model yeniden
  WTP <250 TL → tier/feature mix yeniden
```

## MVP-4+ — "Genişleme" 📅 PLANLI

```text
+ Comparison mode tam (R-PRD-03 telemetry kararı sonra)
+ Görsel zeka tam (Faz 4)
+ Stil profili tam (Faz 5)
+ Premium model tier (Sonnet 4.6 expansion)
+ Stripe USD
+ Çoklu dil (EN)

Yatay ölçek:
  MRR ≥ $5K (≈ 250 paid user) sonrası:
    - Web/API behind Caddy LB (replica)
    - Worker'lar ayrı VPS'e
    - PgBouncer connection pooling
    - Read replica (analytics)
    - CDN (Cloudflare) static assets
```

## Sürpriz: MVP-2'nin -19 hafta erken delivery'si

Bu büyük ön-yükleme dokümante edilmiş net gerekçe yok. Olası nedenler:

1. **Discovery validation çok güçlü çıkması** (27 görüşme, %100 olumlu) → MVP-2 scope güveni arttı.
2. **AI agent verimliliği** (Claude Code, Cursor) — solo founder velocity'yi 3-5x büyüttü.
3. **MVP-1.x hardening fazlarında "ek olarak" MVP-2 feature'larının dahil edilmesi** — örn. eval framework, settings panel, image pipeline.

> **Aksiyon:** Retro issue açılmalı: "MVP-2 -19 hafta erken delivery — gerçek nedenler ve MVP-3 timeline impact." [[kill-switch]] sayfasındaki açık soru.

## İlişkiler

- **Beslediği kararlar:** [[mvp-1-scope-lock]] (MVP-1 anchor), [[contabo-vps-hosting]] (MVP-1.5).
- **İlgili kavramlar:** [[mvp-cut-list-method]] (her MVP'de uygulanır), [[kill-switch]] (KS-1/2/3 noktaları).
- **İlgili topics:** [[mvp-1-scope]] (MVP-1 detay envanter), [[risk-catalog]] (KS no-go riskleri).
- **İlgili varlıklar:** [[deepseek]], [[claude-haiku-4-5]] (MVP-3'te aktif), [[contabo-vps]].

## Açık sorular / TODO

- **KS-1 retro:** MVP-1 acceptance check resmi olarak yapıldı mı? Hangi kriter ✅, hangi ⚠️? Issue açılmalı.
- **MVP-3 timeline impact:** MVP-2 -19 hafta erken delivered olduğu için MVP-3 da 2026-Q3'e çekilebilir mi? Yoksa KS-2 acceptance bekleniyor mu (#385-#389)?
- **MVP-4+ tarihi:** Hala planning mode. MVP-3 launch sonrası 2027-Q1+ tahmini ama net değil.
- **Sapma metriği:** MVP-1.2/1.3/1.6 cut-list dışı eklemeler. "Controlled expansion" mı, scope creep mi? Retro.

## Kaynaklar

- [docs/strategy/risk-register.md §5 (revize roadmap)](../../docs/strategy/risk-register.md)
- [INDEX.md §5b (milestone tablosu)](../../INDEX.md)
- [README.md (Milestone durumu)](../../README.md)
- [CHANGELOG.md](../../CHANGELOG.md) — sürüm geçmişi detay
