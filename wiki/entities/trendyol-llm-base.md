---
type: entity
title: "Trendyol-LLM-7B-chat-v4.1.0 (planlanan SLM base)"
slug: "trendyol-llm-base"
category: "provider"
status: "planned"
created: "2026-05-10"
updated: "2026-05-10"
sources:
  - "https://huggingface.co/Trendyol/Trendyol-LLM-7B-chat-v4.1.0"
  - "wiki/decisions/own-slm-strategy.md"
tags: ["llm", "base-model", "qwen2", "turkish", "trendyol", "planned", "open-source"]
aliases: ["trendyol-llm-v4", "trendyol-7b-chat", "trendyol-llm", "nodrat-base-model"]
---

# Trendyol-LLM-7B-chat-v4.1.0 (planlanan SLM base)

> **TL;DR:** Nodrat'ın kendi domain-spesifik Türkçe SLM'inin **base model'i** olarak seçildi (2026-05-10). Trendyol'un Qwen 2 7B üzerine ürettiği Türkçe fine-tune. **Apache 2.0 lisansı** sayesinde naming şartı + attribution yükümlülüğü olmadan ticari türev iş üretilebilir. Şu an aktif kullanımda **değil**; MVP-1.7 ([[sft-data-pipeline]]) ile veri toplama altyapısı kurulduktan sonra Faz 1+ eğitim için kullanılacak.

## Tanım

`Trendyol-LLM-7B-chat-v4.1.0`, Trendyol Group AI ekibi tarafından üretilen, **Qwen 2 7B** üzerine yoğun Türkçe corpus ile fine-tune edilmiş, instruction-following + conversational capability'lere sahip 7B parametreli bir dil modeli. Hugging Face üzerinde açık paylaşılır (`safetensors` formatında).

**Lineage zinciri (3 katman da Apache 2.0):**

```
Qwen 2 7B (Alibaba, Apache 2.0)
   ↓ Türkçe DAPT + SFT (Trendyol)
Trendyol-LLM-7B-chat-v4.1.0 (Apache 2.0)   ← Nodrat'ın base'i
   ↓ Nodrat DAPT + SFT + DPO + tokenizer ext (planlanan)
Nodrat AI (Apache 2.0 türev)
```

**Kritik:** Qwen 2 ailesinde **sadece 7B sürümü Apache 2.0**. Daha büyük 72B sürümü Tongyi Qianwen lisansında (kısıtlı). Trendyol akıllıca 7B'yi seçmiş — Nodrat için ekstra şanslı bir lineage.

## Nodrat'ta planlanan kullanım

- **Hangi servis kullanır:** Faz 4'te yeni `NodratAIProvider` ([[provider-abstraction]] üzerine implementation) — `apps/api/app/providers/nodrat_ai.py` (henüz yok)
- **Hangi tier'da aktif olacak:** Free + Starter (Pro/Agency Haiku ile devam — [[claude-haiku-premium-llm]])
- **Hangi MVP'de devreye girecek:** MVP-3 sonrası (eval gate başarılıysa). MVP-1.7 sadece veri toplama altyapısı.
- **Hangi prompt'ları handle edecek:** Content Generator + Query Planner + Style Analyzer (image caption Faz 4'te VLM ayrı)

## Önemli özellikler / parametreler

| Parametre | Değer | Kaynak |
|---|---|---|
| Mimari | Qwen 2 (decoder-only transformer) | Hugging Face model card |
| Parametre sayısı | 7B (~13.4 GB FP16) | safetensors metadata |
| Tokenizer vocab | 32K (qwen2 default) | Genişletilecek → 35K (Nodrat domain) |
| Context window | 32K token | Qwen 2 spec |
| Lisans | **Apache 2.0** ✅ | HF model card |
| Türkçe baseline | Mevcut TR-fine-tune'lardan en güçlülerden | Trendyol product page |
| HF model ID | `Trendyol/Trendyol-LLM-7B-chat-v4.1.0` | HF |
| Format | safetensors | HF |

## Apache 2.0 — hak ve sınırlar tablosu

### ✅ Sınırsız izin

- **Ticari kullanım** — Pro/Agency tier'ında ücretli sun
- **Modifikasyon** — DAPT, SFT, DPO, tokenizer extension, hepsi serbest
- **İstediğin ad** — "Nodrat-AI-7B" (Llama'nın aksine naming şartı **yok**)
- **Closed-source dağıtım** — fine-tune sonrası weights paylaşma zorunluluğu yok (SaaS olarak servis)
- **Sublicense** — istersen başka şirkete satabilirsin
- **Patent grant** — Trendyol'un patent hakları otomatik aktarılır

### ⚠️ Uyulması gereken küçük şart (sadece weights dağıtırsan)

- LICENSE dosyasını paket içinde koru
- NOTICE dosyası varsa onu da koru (HF model card kontrolü gerek)
- **Nodrat SaaS olarak servis ediyor (weights kullanıcılara verilmiyor) → bu şart tetiklenmez**

### ❌ Yasak (önemsiz)

- "Trendyol" markasını/logosunu kendi pazarlamanda kullanmak (zaten yapmazsın)
- "Bu Trendyol'un onayladığı modeldir" gibi yanıltıcı ifadeler

## Türkçe kalite — 5-test stres profili sonucu (önceki LLM karşılaştırma turunda)

Henüz Trendyol v4.1.0 stres test'inde koşulmadı. Önceki turda denenen modeller:

| Model | Skor (5 test, 80 puan) | DeepSeek'e oran |
|---|---|---|
| Gemma 4 31B | 49 | %100+ baseline |
| Ministral 14B | 46 | %94 |
| Open Mistral 7B | 41 (T1 auto-fail) | %59 (diskalifiye) |
| Gemma 3 12B | 40 | %80 |
| Qwen 2.5 7B Turbo | 32 | %65 |
| Gemma 3n e4b | 30 | %60 |
| Qwen 2.5 14B | 30 (factual error) | %60 (diskalifiye) |

**Bekleme:** Trendyol v4.1.0 (Qwen 2 7B base + Türkçe DAPT) Open Mistral 7B'den ve Qwen 2.5 7B Turbo'dan üstün skor vermeli. Tahmini ~38-44/80 (%75-85). Gerçek sayı stres testi yapıldığında belli olacak.

## Stres test TODO

Önceki turdaki 5 prompt setiyle Trendyol v4.1.0'ı (HF Inference API veya local quantize) test edip baseline ölç:

1. T1 — Halüsinasyon vakum testi (insufficient_data discipline)
2. T2 — Sayısal hassasiyet + Türkçe format
3. T3 — Kaynak güvenilirlik hiyerarşisi
4. T4 — Tone mimicry + yasaklı kelime
5. T5 — Multi-hop inference

İdeal eşik: ≥%85 of DeepSeek skoru. Test sonucu burada güncellenecek.

## Kararlar (locked)

- [[own-slm-strategy]] — bu varlığın "Nodrat'ın gelecekteki SLM base'i" rolü locked karar.

## İlişkiler

- **İlgili kavramlar:** [[provider-abstraction]] (gelecekte `NodratAIProvider` Protocol implementation'ı), [[sft-data-pipeline]] (eğitim verisi mimarisi), [[pii-redaction-mandatory]] (training_samples öncesi PII secondary scan)
- **İlgili varlıklar:** [[deepseek]] (mevcut default LLM, SFT için training data kaynağı), [[claude-haiku-4-5]] (premium tier — paralel kalır)
- **İlgili kararlar:** [[own-slm-strategy]] (ana karar), [[deepseek-default-llm]] (rolü uzun vadede revize edilir)
- **İlgili topics:** [[llm-provider-strategy]] (Faz 4 sonrası genişletilecek)

## Açık sorular / TODO

- **5-test stres profili**: Trendyol v4.1.0'ı önceki test setinde koş, baseline skor kaydet. Eğer DeepSeek'in %75 altıysa fine-tune ile %85'e çıkarmak gerek çok eğitim demektir → strateji yeniden değerlendir.
- **HF model card NOTICE dosyası**: Var mı? Varsa içeriği nedir? (sadece weights dağıtırsak şart tetiklenir)
- **Quantize formatı seçimi**: Production deploy'da Q4_K_M GGUF (CPU) mu, AWQ Q4 (GPU) mu? Şu an [[contabo-vps]] CPU-only — fine-tune sonrası ayrı GPU node mu eklenecek?
- **Trendyol attribution etiği**: Apache 2.0 zorunlu kılmasa da model card'da "Built on Trendyol-LLM-7B-chat-v4.1.0" lineage transparency etik tavsiye. Lansman aşamasında karar.
- **HF Hub upload**: Fine-tune edilmiş "Nodrat-AI-7B" weights'i HF Hub'a private mı, public mı yüklenecek? Önerim: private (şirket IP'si).

## Kaynaklar

- [Trendyol-LLM-7B-chat-v4.1.0 — Hugging Face model card](https://huggingface.co/Trendyol/Trendyol-LLM-7B-chat-v4.1.0)
- [Qwen 2 technical report](https://qwenlm.github.io/blog/qwen2/) — base mimari
- [Apache 2.0 LICENSE metni](https://www.apache.org/licenses/LICENSE-2.0)
- [[own-slm-strategy]] — bağlı locked decision
- [[sft-data-pipeline]] — eğitim verisi pipeline
