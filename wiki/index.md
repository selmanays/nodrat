---
title: Wiki Index — Sayfa Kataloğu
type: hub
updated: 2026-05-10
last_lint: 2026-05-08
last_resync: 2026-05-10 (akşam)  # MVP-1.7 SFT Foundation delivered — 6 issue × 11 PR / 1 günde production'da: backend (generations cols + KVKK consent + endpoints + ETL worker + admin dashboard) + frontend (hooks + onboarding + /app/me toggle + /admin/sft Pipeline Ayarları + 'Şimdi çalıştır' button) + 4 hukuki doc v0.4 opt-out modeli. Wiki planning sayfaları (own-slm-strategy + trendyol-llm-base + sft-data-pipeline) hâlâ PR #574'te bekliyor (kullanıcı kararı).
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
- [[trendyol-llm-base|Trendyol-LLM-7B-chat-v4.1.0 (planlanan SLM base)]] — Apache 2.0 lisanslı Qwen 2 7B üstüne Türkçe fine-tune. Nodrat'ın gelecekteki kendi domain-spesifik SLM'inin base model'i. `status: planned` — MVP-3 sonrası eğitim. ([[own-slm-strategy]])

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
- [[multi-query-rewrite|Multi-query rewrite — RAG retrieval 2 varyant + RRF füzyon]] — Perplexity-style: orijinal sorgu + sınırlı enriched (topic_query + keywords[:3]) paralel arama, RRF k=60 ile birleşim. PR-E.1 ile 3. varyant kaldırıldı (Toprakaltı→Slovenya tüneli too broad). MVP-1.8 PR #626 + #633.
- [[multi-source-synthesis|Multi-source synthesis — Perplexity-style sentez]] — content_generator prompt: her iddia min 2 kaynak referansı, çelişen kaynaklar açık belirtim, tek-kaynak disclaimer. PR-E.3. MVP-1.8 PR #633.
- [[cross-source-agreement|Cross-source agreement — kaynaklar arası onay]] — 4 level (hemfikir/kısmen çelişen/tam çelişen/tek kaynak); per-source perspective ile birleşir. PR-F. MVP-1.8 PR #634.
- [[hyde-feature-flag|HyDE feature flag — hipotetik döküman embed]] — DeepSeek hipotetik haber → embed → RRF varyantı. `retrieval.hyde_enabled` (default OFF, A/B). MVP-1.8 PR #627.
- [[streaming-json-parser|Streaming JSON post extractor]] — DeepSeek json_mode chunk akışından `posts[N]` objelerini erkenden emit eden brace-aware parser. Issue #527, MVP-2.2.
- [[sft-data-pipeline|SFT Data Pipeline — generations log → training_samples ETL]] — User-action telemetry + KVKK consent gate + PII secondary scan + nightly Celery ETL → ChatML training_samples + JSONL export. MVP-1.7 milestone (#563-#569), Faz 0 ([[own-slm-strategy]]).
- [[conditional-http-get|Conditional HTTP GET — ETag + If-Modified-Since]] — RFC 7232 cache-validation; RSS fetch'te 304 Not Modified path = body parse yok, queue dispatch yok, ~%80 bandwidth ↓. PR #571 (#565 Faz 0+1).
- [[adaptive-polling-tier|Adaptive polling tier — hot/normal/cold/hibernate]] — RSS kaynak başına yayın hızına göre tier (60sn / 5dk / 30dk / 4saat). Faz 0+1 schema (PR #571); Faz 2 shadow mode hesabı production'da (PR #581 + #582 hotfix, 2026-05-10) — would_be_tier hesaplanır + tier_metadata JSONB telemetri yazılır; polling_tier dokunulmaz. Faz 3'te apply mode.

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

### RAG quality (MVP-1.8)
- [[chunks-first-retrieval|Chunks-first retrieval — RAG hazinesini görünür kılma]] — chunks PRIMARY (90 gün, top_k 15+), agenda_cards secondary. Singleton + eski article'lar görünür. Tek-kaynak haberi disclaimer ile cevaplanır (Plan B). 3800+ cleaned article hazinesinin tamamı arama uzayında. PR #638 (kök çözüm — kullanıcı "hazinemizi çöpe atıyoruz" feedback'i).
- [[source-diversity-cap|Source diversity cap — aynı domain'den max 2 kart]] — Tek-kaynak halüsinasyon koruması; multi-query RRF sonrası filter. Üretim: 20-sorgu testte ortalama 3-4 farklı domain. PR #624.
- [[chunks-always-on-fallback|Chunks always-on fallback — agenda<3 ise chunks ekle]] — PR-H ile **chunks-first**'e evrildi. Yeni mimari: [[chunks-first-retrieval]]. PR #624 → #638.
- [[entity-match-relevance|Entity match relevance — ana konu + key entity match zorunlu]] — Kategorik benzerlik yetmez ama kelime kelime tam eşleşme de aşırı sıkı. ANA KONU + KEY ENTITY anlam-bazlı eşleşme. PR #630 + #633 rebalance + #648 yamaların kaldırılması.
- [[smart-quote-normalization|Smart-quote normalization — RAG körlük kök sebebi]] — Bianet/Hürriyet/T24 gibi smart-quote (`""`/`''`) kullanan kaynaklarda phrase-match patlıyordu (sadece chr39+chr8217 silinen REPLACE chain). 19 quote varyantı tek noktadan strip + article metadata sparse pool + entity-aware rerank boost (genel kural). PR #648 (kök çözüm — kullanıcı "yama mı yaptın" denetimi sonrası DB doğrulamayla bulundu). Toprakaltı Bianet article #1 retrieve.
- [[ragflow-tier-rebuild|RAGFlow-tier rebuild — niş entity recall (4 faz)]] — Founder 11 niş test, 7 başarısız → DB analizinde chunker semantic dilution. 4 faz: (1) sentence-window chunker target 256 + re-chunk task; (2) self-query date filter; (3) HyDE always-on (streaming parity dahil); (4) LLM answer-aware rerank top-3. Eval framework + 11-sorgu golden set. Üretim: Emine Aydınbelge ❌→#1, Sovyetler/Trump 6 Mayıs top-10. PR #653/#654/#655.
- [[ner-pipeline|NER pipeline — niş entity recall sıçraması (Faz 6+7a)]] — Bge-m3 Türkçe niş entity sınırına Faz 6 NER ile çözüm. DeepSeek-based entity extraction (person/place/org/event/money/number), entities tablosu + hybrid_search RRF stream (K=30). Faz 7a: numeric entity vurgu (yüzde/oran/sayı). Üretim: 27.3% → 82%+ UI test (9-10/11). 10 PR (#668-#679): NER + prompt chunks-primary + halüsinasyon yasağı + sufficiency archive bypass.
- [[pipeline-optimization|Boruhatları optimizasyonu — TTFT + cost + concurrency (#684)]] — Worker concurrency 1→4, DB pool 5→10, max_connections 300→500, model warm-up startup, HyDE conditional (generic skip), multi-query batch embedding, top_k 15→10, content max_tokens 2000→1500, 4200 article re-NER backfill. Etki: TTFT 16-22sn → 10-15sn, cost -%40, bulk ops 3 saat → 45dk. 4 PR (#685, #686, #688). NER backfill bittiğinde benchmark recall@5 hedef 75-80%.

### Performance / streaming
- [[sse-streaming-default|SSE streaming default — /app/generate-stream]] — TTFT <1s hedefi; DeepSeek `stream:true` + speculative retrieval + planner cache + post-stream citation/image. Eski `/app/generate` backward-compat aynen korunur. Sahte hız değil — gerçek streaming, kalite gate'leri korunur. PR #528 / Issue #527.
- [[realtime-rss-polling|RSS realtime polling — adaptive tier + Conditional GET]] — Sabit 30dk polling → Faz 2'de adaptive tier (hot 60sn / normal 5dk / cold 30dk / hibernate 4saat). Faz 0+1 (PR #571, 2026-05-10) schema foundation + [[conditional-http-get]] (304 path → bandwidth ~%80↓) + admin runtime edit ship. Forward-compatible (flag default false). Gündem radarının ön gerek altyapısı.

### Payment / billing
- [[lemon-squeezy-payment-provider|Lemon Squeezy payment provider (MoR, USD primary) ✅ avukat şartlı + vergi danışmanı onaylı]] — Faz 6 ödeme stack'i Iyzico'dan LS MoR'a (Epic #448 review-resolved 2026-05-08). Şahıs ticari kazanç mükellefi (Limited Şti. defer, $5K plan/$10K convert), e-Arşiv kalktı (LS keser), USD primary. Multi-seat = LS variant + seat counter. KVKK m.9 yurt dışı transfer açık rıza zorunlu (frontend #453 + backend server-side enforcement #470). 3 yeni canonical doc: refund-policy.md, mesafeli-satis-sozlesmesi.md, payment-fallback-plan.md (R-FIN-04 6-senaryo).

### Strategy / long-term
- [[own-slm-strategy|Own SLM strategy — Trendyol LLM v4.1 üzerine domain-spesifik fine-tune]] — Nodrat'ın uzun vade kendi Türkçe SLM'i: [[trendyol-llm-base]] (Apache 2.0) üzerine DAPT + SFT + DPO + tokenizer extension. Hedef "Basamak 3" (savunulabilir 'kendi modelimiz' iddiası). Faz 0 = MVP-1.7 SFT Foundation milestone (Issues #563-#569, delivered 2026-05-10). Maliyet ikincil; motivasyon: vendor lock-in azaltma + IP/moat + talent.

## Sources (kaynak özetleri)

> Her `docs/...` doküman için 1 sayfa: ne içerir, ana çıkarımlar, hangi entity/concept'lere bağlanır.

- [[architecture-md|architecture.md]] — Teknik mimari ve deployment; 9 prensip + 5 worker + provider katmanı + storage tier + secrets workflow. v0.3 (#410) — DeepSeek + Hosting + Backup + embedding (#350, 2026-05-06) **tüm çelişkiler resolved**. Production durum: tüm runtime override'lar admin panel'de kontrol edilebilir.
- [[risk-register-md|risk-register.md]] — 30 risk + MVP cut-list + KS-1/2/3 kill-switches + roadmap. v0.2 (#414) — §2.1/§2.2 skor anomalileri resolved (R-FIN-02, R-MKT-02, R-MKT-03 §2.2 → §2.1).

---

## İstatistik

- Toplam sayfa: **111** (**15 entity** + **25 concept** + 6 topic + **27 decision** + **35 source** + 3 hub) — 2026-05-11: MVP-1.8 sprint final. Bugün 4 PR: #713 (4 bug + Performance mimari card), #715 (cards path NER + locked decision revoke), #717 (cards NER NameError fix), #718 (RAG İzlencesi final senkron + NER K=10 + mode-aware phrase boost + Inspector "production" suite). RAG İzlencesi 8 sekme tamamen prod-pipeline ile %100 senkron — kullanıcı /api/generate akışı ↔ admin RAG İzlencesi Inspector "production" suite default ile aynı sonucu döner.
- Kaynak sayısı: **5** / 32 (`docs/**/*.md`) — `architecture.md`, `risk-register.md`, `data-model.md`, `api-contracts.md`, `prompt-contracts.md` (#696 D16)
- Son ingest: **2026-05-11 (#696 D16)** — `docs/engineering/data-model.md` (v0.4), `api-contracts.md` (v0.6), `prompt-contracts.md` (v0.4) source özet sayfaları olarak ingest edildi. Detay entity/concept çıkarımı sonraki sprintte planlı (her doc 1000-2200 satır).
- Son re-sync: **2026-05-10 (akşam)** (MVP-1.7 SFT Foundation kapanış sync; öncesinde #578 Faz 2 + #582 hotfix, #565 Faz 0+1)
- Son lint: **2026-05-11** (#696 D18 sweep #2 — bidirectional backlink fix: 201 violation → **0** (2-pass auto); 163+38 = 201 backlink eklendi; yetim 0; çelişki 0)
- Açık çelişki sayısı: **0** ✅
- Açık operasyonel migration: **0** ✅ (MVP-1.7: 20260510_0200 generations SFT cols + 20260510_0300 KVKK consent + 20260510_0500 training_samples production'da)
- Açık doküman senkronizasyonu: **0** ✅ (data-model v0.4 + api-contracts v0.6 + 4 hukuki doc v0.4 + INDEX.md v1.8 + wiki katalog tüm güncel)
- Devam eden ops todo (opsiyonel): SFT kill switch (sft.curator.enabled=false default — kullanıcı /admin/sft'den 1 toggle ile açabilir); ilk eğitim run'ı için ~10K sample biriktirme süreci (~3-4 ay tahmin, opt-in oranına bağlı); Faz 2 adaptive tier hesabı (#565 follow-up); Faz 3 beat refactor + worker concurrency; Faz 4 URL/scrape opt-in realtime; drill-down panel (#461); local rerank flip (#347 eval gate).
- Açık locked decision: **19** (#440 sonrası 2 + Epic #448 sonrası 1 + 2026-05-09: shadcn-customization-policy + sse-streaming-default + 2026-05-10: realtime-rss-polling + own-slm-strategy + 2026-05-11: age-gate-18-plus + model-improvement-default-opt-out + pre-launch-security-checklist + margin-70-target + geographic-pricing-policy)
  - **REVOKED 2026-05-11:** ~~cards-path-ner-out-of-scope~~ (#714 — yanlış varsayım üzerine kuruluydu, cards path PRIMARY /api/generate retrieval olduğu fark edildi, NER eklendi)
