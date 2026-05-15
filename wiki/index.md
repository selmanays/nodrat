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
- [[deepseek|DeepSeek (default LLM)]] — MVP-1'de TÜM tier'larda default LLM. **DeepSeek native API** + `deepseek-v4-flash` (thinking-disabled). #720 ile NIM chat fallback decommission; `DEEPSEEK_API_KEY` zorunlu. Eski slug `deepseek-v3` aliases içinde (Obsidian search uyumu için).
- [[claude-haiku-4-5|Claude Haiku 4.5]] — Pro/Agency tier'larında premium LLM (Anthropic native API), Faz 2'de operasyonel.
- [[local-bge-m3|Local BAAI/bge-m3 (embedding provider)]] — `BAAI/bge-m3` SentenceTransformer, VPS CPU üzerinde, 1024-dim. Tek embedding provider.
- [[contabo-vps|Contabo Cloud VPS 40 + Object Storage]] — Production hosting (12 vCPU / 48 GB / 250 GB NVMe), MVP-1.5'ten itibaren.
- [[celery-worker|Celery worker stack]] — 5 queue grubu + scheduler, Redis broker üzerinde async iş yığını.
- [[shadcn-ui-stack|shadcn/ui (preset b1VlIttI / radix-luma)]] — Tek UI bileşen kütüphanesi (`apps/web`); Tailwind v4 + Radix primitives. Init: `pnpm dlx shadcn@latest init --preset b1VlIttI --template next --monorepo`. MCP: `mcp__Shadcn_UI__*`.
- [[style-profile-system|Style Profile System (Faz 5)]] — Pro+ stil profili servisi: 2 tablo + DeepSeek Style Analyzer Celery task + /app/style-profiles + generation entegrasyonu. Pro=3, Agency=10 slot.
- [[trendyol-llm-base|Trendyol-LLM-7B-chat-v4.1.0 (planlanan SLM base)]] — Apache 2.0 lisanslı Qwen 2 7B üstüne Türkçe fine-tune. Nodrat'ın gelecekteki kendi domain-spesifik SLM'inin base model'i. `status: planned` — MVP-3 sonrası eğitim. ([[own-slm-strategy]])
- [[wikipedia-provider|Wikipedia Provider (knowledge layer)]] — Wikipedia REST + Wikidata SPARQL HTTP client. Layer 2 (general knowledge) altyapısı. CC BY-SA 4.0, $0 cost, Redis 24h cache. 8 Wikidata factual property (P569 birth, P1082 population, P36 capital, ...). 13 unit test. PR [#812](https://github.com/selmanays/nodrat/pull/812).

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
- [[style-analyzer-prompt|Style Analyzer prompt v1.0]] — DeepSeek V4 Flash JSON-mode prompt; 3-50 sample, 80k char limit, 7-alan şema (style_name, sentence_length, tone, rhetorical_patterns, avoid, sample_transforms). FSEK 25-kelime + PII-redaction kuralları.
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
- [[query-class-classification|query_class — 4-sınıf kullanıcı sorgu sınıflandırma]] — Query Planner output field: `news_query | general_knowledge | meta_query | mixed`. `intent` (content-generation) ile karıştırılmamalı. **Rol değişti (#823):** routing değil → meta bypass + news-first tool gating + telemetri. PR #810→#823.
- [[retrieval-confidence-score|Retrieval Confidence Score — 5-signal fusion]] — semantic + source_count + recency + entity_match + citation_density fusion. **Rol değişti (#823): routing YAPMAZ, sadece telemetri** (observability + done event). PR #810→#823.

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
- [[chat-knowledge-evolution|Chat knowledge source mimari evrimi]] — #809→#828 karar/vazgeçiş zinciri (retrospektif). Confidence-routing → CTA → pattern-matching → fast-path hepsi başarısız; doğru çözüm LLM tool-use. 7 anti-pattern dersi. [[failed-experiments-rag-quality]] benzeri.

## Decisions (locked kararlar)

> Tüm Nodrat dokümanlarında tutarlı kalan, geri dönülmez kararlar.

### LLM / provider
- [[deepseek-default-llm|DeepSeek default LLM]] — Free/Starter/Trial için varsayılan LLM. Native API + `deepseek-v4-flash` (thinking-disabled). NIM endpoint fallback. Cost $0.27/$1.10 per 1M (kampanya: %75 indirim 2026-05-31'e kadar).
- [[claude-haiku-premium-llm|Claude Haiku 4.5 premium LLM]] — Pro+ tier'larda premium model; Agency comparison_generation için Sonnet 4.6 upgrade. **MVP-1'de pending** ([[anthropic-adapter-planned]]), Faz 2'de adapter yazılınca aktif.
- [[anthropic-adapter-planned|Anthropic Claude adapter — planlanan iş (Faz 2)]] — Pro/Agency Haiku 4.5 premium LLM için provider implementasyonu; MVP-1'de tüm tier'lar DeepSeek alıyor, UI/docs "Faz 2'de aktif" notu ile transparan iletiyor. #720.

### Infrastructure
- [[contabo-vps-hosting|Contabo Cloud VPS 40 hosting]] — MVP-1.5'te Contabo VPS 10'dan upgrade (production hep Contabo); backup için aynı sağlayıcı Object Storage (önceki backup B2'den migrate).

### Legal / output
- [[twenty-five-word-quote-cap|25-kelime direct quote hard cap (FSEK)]] — Output validator + system prompt çift güvenlik; R-LGL-02 ana mitigation.
- [[pii-redaction-mandatory|PII redaction zorunlu (LLM çağrısı öncesi)]] — Avukat eklemesi; KVKK + yurt dışı transfer mitigation.

### Scope
- [[mvp-1-scope-lock|MVP-1 scope lock]] — 12 sayfa / 12 tablo / ~20 endpoint; MVP-1 production'da delivered.
- [[style-profiles-pro-paywall|Stil profili Pro+ paywall + slot quota]] — Faz 5 server-side enforcement; Pro=3, Agency=10. Free/Starter 402; client-side bypass yok. Plan seed migration ile sabit (admin UI'da read-only).
- [[chat-only-migration|Chat-only migration — form modu/eski geçmiş/kayıtlı sayfaları kaldırma]] — #800 epic 6 sprint (S1A-S1F): `/app/generate`, `/app/generations`, `/app/saved` route'ları + `generations` + `saved_generations` tabloları TAMAMEN kaldırıldı; tek erişim noktası `/app/chat`. Halu/action/SFT/DPO kolonları messages tablosuna taşındı. KVKK export shape `conversations` (nested messages 50/conv). 5 PR: #800/#801/#802/#803/#805.

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
- [[sufficiency-soft-gate|Sufficiency soft-gate — agenda yetersizse chunks-first fallback dene]] — Önceden `mode='current'` + insufficient → erken çıkış (`insufficient_data`), chunks-first bypass ediliyordu. #726 ile erken çıkış kaldırıldı; sufficiency telemetri olarak çalışır, gerçek "kaynak yok" kararı yalnız retrieval sonucundan verilir. Üretim: "afyon belediye başkanı olayı nedir" insufficient_data → completed. Triloji: #725 inspector parity + #726 soft-gate + #727 planner default timeframe.
- [[cross-encoder-rerank-disabled|Cross-encoder reranker production'da kalıcı kapalı (eval-confirmed)]] — `rerank.enabled=false` (2026-05-10'dan beri). #750 eval gate koşumu (2026-05-12) NDCG@10 ≥ 0.90 eşiğini geçemedi: off baseline 0.627, local bge-reranker 0.509, NIM rerank 0.542. Her ikisi de baseline'dan **kötü** + recall 8/11 → 7/11 düşüş + latency +2-3s. Karar **kalıcı**; geri açma için yeni reranker modeli (BAAI v2-gemma / mxbai / Cohere v3.5) test edilmeli. Pipeline RRF + NER (#667) + mode-aware phrase boost (#718) + LLM rerank Faz 4 kombinasyonu yeterli.
- [[chunk-keyword-extraction|Per-chunk LLM keyword + question extraction (RagFlow adaptation)]] — Her `article_chunks` satırı için LLM ile 3-5 keyword + 3 olası soru çıkarılır; `keywords`/`question_keywords` TEXT[] kolonları + 2 GIN index. Açılış vakası "çocukların bahis oynamasını": target article BASELINE'da kayıp → #1. 12815 chunk backfill DeepSeek paralel 68 dakikada. Runtime'da Celery task otomatik. PR [#779](https://github.com/selmanays/nodrat/pull/779) (#778).
- [[critical-entity-must-match|Critical entity MUST_MATCH (rescue + filter 2-aşamalı)]] — Planner v1.3.0 `critical_entities` field (1-3 diskriminatif kelime). Retrieval'da iki aşama: RESCUE (article surface, K=12 en güçlü stream) + FILTER (precision). Soft fallback 0 match → orijinal RRF. Sadece filter yapsa target rescue edilmezdi (RRF dışındaysa kaybedilir). PR [#779](https://github.com/selmanays/nodrat/pull/779) (#778).
- [[multi-llm-per-op-routing|Multi-LLM per-operation routing (DeepSeek + Gemini cascade)]] — 4 op (ner/planner/rerank/generation) için admin /settings/llm dropdown ile provider seçimi. Gemma 4 26B/31B ücretsiz tier (3K req/gün toplam). Gemini quota tükenince otomatik DeepSeek cascade (provider-level + script-level). Gemma 4 CoT JSON üretiyor — robust extractor. PR [#779](https://github.com/selmanays/nodrat/pull/779) (#778).
- [[llm-rerank-default-off|LLM rerank default OFF — A/B kanıt: kalite 0, latency -1s]] — A/B test sonucu ON vs OFF aynı recall (8/11), ama OFF -%18 latency (5032→4102ms). DeepSeek answer-aware top-3 rerank mevcut pipeline'a (RRF + critical_entities + chunk_keywords) marjinal değer katmıyor. Admin /settings/retrieval ile geri açılabilir. PR [#783](https://github.com/selmanays/nodrat/pull/783).
- [[retrieval-cache-1h-ttl|Retrieval result Redis cache (1h TTL) — warm hit sub-saniye]] — `hybrid_search_chunks` çıktısı Redis-backed. Cache key: norm_query + retrieval params hash. Warm hit'lerde tüm pipeline atlanır. A/B: cold 4099ms → warm 1001ms (-%76). 1h TTL haber gündem dinamiği için kabul edilebilir stale window. PR [#784](https://github.com/selmanays/nodrat/pull/784).
- [[planner-bypass-short-query|Planner-bypass kısa entity-tipi sorgular]] — ≤4 kelime + soru marker yok → planner LLM çağrısı (~2s) atlanır. Sensible defaults uygulanır (mode='current', critical_entities = en uzun 2 kelime heuristic). Bypass plan cache'e yazılır. Kısa entity sorgularda ~2s tasarruf, soru-tipi ve uzun sorgular hâlâ LLM'e gider. PR [#785](https://github.com/selmanays/nodrat/pull/785).
- [[answer-aware-generation|Answer-aware generation context — pre-extracted numerical spans]] — Generator'a verilen her chunk için `extract_numerical_spans` (generic regex: yüzde/oran/sayı/skor/yıl) çıktısı `answer_spans` field olarak iletilir. Generator rakamsal sorgularda önce bu listeyi tarar. Evergreen — sorgu-agnostic. PR [#788](https://github.com/selmanays/nodrat/pull/788).
- [[benchmark-production-parity|Benchmark production-parity V2]] — Eski niche_chunks_benchmark raw query path test ediyordu (planner+HyDE+critical_entities atlanıyordu). V2 tam pipeline ile niche_006 fixed göründü (V1 0.727 → V2 0.818 recall@10). Eski V1 ölçümü kullanıcı deneyimini eksik temsil ediyordu. PR [#789](https://github.com/selmanays/nodrat/pull/789).
- [[llm-tool-use-wikipedia|LLM Tool-Use Wikipedia (GÜNCEL Faz 2 mimari)]] — LLM `search_wikipedia` function calling: haber yetersizse kendi karar verir. 2-aşama: Aşama 1 **non-streaming** `generate_text(tools=)` (DeepSeek DSML token bug, #840 — #836 streaming revize), tool varsa Aşama 2 TOOLSUZ stream, tool yoksa `_simulate_stream`. confidence routing/CTA/banner TERK edildi. news_query → tool yok (C2 tool gating). entity-relevance (#834). PR #823→#840.
- [[conversational-query-rewriting|Conversational query rewriting (condense step)]] — Multi-turn'de planner'dan önce izole LLM call follow-up'ı standalone query'ye çevirir ("ilk bölümün adı neydi" → "Stargate SG-1 ilk bölüm adı"). Perplexity/LangChain standardı. plan_input'a talimat gömmek çalışmadı (#832 planner ezdi). PR [#833](https://github.com/selmanays/nodrat/pull/833) + [#835](https://github.com/selmanays/nodrat/pull/835).
- [[wikipedia-wikidata-knowledge-source|Wikipedia + Wikidata kombine]] — Wikipedia prose (`list=search` relevance) + Wikidata structured facts (P569/P1082/...) paralel. REST extract infobox içermez → factual sorular Wikidata'da. PR [#825](https://github.com/selmanays/nodrat/pull/825) + [#828](https://github.com/selmanays/nodrat/pull/827).
- [[tiered-knowledge-architecture|Tiered Knowledge Architecture (Faz 2)]] — Chat 3 katman: Layer 1 (haber moat), Layer 2 (Wikipedia+Wikidata), Layer 3 (conversation memory). Katmanlar arası geçiş **LLM tool-use ile** ([[llm-tool-use-wikipedia]]); ilk confidence-router tasarımı terk edildi. LLM kendi bilgi haznesinden ASLA cevap yok (C1). PR #810→#828.
- [[confidence-based-routing|Confidence Router (SUPERSEDED)]] — ⚠️ Routing TERK edildi (#823), confidence artık sadece telemetri. Tarihsel: 5-signal score, T_high/T_low. PR [#810](https://github.com/selmanays/nodrat/pull/810).
- [[wikipedia-fallback-controlled|Wikipedia fallback CONTROLLED (SUPERSEDED)]] — ⚠️ Kullanıcı CTA onayı KALDIRILDI (#823) — Wikipedia artık tool-use ile otomatik. "PRIMARY değil" prensibi korundu. PR [#812](https://github.com/selmanays/nodrat/pull/812)+[#814](https://github.com/selmanays/nodrat/pull/814).
- [[news-first-strict-contamination-guard|News-first STRICT — Wikipedia leak engelleme]] — C2 invariant korundu; mekanizma evrim: query_class hard-gate (#816) → confidence gate (#818) → **tool gating** (#823, güncel — news_query'de tool LLM'e verilmez). PR #816→#823.

### Performance / streaming
- [[sse-streaming-default|SSE streaming default — /app/generate-stream]] — TTFT <1s hedefi; DeepSeek `stream:true` + speculative retrieval + planner cache + post-stream citation/image. Eski `/app/generate` backward-compat aynen korunur. Sahte hız değil — gerçek streaming, kalite gate'leri korunur. PR #528 / Issue #527.
- [[realtime-rss-polling|RSS realtime polling — adaptive tier + Conditional GET]] — Sabit 30dk polling → Faz 2'de adaptive tier (hot 60sn / normal 5dk / cold 30dk / hibernate 4saat). Faz 0+1 (PR #571, 2026-05-10) schema foundation + [[conditional-http-get]] (304 path → bandwidth ~%80↓) + admin runtime edit ship. Forward-compatible (flag default false). Gündem radarının ön gerek altyapısı.

### Payment / billing
- [[lemon-squeezy-payment-provider|Lemon Squeezy payment provider (MoR, USD primary) ✅ avukat şartlı + vergi danışmanı onaylı]] — Faz 6 ödeme stack'i Iyzico'dan LS MoR'a (Epic #448 review-resolved 2026-05-08). Şahıs ticari kazanç mükellefi (Limited Şti. defer, $5K plan/$10K convert), e-Arşiv kalktı (LS keser), USD primary. Multi-seat = LS variant + seat counter. KVKK m.9 yurt dışı transfer açık rıza zorunlu (frontend #453 + backend server-side enforcement #470). 3 yeni canonical doc: refund-policy.md, mesafeli-satis-sozlesmesi.md, payment-fallback-plan.md (R-FIN-04 6-senaryo).

### Strategy / long-term
- [[own-slm-strategy|Own SLM strategy — Trendyol LLM v4.1 üzerine domain-spesifik fine-tune]] — Nodrat'ın uzun vade kendi Türkçe SLM'i: [[trendyol-llm-base]] (Apache 2.0) üzerine DAPT + SFT + DPO + tokenizer extension. Hedef "Basamak 3" (savunulabilir 'kendi modelimiz' iddiası). Faz 0 = MVP-1.7 SFT Foundation milestone (Issues #563-#569, delivered 2026-05-10). Maliyet ikincil; motivasyon: vendor lock-in azaltma + IP/moat + talent.
- [[sft-message-source|SFT pipeline messages source — chat-derived ETL]] — `sft_curator` artık `generations` yerine `messages` tablosundan beslenir (#800 chat-only sonrası). 3 sample tipi: `sft` (sft_eligible), `dpo_rejected` (halu), `dpo_chosen` (pair). Partial UNIQUE `(message_id, task_type, sample_type)` idempotency. Task type: `chat_answer` (eski `content_generator` nullable miras). PR #805.
- [[dpo-rejected-samples|DPO rejected samples — halu mesajları DPO eğitimi için sakla]] — Kullanıcı halu işaretli mesajlar silinmez; `dpo_rejected=true` + opsiyonel `dpo_chosen_content` ile DPO chosen/rejected pair üretilir. Trendyol-LLM fine-tune'unda DPO step için kritik negative example havuzu. POST `/chat/messages/{id}/flag-halu` 2 textarea (reason + chosen_content). PR #802 + #805.

## Sources (kaynak özetleri)

> Her `docs/...` doküman için 1 sayfa: ne içerir, ana çıkarımlar, hangi entity/concept'lere bağlanır.

- [[architecture-md|architecture.md]] — Teknik mimari ve deployment; 9 prensip + 5 worker + provider katmanı + storage tier + secrets workflow. v0.3 (#410) — DeepSeek + Hosting + Backup + embedding (#350, 2026-05-06) **tüm çelişkiler resolved**. Production durum: tüm runtime override'lar admin panel'de kontrol edilebilir.
- [[risk-register-md|risk-register.md]] — 30 risk + MVP cut-list + KS-1/2/3 kill-switches + roadmap. v0.2 (#414) — §2.1/§2.2 skor anomalileri resolved (R-FIN-02, R-MKT-02, R-MKT-03 §2.2 → §2.1).

---

## İstatistik

- Toplam sayfa: **141** (**16 entity** + **27 concept** + **9 topic** + **51 decision** + **35 source** + 3 hub) — 2026-05-15 (#840 non-streaming delta + final benchmark): #836 "tool-aware streaming" superseded. DeepSeek streaming+tools yapısal `delta.tool_calls` vermiyor — `<｜DSML｜tool_calls>` özel token'ını content'e ham basıyordu (kullanıcı ham token görür + uzun-yazıp-kısaya-dönme). #840: Aşama 1 tekrar **non-streaming** `generate_text(tools=)` (yapısal tool_calls, #825'te ÇALIŞTIĞI doğrulanmış), content yield edilmez; tool varsa Aşama 2 **TOOLSUZ** `generate_text_stream` (gerçek streaming, DSML yok); tool yoksa `_simulate_stream` (4-kelime grup + 18ms, ekstra LLM call yok). Ana flow + meta-query handler. Güncellendi: [[llm-tool-use-wikipedia]] + [[chat-knowledge-evolution]] (anti-pattern ders #10 revize: streaming+tool-call provider-bağımlı, OpenAI formatı varsayma) + docs api-contracts §17.5.6 + prompt-contracts §4.x (kullanıcı docs/ yazma yetkisi verdi). Final benchmark v2 (prod-parity, VPS, re-chunk v2 sonrası 14136 chunk %99.94 embed): recall@5 0.636 (7/11), recall@10 **0.818** (9/11), mrr@10 0.488 — dökümante baseline ile AYNI, re-chunk v2 regresyon YOK; niche_007/009 bilinen entity-synonym broken ([[failed-experiments-rag-quality]]). 29 unit test PASS. Production: https://nodrat.com/app/chat. **Önceki:** 2026-05-15 (Faz 2.1 conversational rewrite + streaming re-sync): tool-use mimarisi sonrası çok-turlu sohbet kırıldı + streaming kayboldu. 1 yeni decision [[conversational-query-rewriting]] (#833 izole condense step — Perplexity/LangChain standardı; "ilk bölümün adı neydi" → "Stargate SG-1 ilk bölüm adı"). Güncellendi: [[llm-tool-use-wikipedia]] (tool-aware streaming #836 + entity-relevance #834 + effective_query #835), [[chat-knowledge-evolution]] (Faz 2.1 zinciri + 3 yeni anti-pattern dersi), [[tiered-knowledge-architecture]]. Akış: Step 1.5 condense → planner → tool-aware streaming (gerçek token streaming geri). Başarısız ara çözümler: #829 gen_user_msg context, #831 sadece meta path, #832 plan_input enrichment (planner ezdi), #826 fast-path REVERT. docs/ notu: query_rewrite.py + chat akış değişikliği — prompt-contracts.md + api-contracts.md insan tarafından güncellenmeli (CLAUDE.md §1.1). **Önceki:** 2026-05-15 (#808 Faz 2 tool-use re-sync): ilk Faz 2 mimarisi (confidence router + Wikipedia CTA + insufficiency banner) production'da kırıldı; kullanıcı geri bildirimi sonrası **LLM tool-use mimarisine** yeniden tasarlandı (#823→#828). 3 yeni sayfa ([[llm-tool-use-wikipedia]] decision, [[wikipedia-wikidata-knowledge-source]] decision, [[chat-knowledge-evolution]] topic — #809→#828 anti-pattern retrospektifi). 6 sayfa güncellendi/superseded ([[confidence-based-routing]] + [[wikipedia-fallback-controlled]] SUPERSEDED; [[tiered-knowledge-architecture]] + [[news-first-strict-contamination-guard]] + [[query-class-classification]] + [[retrieval-confidence-score]] + [[wikipedia-provider]] mekanizma güncel). LLM `search_wikipedia` function calling: haber yetersizse LLM kendi karar verir, 2-aşama. confidence/query_class → telemetri+tool-gating (routing YAPMAZ). C1/C2/C3 korundu, mekanizmalar değişti. Wikipedia `list=search` relevance + Wikidata structured fact kombine. Vazgeçilenler: confidence routing #810, CTA #814, banner #816, pattern-matching #819, fast-path #826(revert #828). 42 unit test. Bonus: #820 stream chunk bug (Faz 1'den beri broken). Production: https://nodrat.com/app/chat. **Önceki:** 2026-05-15 (#808 Faz 2 Tiered Knowledge Architecture ilk sync, PR #810/#812/#814/#816 — yukarıda tool-use ile supersede edildi): 4 decision + 2 concept + 1 entity, Confidence Router 5-signal. **Önceki:** 2026-05-14 (#800 chat-only epic FINAL sync, PR #806): 3 yeni decision sayfası ([[chat-only-migration]], [[sft-message-source]], [[dpo-rejected-samples]]) — `/app/generate` + `/app/generations` + `/app/saved` route'ları + `generations` + `saved_generations` tabloları DROP edildi; SFT pipeline messages source rewrite; DPO chosen/rejected pair sample'lar. 6 PR seansta: #800 (S1A UI cleanup) → #801 (S1B DB migration) → #802 (S1C halu+action) → #803 (S1D ChatSettingsModal) → #805 (S1E+S1F+app_me.py fix). Production: https://nodrat.com/app/chat. **Önceki:** 2026-05-14 (#799 final docs+wiki sync): 3 yeni decision sayfası ([[chunk-text-norm-gin-trigram]], [[chunk-text-tsv-fts]], [[planner-cache-key-v2]]) yetim referansları kapattı + docs/engineering güncel (data-model §5.x conversations+messages, api-contracts §17.5 /chat/* 6 endpoint, prompt-contracts §4.x chat_answer). **Önceki:** 2026-05-14 (#793 Perplexity epic SHIPPED): [[perplexity-ux-redesign]] status "shipped" — 5 PR tek seansta (#793-#797). Production: https://nodrat.com/app/chat. Backward compat /app/generate korundu. **Önceki:** 2026-05-14 (#791 experiment-revert sync): yeni topic [[failed-experiments-rag-quality]] (4 başarısız deneme kataloğu — anti-pattern listesi: cross-encoder/sub-chunk/LLM rerank/tier'lı RESCUE). niche_007/009 kalıcı broken — entity-synonym problem, query rewriting gelecek sprint. **Önceki:** 2026-05-14 (quality-sprint sync): 2 yeni decision ([[answer-aware-generation]], [[benchmark-production-parity]]) + V2 benchmark (#789). production-parity recall@10: 0.727 → 0.818 (niche_006 ✅). 3 PR (#787/#788/#789). Hâlâ broken: niche_007/009 (sub-chunk indexing future). **Önceki:** 2026-05-14 (perf-sprint sync): 3 yeni decision ([[llm-rerank-default-off]], [[retrieval-cache-1h-ttl]], [[planner-bypass-short-query]]) + 1 yeni topic ([[perf-sprint-2026-05-14]]). 5 PR (#781/#782/#783/#784/#785) → niche_chunks_golden avg latency 21.8s → 1s warm hit (21.5× hızlanma, sıfır regresyon). **Önceki:** 2026-05-14 (#778 RagFlow adaptation sync): 3 yeni decision eklendi ([[chunk-keyword-extraction]], [[critical-entity-must-match]], [[multi-llm-per-op-routing]]); [[chunks-first-retrieval]] keyword stream + critical_entities param ile güncellendi; sıradaki sprint hız sprintı (PR-E/F/G/H). **Önceki:** 2026-05-12 (housekeeping audit): 7 stale issue kapatıldı (#695/#684/#652/#617/#616 Kategori A + #613/#614), yeni decision [[cross-encoder-rerank-disabled]] eklendi (önceden belgelenmemiş mimari karar netleştirildi). **Önceki:** 2026-05-12 (#725/#726/#727 fix triloji + #732 mini-fix): yeni decision [[sufficiency-soft-gate]] eklendi; [[chunks-first-retrieval]] + [[chunks-always-on-fallback]] backlink güncellendi. RAG pipeline 3 katmanlı savunma (planner default timeframe + sufficiency soft-gate + inspector prod parity) production'da. **Önceki:** 2026-05-12 (#720 audit sync): yeni decision [[anthropic-adapter-planned]] eklendi; [[ner-pipeline]] + [[pricing-tier-matrix]] güncellendi (MVP-1 reality + Faz 7c NER prompt admin-tunable). Kod tarafında: admin /prompts 3 → 11 prompt (pipeline sekmeleri: ingestion + generate); 5 dead setting key + NIM chat fallback temizlendi; `retrieval.content_top_k` registry'ye eklendi. Önceki: MVP-1.8 sprint final 4 PR (#713/#715/#717/#718) — RAG İzlencesi 8 sekme tam prod-pipeline senkron.
- Kaynak sayısı: **5** / 32 (`docs/**/*.md`) — `architecture.md`, `risk-register.md`, `data-model.md`, `api-contracts.md`, `prompt-contracts.md` (#696 D16)
- Son ingest: **2026-05-11 (#696 D16)** — `docs/engineering/data-model.md` (v0.4), `api-contracts.md` (v0.6), `prompt-contracts.md` (v0.4) source özet sayfaları olarak ingest edildi. Detay entity/concept çıkarımı sonraki sprintte planlı (her doc 1000-2200 satır).
- Son re-sync: **2026-05-15** (#838 multi-turn bağlam kilidi + condense referans-yakınlığı + docs/ güncellendi). Öncesinde Faz 2.1 (#833 condense, #836 streaming) + #808 tool-use re-sync.
- Son lint: **2026-05-11** (#696 D18 sweep #2 — bidirectional backlink fix: 201 violation → **0** (2-pass auto); 163+38 = 201 backlink eklendi; yetim 0; çelişki 0)
- Açık çelişki sayısı: **0** ✅
- Açık operasyonel migration: **0** ✅ (MVP-1.7: 20260510_0200 generations SFT cols + 20260510_0300 KVKK consent + 20260510_0500 training_samples production'da)
- Açık doküman senkronizasyonu: **0** ✅ (data-model v0.4 + api-contracts v0.6 + 4 hukuki doc v0.4 + INDEX.md v1.8 + wiki katalog tüm güncel)
- Devam eden ops todo (opsiyonel): SFT kill switch (sft.curator.enabled=false default — kullanıcı /admin/sft'den 1 toggle ile açabilir); ilk eğitim run'ı için ~10K sample biriktirme süreci (~3-4 ay tahmin, opt-in oranına bağlı); Faz 2 adaptive tier hesabı (#565 follow-up); Faz 3 beat refactor + worker concurrency; Faz 4 URL/scrape opt-in realtime; drill-down panel (#461); local rerank flip (#347 eval gate).
- Açık locked decision: **25** (#440 sonrası 2 + Epic #448 sonrası 1 + 2026-05-09: shadcn-customization-policy + sse-streaming-default + 2026-05-10: realtime-rss-polling + own-slm-strategy + 2026-05-11: age-gate-18-plus + model-improvement-default-opt-out + pre-launch-security-checklist + margin-70-target + geographic-pricing-policy + 2026-05-14 #800: chat-only-migration + sft-message-source + dpo-rejected-samples + 2026-05-15 #823: llm-tool-use-wikipedia + wikipedia-wikidata-knowledge-source; SUPERSEDED: confidence-based-routing + wikipedia-fallback-controlled + 2026-05-15 #833: conversational-query-rewriting)
  - **REVOKED 2026-05-11:** ~~cards-path-ner-out-of-scope~~ (#714 — yanlış varsayım üzerine kuruluydu, cards path PRIMARY /api/generate retrieval olduğu fark edildi, NER eklendi)
