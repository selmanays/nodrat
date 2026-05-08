---
type: topic
title: "Risk catalog — 30 risk inventory + heat-map"
slug: "risk-catalog"
category: "synthesis"
status: "live"
created: "2026-05-08"
updated: "2026-05-08"
sources:
  - "docs/strategy/risk-register.md§2"
  - "docs/strategy/risk-register.md§3"
tags: ["risk", "catalog", "inventory", "synthesis"]
aliases: ["risk-inventory", "30-risk", "risk-list"]
---

# Risk catalog — 30 risk inventory

> **TL;DR:** Nodrat risk register'ındaki 30 riskin tam envanteri. 7 🔴 kırmızı (skor ≥9, mitigation gerek), 17 🟡 sarı (4-8, izleme), 6 🟢 yeşil (1-3, kabul edilebilir, 1 ÇÖZÜLDÜ). Top-7 kırmızı için detaylı mitigation playbook'ları kendi entity sayfalarında.

## Bağlam

Bu sentez şu soruyu cevaplar: "Nodrat'ta hangi riskler var, durumları ne, hangileri için aksiyon gerekli?"

Ham 30 risk listesi [docs/strategy/risk-register.md §2](../../docs/strategy/risk-register.md) içinde 3 tabloda. Bu sayfa onları tek bakışta gösterir + ✅ delivered mitigation'ları, ⏳ açık iş kalemlerini, ⚠️ skor anomalilerini işaretler.

## Heat-map (skor × kategori)

| Kategori | 🔴 9+ | 🟡 4-8 | 🟢 1-3 | Toplam |
|---|---|---|---|---|
| LGL (Yasal) | 2 | 5 | 4 | 11 |
| PRD (Ürün) | 2 | 2 | 0 | 4 |
| TCH (Teknik) | 0 | 3 | 0 | 3 |
| OPS (Operasyonel) | 1 | 3 | 1 (✅) | 5 |
| FIN (Finansal) | 1 | 2 | 0 | 3 |
| MKT (Pazar) | 1 | 3 | 0 | 4 |
| SEC (Güvenlik) | 0 | 3 | 0 | 3 |
| PEO (İnsan) | 1 | 0 | 0 | 1 |
| **Toplam** | **7** | **17** | **6** | **30** |

> ⚠️ **Skor anomalisi:** §2.2'de 🟡 sarı tabloda "skor 9" olarak işaretlenmiş **R-FIN-02, R-MKT-02, R-MKT-03** üç risk → skor 9 → 🔴 olmalı. Bu sayfada **doğru kategorizasyon** uygulandı (🔴'a taşındılar). Kaynak doküman güncellenmeli (bkz. [[risk-scoring]] uyarı bloğu).

## 🔴 Kırmızı — yüksek öncelik (skor ≥9)

| ID | Risk | O | E | Skor | Detay sayfa | Locked decision |
|---|---|---|---|---|---|---|
| **R-LGL-02** | FSEK telif tazminat | 3 | 4 | **12** | [[risk-fsek-telif]] | [[twenty-five-word-quote-cap]] |
| **R-PEO-01** | Solo founder bandwidth | 4 | 3 | **12** | (entity yok — `concepts/mvp-cut-list-method` mitigation) | [[mvp-1-scope-lock]] |
| **R-PRD-01** | Halüsinasyon → tazminat | 3 | 3 | 9 | (sıradaki ingest) | (citation %100, halü <%2 hedefleri — sıradaki ingest) |
| **R-LGL-01** | KVKK ihlali | 3 | 3 | 9 | [[risk-kvkk-violation]] | [[pii-redaction-mandatory]] |
| **R-OPS-01** | Kaynak HTML kırılganlığı | 3 | 3 | 9 | [[risk-source-fragility]] | — |
| **R-FIN-01** | LLM cost runaway | 3 | 3 | 9 | [[risk-cost-runaway]] | — |
| **R-MKT-01** | ChatGPT TR gündem | 3 | 3 | 9 | (sıradaki ingest — competitive-analysis) | — |
| **R-FIN-02** | DeepSeek API instability ⚠️ | 3 | 3 | 9 | (sıradaki ingest) | [[provider-abstraction]] (with_fallback) |
| **R-MKT-02** | "ChatGPT yeter" pazar tepkisi ⚠️ | 3 | 3 | 9 | (sıradaki ingest) | — |
| **R-MKT-03** | Düşük WTP (10$ max) ⚠️ | 3 | 3 | 9 | (sıradaki ingest — pricing-strategy) | — |

> ⚠️ İşaretli ⚠️ riskler kaynak doküman §2.2'de yanlışlıkla 🟡 sarı tabloda; bu envanterde 🔴 olarak gösterilmiştir.

## 🟡 Sarı — orta öncelik (skor 4-8)

| ID | Risk | Skor | Mitigation özet | Durum |
|---|---|---|---|---|
| R-LGL-03 | Robots.txt ihlali | 8 | Rate limit per domain + good UA | ✅ INDEX §4 locked (sıfır tolerans) |
| R-LGL-04 | 5651 takedown gecikmesi | 6 | 24h SLA prosedür | 🟡 4 takedown endpoint Faz 1 |
| R-LGL-10 | Vergi/e-Fatura uyumsuzluk | ~~8~~ → 2 | ~~Iyzico e-Arşiv~~ → **Lemon Squeezy MoR fatura keser** ([[lemon-squeezy-payment-provider]]) | ✅ büyük ölçüde mitigate (LS MoR e-Arşiv + KDV handling) |
| R-LGL-11 | Yurt dışı veri transfer | 8 | Açık rıza + SCC + KVKK m.9 (LS US PII transfer dahil) | 🟡 register checkbox + DPA + LS m.9 ek checkbox (#453) |
| R-FIN-03 | NIM free tier kapanması | 6 | Local bge-m3 fallback | ✅ scaffold (USE_LOCAL_EMBEDDING flag) |
| R-OPS-02 | VPS tek nokta arıza | 8 | Backup zorunlu, recovery runbook | ✅ restic + Contabo OS |
| R-OPS-03 | Backup başarısızlığı | 8 | Restore drill ayda 1 | ✅ aylık drill |
| R-OPS-04 | Spam/bot abuse | 8 | Multi-layer rate limit + fingerprint | 🟡 partial |
| R-TCH-01 | pgvector ölçek limiti | 6 | ivfflat → hnsw geçiş | ✅ binary quantization scaffold ([[binary-quantization]]) |
| R-TCH-02 | Embedding queue backlog | 6 | Local fallback otomatik | ✅ scaffold |
| R-TCH-03 | Playwright resource yükü | 6 | Sadece zorunluda | ✅ MVP-1'de Playwright OUT |
| R-PRD-02 | Beta retention <%30 (D7) | 9 → KS-3 | Discovery + iterasyon | ⚠️ **KS-2 founder bypass** (2026-05-08, #385 closed); KS-3 gate'te ilk 50 paid user retention ile tekrar ölçülecek |
| R-PRD-03 | Comparison mode imaginary | 6 | Beta usage telemetry | ✅ MVP-2 #51 feature flag delivered |
| R-PRD-04 | Stil profili düşük adoption | 6 | Beta sonrası karar | 🟡 MVP-3 |
| R-MKT-04 | Türkiye economic downturn | 6 | TL fiyat ayarlanabilir | 🟡 izleme |
| R-SEC-01 | Admin panel breach | 8 | 2FA zorunlu | 🟡 MVP-3 öncesi (INDEX §6) |
| R-SEC-02 | Prompt injection | 6 | System prompt isolation + sanitize | 🟡 partial |
| R-SEC-03 | API key sızıntısı | 8 | Secret manager + git-secrets | ✅ sops + age + Fernet |

## 🟢 Yeşil — düşük öncelik (skor ≤3)

| ID | Risk | Skor | Notlar |
|---|---|---|---|
| R-LGL-06 | Basın kanunu yanlış statü | 1 | "Üretim aracıyız" pozisyonu (INDEX §4 locked) |
| R-LGL-07 | RTÜK kapsam | 1 | Yayın platformu değiliz |
| R-LGL-08 | X Developer Policy | 1 | MVP'de X API yok |
| R-LGL-09 | Çocuk koruması | 2 | 18+ ToS (INDEX §4 locked) |
| R-LGL-12 | Tüketici Kanunu | 2 | 14 gün cayma yapısı (LS hosted refund flow yönetir) |
| ~~R-OPS-05~~ | ~~Görsel storage growth~~ | ✅ ÇÖZÜLDÜ | #304 MVP-1.4 process & discard mimarisi: bytes saklanmaz, 5 TB/yıl → 90 GB/yıl (98% azalma) |

## Çıkarımlar

1. **🔴 risklerin %70'i hukuki/iş.** 7 kırmızıdan 4'ü LGL/MKT/FIN — yani teknik değil, daha çok strateji, hukuk, GTM kanalı. Bu solo founder için disiplin gerektirir (R-PEO-01 da bu disiplinin bekçisi).
2. **Top-2 risk (skor 12) farklı eksenlerde.** R-LGL-02 (FSEK) eksternal hukuki; R-PEO-01 (solo founder) internal kapasite. Mitigation'ları da farklı: birinde locked decisions ve ToS, ötekinde scope discipline ve agent kullanımı.
3. **OPS riskleri büyük ölçüde mitigated.** R-OPS-01/02/03/04 (5 risk) — backup/health monitor/site profile/rate limit ile sağlam savunma. R-OPS-05 ✅ çözüldü.
4. **TCH riskleri "küçük operatör"** — hepsi 🟡 6, mevcut altyapı ile çözülebilir.
5. **Açık 🔴 riskler:** R-PRD-01 (halü), R-MKT-01/02/03 (rekabet/WTP). Bunlar [[risk-catalog]]'da entity sayfası yok — sıradaki ingest döngüsünde (`prompt-contracts.md`, `competitive-analysis.md`, `pricing-strategy.md`) ele alınacak.

## Mitigation kapsama matrisi (locked decisions × risk)

```text
[[twenty-five-word-quote-cap]]    → R-LGL-02 (M1)
[[pii-redaction-mandatory]]       → R-LGL-01 (avukat eklemesi)
[[mvp-1-scope-lock]]              → R-PEO-01 (cut-list disiplin)
[[provider-abstraction]]          → R-FIN-02 (with_fallback), R-FIN-01 (circuit breaker)
[[binary-quantization]]           → R-TCH-01 (pgvector ölçek)
[[hot-cold-tier]]                 → R-OPS-02/03 (backup + DR)
[[contabo-vps-hosting]]           → R-OPS-02 (single VPS dedicated, backup)
```

## İlişkiler

- **Beslediği kararlar:** Tüm locked decisions yukarıda mitigation kapsama matrisinde.
- **İlgili kavramlar:** [[risk-scoring]] (metodoloji), [[mvp-cut-list-method]] (R-PEO-01 mitigation), [[kill-switch]] (KS noktaları riskleri test eder).
- **İlgili varlıklar:** Top-4 detaylı: [[risk-fsek-telif]], [[risk-kvkk-violation]], [[risk-source-fragility]], [[risk-cost-runaway]].

## Açık sorular / TODO

- **Sıradaki ingest:** R-PRD-01 (halü) için `prompt-contracts.md` ingest. R-MKT-01/02 için `competitive-analysis.md`. R-MKT-03 için `pricing-strategy.md`.
- **Skor anomalisi düzeltme:** Source doküman §2.2'de 3 risk yanlış kategoride. `nodrat-dev` ile risk-register-md.md PR.
- **R-PEO-01 entity sayfası:** Skor 12 ama entity yok. Diğer top risklerde entity var. Tutarlılık için R-PEO-01 entity eklenebilir mi? Veya `mvp-cut-list-method` zaten yeterli mi?

## Kaynaklar

- [docs/strategy/risk-register.md §2 (30 risk listesi)](../../docs/strategy/risk-register.md)
- [docs/strategy/risk-register.md §3 (top-7 detay)](../../docs/strategy/risk-register.md)
- [INDEX.md §4 (locked decisions — risk mitigation'lar)](../../INDEX.md)
- Detay sayfalar: [[risk-fsek-telif]], [[risk-kvkk-violation]], [[risk-source-fragility]], [[risk-cost-runaway]]
