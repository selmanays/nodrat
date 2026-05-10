---
type: concept
title: "SFT Data Pipeline — generations log → training_samples ETL"
slug: "sft-data-pipeline"
category: "architecture-pattern"
status: "planned"
created: "2026-05-10"
updated: "2026-05-10"
sources:
  - "MVP-1.7 milestone — SFT Foundation"
  - "wiki/decisions/own-slm-strategy.md"
  - "GitHub issues #563, #564, #566, #567, #568, #569"
tags: ["llm", "sft", "training-data", "etl", "pipeline", "kvkk", "planned"]
aliases: ["sft-pipeline", "training-data-pipeline", "nodrat-sft-etl"]
---

# SFT Data Pipeline — generations log → training_samples ETL

> **TL;DR:** Nodrat'ın production'daki ham (input, output) generation log'unu, **kullanıcı eyleminden gelen kalite sinyalleri + KVKK consent kapısı + PII secondary scan** ile filtreleyip, gece çalışan ETL worker ile ChatML format'ında curated `training_samples` tablosuna dönüştüren pipeline. Çıktı: Trendyol LLM v4.1.0 üzerine SFT için Hugging Face uyumlu JSONL dataset.

## Tanım

**SFT (Supervised Fine-Tuning) data pipeline**, mevcut LLM çağrılarını gözleyerek bunlardan **eğitim için yeterince kaliteli ve hukuki olarak kullanılabilir** olanları otomatik seçen ve normalize eden bir veri hazırlama hattıdır.

Genel SFT için "altın etiket" 3 kriteri:
1. **Quality** — output gerçekten iyi (halü yok, schema valid, citation correct)
2. **Validation** — kullanıcı tarafından "kabul edilmiş" (copy/post sinyali, regenerate yok)
3. **Compliance** — kullanıcı eğitim için izin vermiş (consent), PII içermiyor

Nodrat'ın pipeline'ı bu üçünü mekanize eder.

## Neden Nodrat'ta var

- **Hangi probleme cevap veriyor:** Kendi domain-spesifik Türkçe SLM'inin ([[trendyol-llm-base]] üstüne) eğitilmesi için **otomatik altın-etiketli dataset** üretmek. Manuel curation 6 ay içinde 18K sample = haftada ~8 saat insan emeği — pipeline ile sıfır.
- **Hangi alternatif(ler)e karşı seçildi:**
  - Manuel data curation → çok pahalı, ölçeklenmez
  - Sadece public corpora (Türkçe CC-100, Wikipedia TR) → Nodrat'ın domain'i (haber sentezi + X post format + citation discipline) yok
  - Synthetic data (DeepSeek'ten yeni veri üretmek) → ToS gri alanı + distribution shift riski
  - **Production log'u + user signal**: en doğal, en uygun maliyetli, en KVKK-uyumlu yol → seçildi
- **Hangi locked karar(lar) bu kavramı çağırıyor:**
  - [[own-slm-strategy]] — Nodrat-AI eğitim stratejisi
  - [[pii-redaction-mandatory]] — secondary PII scan zorunluluğu

## Mimari — uçtan uca akış

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. Live generation                                              │
│    User → /app/generate-stream → DeepSeek V4 → response         │
│    INSERT INTO generations (status='completed', completed_at)   │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 2. User action telemetry (Issue #566)                            │
│    Frontend hooks → POST /app/generations/{id}/copied|posted|... │
│    UPDATE generations SET user_action, action_at,               │
│      time_to_action_sec, edited_text, edit_distance             │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 3. Auto eligibility recompute (her action sonrası)              │
│    _recompute_sft_eligibility(gen):                              │
│      sft_eligible = TRUE iff:                                    │
│        status = 'completed'                                      │
│      AND user.model_improvement_consent_at IS NOT NULL          │
│      AND user.model_improvement_consent_revoked_at IS NULL      │
│      AND user_action IN ('copied', 'posted')                    │
│      AND (edit_distance IS NULL OR < 0.05)                      │
│      AND halu_flagged_at IS NULL                                │
│      AND (created_at < NOW() - 7 days)  -- review buffer        │
│    ELSE: sft_excluded_reason set                                │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 4. Nightly ETL (03:00 TRT, Celery beat — Issue #567)            │
│    a) SELECT generations WHERE sft_eligible=true                │
│       AND created_at >= NOW() - 24h                             │
│    b) PII secondary scan (defense-in-depth)                     │
│       → hit ise skip + sft_excluded_reason='pii_secondary_hit' │
│    c) Quality signals hesapla                                    │
│       (citation_supported_ratio, schema_valid, char_count, ...) │
│    d) ChatML serialize                                           │
│    e) Deterministic split: hash(gen_id) % 100                   │
│       → train(0-79) / val(80-89) / test(90-99)                  │
│    f) INSERT INTO training_samples (UNIQUE constraint)          │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 5. Admin dashboard + JSONL export (Issue #569)                   │
│    GET /admin/sft/stats → günlük rate, distribution, quality    │
│    POST /admin/sft/export → JSONL streaming response            │
│    scripts/sft_push_hf.py → HF Hub private dataset push          │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 6. Faz 1+ — Eğitim (gelecekte, MVP-3 sonrası)                   │
│    Runpod / Lambda Cloud GPU spot — 1× A100 × 6-12 saat         │
│    Trendyol-LLM-7B-chat-v4.1.0 + Nodrat DAPT + SFT + DPO        │
└─────────────────────────────────────────────────────────────────┘
```

## Eligibility kuralları — nereden geliyor?

Her kuralın hukuki/kalite gerekçesi:

| Kural | Sebep |
|-------|-------|
| `model_improvement_consent_at IS NOT NULL` | KVKK md.5 — açık ve özgül amaç (eğitim için ayrı consent) |
| `model_improvement_consent_revoked_at IS NULL` | KVKK md.11 — geri çekme hakkı |
| `user_action IN ('copied', 'posted')` | Pozitif kalite sinyali (kullanıcı kabul etti) |
| `edit_distance < 0.05` | Az düzenleme = output zaten iyi (büyük edit "model yanlıştı" sinyali) |
| `halu_flagged_at IS NULL` | Halü detector flag'i = kalitesiz output |
| `created_at < NOW() - 7 days` | Review buffer — kullanıcı geri çekebilir |

## Quality signals — `training_samples.quality_signals` JSONB

```json
{
  "citation_supported_ratio": 1.0,    // _citation metadata'dan
  "edit_distance": 0.02,              // generations.edit_distance
  "time_to_action_sec": 47,           // çok kısa → kullanıcı dikkatli okumadı
  "schema_valid": true,               // Pydantic re-validation
  "json_parse_ok": true,
  "source_count": 3,
  "char_count": 247
}
```

İleride `min_quality_score` (admin tunable, default 0.7) bu sinyallerden composite skor hesaplayıp threshold filter ekleyecek.

## Train/val/test split — deterministic

```python
import hashlib

def assign_split(generation_id: str) -> str:
    h = hashlib.sha256(generation_id.encode()).hexdigest()[:8]
    bucket = int(h, 16) % 100
    if bucket < 80: return 'train'
    if bucket < 90: return 'val'
    return 'test'
```

**Özellikler:**
- Deterministic — aynı `generation_id` her zaman aynı split'e gider
- Distributed — 80% train, 10% val, 10% test (büyük örneklemde)
- Idempotent — ETL 2 kez çalışınca aynı split üretir

## ChatML çıktı format

```json
{
  "messages": [
    {"role": "system", "content": "<system_prompt>"},
    {"role": "user", "content": "<user_payload>"},
    {"role": "assistant", "content": "<edited_output_or_original>"}
  ],
  "metadata": {
    "task_type": "content_generator",
    "prompt_version": "1.1.0",
    "quality_signals": {...},
    "sft_split": "train"
  }
}
```

`edited_output` varsa onu kullan (kullanıcının nihai versiyonu — DPO için altın). Yoksa `output_payload`.

## KVKK silme propagation — hard requirement

```
User soft delete                     →  CASCADE → training_samples.user_id satırları silinir
User explicit consent revoke         →  Ayrı task: DELETE FROM training_samples WHERE user_id=X
generation.deleted_at SET            →  CASCADE → training_samples.generation_id satırı silinir
```

KVKK md.11 (geri çekme) + md.7 (silme) hakları training_samples'a otomatik akıyor.

## Configuration — admin tunable (SettingsStore)

| Key | Type | Default | Açıklama |
|-----|------|---------|----------|
| `sft.curator.review_buffer_days` | INT | 7 | Generation oluşturulduktan kaç gün sonra ETL'e dahil |
| `sft.curator.daily_max_samples` | INT | 1000 | Overflow protection |
| `sft.curator.min_quality_score` | FLOAT | 0.7 | Composite threshold (0-1 arası) |
| `sft.curator.enabled` | BOOL | false | Kill switch |

## Ölçüm / uygulama

- **Telemetri:** Redis counter `sft.curated.daily.{task_type}` INCR
- **Admin dashboard:** `/admin/sft` (Issue #569)
- **Eğitim hazırlığı eşik:** ≥10K sample / task_type (~3-4 ay üretim)

## İlişkiler

- **İlgili kavramlar:** [[provider-abstraction]] (gelecekte Nodrat-AI provider eklenecek), [[hot-cold-tier]] (DAPT corpus cold tier'da arşiv), [[pii-redaction-mandatory]]
- **İlgili varlıklar:** [[trendyol-llm-base]] (eğitim hedefi), [[deepseek]] (eğitim verisi kaynağı), [[celery-worker]] (ETL task'ı)
- **İlgili kararlar:** [[own-slm-strategy]] (ana karar), [[pii-redaction-mandatory]] (secondary scan zorunluluğu)
- **İlgili topics:** [[llm-provider-strategy]] (genişletilecek)

## Açık sorular / TODO

- **DPO format**: Preference pairs için ayrı tablo mı (`training_pairs`)? Şu an MVP-1.7'de SFT için tek tablo, DPO Faz 2'de eklenecek.
- **Multi-task ratio**: Eğitim sırasında content_generator vs query_planner vs style_analyzer karışımı ne olacak? Şu an her task ayrı; karar Faz 1+ eğitim hazırlığında.
- **Distillation augmentation**: Aynı input'a DeepSeek'ten birden fazla output sample'ı sentetik üretme — synthetic data augmentation. ToS gri alanı + Trendyol Apache 2.0 base ile etik. Şu an dışı; gelecek tartışma.
- **Self-distillation feedback loop**: Nodrat-AI Faz 4'te deploy edildikten sonra kendi output'ları yeni training_samples üretir mi? Drift riski var (model errors model errors'i pekiştirir). Karar: hayır, sadece premium model output'ları (DeepSeek + Haiku) eğitim verisi olur.

## Kaynaklar

- [GitHub MVP-1.7 milestone](https://github.com/selmanays/nodrat/milestone/15)
- [Issue #563 — generations user-action telemetry kolonları](https://github.com/selmanays/nodrat/issues/563)
- [Issue #564 — model_improvement_consent KVKK checkbox](https://github.com/selmanays/nodrat/issues/564)
- [Issue #566 — user action endpoints + consent revoke](https://github.com/selmanays/nodrat/issues/566)
- [Issue #567 — training_samples + nightly ETL worker](https://github.com/selmanays/nodrat/issues/567)
- [Issue #568 — frontend hooks + onboarding consent](https://github.com/selmanays/nodrat/issues/568)
- [Issue #569 — admin SFT dashboard + JSONL export](https://github.com/selmanays/nodrat/issues/569)
- [[own-slm-strategy]] — bağlı locked decision
- [[trendyol-llm-base]] — eğitim hedefi base model
