---
title: Wiki Index — Sayfa Kataloğu
type: hub
updated: 2026-05-10
last_lint: 2026-05-08
last_resync: 2026-05-10  # Contabo Object Storage code-level sync — 5 aşama topic + entity/concept/topic backlink + flag çelişkisi flagged
---

# Wiki Index

Bu dosya **wiki içindeki her sayfa için** tek satırlık girişler içerir. LLM her `ingest` ve `lint` pass'ında bu indeksi günceller.

> Kanonik **doküman indeksi** için (PRD, architecture vb. `docs/` altındaki dosyalar) kök [INDEX.md](../INDEX.md)'ye bak. Bu dosya `wiki/` özelidir.

## Format

```
- [[slug|Görünen ad]] — 1 cümle özet
```

Varsa kategoriye göre gruplanır. Tarih veya kaynak sayısı opsiyonel metadata olarak eklenebilir: `(2 kaynak, 2026-05-07)`.

---

## Entities (varlıklar)

> Somut "şey"ler: provider, persona, servis, platform, tool, doküman, risk objesi.

### Provider / servis / infra
- [[deepseek|DeepSeek (default LLM)]] — Free/Starter/Trial tier'larında default LLM. **DeepSeek native API** + `deepseek-v4-flash` (thinking-disabled). NIM endpoint fallback. Eski slug `deepseek-v3` aliases içinde.
- [[claude-haiku-4-5|Claude Haiku 4.5]] — Pro/Agency tier'larında premium LLM (Anthropic native API), Faz 2'de operasyonel.
- [[local-bge-m3|Local BAAI/bge-m3 (embedding provider)]] — `BAAI/bge-m3` SentenceTransformer, VPS CPU üzerinde, 1024-dim. Tek embedding provider.
- [[contabo-vps|Contabo Cloud VPS 40 + Object Storage]] — Production hosting (12 vCPU / 48 GB / 250 GB NVMe), MVP-1.5'ten itibaren.
- [[celery-worker|Celery worker stack]] — 5 queue grubu + scheduler, Redis broker üzerinde async iş yığını.
- [[shadcn-ui-stack|shadcn/ui (preset b1VlIttI / radix-luma)]] — Tek UI bileşen kütüphanesi (`apps/web`); Tailwind v4 + Radix primitives. Init: `pnpm dlx shadcn@latest init --preset b1VlIttI --template next --monorepo`. MCP: `mcp__Shadcn_UI__*`.
- [[style-profile-system|Style Profile System (Faz 5)]] — Pro+ stil profili servisi: 2 tablo + DeepSeek Style Analyzer Celery task + /app/style-profiles + generation entegrasyonu. Pro=3, Agency=10 slot.

### Risk objeleri
- [[risk-fsek-telif|R-LGL-02 — FSEK Telif Tazminat]] — Skor 12 🔴 (en yüksek). 7 katmanlı mitigation aktif; M1 = [[twenty-five-word-quote-cap]].
- [[risk-kvkk-violation|R-LGL-01 — KVKK İhlali]] — Skor 9 🔴. Mitigation: aydınlatma + checkbox + DPO + [[pii-redaction-mandatory]] + ROPA.
- [[risk-source-fragility|R-OPS-01 — Kaynak HTML Kırılganlığı]] — Skor 9 🔴. Mitigation: source health + selector test UI + 3-tier extraction + site profile.
- [[risk-cost-runaway|R-FIN-01 — LLM Cost Runaway]] — Skor 9 🔴. Mitigation: per-user rate limit + provider hard cap + alarm + circuit breaker.

## Concepts (kavramlar)

> Soyut kavramlar: metric, technique, rule, framework.

### Architecture / technique
- [[provider-abstraction|Provider abstraction]] — A3 mimari prensibi, `ModelProvider` Protocol; vendor lock'a immune yapı.
- [[hot-cold-tier|Hot/Cold storage tier]] — Son 30 gün VPS lokal (HOT), 30+ gün Contabo Object Storage (COLD); MVP-1.5'ten beri aktif.
- [[binary-quantization|pgvector binary quantization]] — `vector(1024)` yanına `bit(1024)` 32x sıkışma + HNSW hamming index; default flag False (eval gate öncesi).
- [[queue-management|Queue management — Celery broker introspection + DLQ severity]] — `/admin/queue` 4 ana queue (Redis LLEN + inspect active) + `failed_jobs.severity` 3-tier (error/warning/permanent_info) + Celery `apply_async` retry. Epic #443 (PR #447, #449, #454, #456).
- [[style-analyzer-prompt|Style Analyzer prompt v1.0]] — DeepSeek V3 JSON-mode prompt; 3-50 sample, 80k char limit, 7-alan şema (style_name, sentence_length, tone, rhetorical_patterns, avoid, sample_transforms). FSEK 25-kelime + PII-redaction kuralları.
- [[speculative-retrieval|Speculative retrieval — embed paralel başlat]] — `embed(raw_query)` Query Planner ile paralel; raw≈enriched ise embedding reuse. Issue #527, MVP-2.2.
- [[planner-cache|Query Planner Redis cache — gün granülü]] — `qp:v1:sha1(req+locale+tier+yyyymmdd)` 24h TTL; cache hit ~10ms vs LLM ~1.5s. Issue #527, MVP-2.2.
- [[streaming-json-parser|Streaming JSON post extractor]] — DeepSeek json_mode chunk akışından `posts[N]` objelerini erkenden emit eden brace-aware parser. Issue #527, MVP-2.2.

### Methodology / framework
- [[risk-scoring|Risk skor metodolojisi]] — 1-25 ölçek (olasılık × etki), 8 kategori, 🔴🟡🟢 gruplar.
- [[mvp-cut-list-method|MVP cut-list (IN/OUT/LATER) framework]] — PRD scope'undan MVP'ye inmek için disiplin.
- [[kill-switch|Kill-switch (KS-1/2/3) gate'leri]] — Her MVP geçişinde acceptance + no-go kriterleri.

## Topics (sentez / karşılaştırma)

> Birden fazla sayfayı birleştiren analiz, karşılaştırma, özet.

- [[llm-provider-strategy|LLM provider stratejisi]] — Tier × provider routing + cost karşılaştırma + fallback chain sentezi.
- [[risk-catalog|Risk catalog (30 risk inventory)]] — Tüm risklerin tek bakışta envanteri + heat-map + locked decisions kapsama matrisi.
- [[mvp-1-scope|MVP-1 scope envanteri]] — Faz × özellik tablosunda IN/OUT/LATER tam liste + MVP-1.x sapma analizi.
- [[mvp-roadmap|MVP roadmap]] — MVP-1 → 1.1 → 1.6 → 2 → 2.1 → 3 → 4+ timeline + KS noktaları + sürpriz erken-delivery analizi.
- [[pipeline-performance-baseline|Pipeline Performance Baseline & Tracking]] — `/app/generate` baseline metrikleri (token/latency/$ snapshot 2026-05-08) + her PR sonrası tracking tablosu. MVP-2.1 ilerlemesi izlenir.
- [[data-pipelines|Data Pipelines — 8 boru hattı overview]] — Source crawl, embedding, clustering+agenda, image VLM, RAPTOR weekly, /app/generate, /ara public search, object storage + cold tier + backup. Her pipeline için trigger + akış diyagramı + DB tabloları + provider envanteri.
- [[contabo-object-storage-usage|Contabo Object Storage — 5 kullanım aşaması]] — eu2.contabostorage.com bucket'ının kod-seviye kullanımı: cold archive task + cold restore + restic backup + admin telemetry + boto3 factory. Path:line refs, settings flag durumu (`cold_tier.enabled` default False), bucket prefix haritası. 2026-05-10.

## Decisions (locked kararlar)

> Tüm Nodrat dokümanlarında tutarlı kalan, geri dönülmez kararlar.

### LLM / provider
- [[deepseek-default-llm|DeepSeek default LLM]] — Free/Starter/Trial için varsayılan LLM. Native API + `deepseek-v4-flash` (thinking-disabled). NIM endpoint fallback. Cost $0.27/$1.10 per 1M (kampanya: %75 indirim 2026-05-31'e kadar).
- [[claude-haiku-premium-llm|Claude Haiku 4.5 premium LLM]] — Pro+ tier'larda premium model; Agency comparison_generation için Sonnet 4.6 upgrade.

### Infrastructure
- [[contabo-vps-hosting|Contabo Cloud VPS 40 hosting]] — MVP-1.5'te Contabo VPS 10'dan upgrade (production hep Contabo); backup için aynı sağlayıcı Object Storage (önceki backup B2'den migrate).

### Legal / output
- [[twenty-five-word-quote-cap|25-kelime direct quote hard cap (FSEK)]] — Output validator + system prompt çift güvenlik; R-LGL-02 ana mitigation.
- [[pii-redaction-mandatory|PII redaction zorunlu (LLM çağrısı öncesi)]] — Avukat eklemesi; KVKK + yurt dışı transfer mitigation.

### Scope
- [[mvp-1-scope-lock|MVP-1 scope lock]] — 12 sayfa / 12 tablo / ~20 endpoint; MVP-1 production'da delivered.
- [[style-profiles-pro-paywall|Stil profili Pro+ paywall + slot quota]] — Faz 5 server-side enforcement; Pro=3, Agency=10. Free/Starter 402; client-side bypass yok. Plan seed migration ile sabit (admin UI'da read-only).

### Engineering convention
- [[endpoint-naming-policy|Endpoint adlandırma politikası — milestone-bound ad yasak]] — Production endpoint URL'leri sürüm/sprint/epic kodu içeremez (#440 vakası). Eylem-bazlı isim zorunlu (örn. `/pipeline-comparison`, `/test-listing`).
- [[pipeline-observability-location|Pipeline observability yeri — /admin/rag (LLM), /admin/observability (infra)]] — LLM/RAG pipeline metric araçları `/admin/rag` sayfasına sekme olarak eklenir. `/admin/observability` infrastructure-only.
- [[shadcn-customization-policy|shadcn bileşen özelleştirme politikası]] — `apps/web/src/components/ui/*.tsx` shadcn defaults, **dokunulmaz**; özelleştirme bileşenin çağrıldığı yerde (page/block) `className`/`variant`/`prop` ile yapılır. shadcn ekleme/inceleme `mcp__Shadcn_UI__*` MCP üzerinden tercih edilir.

### Performance / streaming
- [[sse-streaming-default|SSE streaming default — /app/generate-stream]] — TTFT <1s hedefi; DeepSeek `stream:true` + speculative retrieval + planner cache + post-stream citation/image. Eski `/app/generate` backward-compat aynen korunur. Sahte hız değil — gerçek streaming, kalite gate'leri korunur. PR #528 / Issue #527.

### Payment / billing
- [[lemon-squeezy-payment-provider|Lemon Squeezy payment provider (MoR, USD primary) ✅ avukat şartlı + vergi danışmanı onaylı]] — Faz 6 ödeme stack'i Iyzico'dan LS MoR'a (Epic #448 review-resolved 2026-05-08). Şahıs ticari kazanç mükellefi (Limited Şti. defer, $5K plan/$10K convert), e-Arşiv kalktı (LS keser), USD primary. Multi-seat = LS variant + seat counter. KVKK m.9 yurt dışı transfer açık rıza zorunlu (frontend #453 + backend server-side enforcement #470). 3 yeni canonical doc: refund-policy.md, mesafeli-satis-sozlesmesi.md, payment-fallback-plan.md (R-FIN-04 6-senaryo).

## Sources (kaynak özetleri)

> Her `docs/...` doküman için 1 sayfa: ne içerir, ana çıkarımlar, hangi entity/concept'lere bağlanır.

- [[architecture-md|architecture.md]] — Teknik mimari ve deployment; 9 prensip + 5 worker + provider katmanı + storage tier + secrets workflow. v0.3 (#410) — DeepSeek + Hosting + Backup + embedding (#350, 2026-05-06) **tüm çelişkiler resolved**. Production durum: tüm runtime override'lar admin panel'de kontrol edilebilir.
- [[risk-register-md|risk-register.md]] — 30 risk + MVP cut-list + KS-1/2/3 kill-switches + roadmap. v0.2 (#414) — §2.1/§2.2 skor anomalileri resolved (R-FIN-02, R-MKT-02, R-MKT-03 §2.2 → §2.1).

---

## İstatistik

- Toplam sayfa: **43** (**12 entity** + **11 concept** + 6 topic + **12 decision** + 2 source) — 2026-05-10: [[contabo-object-storage-usage]] code-level sync topic
- Kaynak sayısı: **2** / 32 (`docs/**/*.md`) — `architecture.md`, `risk-register.md`
- Son ingest: **2026-05-10** (Contabo Object Storage code-level sync — 1 yeni topic + 4 page update; kullanıcı sorusu "Contabo OS hangi aşamalarda kullanılıyor" → 5 aşama path:line ref'leriyle [[contabo-object-storage-usage]]; flag çelişkisi tespit edildi: `cold_tier.enabled` default False vs [[hot-cold-tier]] "MVP-1.5'ten beri aktif" — production app_settings doğrulaması açık)
- Son re-sync: **2026-05-10** (Contabo OS sync — kaynak: kod, wiki güncel değildi)
- Son lint: **2026-05-08** (file rename + cross-link integrity + duplicate content split)
- Açık çelişki sayısı: **1** ⚠️ ([[hot-cold-tier]] vs `cold_tier.enabled` default False — production app_settings'te flip durumu doğrulanmalı)
- Açık operasyonel migration: **0** ✅ (Epic #443 stabilizasyon + MVP-3 backend kick-off DB tamam — 4 yeni migration uygulandı, 5/5 smoke test PASS)
- Açık doküman senkronizasyonu: **0** ✅ (#527 + #529 + #539 wiki sync + 2026-05-10 Contabo OS sync — bu commit ile)
- Devam eden ops todo (opsiyonel, çelişki değil): drill-down panel (#461, sonraki oturum); provider key validity check task (R-OPS-07 candidate, NIM 403 incident öğrenimi); local rerank flip (`llm.use_local_rerank=false` hâlâ — NIM rerank aktif, local bge-reranker scaffold'u #224 hazır, eval gate #347); TTFB metric'in `provider_call_logs` schema'sına kalıcı eklenmesi (#527 follow-up); planner cache hit/miss counter Redis INCR (#527 follow-up); manual deploy script source path sanity check (#539 worktree drift dersi); **2026-05-10 yeni:** production'da `cold_tier.enabled` mevcut değer doğrulaması (admin panel /admin/settings veya /admin/system bucket cold/ prefix object count). **Kapatıldı 2026-05-09:** AA SPA migration kararı (#460/#71) — extractor multi-mode (#529) ile SSR HTML üzerinden çalışıyor, Playwright header gerekmedi.
- Açık locked decision: **11** (#440 sonrası eklenen 2 + Epic #448 sonrası 1 + 2026-05-09 frontend convention 1: shadcn-customization-policy + 2026-05-09 performance 1: sse-streaming-default)
