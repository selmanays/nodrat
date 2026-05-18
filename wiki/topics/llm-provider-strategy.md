---
type: topic
title: "LLM provider stratejisi — tier-based routing + fallback"
slug: "llm-provider-strategy"
category: "synthesis"
status: "live"
created: "2026-05-07"
updated: "2026-05-08"
sources:
  - "docs/engineering/architecture.md§4"
  - "INDEX.md§4"
  - "wiki/entities/deepseek.md"
  - "wiki/entities/claude-haiku-4-5.md"
  - "wiki/entities/local-bge-m3.md"
  - "wiki/decisions/deepseek-default-llm.md"
  - "wiki/decisions/claude-haiku-premium-llm.md"
tags: ["llm", "provider", "routing", "tier", "synthesis"]
aliases: ["provider-routing", "tier-llm-mapping"]
---

# LLM provider stratejisi

> **TL;DR:** Nodrat LLM stack'i 3 katmanlı: **default** (DeepSeek native API, `deepseek-v4-flash` thinking-disabled, $0.14 cache-miss / $0.0028 cache-hit / $0.28 output per 1M token, indirim YOK) Free/Starter/Trial için, **premium** (Claude Haiku 4.5) Pro/Agency için, **özel** (Sonnet 4.6) sadece Agency `comparison_generation` için. Embedding tek katman: **local BAAI/bge-m3** ([[local-bge-m3]] — sentence-transformers, VPS CPU, 2026-05-06 #350 migration tamam) Tüm bunlar [[provider-abstraction]] üzerinden — vendor lock'a immune. DeepSeek v4-flash default tier'da Haiku'ya kıyasla ~7x (input) / ~18x (output) ucuz.

## Bağlam

Bu sentez şu soruyu cevaplar: "Nodrat'ta hangi tier hangi LLM'i çağırır, neden, alternatif olduğunda ne olur?"

Soru kritik çünkü:
- Cost margin'in en büyük belirleyicisi (≥%75 hedef — INDEX §4)
- Tier value proposition'unun teknik dayanağı
- Provider outage'ında failover stratejisinin temeli

## Tier × Provider mapping

| Tier | Aylık fiyat | Default LLM | Premium use case |
|---|---|---|---|
| **Trial** | 0 TL (limitli) | [[deepseek]] | — |
| **Free** | 0 TL | [[deepseek]] | — |
| **Starter** | 249 TL | [[deepseek]] | — |
| **Pro** | 749 TL | [[claude-haiku-4-5]] | — |
| **Agency** | 2.499 TL | [[claude-haiku-4-5]] | `comparison_generation` → Sonnet 4.6 |

Embedding tüm tier'larda [[local-bge-m3]] (BAAI/bge-m3, 1024-dim, VPS CPU, $0). Tier-based embedding ayrımı yok — citation kalitesi tüm tier'larda aynı garantili.

## Routing kodu (architecture.md §4.3)

```python
def route_request(user: User, task_type: str) -> Provider:
    if user.tier == "agency" and task_type == "comparison_generation":
        return AnthropicProvider(model="claude-sonnet-4-6")
    if user.tier in ("pro", "agency"):
        return AnthropicProvider(model="claude-haiku-4-5")
    if user.tier in ("starter", "free", "trial"):
        return DeepSeekProvider(model="deepseek-v4-flash")
    raise ValueError("Unknown tier")
```

> **Not:** Routing içinde `DeepSeekProvider` artık DeepSeek native API'yi kullanır (`api.deepseek.com/v1`). NIM endpoint via `NimChatProvider` registry name `deepseek` ile fallback rolünde — `DEEPSEEK_API_KEY` yoksa devreye girer (#163).

## Cost karşılaştırması (per 1M token, 2026-05-08 itibarıyla)

| Provider | Input (cache miss / cache hit) | Output | Aktivasyon |
|---|---|---|---|
| DeepSeek native (`deepseek-v4-flash`) | $0.14 / $0.0028 | $0.28 | MVP-1, default ✅ |
| DeepSeek NIM (NimChatProvider) | $0 (NIM free) | $0 | Fallback (`DEEPSEEK_API_KEY` yoksa) |
| Claude Haiku 4.5 | ~$0.80 | ~$4 | Faz 2 (Pro+) |
| Claude Sonnet 4.6 | ~$3 | ~$15 | Agency comparison_generation |

> **İndirim YOK (#990).** %75 "kampanya" yalnız deepseek-v4-pro içindi; Nodrat v4-flash kullanır. v4-flash gerçek fiyatı: $0.14 cache-miss / $0.0028 cache-hit / $0.28 output per 1M (api-docs.deepseek.com/quick_start/pricing).

Net etki: default tier'larda LLM cost minimal ama sıfır değil — production load'unda kullanıcı başına aylık ≈$0.01-0.10 USD seviyesinde (cache hit oranına bağlı). Margin ≥%75 hedefi DeepSeek native pricing + cache discipline ile korunuyor. Pro+ tier'larda fiyat farkı (Haiku ~3x DeepSeek native, Sonnet ~10x) müşterinin ödediği premium ile karşılanır. NIM düşerse fallback'a inilir, cost şişmez.

## Fallback chain (production state — 2026-05-08)

```text
Chat:
  Primary:     DeepSeekProvider (native API, deepseek-v4-flash) — ✅ AKTİF
  Fallback 1:  NimChatProvider (deprecated, DEEPSEEK_API_KEY yoksa devreye girer)
  Fallback 2:  OpenRouterProvider (registry'de, generic)
  Fallback 3:  OpenAICompatibleProvider (son fallback, OpenAI-compatible endpoint)

Embedding:
  Tek provider: LocalBgeM3Provider (BAAI/bge-m3 ~2.3 GB FP32 CPU) — ✅ AKTİF
                Lokal model init fail ederse embedding broken durumu (ayrı handler)

Rerank:
  Primary:     NimRerankProvider (nvidia/nv-rerankqa-mistral-4b-v3) — ✅ AKTİF
               admin panel `llm.use_local_rerank=false` (production hâlâ NIM)
  Fallback:    LocalBgeRerankerProvider (BAAI/bge-reranker-v2-m3) — ⏳ scaffold (#224)
               Local'e geçiş gate: NDCG@10 ≥ 0.90 (#347)
               Reranker stateless — DB migration gerekmez (embedding'in aksine)
```

> **Embedding migration tamam, rerank pending:** Embedding tarafı [[local-bge-m3]]'e geçti (#345/#346/#350); rerank hâlâ NIM aktif. İkisi bağımsız feature flag (`llm.use_local_embedding` vs `llm.use_local_rerank`). Reranker flip için urgency düşük çünkü NIM rerank free tier yeterli (62 çağrı/gün, $0).

## Aktif kararlar

- [[deepseek-default-llm]] — DeepSeek V4 Flash default LLM
- [[claude-haiku-premium-llm]] — Claude Haiku 4.5 Pro+ tier

## Çıkarımlar

1. **Default tier net cost minimal ($0.01-0.10/user/ay).** DeepSeek native pricing + cache hit discipline ile margin ≥%75 hedefi korunuyor. Free tier kötüye kullanım rate-limit + per-user cost cap ile yönetilir.
2. **Pro+ tier value proposition** salt LLM kalitesi değil, "bilinçli premium model seçimi"dir. Müşteri 749 TL/ay'da Haiku için ödüyor; bu net bir özellik farkı (Free'de DeepSeek).
3. **Sonnet sadece Agency comparison_generation'da** — bu en pahalı çağrı. Tüm Agency tier için Sonnet açılırsa margin çöker (~$15/1M output). Agency segmentinde "comparison" özelliği farklılaştırıcı.
4. **Embedding tek tier** — citation %100 hedefi tüm tier'larda aynı. Embedding'i tier'lara bölmek mühendislik karmaşıklığı + retrieval kalitesi rastgele bölünmüş corpus.
5. **Vendor lock immune değil ama yumuşatılmış.** Adapter pattern bir günde provider değiştirebilir (1-2 hafta eval re-baseline süresi dahil).

## Risk tabosu

| Risk | Olasılık | Etki | Mitigation |
|---|---|---|---|
| ~~DeepSeek %75 kampanya bitişi~~ — #990 YANILGI: %75 yalnız v4-pro; v4-flash zaten indirimsiz liste fiyatı, kampanya-bitişi riski YOK | — | — | Kapandı 2026-05-18 (#990) |
| DeepSeek native API outage | Orta | NIM fallback'a düş | NimChatProvider auto-fallback (`DEEPSEEK_API_KEY` boşsa); circuit breaker |
| NIM free tier kapanır | Orta | Fallback path zayıflar; OpenRouter'a düşülür | Cost track + alarm; OpenRouter capacity test |
| Anthropic Haiku 4.5 deprecate | Düşük | Pro+ tier upgrade | Haiku 5/Sonnet test, 1-2 hafta migration |
| **DeepSeek prompt cache hit ratio düşük** (system prompt'ta `{max_posts}/{tone}` interpolation → prefix instabilitesi) | ✅ Resolved | Cache hit yok → her request full input price | **MVP-2.1 PR [#418](https://github.com/selmanays/nodrat/pull/418)** prompt prefix stability — interpolation prefix dışına çıkarıldı |
| Local embedding fallback'a inerse retrieval bozulur (DB cosine ≈ 0 NIM modeline) | Düşük (admin panel manuel) | Geçici retrieval kalite kaybı | Admin panel toggle koruma + DB re-embed task ([maintenance.py:522](../../apps/api/app/workers/tasks/maintenance.py:522)) |
| DeepSeek native rate limit (RPM/TPM) | Orta | Generation gecikme | Circuit breaker, NIM fallback, OpenRouter ikinci fallback |
| Tier mapping kod hatası | Düşük | Free user'a Pro feature | nodrat-dev anti-pattern (server-side check) |

## İlişkiler

- **Beslediği kararlar:** [[deepseek-default-llm]], [[claude-haiku-premium-llm]].
- **İlgili varlıklar:** [[deepseek]], [[claude-haiku-4-5]], [[local-bge-m3]] (embedding primary).
- **İlgili kavramlar:** [[provider-abstraction]] — tüm bu sentez bu pattern olmadan mümkün değil.
- **İlgili topics:** [[pipeline-performance-baseline]] (token/latency/$ baseline + her PR sonrası delta tracking).
- [[data-pipelines]]
- [[own-slm-strategy]]
- [[risk-cost-runaway]]
- [[sft-data-pipeline]]
- [[trendyol-llm-base]]
- [[architecture-md]]

## Açık sorular / TODO

- **Faz 2 timing:** Pro tier launch tarihi MVP-3 milestone'unda (2026-11-30 hedef). Aradaki 6 ay içinde Anthropic pricing nasıl değişir?
- **comparison_generation tanımı:** Hangi exact endpoint'ler "comparison_generation" task_type'ında çağrılır? Routing doğrudan `app.providers.registry` üzerinden (services/llm_router.py mevcut DEĞİL).
- **Free tier abuse alarm:** DeepSeek v4-flash ucuz ama bedava değil — N kullanıcı × M generation × $0.14/$0.28 hesabı (v4-flash indirimsiz liste fiyatı; %75 "kampanya" YANILGIYDI #990) nasıl davranır? Per-user rate limit thresholds dokümante edilmeli (docs/engineering/alarm-thresholds.md var — INDEX'te referans).
- **Pricing düzeltmesi (#990, 2026-05-18):** "%75 kampanya" v4-flash için YANILGIYDI (indirim yalnız deepseek-v4-pro). v4-flash zaten indirimsiz liste fiyatı ($0.14/$0.0028/$0.28). Kampanya-bitişi riski YOK; düzeltilmiş maliyet eskisinden düşük → marj korunur.

## Kaynaklar

- [docs/engineering/architecture.md §4 (Provider katmanı)](../../docs/engineering/architecture.md)
- [INDEX.md §4 (Çekirdek kararlar)](../../INDEX.md)
- [docs/strategy/pricing-strategy.md](../../docs/strategy/pricing-strategy.md) — tier yapısı
- [docs/strategy/unit-economics.md §4](../../docs/strategy/unit-economics.md) — cost-per-generation
- [docs/engineering/prompt-contracts.md](../../docs/engineering/prompt-contracts.md) — model-specific prompt tuning
- [[deepseek]], [[claude-haiku-4-5]] — adapter detayları
