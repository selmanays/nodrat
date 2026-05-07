---
type: source
title: "risk-register.md — Risk Register & MVP Cut-List"
slug: "risk-register-md"
source_path: "docs/strategy/risk-register.md"
source_version: "v0.1"
source_updated: "2026-05-07"
ingested_on: "2026-05-07"
created: "2026-05-07"
updated: "2026-05-07"
tags: ["source", "strategy", "risk", "mvp-scope"]
aliases: ["risk-register", "mvp-cut-list-source"]
---

# risk-register.md — Özet

> Bu sayfa [`docs/strategy/risk-register.md`](../../docs/strategy/risk-register.md)'ın LLM-üretilmiş özetidir. Doğruluk kaynağı her zaman orijinal dokümandır.

## Doküman bilgisi

- **Yol:** [`docs/strategy/risk-register.md`](../../docs/strategy/risk-register.md)
- **Sürüm:** v0.1 (§5.2 ve §5.1b ile MVP-1.5 + MVP-2 delivered durumu güncel)
- **Son güncelleme:** 2026-05-07 (Dalga 6 closure sync — INDEX §5.2 ile birlikte)
- **İçe alındı:** 2026-05-07
- **Boyut:** ~720 satır

## Ne içerir

Tüm proje risk envanteri (30 risk, 8 kategori, 1-25 skor matrisi), top-7 kritik risk için detaylı mitigation playbook'ları, PRD'nin 6 fazlı geniş kapsamından **MVP-1 minimum kabul edilebilir ürün**'e indirgeyen IN/OUT/LATER cut-list'i, MVP-1 → MVP-1.5 → MVP-2 → MVP-3 → MVP-4+ revize roadmap'i, KS-1/KS-2/KS-3 kill-switch noktaları (acceptance + no-go kriterleri), Yıl 1 risk mitigation bütçesi (~125K TL).

## Ana çıkarımlar

1. **Top-5 risk (skor ≥9 🔴):** R-LGL-02 (FSEK telif, 12), R-PEO-01 (solo founder, 12), R-PRD-01 (halüsinasyon, 9), R-LGL-01 (KVKK, 9), R-OPS-01 (HTML kırılganlık, 9), R-FIN-01 (LLM cost runaway, 9), R-MKT-01 (ChatGPT TR, 9).
2. **MVP-1 scope ≪ PRD scope.** PRD 6 faz × ~150 alt-gereksinim 10-14 ay; MVP-1 8-12 hafta. Cut-list'in özü §4.9: 12 sayfa, 12 tablo, ~20 endpoint, sadece DeepSeek + bge-m3 NIM.
3. **MVP-1 ↔ MVP-2 ↔ MVP-3 fonksiyonel kapsam farkı net:** MVP-1 "çalışan minimum"; MVP-2 "kullanılabilir SaaS" (selector UI, category page, X thread, comparison flag); MVP-3 "ücretli launch" (ödeme, e-Arşiv, stil profili).
4. **MVP-1.5 (Epic #215, 2026-05-06 delivered):** Hetzner CCX23 → Contabo VPS 40 migration + Object Storage geçişi + body_html drop + binary quantization scaffold + local model preload. Bu wiki'nin [[contabo-vps-hosting]] ve [[binary-quantization]] sayfaları doğrudan bu fazdan çıktı.
5. **MVP-2 -19 hafta erken delivered (2026-05-07).** Hedef 2026-09-29'du. 12 issue + 17 PR. KS-2 acceptance ölçümleri MVP-3 cut-over'a taşındı (#385-#389).
6. **3 kill-switch:** KS-1 (extraction ≥%70 + alpha feedback olumlu + maliyet <$0.01/gen + halü <%5), KS-2 (D7 retention ≥%30 + NPS ≥30 + 25 persona + 5+ kaynak), KS-3 (free→paid conversion ≥%3 + trial→free ≥%20 + WTP ≥250 TL).
7. **Genel kill-switch:** 6 ay içinde 50+ paid yoksa B2B pivot değerlendir; 12 ay MRR < cost ise kapatma; KVKK Kurul kararı uyumsuzluğu kapatma.
8. **Top mitigation grupları:** FSEK için 25-kelime quote cap + ToS sorumluluk transferi; KVKK için aydınlatma + register checkbox + DPO; HTML için source health monitor + selector test + 3-tier extraction; cost runaway için per-user rate limit + provider hard cap + alarm; halü için citation validator (#180) + cross-encoder reranker (#181).
9. **Yıl 1 risk yatırımı: ~125K TL.** En büyük kalem avukat ön-görüş (50K TL) + DPO outsource (30K TL/yıl) + cyber sigorta opsiyonel (20K TL/yıl).

## Dokümanın bölüm haritası

```
§0  Yönetici özeti (top 5 + MVP karar + kill-switch)
§1  Risk register metodolojisi (skor + kategori)
§2  Risk register — 30 risk (🔴 kırmızı 7, 🟡 sarı 17, 🟢 yeşil 6)
§3  Top-7 kritik risk detay (R-LGL-02, R-PRD-01, R-LGL-01, R-OPS-01, R-FIN-01, R-MKT-01, R-PEO-01)
§4  MVP cut-list (Faz 0/1/2/3/4/5/6 IN/OUT/LATER + §4.9 final scope)
§5  MVP roadmap (5.1 MVP-1, 5.1b MVP-1.5 ✅, 5.2 MVP-2 ✅, 5.3 MVP-3, 5.4 MVP-4+)
§6  Kill-switch noktaları (KS-1/2/3 acceptance + no-go + genel)
§7  Risk mitigation bütçesi
§8  Karar noktaları (D1-D10)
§9  Çapraz referans
```

## Bu kaynaktan üretilen wiki sayfaları

### Entities (kritik risk objeleri)
- [[risk-fsek-telif]] — R-LGL-02, skor 12, FSEK telif tazminat (en yüksek tek risk)
- [[risk-kvkk-violation]] — R-LGL-01, skor 9, KVKK ihlali
- [[risk-source-fragility]] — R-OPS-01, skor 9, kaynak HTML kırılganlığı
- [[risk-cost-runaway]] — R-FIN-01, skor 9, LLM cost runaway

### Concepts
- [[risk-scoring]] — skor metodolojisi (olasılık × etki, 1-25 ölçek, 🔴🟡🟢 gruplar)
- [[mvp-cut-list-method]] — IN/OUT/LATER decision framework
- [[kill-switch]] — KS-1/2/3 go/no-go gate yapısı

### Decisions
- [[twenty-five-word-quote-cap]] — output 25 kelime direct quote hard cap (R-LGL-02 ana mitigation)
- [[mvp-1-scope-lock]] — MVP-1 final scope kilit (§4.9 — 12 sayfa, 12 tablo, ~20 endpoint)
- [[pii-redaction-mandatory]] — LLM çağrısı öncesi PII redaction zorunlu (R-LGL-01 + avukat eklemesi)

### Topics
- [[risk-catalog]] — 30 risk inventory + kategori dağılımı + skor heat-map
- [[mvp-1-scope]] — MVP-1 IN/OUT/LATER tam envanter (Faz 0/1/2/3 detay)
- [[mvp-roadmap]] — MVP-1 → 2 → 3 → 4+ timeline + delivered/planned durumu

## Çapraz referanslar (kaynak içinde)

- [docs/legal/compliance-brief.md](../../docs/legal/compliance-brief.md) §3 — R-LGL-02 (FSEK)
- [docs/legal/compliance-brief.md](../../docs/legal/compliance-brief.md) §2 — R-LGL-01 (KVKK)
- [docs/product/prd.md](../../docs/product/prd.md) §12.4 — R-PRD-01 (halü prompt rules)
- [docs/product/prd.md](../../docs/product/prd.md) §1.10 — R-OPS-01 (source health)
- [docs/product/prd.md](../../docs/product/prd.md) §1.4 — R-OPS-01 (selector test)
- [docs/strategy/unit-economics.md](../../docs/strategy/unit-economics.md) §6 — R-FIN-01 (cost tracking)
- [docs/strategy/competitive-analysis.md](../../docs/strategy/competitive-analysis.md) §5, §6.1 — R-MKT-01, R-MKT-02
- [docs/strategy/success-metrics.md](../../docs/strategy/success-metrics.md) — KS-1 acceptance + KS-3 conversion
- [docs/product/information-architecture.md](../../docs/product/information-architecture.md) §13 — Faz haritası ↔ MVP scope

## Açık sorular / belirsizlikler

- **R-FIN-02 vs R-FIN-01 skor tutarlılığı:** Risk register §2.1'de "R-FIN-02: DeepSeek API instability skor 9" 🔴 kırmızı listesinde değil ama §2.2 sarı listesinde "skor 9" olarak yazılı. Skor 9 → 🔴 kategoriye girer. **Aksiyon:** §2.2'de `R-FIN-02 | 3 | 3 | 9` satırı yanlışlıkla sarı tabloda; §2.1 kırmızıya taşınmalı (veya skor revize edilmeli — Olasılık 3 → 2 olabilir, sonuç 6 olur).
- **R-MKT-02 / R-MKT-03 skor 9 sarıda:** §2.2'de 🟡 sarı tablosunda "Skor 9" görünüyor — yine aynı kategori hatası. **Aksiyon:** kırmızıya taşınmalı veya skor revize.
- **MVP-1 KS-1 acceptance status:** Avukat review ✅ Discovery ✅ ama "extraction ≥%70", "halü <%5", "alpha 5+ olumlu" hala unchecked. MVP-1 zaten production'da → bu kriterler post-hoc doğrulanmalı.
- **§5.2'de MVP-2 erken delivered (-19 hafta).** Bu büyük ön-yükleme nedeni dokümante edilmemiş — discovery validation güçlü çıkması mı? AI agent verimliliği mi? Roadmap'in geri kalanına etkisi (MVP-3 hedef 2026-11-30 hala geçerli mi?) açık.

## Sürüm değişikliği takibi

| Sürüm | Tarih | Değişiklik | Wiki etkisi |
|---|---|---|---|
| v0.1 | 2026-05-01 | initial | — |
| v0.1 | 2026-05-06 | §5.1b MVP-1.5 delivered (Epic #215) | — |
| v0.1 | 2026-05-07 | §5.2 MVP-2 delivered closure (Dalga 6 sync) | sayfalar oluşturuldu (2026-05-07 ingest) |
