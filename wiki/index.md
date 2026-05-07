---
title: Wiki Index — Sayfa Kataloğu
type: hub
updated: 2026-05-08
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
- [[deepseek-v3|DeepSeek V3 (NIM endpoint)]] — Free/Starter/Trial tier'larında default LLM, NIM üzerinden `deepseek-v3.1-terminus`, cost $0.
- [[claude-haiku-4-5|Claude Haiku 4.5]] — Pro/Agency tier'larında premium LLM (Anthropic native API), Faz 2'de operasyonel.
- [[nim-bge-m3|NIM bge-m3 (embedding)]] — Default embedding provider. Adapter adı yanıltıcı; aslında `nvidia/nv-embedqa-e5-v5` (1024-dim).
- [[contabo-vps|Contabo Cloud VPS 40 + Object Storage]] — Production hosting (12 vCPU / 48 GB / 250 GB NVMe), MVP-1.5'ten itibaren.
- [[celery-worker|Celery worker stack]] — 5 queue grubu + scheduler, Redis broker üzerinde async iş yığını.

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

### Methodology / framework
- [[risk-scoring|Risk skor metodolojisi]] — 1-25 ölçek (olasılık × etki), 8 kategori, 🔴🟡🟢 gruplar.
- [[mvp-cut-list-method|MVP cut-list (IN/OUT/LATER) framework]] — PRD scope'undan MVP'ye inmek için disiplin.
- [[kill-switch|Kill-switch (KS-1/2/3) gate'leri]] — Her MVP geçişinde acceptance + no-go kriterleri.

## Topics (sentez / karşılaştırma)

> Birden fazla sayfayı birleştiren analiz, karşılaştırma, özet.

- [[llm-provider-strategy|LLM provider stratejisi]] — Tier × provider routing + cost karşılaştırma + fallback chain sentezi.
- [[risk-catalog|Risk catalog (30 risk inventory)]] — Tüm risklerin tek bakışta envanteri + heat-map + locked decisions kapsama matrisi.
- [[mvp-1-scope|MVP-1 scope envanteri]] — Faz × özellik tablosunda IN/OUT/LATER tam liste + MVP-1.x sapma analizi.
- [[mvp-roadmap|MVP roadmap]] — MVP-1 → 1.1 → 1.6 → 2 → 3 → 4+ timeline + KS noktaları + sürpriz erken-delivery analizi.

## Decisions (locked kararlar)

> Tüm Nodrat dokümanlarında tutarlı kalan, geri dönülmez kararlar.

### LLM / provider
- [[deepseek-default-llm|DeepSeek V3 default LLM]] — Free/Starter/Trial için varsayılan LLM (NIM endpoint, cost $0).
- [[claude-haiku-premium-llm|Claude Haiku 4.5 premium LLM]] — Pro+ tier'larda premium model; Agency comparison_generation için Sonnet 4.6 upgrade.

### Infrastructure
- [[contabo-vps-hosting|Contabo Cloud VPS 40 hosting]] — MVP-1.5'te Hetzner CCX23'ten geçiş; backup için aynı sağlayıcı Object Storage.

### Legal / output
- [[twenty-five-word-quote-cap|25-kelime direct quote hard cap (FSEK)]] — Output validator + system prompt çift güvenlik; R-LGL-02 ana mitigation.
- [[pii-redaction-mandatory|PII redaction zorunlu (LLM çağrısı öncesi)]] — Avukat eklemesi; KVKK + yurt dışı transfer mitigation.

### Scope
- [[mvp-1-scope-lock|MVP-1 scope lock]] — 12 sayfa / 12 tablo / ~20 endpoint; MVP-1 production'da delivered.

## Sources (kaynak özetleri)

> Her `docs/...` doküman için 1 sayfa: ne içerir, ana çıkarımlar, hangi entity/concept'lere bağlanır.

- [[architecture-md|architecture.md]] — Teknik mimari ve deployment; 9 prensip + 5 worker + provider katmanı + storage tier + secrets workflow. **3 çelişki** (hosting, backup, embedding).
- [[risk-register-md|risk-register.md]] — 30 risk + MVP cut-list + KS-1/2/3 kill-switches + roadmap. **3 skor anomalisi** (R-FIN-02, R-MKT-02, R-MKT-03 yanlış kategoride).

---

## İstatistik

- Toplam sayfa: **27** (9 entity + 6 concept + 4 topic + 6 decision + 2 source)
- Kaynak sayısı: **2** / 32 (`docs/**/*.md`) — `architecture.md`, `risk-register.md`
- Son ingest: **2026-05-08** ([[risk-register-md]])
- Son lint: —
- Açık çelişki sayısı: **6** total (architecture: 3, risk-register: 3 skor anomalisi)
- Açık locked decision: **6** (4 yeni risk-register'dan eklendi: 25-kelime, PII redaction, MVP-1 scope, Contabo)
