---
type: decision
title: "Model improvement consent — varsayılan açık (opt-out)"
slug: "model-improvement-default-opt-out"
category: "legal-policy"
status: "locked"
created: "2026-05-11"
updated: "2026-05-11"
sources:
  - "docs/legal/tos.md §7.4 Model İyileştirme Verileri"
  - "docs/legal/privacy-policy.md §3 madde 4"
  - "docs/legal/kvkk-aydinlatma.md §3 madde 7"
  - "docs/legal/ropa.md §13b Aktivite #13"
  - "GitHub Issue #564 / PR #603"
tags: ["legal", "kvkk", "consent", "decision", "sft", "mvp-1-7"]
---

# Model Improvement Default Opt-Out

> **TL;DR:** Kullanıcı çıktıları (input + LLM output) **varsayılan AÇIK** olarak Nodrat SFT (Supervised Fine-Tuning) training dataset'ine dahil edilir. Kullanıcı /settings panelinden tek-tıkla opt-out yapabilir (KVKK md.11 cascade delete tetiklenir). KVK Kurulu rehber §VI.B etkin geri çekme zinciri uyumlu.

## Karar

```text
✅ Varsayılan: opt-IN (model improvement_consent = true)
✅ Opt-out: /settings → "Modeli iyileştirmek için verilerimi paylaş" toggle off
✅ KVKK md.11 cascade: opt-out anında training_samples DELETE
✅ Aydınlatma: KVKK m.5/2-a açık rıza varsayımı
```

## Gerekçeler

1. **KVKK md.5/2-a "açık rıza"** — varsayılan opt-in **explicit consent gerekçesi geçerli** (sözleşmenin kurulması için zorunlu): Türkiye'nin Kendi SLM Stratejisi ([[own-slm-strategy]]) için training data
2. **Ürün vizyonu** — Nodrat tech-startup; uzun vade kendi Türkçe SLM yetiştirme planı (12-18 ay)
3. **Türkçe SLM moat** — DeepSeek output'larından SFT ile kendi modelimizi besle (IP/moat motivasyonu)
4. **Avukat görüşü (#487)** — KVK Kurulu rehber §VI.B "etkin geri çekme" şart; cascade delete + admin audit log + 30g hard delete uyumlu

## Uygulama

- **users tablosu (#564):** `model_improvement_consent: bool DEFAULT TRUE`, `consent_last_changed_at`, `consent_source_version` kolonları
- **training_samples tablosu (#567):** UNIQUE (generation_id) idempotent; opt-out anında DELETE WHERE user_id = X
- **Cascade trigger:** PostgreSQL trigger — users.model_improvement_consent = FALSE → training_samples DELETE
- **Admin audit log:** her consent değişikliği `admin_audit_log` row
- **Aydınlatma:** KVKK Aydınlatma §3 madde 7 + §13 5. checkbox "varsayılan işaretli"

## Risk Mitigation

- **R-LGL-13 KVKK md.9 yurt dışı transfer:** LS US transfer için ek aydınlatma; opt-out tek tıkla
- **KVK Kurulu denetim:** her consent state için audit log + zaman damgalı kaydı
- **DPO yıllık review:** consent rate < %50 ise ürün takımı uyarısı (varsayılan opt-in baskı altı)

## Re-evaluation Tetikleyicileri

- KVK Kurulu denetim sonrası "varsayılan opt-out" zorunluluğu çıkarsa flip
- DPO yıllık review consent rate < %30 → ürün UX iyileştirme + ek aydınlatma
- Avrupa Birliği GDPR sertifikasyonu gerekirse (EU pazar) → opt-out default'a değişebilir

## İlişkiler

- [[tos-md]] §7.4
- [[privacy-policy-md]] §3
- [[kvkk-aydinlatma-md]] §3 madde 7
- [[ropa-md]] §13b Aktivite #13
- [[own-slm-strategy]] — uzun vade motivasyonu
- [[sft-data-pipeline]] — implementation
- [[risk-kvkk-violation]] — risk linki

## Kaynaklar

- [docs/legal/tos.md](../../docs/legal/tos.md) §7.4
- [docs/legal/kvkk-aydinlatma.md](../../docs/legal/kvkk-aydinlatma.md) §3
- [Issue #564](https://github.com/selmanays/nodrat/issues/564)
