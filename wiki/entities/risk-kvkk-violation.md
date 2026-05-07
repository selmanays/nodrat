---
type: entity
title: "R-LGL-01 — KVKK İhlali"
slug: "risk-kvkk-violation"
category: "risk"
status: "live"
created: "2026-05-07"
updated: "2026-05-07"
sources:
  - "docs/strategy/risk-register.md§3.3"
  - "docs/strategy/risk-register.md§2.1"
  - "docs/legal/compliance-brief.md§2"
tags: ["risk", "legal", "kvkk", "privacy", "red"]
aliases: ["R-LGL-01", "kvkk-risk", "kvkk-ihlali"]
---

# R-LGL-01 — KVKK İhlali

> **TL;DR:** Kullanıcı verisinin izinsiz işlenmesi sonucu KVK Kurul incelemesi → 50K-2.5M TL idari para cezası. Skor **9 🔴**. Mitigation: aydınlatma metni + register flow checkbox + DPO outsource + [[pii-redaction-mandatory]] + soft delete + 30g hard delete + ROPA + 4 takedown endpoint.

## Tanım

6698 sayılı Kişisel Verilerin Korunması Kanunu (KVKK) kapsamında Nodrat veri sorumlusu (data controller) sıfatına haiz. İhlal kategorileri:

1. **Açık rıza eksikliği** — register flow'da checkbox yoksa veya genel rıza alınıyorsa.
2. **Aydınlatma yükümlülüğü** — kullanıcıya hangi veri, ne için, ne kadar süre, kimle paylaşıldığı bildirilmemişse.
3. **Yurt dışı transfer** (R-LGL-11 ile bağlı) — provider US/HK ise SCC + açık rıza zorunlu.
4. **Veri minimizasyonu** — gerek olmayan veri toplama.
5. **Saklama süresi** — silme/anonimleştirme yapılmaması.
6. **Veri güvenliği** — sızma sonrası 72 saat içinde KVK Kurul'a bildirilmeme.

## Skor

| Boyut | Değer | Açıklama |
|---|---|---|
| **Olasılık** | 3 | Aydınlatma + rıza akışı eksikse büyük olasılık. |
| **Etki** | 3 | 50K-2.5M TL idari para cezası + brand damage + Kurul kararı uyumsuzluğunda kapatma. |
| **Skor** | **9** | 🔴 Kırmızı. |

## Mitigation (Legal Brief §2 — full)

| Önlem | Durum |
|---|---|
| Açık rıza checkbox (register flow 4 madde) | 🟡 ToS draft, Faz 1 launch öncesi canlı |
| Aydınlatma metni (kvkk-aydinlatma.md) | 🟡 draft + avukat final review bekliyor |
| ROPA (veri işleme envanteri) | 🟡 ilk taslak, DPO ile finalize edilecek |
| DPO outsource | 🟡 sözleşme template hazır, uzman seçimi açık |
| [[pii-redaction-mandatory]] (LLM çağrısı öncesi) | ✅ locked decision |
| Soft delete (30 gün) | ✅ data-model schema |
| Hard delete (30 gün sonra) | ✅ retention task |
| 4 takedown endpoint (`/legal/abuse`, `/takedown`, `/copyright`, `/privacy-request`) | 🟡 Faz 1 launch öncesi |
| 72h ihlal bildirim playbook (incident-response.md) | ✅ doc hazır |
| VERBİS gönüllü kayıt (1K+ user sonra) | ⏳ planlı |

## Tetikleyici

```text
Tetikleyici: Açık rıza eksikliği veya aydınlatma yükümlülüğü ihmali
Senaryo:    Bir kullanıcı şikâyet eder ya da KVK Kurul re'sen inceleme başlatır.
            "Provider'a hangi veriyi göndermişler?" sorulur.
            ROPA + register checkbox + DPO log'u olmazsa cevap veremezsin.
            Idari para cezası kesinleşir.
```

## Kontrol checkpoint'leri

```text
Aylık (DPO raporu):
  - Yeni provider eklemesi DPA imzalı mı
  - PII detect oranı ne (anomaly var mı)
  - Hard delete başarılı mı (30 gün cutoff)

Ayda 1: ROPA güncel mi (yeni veri kategorisi eklendi mi)
Yıllık: VERBİS gönüllü kayıt güncellemesi (1K+ user sonra)

İhlal anı:
  - 72h içinde KVK Kurul bildirim
  - Etkilenen kullanıcılara bildirim
  - DPO çağrısı (DPO Contract template'teki iletişim)
  - SEV-1 prosedürü (incident-response.md)
```

## Çapraz referanslar

- **Bağlı kararlar:** [[pii-redaction-mandatory]] (LLM provider'a PII gitmemesi için), [[mvp-1-scope-lock]] (MVP-1'de KVKK gerekli olan tüm yapı IN).
- **Bağlı kavramlar:** [[risk-scoring]].
- **İlgili topics:** [[risk-catalog]].
- **İlgili dokümanlar:**
  - [docs/legal/compliance-brief.md §2](../../docs/legal/compliance-brief.md)
  - [docs/legal/kvkk-aydinlatma.md](../../docs/legal/kvkk-aydinlatma.md)
  - [docs/legal/privacy-policy.md](../../docs/legal/privacy-policy.md)
  - [docs/legal/ropa.md](../../docs/legal/ropa.md)
  - [docs/legal/dpo-contract-template.md](../../docs/legal/dpo-contract-template.md)
  - [docs/legal/incident-response.md](../../docs/legal/incident-response.md)
  - [docs/legal/opinion-integration.md](../../docs/legal/opinion-integration.md)

## Açık sorular / TODO

- **DPO uzman seçimi:** Sözleşme template hazır ama uzman seçilmedi (INDEX §6.1 todo). Bu blocker — Faz 1 launch öncesi çözülmeli.
- **Register flow 4 checkbox:** Net hangi 4 madde? KVKK rıza + ToS + Privacy + Cookie? Wireframe + UX kontrolü.
- **Provider DPA listesi:** DeepSeek, Anthropic için DPA imzalı mı (INDEX §6.1 todo). Faz 0 sonu hedefli.

## Kaynaklar

- [docs/strategy/risk-register.md §3.3 (R-LGL-01 detay)](../../docs/strategy/risk-register.md)
- [docs/strategy/risk-register.md §2.1](../../docs/strategy/risk-register.md)
- [docs/legal/compliance-brief.md §2 (KVKK full)](../../docs/legal/compliance-brief.md)
- [INDEX.md §4](../../INDEX.md) — locked KVKK decisions
