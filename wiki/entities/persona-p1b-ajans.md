---
type: entity
entity_kind: persona
title: "Persona P1B — Politik İletişim Ajansı (ikincil persona, multi-seat MUST)"
slug: "persona-p1b-ajans"
status: "live"
created: "2026-05-11"
updated: "2026-05-11"
sources:
  - "docs/product/prd.md §4 Kullanıcı Rolleri"
  - "docs/strategy/pricing-strategy.md §2 Tier Yapısı (Agency $79)"
  - "INDEX.md §4 locked"
tags: ["persona", "secondary", "ajans", "p1b", "agency-tier", "multi-seat"]
---

# Persona P1B — Politik İletişim Ajansı

> **TL;DR:** İkincil persona. Türkiye'de politik iletişim/sosyal medya yöneten **ajans/danışmanlık** (5-25 kişi). Çoklu müşteri portfolyosu yönetir, ekip üyeleri Nodrat'ı kullanır. **Multi-seat MUST** — Agency $79 tier'ı spesifik olarak bu persona için.

## Profil

- **Şirket tipi:** Politik PR/iletişim ajansı, dijital ajans, parti danışmanlığı
- **Büyüklük:** 5-25 çalışan
- **Müşteri sayısı:** 3-10 (politikacı, parti, kurum, STK)
- **Konum:** Ankara + İstanbul ağırlık
- **Karar verici:** Ajans sahibi / digital director
- **Kullanıcı:** Junior content writers (5-10 seat)

## Pain Points (P1A'dan farklı)

1. **Çoklu müşteri yönetimi** — her müşterinin sesi/tonu farklı (Tone profiles şart)
2. **Style consistency** — markaya göre üretim tutarlılığı (Style Cloning Faz 5)
3. **Onboarding hızı** — yeni junior'lar uygulama öğrenmeli (UX wireframes simple shipped)
4. **Audit log** — kim ne üretti, müşteri raporu için
5. **Cost predictability** — junior'lar pahalı LLM çağrıları açıp budget patlatabilir
6. **GDPR/KVKK uyum** — müşteri verisi taşıma sorumluluğu (SOC 2-lite gerekecek)

## Nodrat Değer Önerisi

- **Multi-seat ($79 Agency tier)** — 5 seat dahil, fazla +$10/seat/ay
- **Audit log per seat** — admin_audit_log filter user_id
- **Style profiles per müşteri** ([[style-profile-system]])
- **Higher quota** — Pro $24'in 5x kontörü
- **Pro+ features** — Claude Haiku premium ([[claude-haiku-premium-llm]])
- **Müşteri tagleme** — saved_generations + custom tags

## Multi-seat MUST (locked decision)

INDEX.md §4: "İkincil persona: P1B (ajans, **multi-seat MUST**)" — Pro tier'ı seat-by-seat satmak yerine Agency $79 single bundle. Bu tier olmadan P1B segmenti kaybolur.

## Aha Moment (P1A'dan farklı)

İlk **müşteri tone profile** kayıt sırasında. Junior'a "müşteri A için sabit tone, müşteri B için sabit tone, otomatik üretim" göstermesi. P1A'daki citation aha'sından farklı: hız + tutarlılık.

## Re-evaluation Tetikleyicileri

- Ajans pazarı R&D — P1B oranı %30+'ya çıkarsa Pricing tier yeniden konumlandırma
- Müşteri segregation hostage olursa (Agency'nin müşterileri Nodrat'a doğrudan kayıt) — anti-cannibalization

## İlişkiler

- [[persona-p1a-politik-creator]] — birincil persona, ortak ürün vizyon
- [[prd-md]] §4
- [[pricing-strategy-md]] §2 Agency $79
- [[style-profile-system]] — Faz 5 tone/style cloning
- [[claude-haiku-premium-llm]] — Pro+ tier

## Kaynaklar

- [docs/product/prd.md](../../docs/product/prd.md) §4
- [docs/strategy/pricing-strategy.md](../../docs/strategy/pricing-strategy.md) §2
