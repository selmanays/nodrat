---
type: decision
title: "DPO rejected samples — halu mesajları DPO eğitimi için sakla"
slug: "dpo-rejected-samples"
status: "locked"
decided_on: "2026-05-14"
decided_by: "founder"
created: "2026-05-14"
updated: "2026-05-14"
sources:
  - "docs/engineering/data-model.md§5"
tags: ["locked-decision", "sft", "dpo", "training"]
aliases: ["halu-feedback-dpo"]
---

# DPO rejected samples — halu mesajları DPO eğitimi için sakla

> **Karar:** Kullanıcı tarafından "halüsinasyon" işaretlenen mesajlar **silinmez veya yok sayılmaz**; `dpo_rejected=true` ile DPO (Direct Preference Optimization) eğitimi için saklanır. Opsiyonel `dpo_chosen_content` ile pair complete olur.
> **Durum:** locked
> **Tarih:** 2026-05-14

## Bağlam

Chat-only migration sırasında halu feedback mekanizması yeniden tasarlandı (S1C, #802). Eski form modu'nda halu flag'ı sadece `sft_eligible=false` sebebi olarak kullanılıyordu — değerli "negative example" sinyali atılıyordu.

Soru: Halu mesajını sadece SFT'den dışla mı, yoksa DPO için sakla mı?

## Alternatifler ve neden reddedildi

| Alternatif | Artı | Eksi | Karar |
|---|---|---|---|
| Halu mesajları sadece `sft_eligible=false` ile dışla, kaydetme | Storage tasarrufu | Negative example sinyali atılır; DPO için zaman kazanılmaz | reddedildi |
| Halu mesajları soft-delete et | Audit trail kalır | Storage sorunu hâlâ var; DPO için kullanılamaz | reddedildi |
| **Halu mesajları `dpo_rejected=true` ile sakla; kullanıcıdan opsiyonel "doğru cevap" iste; pair complete olursa DPO sample** | Negative + positive example tek API call ile yakalanır; Trendyol-LLM 7B üzerine fine-tune için değerli | Şema biraz daha karmaşık; sample_type discriminator gerekir | **seçildi** |

## Uygulama

**Schema (messages tablosu, migration `20260514_1800`):**

```sql
ALTER TABLE messages ADD COLUMN halu_flagged_at TIMESTAMPTZ;
ALTER TABLE messages ADD COLUMN halu_flagged_by UUID REFERENCES users(id) ON DELETE SET NULL;
ALTER TABLE messages ADD COLUMN halu_flagged_reason TEXT;
ALTER TABLE messages ADD COLUMN dpo_rejected BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE messages ADD COLUMN dpo_chosen_content TEXT;
CREATE INDEX idx_messages_dpo_rejected ON messages(dpo_rejected, role)
  WHERE dpo_rejected = true AND role = 'assistant';
```

**Endpoint (`POST /chat/messages/{msg_id}/flag-halu`):**

```python
class FlagHaluRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)
    chosen_content: str | None = Field(default=None, max_length=5000)
    # DPO için kullanıcının "doğru cevap" önerisi opsiyonel
```

Side effects:
- `halu_flagged_at`, `halu_flagged_by`, `halu_flagged_reason` set
- `dpo_rejected=true`
- `dpo_chosen_content` (varsa)
- `sft_eligible=false`, `sft_excluded_reason='halu_flagged'`
- AdminAuditLog entry

**Training samples (`sample_type` discriminator):**

| Sample type | Üretim koşulu | Anlam |
|---|---|---|
| `sft` | `sft_eligible=true` | "Bu cevap iyi, taklit et" |
| `dpo_rejected` | `dpo_rejected=true` | "Bu cevap kötü, üretme" |
| `dpo_chosen` | `dpo_rejected=true` + `dpo_chosen_content` | "Bunun yerine bu cevabı üret" (pair complement) |

DPO pair sayısı admin/sft/stats `dpo_pair_complete` field'ında — `chosen + rejected` aynı `message_id` için.

## Sonuçlar

- **Şema:** `training_samples.sample_type VARCHAR(16) NOT NULL DEFAULT 'sft'`, CHECK constraint 3 değer
- **Idempotency:** Partial UNIQUE `(message_id, task_type, sample_type)` — aynı message için her tipten en fazla 1 sample
- **Curator:** Tek query iki sample tipini de üretir (sft_eligible varsa SFT; dpo_rejected varsa DPO_REJECTED; chosen_content varsa ek olarak DPO_CHOSEN)
- **UI:** HaluFlagModal — 2 textarea (reason + chosen_content for DPO); admin SFT dashboard'da sample_type badge
- **Long-term:** Trendyol-LLM-7B-chat-v4.1.0 fine-tune'unda DPO step için chosen/rejected pair'ler hazır — bkz. [[own-slm-strategy]]

## Geri alma maliyeti

> DPO sample'ları silinirse training data kaybedilir. Şema kalıcı; revisable değil — yalnızca **policy** değişebilir (örn. retention süresi kısaltma).
> Saklama süresi: KVKK kapsamında kullanıcı consent revoke ederse messages.user_id CASCADE ile silinir → DPO sample'lar da kaybolur (acceptable trade-off).

## İlişkiler

- **Bağlı varlıklar:** [[sft-data-pipeline]]
- **Bağlı kavramlar:** [[chat-message-feedback-columns]]
- **Bağlı decisions:** [[chat-only-migration]], [[sft-message-source]], [[own-slm-strategy]], [[artifact-edit-dpo]] (aynı "user-correction=tercih" semantiğinin artefakt karşılığı)

## Kaynaklar

- [docs/engineering/data-model.md](../../docs/engineering/data-model.md) §5 (messages dpo_rejected + dpo_chosen_content)
- Migrations: `20260514_1800_messages_feedback_dpo_columns.py`, `20260514_1900_training_samples_message_link.py`
- Endpoint: `apps/api/app/api/app_chat.py` (POST /chat/messages/{id}/flag-halu)
- UI: `apps/web/src/components/chat/HaluFlagModal.tsx`
