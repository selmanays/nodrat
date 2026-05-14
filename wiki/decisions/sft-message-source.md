---
type: decision
title: "SFT pipeline messages source — chat-derived ETL"
slug: "sft-message-source"
status: "locked"
decided_on: "2026-05-14"
decided_by: "founder"
created: "2026-05-14"
updated: "2026-05-14"
sources:
  - "docs/engineering/data-model.md§5.4"
  - "wiki/concepts/sft-data-pipeline.md"
tags: ["locked-decision", "sft", "data-pipeline", "mvp-1"]
aliases: ["sft-curator-messages-rewrite"]
---

# SFT pipeline messages source — chat-derived ETL

> **Karar:** `sft_curator` worker'ı artık `generations` tablosundan değil, `messages` tablosundan beslenir; her assistant mesajı potansiyel SFT veya DPO sample'ı olabilir.
> **Durum:** locked
> **Tarih:** 2026-05-14

## Bağlam

Chat-only migration sonrası (#800 epic) `generations` tablosu DROP edildi. SFT pipeline daha önce form modu generation log'larından beslenirken artık tek üretim noktası **sohbet messages**'tır. Pipeline'ı yeniden tasarlamak gerekti.

## Alternatifler ve neden reddedildi

| Alternatif | Artı | Eksi | Karar |
|---|---|---|---|
| `generations` tablosunu koru; chat'i ayrı snapshot olarak generations'a kopyala | Mevcut SFT pipeline aynen çalışır | Çift veri (storage); cascade audit zor; data-drift riski | reddedildi |
| Yeni `chat_samples` tablo (curated messages cache) | İzole | Bir tablo daha bakım; double-write riski | reddedildi |
| **Messages tablosunu doğrudan beslens — curator NOT EXISTS filter ile idempotent** | Tek doğruluk kaynağı; ek tablo yok; partial UNIQUE index ile idempotent | Mesaj tablosu hızla büyüyor (her sohbet kullanıcısı için) — fakat partial index'ler bunu hafifletir | **seçildi** |

## Uygulama

**Query (apps/api/app/workers/tasks/sft_curator.py):**

```python
select(Message, Conversation, User)
  .join(Conversation, Conversation.id == Message.conversation_id)
  .join(User, User.id == Conversation.user_id)
  .where(
    Message.role == "assistant",
    (Message.sft_eligible.is_(True)) | (Message.dpo_rejected.is_(True)),
    ~Message.id.in_(
        select(TrainingSample.message_id).where(
            TrainingSample.message_id.is_not(None),
            TrainingSample.task_type == "chat_answer",
        )
    ),
  )
  .order_by(Message.created_at.asc())
  .limit(daily_max)
```

**Sample tipleri:**

| Mesaj durumu | Üretilen sample(s) |
|---|---|
| `sft_eligible=true` | `sample_type='sft'` (1 satır) |
| `dpo_rejected=true` | `sample_type='dpo_rejected'` (1 satır) |
| `dpo_rejected=true` + `dpo_chosen_content` | yukarıya ek olarak `sample_type='dpo_chosen'` (pair complete) |

**Idempotency:** Partial UNIQUE index `uq_training_samples_message_task_sample(message_id, task_type, sample_type) WHERE message_id IS NOT NULL` (migration `20260514_1900`)

**Task type:** `chat_answer` (yeni); eski `content_generator` task_type'lı satırlar nullable `generation_id` ile miras hâlde durur.

**Deterministic split:** `hash(message_id) % 100` → train/val/test (80/10/10)

## Sonuçlar

- **`training_samples` schema:** `message_id` FK eklendi (CASCADE on message delete); `generation_id` nullable (FK kaldırıldı; eski satırlar anonim hâlde durur)
- **PII secondary scan:** Her message için curator `redact()` çağırır (defense-in-depth); hit varsa `sft_eligible=false`, `sft_excluded_reason='pii_secondary_hit'`
- **ChatML input:** Önceki user mesajı + `sources_used` (max 10 kaynak listesi) → input_payload; assistant `content` → output_payload
- **Quality signals:** edit_distance, user_action, halu_flagged, dpo_rejected, has_thinking_steps
- **admin/sft/stats:** Yeni alanlar — `by_sample_type` (sft/dpo_chosen/dpo_rejected breakdown), `dpo_pair_complete` (chosen+rejected pair count); `eligible_pending` artık `messages.sft_eligible OR dpo_rejected` üzerinden

## Geri alma maliyeti

> Curator'u geri çevirmek için **generations tablosu yeniden CREATE edilmeli** — tarihçe dönülmez kayıp. Pratik olarak `revisable` değil; bu yüzden **locked**.

## İlişkiler

- **Bağlı varlıklar:** [[sft-data-pipeline]]
- **Bağlı kavramlar:** [[chat-message-feedback-columns]]
- **Bağlı decisions:** [[chat-only-migration]], [[dpo-rejected-samples]], [[own-slm-strategy]]

## Kaynaklar

- [docs/engineering/data-model.md](../../docs/engineering/data-model.md) §5.4 (training_samples)
- [docs/engineering/data-model.md](../../docs/engineering/data-model.md) §5.x (conversations + messages)
- Migration: `apps/api/alembic/versions/20260514_1900_training_samples_message_link.py`
- Worker: `apps/api/app/workers/tasks/sft_curator.py`
