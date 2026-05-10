---
type: decision
title: "Own SLM strategy — Trendyol LLM v4.1 üzerine domain-spesifik fine-tune"
slug: "own-slm-strategy"
status: "locked"
decided_on: "2026-05-10"
decided_by: "founder"
created: "2026-05-10"
updated: "2026-05-10"
sources:
  - "MVP-1.7 milestone — SFT Foundation"
  - "https://huggingface.co/Trendyol/Trendyol-LLM-7B-chat-v4.1.0"
  - "wiki/decisions/deepseek-default-llm.md"
  - "wiki/entities/trendyol-llm-base.md"
  - "wiki/concepts/sft-data-pipeline.md"
tags: ["locked-decision", "llm", "strategy", "sft", "moat", "long-term"]
aliases: ["nodrat-slm-strategy", "trendyol-fine-tune-strategy", "own-model-strategy", "slm-roadmap"]
---

# Own SLM strategy — Trendyol LLM v4.1 üzerine domain-spesifik fine-tune

> **Karar:** Nodrat, uzun vadede DeepSeek'e teknolojik bağımlılığı kırmak ve IP/moat oluşturmak için kendi domain-spesifik Türkçe SLM'ini (Small Language Model) geliştirir. Base: [[trendyol-llm-base|Trendyol-LLM-7B-chat-v4.1.0]] (Apache 2.0). Yöntem: DAPT + SFT + DPO + tokenizer extension (Basamak 3 — "Türkçe içerik üretimi için özel-eğitilmiş Nodrat modeli" olarak savunulabilir kimlik).
> **Durum:** locked (strateji); planning (uygulama)
> **Tarih:** 2026-05-10

## Bağlam

DeepSeek V4 Flash MVP-1'den beri Nodrat'ın varsayılan LLM'i ([[deepseek-default-llm]]). Bu karar **maliyet motivasyonlu değildir** — kampanya indirimiyle birlikte fatura ayda ~$2-5 seviyesinde, ölçeklendiğinde bile ~$33/ay. Asıl motivasyon şu üç stratejik kazanım:

1. **Vendor lock-in azaltma** — DeepSeek'in Çin merkezli olması, ToS değişikliği veya jeopolitik kısıtlamalara karşı bir "kendi modelimiz var" güvencesi gerek.
2. **IP / moat** — Nodrat'ın user-validated (input, output) çiftleri **hiçbir rakipte olmayan** Türkçe içerik üretimi domain corpus'u oluşturuyor. Bu veri ile fine-tune edilmiş model = Nodrat'ın savunulabilir teknolojik avantajı.
3. **Talent + PR** — "Kendi modelimiz var" diyebilen Türk teknoloji girişimi az; ML hire'ı çekmek + "made in Turkey" anlatısı bunun üstüne kurulur.

## Karar — neden Trendyol LLM v4.1.0?

3 alternatif arasından seçildi:

| Alternatif | Lisans | Türkçe baseline | Karar |
|---|---|---|---|
| **Trendyol-LLM-7B-chat-v4.1.0** (Qwen 2 base) | **Apache 2.0** ✅ | Mevcut en güçlü TR-fine-tune'lardan | **Seçildi** |
| Mistral 7B base | Apache 2.0 | TR baseline zayıf (5-test stres profilinde 41/80) | Reddedildi — TR için extra DAPT yükü |
| Llama 3.1 8B | Llama Community | TR orta | Reddedildi — naming şartı ("Llama-X-7B") + AUP yükü |

**Lineage zinciri (3 katman da Apache 2.0):**

```
Qwen 2 7B (Alibaba, Apache 2.0)
   ↓ Türkçe fine-tune
Trendyol-LLM-7B-chat-v4.1.0 (Apache 2.0)
   ↓ Nodrat türev iş (planlanan)
Nodrat AI (Apache 2.0 türev — naming şartı yok)
```

**Apache 2.0 ne sağlıyor:**
- ✅ Ticari kullanım (Pro/Agency tier'ında para karşılığı sun)
- ✅ İstediğin ad ("Nodrat-AI-7B" — Llama'nın aksine naming şartı yok)
- ✅ Closed-source dağıtım (fine-tune sonrası weights paylaşma zorunluluğu yok)
- ✅ Sublicense + patent grant
- ⚠️ LICENSE/NOTICE dosyalarını koru (sadece weights dağıtırsan; SaaS olarak servis edersen tetiklenmez)

## "Kendi modelimiz" iddiasının savunulabilir basamağı — Basamak 3

5 basamaklı sahiplik merdiveninde hedef = Basamak 3 (DAPT + SFT + DPO + tokenizer ext):

```
Basamak 5 — Sıfırdan pretrain          [%100 sahiplik, $5M+]   ❌ MVP-1.7'de değil
Basamak 4 — Mimari + tokenizer + pretrain'in büyük kısmı       ❌ Faz 4+ için
Basamak 3 — DAPT + SFT + DPO + tokenizer extension             ✅ HEDEF
Basamak 2 — Sadece full SFT                                    🟡 yetersiz
Basamak 1 — Sadece LoRA                                        ❌ "fine-tune" demeyi gerektirir
```

Basamak 3'e çıkmak için 6 iş yapılır (yol haritası §"Roadmap"e bak):
1. **DAPT** (Continued/Domain-Adaptive Pretraining) — 5-10B Türkçe haber/sosyal token
2. **Tokenizer extension** — qwen2 tokenizer'ına +3K Türkçe domain token
3. **Full SFT** — Nodrat'ın altın-etiketli (input, output) çiftleri
4. **DPO** (Direct Preference Optimization) — user "copy/post" vs "regenerate" sinyalleri
5. **Eval framework** — kendi golden test set'i (halü <%2, citation %100)
6. **Model card + lineage transparency** — Hugging Face model card + closed weights

## Pazarlama dili — net izinler

| ✅ Diyebileceğimiz | ❌ Diyemeyeceğimiz |
|---|---|
| "Nodrat'ın kendi içerik AI modeli" | "Sıfırdan eğittiğimiz model" |
| "Türkçe için özel-eğitilmiş Nodrat AI" | "Hiçbir base model kullanmadan" |
| "Domain-adapted ve preference-tuned, Trendyol LLM v4 base üzerine" | "Türkiye'nin ilk LLM'i" (Trendyol, KocLLM var) |
| "Açık-kaynak Türkçe LLM ekosistemine domain expertise'imizi kattığımız Nodrat modeli" | "OpenAI/Anthropic seviyesinde model" |

**Altın kural:** Marketing'de ürün adı (Nodrat AI), teknik dokümantasyonda lineage (Trendyol base + DAPT + SFT + DPO).

## Roadmap — bağlı süreçler ve fazlar

### Faz 0 — Veri toplama altyapısı (MVP-1.7, **şimdi**)

- 6 issue'lu milestone: [MVP-1.7 — SFT Foundation](https://github.com/selmanays/nodrat/milestone/15)
- Issue [#563](https://github.com/selmanays/nodrat/issues/563) — generations user-action telemetry kolonları
- Issue [#564](https://github.com/selmanays/nodrat/issues/564) — `model_improvement_consent` 5. KVKK checkbox
- Issue [#566](https://github.com/selmanays/nodrat/issues/566) — user action endpoints + consent revoke
- Issue [#567](https://github.com/selmanays/nodrat/issues/567) — `training_samples` tablosu + nightly ETL worker
- Issue [#568](https://github.com/selmanays/nodrat/issues/568) — frontend hooks + onboarding consent
- Issue [#569](https://github.com/selmanays/nodrat/issues/569) — admin SFT data pipeline dashboard + JSONL export

**Çıktı:** Günde ~100+ altın-etiket sample biriktiren pipeline. 30 gün sonra ~3K, 6 ay sonra ~18K sample.

### Faz 1 — DAPT corpus toplama (MVP-1.8 veya MVP-2.x, **3 ay sonra**)

- Nodrat'ın retrieval pipeline'ı zaten Türkçe haber çekiyor → ham corpus arşivleyen worker
- Hedef: 5-10B Türkçe token (haber + Wikipedia TR + Türkçe CC-100 + sosyal medya)
- Yeni tablo: `dapt_corpus`
- Maliyet: storage ~$5-15/ay (Contabo Object Storage cold tier — [[hot-cold-tier]])

### Faz 2 — Tokenizer extension hazırlığı

- `tokenizer_candidate_tokens` tablosu — Nodrat haber kaynaklarındaki en sık 5K rare token
- Türk parti adları (CHP/AKP/MHP/iyiP), kurumlar (TÜBİTAK/TÜSİAD), sosyal medya patterns (#GündemTürkiye), Nodrat-specific format token'ları (`[CITATION]`, `[INSUFFICIENT_DATA]`, `[X_POST]`)
- Çıktı: tokenizer extension için aday liste

### Faz 3 — İlk eğitim run (MVP-3 sonrası, **6-12 ay sonra**)

- ~10-30K SFT sample biriktikten sonra ilk fine-tune
- Eğitim ortamı: Runpod / Lambda Cloud GPU spot — 1× A100 × 6-12 saat ≈ $30-100
- Aşamalar:
  1. Tokenizer extension (qwen2 32k → 35k vocab)
  2. DAPT (continued pretraining) — 6.2B token üzerinde 1 epoch
  3. SFT (full weights, LoRA değil)
  4. DPO (preference pairs)
- Eval gate: Nodrat golden test set'inde DeepSeek'in ≥%85'ine ulaşmalı
- Geçerse: A/B test (Free tier'da %10 traffic Nodrat-AI-v1, %90 DeepSeek)

### Faz 4 — Production rollout (MVP-3.x veya MVP-4)

- Free tier'da %100 Nodrat-AI (DeepSeek tamamen değişir mi yoksa fallback olarak kalır mı eval'a göre)
- Pro/Agency tier'da Haiku ([[claude-haiku-premium-llm]]) korunuyor (premium)
- Self-host: GPU node ([[contabo-vps]] üstüne değil — ayrı Hetzner GPU veya Runpod sustained)

### Faz 5 — DPO + RLHF iterasyonları (12-18 ay sonra)

- Daha fazla user feedback toplandıkça aylık iterasyon
- Constitutional AI: halü <%2 hedefi rule-based reward shaping ile

## Bağlı süreçler — bu kararı etkileyen / bu karar tarafından etkilenen

| Süreç | Bağlantı |
|---|---|
| [[deepseek-default-llm]] | Şu an default LLM; SFT için training data kaynağı |
| [[claude-haiku-premium-llm]] | Premium tier'da kalır (SLM Free tier'da deploy) |
| [[provider-abstraction]] | `ModelProvider` Protocol — Nodrat-AI provider gelecekte ekleneceğinde sorunsuz takılır |
| [[pii-redaction-mandatory]] | SFT öncesi training_samples'ta secondary PII scan zorunlu |
| [[twenty-five-word-quote-cap]] | Eval gate'inde halü/citation testi bunu da kapsar |
| [[risk-cost-runaway]] | Self-host GPU = sabit cost; runaway riski azalır |
| [[hot-cold-tier]] | DAPT corpus cold tier'da arşivlenir |
| [[sft-data-pipeline]] | Faz 0 mimarisi — bu sayfada detay |
| [[trendyol-llm-base]] | Base model entity'si |

## Geri alma maliyeti

Bu karar değiştirilirse (ör. başka bir base model'e geçiş veya stratejinin terkedilmesi):

1. **Veri korunur** — `training_samples` tablosu format-agnostik (ChatML), her base model'e uyumlu. Loss yok.
2. **Issues / kod** — MVP-1.7 milestone'u tamamlandıysa kod kalır (genel telemetry altyapısı, SFT'a özgü değil).
3. **Wiki** — bu sayfa `status: deprecated` olur, alternative strategy yeni sayfa açar.
4. **Marketing** — eğer "Nodrat AI" lansmanı yapıldıysa rebranding maliyeti.

Tahmini değişiklik süresi: pivot tipine göre 1-8 hafta.

## Sonuçlar

- **Etkilenen varlıklar:** [[trendyol-llm-base]], [[deepseek]] (uzun vade rolü), [[contabo-vps]] (DAPT corpus storage), [[celery-worker]] (yeni ETL task'ı)
- **Etkilenen kavramlar:** [[sft-data-pipeline]], [[provider-abstraction]] (gelecekte Nodrat-AI provider eklenecek)
- **Etkilenen kararlar:** [[deepseek-default-llm]] (uzun vade rolü "training data kaynağı + Pro tier baseline" olarak revize)
- **Etkilenen kod:** MVP-1.7 — `generations` tablosu, `users` tablosu, `training_samples` tablosu (yeni), `apps/api/app/workers/tasks/sft_curator.py` (yeni)
- **Etkilenen dokümanlar:**
  - `docs/legal/kvkk-aydinlatma.md` — yeni §X "Model İyileştirme Verileri" (Issue #564)
  - `docs/legal/tos.md`, `privacy-policy.md`, `ropa.md` — model improvement clause + ROPA aktivitesi
  - `docs/engineering/data-model.md` — `training_samples` tablosu (#567)
  - `docs/engineering/api-contracts.md` — user action endpoints + admin SFT endpoints (#566, #569)
  - `INDEX.md §4` — yeni locked decision (kullanıcı tarafından eklenecek — LLM yetkisi yok)

## İlişkiler

- **Bağlı varlıklar:** [[trendyol-llm-base]], [[deepseek]]
- **Bağlı kavramlar:** [[sft-data-pipeline]], [[provider-abstraction]], [[pii-redaction-mandatory]]
- **Bağlı topics:** [[llm-provider-strategy]] (Faz 4 sonrası bu topic Nodrat-AI'yı da kapsayacak)

## Açık sorular / TODO

- **Hugging Face dataset push (private):** İlk batch JSONL'i ne zaman HF Hub'a push edelim? Karar: pipeline 30 gün stabil çalıştıktan sonra (~Faz 0 sonu).
- **Eval golden set baseline:** DeepSeek'in mevcut golden test skoru kaç? Bu skor Nodrat-AI'nın geçmesi gereken eşik. Önce DeepSeek baseline run'ı `tests/llm-eval/`'a kayıtlı olmalı.
- ✅ **DAPT corpus lisans denetimi (RESOLVED 2026-05-10):** Avukat görüşü tamamlandı — Türkçe haber sitelerinden çekilen ham corpus'un fine-tune için kullanımı **engelsiz**. Mevcut [[twenty-five-word-quote-cap]] + [[pii-redaction-mandatory]] mitigation katmanları bu kullanım için yeterli; ek FSEK §35 öğretim amaçlı kapsamı geniş yorumlanabilir. [[risk-fsek-telif]] skoru bu karardan etkilenmez — Nodrat'ın kullanım modeli (training data, full text kullanıcıya gösterilmiyor) zaten en savunulabilir patern.
- **Marketing timeline:** "Nodrat AI" branding ne zaman lansman edilir? Faz 3 başarılı sonuçtan sonra mı, yoksa MVP-3 paid launch sırasında mı?

## Kaynaklar

- [Trendyol-LLM-7B-chat-v4.1.0 — Hugging Face](https://huggingface.co/Trendyol/Trendyol-LLM-7B-chat-v4.1.0) — base model card
- [Qwen 2 paper](https://qwenlm.github.io/blog/qwen2/) — base mimari
- [Apache 2.0 LICENSE metni](https://www.apache.org/licenses/LICENSE-2.0)
- [GitHub MVP-1.7 milestone](https://github.com/selmanays/nodrat/milestone/15)
- [Issues #563, #564, #566, #567, #568, #569](https://github.com/selmanays/nodrat/milestone/15)
- [[trendyol-llm-base]] — base entity
- [[sft-data-pipeline]] — Faz 0 mimarisi
