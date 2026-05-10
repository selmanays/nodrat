---
type: decision
title: "DeepSeek default LLM"
slug: "deepseek-default-llm"
status: "locked"
decided_on: "2026-05-01"
decided_by: "tech"
created: "2026-05-07"
updated: "2026-05-08"
sources:
  - "apps/api/app/providers/deepseek.py§DEEPSEEK_CHAT_DEFAULT_MODEL"
  - "docs/engineering/architecture.md§0"
  - "docs/engineering/architecture.md§4.2"
  - "docs/engineering/architecture.md§4.3"
  - "INDEX.md§4"
  - "README.md§Çekirdek kararlar"
  - "PR #163 — DeepSeek native API chat provider"
  - "PR #361 — model adı 'deepseek-chat' → 'deepseek-v4-flash'"
  - "PR #378 — smoke feedback fixes"
  - "PR #379 — v4-flash thinking-disabled hotfix"
tags: ["locked-decision", "llm", "provider", "cost"]
aliases: ["deepseek-default", "default-llm-decision", "deepseek-v4-flash-default"]
---

# DeepSeek default LLM

> **Karar:** Free, Starter ve Trial tier'larındaki tüm LLM çağrıları (generation, agenda card, summary) varsayılan olarak DeepSeek native API üzerinden `deepseek-v4-flash` (thinking-disabled) ile yapılır. NIM endpoint geriye dönük fallback rolündedir.
> **Durum:** locked
> **Tarih:** 2026-05-01 (orijinal karar — DeepSeek varsayılan LLM, architecture.md v0.1). 2026-04-29 (#361) model adı `deepseek-chat` → `deepseek-v4-flash`. 2026-05-07 (#379) thinking-disabled hotfix.

## Bağlam

LLM cost-per-1M-token Nodrat'ın unit economics'inin en büyük kalemi. MVP-1 hedef margin ≥%75 (paid tier'da) için ucuz default şart. Aynı zamanda Türkçe kalitesi, latency, ve provider kilitlenmesi (vendor lock-in) endişesi var.

Karar üç problemi çözüyor:

1. **Cost** — DeepSeek endüstrideki en ucuz frontier-class model ($0.27 input cache-miss / $0.07 input cache-hit / $1.10 output per 1M token). Margin hedefini destekler.
2. **Türkçe** — DeepSeek Türkçe'de iyi performans veriyor (eval'lere göre — [docs/engineering/prompt-contracts.md](../../docs/engineering/prompt-contracts.md) §eval).
3. **Native API tercihi** — Native DeepSeek API ([api.deepseek.com/v1](https://api.deepseek.com/v1)) NIM endpoint'inden daha düşük gecikme + güncel model varyantlarına direkt erişim sağlıyor. NIM fallback rolünde tutulur (`DEEPSEEK_API_KEY` yoksa devreye girer).

## Alternatifler ve neden (red/kabul)

| Alternatif | Artı | Eksi | Karar |
|---|---|---|---|
| GPT-4o-mini | Olgun, Türkçe iyi | Cost ~3x DeepSeek, OpenAI vendor lock | Reddedildi (sadece son fallback) |
| Claude Haiku 4.5 default | En iyi Türkçe + güvenlik | Cost 7-10x DeepSeek | Premium tier'a (Pro+) bırakıldı — bkz. [[claude-haiku-premium-llm]] |
| Native DeepSeek API | Resmi sağlayıcı, düşük latency, güncel model varyantları | Ek API key | **Kabul edildi (#163, 2026-04-XX)** — primary provider |
| NIM endpoint (DeepSeek üzerinden) | Embedding ile aynı API key | NIM model isimleri gecikmeli güncellenir | Fallback (DEEPSEEK_API_KEY yoksa) |
| Llama 3.3 70B (Together/Replicate) | Açık model | Türkçe daha zayıf, latency | Reddedildi |
| Mistral Large 3 (NIM) | NIM'de free | Cost-perf benchmark'ta DeepSeek üstün | Reddedildi |

## Sonuçlar

- **Etkilenen varlıklar:** [[deepseek]], [[local-bge-m3]] (production primary embedding)
- **Etkilenen kavramlar:** [[provider-abstraction]] (DeepSeekProvider adapter; NIM fallback)
- **Etkilenen topics:** [[llm-provider-strategy]]
- **Etkilenen kod:** [apps/api/app/providers/deepseek.py](../../apps/api/app/providers/deepseek.py) (`DeepSeekProvider`, `DEEPSEEK_CHAT_DEFAULT_MODEL = "deepseek-v4-flash"`). Registry routing name `deepseek_v3` korunmuş — generation_log backward-compat (yeni rows da `deepseek_v3` ile etiketleniyor).
- **Etkilenen dokümanlar:** [docs/strategy/unit-economics.md](../../docs/strategy/unit-economics.md) §4 (cost-per-generation), [docs/strategy/pricing-strategy.md](../../docs/strategy/pricing-strategy.md) (tier yapısı), [docs/engineering/prompt-contracts.md](../../docs/engineering/prompt-contracts.md) (model-specific tuning).

## Geri alma maliyeti

Bu karar değiştirilirse:

1. **Cost re-modelling.** Margin hesabı sıfırdan: yeni provider $/1M token × token bütçesi × free user başına.
2. **Provider adapter.** Yeni `ModelProvider` implementasyonu (eğer DeepSeek native + NIM dışıysa).
3. **Eval re-baseline.** [docs/engineering/prompt-contracts.md](../../docs/engineering/prompt-contracts.md) §eval — yeni model için golden test set yeniden koşulur, halü < %2 ve citation %100 hedeflerinde regresyon kontrol edilir.
4. **Pricing tier güncellemesi.** Eğer cost önemli ölçüde artarsa tier fiyatları (249/749/2499 TL) revize gerekebilir.
5. **Tüm prompt'lar.** Model-specific tone/format değişikliği gerekirse prompt-contracts re-tune.

Tahmini değişiklik süresi: 2-4 hafta (eval + tuning dahil).

## Model varyantları ve operasyonel notlar

**Production default (2026-05-08 itibarıyla):**

- Model: `deepseek-v4-flash` (DeepSeek native API)
- Thinking mode: **disabled** (#379) — payload'da `"thinking": {"type": "disabled"}` flag'i ile non-thinking mode'a zorlanır. Aksi halde `response.content` boş, `reasoning_content` dolu geliyor → output parsing kırılıyor. Bkz. [api-docs.deepseek.com/guides/thinking_mode](https://api-docs.deepseek.com/guides/thinking_mode).
- Eski model adı `deepseek-chat` (`v3.1-terminus`) sunucu tarafında redirect ediyor; explicit `deepseek-v4-flash` kullanımı audit/log netliği için tercih edildi (#361).
- Pricing: $0.27 input cache-miss / $0.07 input cache-hit / $1.10 output per 1M token. **2026-05-31 23:59 UTC'a kadar %75 kampanya indirimi aktif** (`settings.deepseek_campaign_discount`).

**Migration timeline:**

- 2026-05-01 — orijinal karar: DeepSeek varsayılan, NIM üzerinden `deepseek-v3.1-terminus` (architecture.md v0.1).
- 2026-04-29 — #361: model adı `deepseek-chat` → `deepseek-v4-flash`.
- 2026-04-XX — #163 (PR-A): DeepSeek native API chat provider eklendi, NIM fallback'e indi.
- 2026-05-06 — #378: smoke feedback fixes (UI polish + model field düzeltme).
- 2026-05-07 — #379: thinking-disabled hotfix.

**Backward-compat:** Registry routing name `deepseek_v3` korundu — `generation_log.provider_name` değişmedi, eski satırlar provider değişmiş gibi görünmüyor. Geçişten önceki ve sonraki tüm satırlar `deepseek_v3` etiketli.

Default model kararı kod düzeyinde [apps/api/app/providers/deepseek.py:61](../../apps/api/app/providers/deepseek.py)'de tutulur. **Admin paneli üzerinden runtime tunable** ([admin_settings.py:234](../../apps/api/app/api/admin_settings.py:234) `llm.deepseek_chat_model` setting; seçenekler: `deepseek-v4-flash`, `deepseek-reasoner`, `deepseek-coder`). MVP-1.2 settings panel kapsamı içinde — `app_settings` tablosu + `SettingsStore` singleton runtime override eder; `config.py` default'u sadece DB row yoksa fallback.

## Uzun vade rolü — SFT eğitim verisi kaynağı

[[own-slm-strategy]] (2026-05-10 locked) gereği DeepSeek output'ları MVP-1.7 ([[sft-data-pipeline]]) ile biriktirilen `training_samples` tablosunda Nodrat'ın kendi domain-spesifik Türkçe SLM'inin ([[trendyol-llm-base]] üstüne) eğitim verisi olarak kullanılır. Bu, DeepSeek'in **default LLM rolünü etkilemez** — Faz 4'te Nodrat-AI Free tier'a deploy edildikten sonra DeepSeek "premium fallback" veya "Pro tier baseline" rolüne geçebilir; karar eval gate skoruna bağlı.

## İlişkiler

- **Bağlı varlıklar:** [[deepseek]] (eski slug `deepseek-v3` aliases içinde, registry name `deepseek_v3` backward-compat için kod tabanında korundu)
- **Bağlı kavramlar:** [[provider-abstraction]], [[sft-data-pipeline]]
- **Bağlı topics:** [[llm-provider-strategy]]
- **İlgili kararlar:** [[claude-haiku-premium-llm]] (premium tier eşdeğeri), [[own-slm-strategy]] (DeepSeek output'larından SFT — uzun vade)

## Kaynaklar

- [apps/api/app/providers/deepseek.py](../../apps/api/app/providers/deepseek.py) §`DEEPSEEK_CHAT_DEFAULT_MODEL` — production default model + thinking-disabled comment
- [docs/engineering/architecture.md §0](../../docs/engineering/architecture.md) — yönetici özeti, LLM stack (v0.2)
- [docs/engineering/architecture.md §4.2](../../docs/engineering/architecture.md) — adapter listesi: DeepSeekProvider primary, NimChatProvider fallback (#405)
- [docs/engineering/architecture.md §4.3](../../docs/engineering/architecture.md) — tier-based routing pseudocode `deepseek-v4-flash` (#405)
- [INDEX.md §4 (Çekirdek kararlar — locked)](../../INDEX.md)
- [README.md (Çekirdek kararlar)](../../README.md)
- PR #163 — DeepSeek native API chat provider (PR-A)
- PR #361 — `deepseek-chat` → `deepseek-v4-flash` model adı düzeltmesi
- PR #378 — smoke feedback fixes (DeepSeek model + UI polish)
- PR #379 — v4-flash thinking-disabled hotfix
