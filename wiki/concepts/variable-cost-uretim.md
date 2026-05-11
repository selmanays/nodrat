---
type: concept
title: "Variable cost — kullanıcı üretim maliyeti (per query/per generation)"
slug: "variable-cost-uretim"
category: "business"
status: "live"
created: "2026-05-11"
updated: "2026-05-11"
sources:
  - "docs/strategy/unit-economics.md §3 Variable Cost"
tags: ["business", "cost", "variable", "unit-economics", "llm"]
---

# Variable Cost — Kullanıcı Üretim Maliyeti

> **TL;DR:** Her kullanıcı üretim isteğinde (`/api/generate`) tetiklenen değişken maliyet: retrieval embedding (lokal) + LLM rerank + content generation (DeepSeek / Claude Haiku). Tier'a göre $0.001-$0.005/üretim. #684 PR-D sonrası ~%40 düştü.

## Per Üretim Maliyet Dağılımı (post #684)

| Adım | DeepSeek V3 (default) | Claude Haiku (Pro+) |
|---|---|---|
| Query embedding (bge-m3 lokal) | $0 | $0 |
| Query Planner (DeepSeek) | $0.0003 | $0.0003 |
| HyDE conditional (50% skip) | $0.0005 ortalama | $0.0005 |
| Hybrid search (DB only) | $0 | $0 |
| LLM rerank (cross-encoder lokal) | $0 | $0 |
| Content generation | $0.0020 | $0.0040 |
| Citation validator | $0 (lokal embed cosine) | $0 |
| **TOPLAM** | **~$0.003/üretim** | **~$0.005/üretim** |

## Optimization Wins (#684)

| Faz | Kazanım |
|---|---|
| PR-A worker concurrency | Bulk batch işlem 4x hız (cost aynı, throughput artar) |
| PR-C HyDE conditional | %50 sorguda HyDE skip → $0.0005 tasarruf |
| PR-D batch embedding | 2 round-trip → 1, latency tasarrufu |
| PR-D top_k 15→10 | Rerank candidate -%33 — minor cost |
| PR-D max_tokens 2000→1500 | Content gen output -%25 → büyük tasarruf |

**Net:** $0.005 → $0.003 (-%40 cost) ([[pipeline-optimization]])

## Aylık Maliyet per Tier

| Tier | Aylık üretim | Per üretim | Aylık variable |
|---|---|---|---|
| Free | 25 | $0.003 | $0.08 |
| Starter $8 | 100 | $0.003 | $0.30 |
| Pro $24 | 500 | $0.005 (Haiku) | $2.50 |
| Agency $79 | 2500 | $0.005 | $12.50 |

## DeepSeek vs Claude Haiku Trade-off

- **DeepSeek V3:** $0.27/$1.10 per 1M token. Cheap. Türkçe orta. **Default LLM** ([[deepseek-default-llm]])
- **Claude Haiku 4.5:** $1.00/$5.00 per 1M token. 3.6x pahalı. Türkçe iyi. **Pro+ tier** ([[claude-haiku-premium-llm]])

Pro tier'ı Haiku'ya yükselten gerekçe: kalite (P1A persona content tone hassasiyeti).

## Long-term: Kendi SLM

[[own-slm-strategy]] — 12-18 ay yol. Kendi Türkçe SLM (DeepSeek output'larından SFT). Variable cost potansiyel $0.0005 (DeepSeek 1/6'sı) → margin %85+.

## Ölçek Tetikleyicileri

- LLM fiyat +%30 → variable cost $0.004 → margin alarm (Starter $8'in net'i kırılır)
- Pro tier %15+ Haiku quota patlatırsa → admin cap throttle
- Free tier user ölçek 50K+ → shared cost amortize ama variable $4K/ay (acceptable)

## İlişkiler

- [[unit-economics-md]] §3
- [[shared-cost-haber-havuzu]] — paylaşılan altyapı
- [[pipeline-optimization]] — #684 %40 cost düşüş
- [[deepseek-default-llm]]
- [[claude-haiku-premium-llm]]
- [[own-slm-strategy]] — long-term margin yükseltme

## Kaynaklar

- [docs/strategy/unit-economics.md](../../docs/strategy/unit-economics.md) §3
