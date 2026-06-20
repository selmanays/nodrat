---
type: decision
title: "Artefakt-edit DPO — manuel-edit revizyonlarından konservatif tercih çiftleri"
slug: "artifact-edit-dpo"
status: "locked"
decided_on: "2026-06-20"
decided_by: "founder"
created: "2026-06-20"
updated: "2026-06-20"
sources:
  - "docs/engineering/data-model.md§5"
tags: ["locked-decision", "sft", "dpo", "training", "kume-abonelik"]
aliases: ["artifact-revision-dpo"]
---

# Artefakt-edit DPO — manuel-edit revizyonlarından konservatif tercih çiftleri

> **Karar:** Küme-bağlı artefakt revizyon zincirinden DPO tercih çifti YALNIZ **manuel-edit** (`freetext`/`edit`) revizyonlarından + **anlamlı değişim** (difflib similarity < 0.95) üretilir: **chosen = head** (kullanıcının elle düzelttiği), **rejected = parent** (düzeltmeden önceki). Quick-action reshape'leri (`quick_shorter`/`quick_longer`/`quick_rewrite`/`multi_share`) DPO ÜRETMEZ.
> **Durum:** locked
> **Tarih:** 2026-06-20

## TL;DR

Faz 3c/1b SFT curator artefakt-yolu ([[sft-data-pipeline]]) artefakt HEAD'lerini cluster-anchored SFT örneği yazar. DPO yarısı için: revizyon zincirini doğal chosen/rejected'a çevirmenin tek **güçlü ve gürültüsüz** sinyali = kullanıcının LLM çıktısını **elle düzeltmesi**. Bu, [[dpo-rejected-samples]]'in "user-correction = tercih" semantiğinin artefakt karşılığıdır.

## Bağlam

[[dpo-rejected-samples]] (locked, 2026-05-14) tek tanımlı DPO kaynağını **user halu-flag** olarak veriyordu; küme/artefakt-türevli DPO **açık-soruydu** (hiçbir locked karar tanımlamıyordu). Faz 3c artefakt-curator'ı eklenince soru somutlaştı: revizyon zinciri (parent→head) DPO tercih çiftine çevrilmeli mi, ve hangi semantikle?

## Alternatifler ve neden reddedildi

| Alternatif | Artı | Eksi | Karar |
|---|---|---|---|
| Artefakt-DPO hiç üretme (yalnız SFT) | Basit, locked-uyumlu | Değerli tercih sinyali (kullanıcının elle düzeltmesi) atılır | reddedildi |
| TÜM revizyonlardan DPO (head=chosen, initial=rejected; quick-action dâhil) | Çok veri | **Gürültülü** — `quick_longer`'ın "tercih" olması tartışmalı (kullanıcı o an uzun istedi; parent "kötü/reddedilen" değil, sadece farklı biçim) | reddedildi |
| **Yalnız manuel-edit (`freetext`/`edit`) + anlamlı değişim (similarity < 0.95)** | Güçlü sinyal (kullanıcı LLM çıktısını elle düzeltti = halu-flag DPO'yla aynı mantık); düşük gürültü | Daha az veri (manuel edit nadir) | **seçildi** |

## Eligibility kuralları

SFT ile **ortak**: `model_improvement_consent` (KVKK) + review-buffer (7g) + PII secondary scan (head + parent **ayrı** taranır) + `task_type='research_answer'` reuse + idempotent `ON CONFLICT`.

DPO-**özel** (hepsi AND):
- `head.revision_intent ∈ {freetext, edit}` — manuel kullanıcı düzeltmesi.
- head'in bir `parent_revision_id`'si var (initial=head durumu DPO üretmez).
- `difflib.SequenceMatcher(parent, head).ratio() < 0.95` (≥%5 değişim). Küçük tweak (typo/whitespace) parent'ı "rejected" yapmaz — SFT `edit_distance < 0.05` eşiğinin ayna karşılığı.
- `dpo_chosen` (head içeriği, `artifact_revision_seq=head_seq`) ve `dpo_rejected` (parent içeriği, `parent_seq`) **aynı `input_payload`'ı** paylaşır (DPO contract: aynı prompt, farklı output). `quality_signals.dpo_pair_with` ile eşleşir.

## Sonuçlar

- Etkiler: [[dpo-rejected-samples]], [[sft-data-pipeline]], [[own-slm-strategy]].
- Kod: `app/modules/sft/tasks/artifact_curator.py` (`MANUAL_EDIT_INTENTS`, `_DPO_MIN_CHANGE`). Flag `sft.curator.artifacts.enabled` (default False) ile gate'li; aktivasyon master `sft.curator.enabled` + sub-flag ikisini de gerektirir (data-collection canary).
- Prod-doğrulandı (2026-06-20, direct curate): manuel-edit head → sft + dpo_chosen + dpo_rejected, similarity 0.288 ile tetiklendi.

## Geri alma maliyeti

> **Düşük (additive).** Flag OFF iken hiç üretilmez. Semantik değişirse: yalnız curator DPO dalı + bu sayfa güncellenir. Üretilmiş örnekler `sample_type` + `quality_signals.source='artifact'` + `dpo_pair_with` ile filtrelenebilir/silinebilir. 🛑 Nodrat-SLM deploy edilmeden önce self-distillation provenance filtresi şart (yalnız premium-türevi içerik eğitime girmeli).

## Kaynaklar

- [docs/engineering/data-model.md §5](../../docs/engineering/data-model.md) — training_samples şeması, sample_type discriminator.
- İlgili locked kararlar: [[dpo-rejected-samples]] (halu-flag DPO), [[own-slm-strategy]] (premium-only training data), [[sft-message-source]] (curator kaynağı).
