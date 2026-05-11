---
type: concept
title: "Shared cost — haber havuzu maliyeti (crawl + embed + NER)"
slug: "shared-cost-haber-havuzu"
category: "business"
status: "live"
created: "2026-05-11"
updated: "2026-05-11"
sources:
  - "docs/strategy/unit-economics.md §2 Shared Cost"
tags: ["business", "cost", "shared", "unit-economics", "crawl"]
---

# Shared Cost — Haber Havuzu Maliyeti

> **TL;DR:** Nodrat'ın **paylaşılan altyapı maliyeti** (tüm kullanıcılar arasında bölünür): crawl + embedding + NER + cluster + agenda. Aylık ~$50-120 (MVP-1). Per user maliyet **kullanıcı büyüdükçe düşer** (amortize edilir).

## Bileşenler

| Bileşen | Aylık | Açıklama |
|---|---|---|
| **VPS (Contabo Cloud 40)** | $22 | 12-ay sözleşme |
| **Crawl bandwidth** | $0 | RSS + scrape, robots.txt uyumlu |
| **Embedding (bge-m3 local)** | $0 | Lokal model, GPU yok |
| **NER (DeepSeek V3)** | $20-40 | ~$0.0008/article × 25K-50K article/ay |
| **Cluster + Raptor** | $5-10 | DeepSeek call |
| **Object Storage backup** | $3 | Contabo S3-comp encrypted |
| **Cloudflare** | $0 | Free tier (rate limit yeterli) |
| **MinIO image storage** | $0 | Same VPS volume |
| **Lemon Squeezy MoR setup** | $0 | Per transaction fee (variable) |
| **DPO + legal counsel** | $20/ay | KVKK uyum, avukat saatlik amortize |
| **TOPLAM** | **~$70-95/ay** | |

## Per User Cost (Amortize)

| Kullanıcı sayısı | Shared / user |
|---|---|
| 100 | $0.95 |
| 500 | $0.19 |
| 1.000 | $0.10 |
| 5.000 | $0.02 |
| 10.000 | $0.01 |

→ Shared cost user başına %1'ten az olur ölçek 5K+ → fixed cost handicap'i değil.

## Variable Cost vs Shared Cost

- **Shared:** crawl + embed + NER + cluster — kullanıcı sayısından **bağımsız** (haber sayısı değişir)
- **Variable:** retrieval (her query) + content gen (her üretim) — kullanıcı başına **doğrudan orantılı** ([[variable-cost-uretim]])

## Optimization Patterns

1. **NER backfill bir kere** (#684 PR-B) — $3.40 one-time fix
2. **Embedding lokal** — NIM bge-m3 → local-bge-m3 ([[local-bge-m3]]) ile $0
3. **Cluster cache** — RAPTOR weekly clusters günlük değil, haftalık
4. **Crawl polling tier'ı** — Adaptive polling ([[adaptive-polling-tier]]) — verimsiz kaynaklarda back off

## Ölçek Tetikleyicileri

| Olay | Shared cost değişimi |
|---|---|
| Article corpus 100K → 1M | NER ölçeği × 10 → $200-400/ay |
| Crawl source 3 → 50 | Bandwidth + storage 2-3x |
| User 1K → 10K | Shared cost SABİT (ölçek avantajı) |
| Embedding upgrade (e5-multilingual) | Build time ekstra ama ay aynı |

## İlişkiler

- [[unit-economics-md]] §2
- [[variable-cost-uretim]] — kullanıcı başı maliyet
- [[ner-pipeline]] — NER cost dominant
- [[adaptive-polling-tier]] — crawl cost optimization
- [[contabo-vps]] — fixed cost
- [[margin-70-target]]

## Kaynaklar

- [docs/strategy/unit-economics.md](../../docs/strategy/unit-economics.md) §2
