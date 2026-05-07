---
type: decision
title: "PII redaction zorunlu (LLM çağrısı öncesi)"
slug: "pii-redaction-mandatory"
status: "locked"
decided_on: "2026-05-01"
decided_by: "legal"
created: "2026-05-07"
updated: "2026-05-07"
sources:
  - "docs/strategy/risk-register.md§3.3"
  - "docs/strategy/risk-register.md§2.1"
  - "INDEX.md§4"
  - "docs/legal/opinion-integration.md"
  - "docs/engineering/prompt-contracts.md"
tags: ["locked-decision", "kvkk", "pii", "legal", "llm-safety"]
aliases: ["pii-redaction", "kvkk-pii", "pre-llm-redaction"]
---

# PII redaction zorunlu

> **Karar:** Her LLM çağrısı (generation, agenda card synthesis, summary, RAPTOR) öncesinde input metni PII redaction modülünden geçer. E-posta, telefon, TC kimlik, IP, account ID, kişisel mesleki/sağlık detayları redact edilir. Redact başarısız olursa çağrı bloklanır (insufficient_data fallback).
> **Durum:** locked. Avukat ön-görüşü gereği zorunlu (R-LGL-01 mitigation).
> **Tarih:** 2026-05-01 (risk-register.md v0.1 + opinion-integration.md ile lock).

## Bağlam

R-LGL-01 (KVKK ihlali, skor 9 🔴) için iki kanaldan risk var:

1. **Kullanıcı verisi** — register, generation history vb. KVKK uyum.
2. **Provider transferi** — LLM çağrısı sırasında metin DeepSeek/NIM/Anthropic gibi yurt dışı (US/HK) provider'lara gider. Eğer metinde PII varsa, bu **yurt dışı veri transferi** sayılır (R-LGL-11) ve ek açık rıza + SCC gerektirir.

Avukat ön-görüşünün önemli ek istekleriyle birlikte ([docs/legal/opinion-integration.md](../../docs/legal/opinion-integration.md)) PII redaction'ın **LLM çağrısından önce** yapılması zorunlu kılındı:

- Kazınan haber metnindeki rastgele kişisel veriler (köşe yazarı emaili, kullanıcı yorumu, vb.) provider'a gitmeden temizlenmeli.
- User-provided input (example prompts) da aynı redaction'dan geçmeli.

## Karar detayı

```text
1. INPUT katmanı:
   Kazınan article.clean_text → redact_pii() → article.redacted_text
   User prompt → redact_pii() → safe_prompt
   
2. REDACTION pipeline:
   a. Regex (e-posta, telefon TR formatları, TC kimlik 11-haneli)
   b. NER (NLP — kişi/kuruluş adları, sağlık verisi vb.)
   c. URL pattern (account ID, password reset link vb.)
   d. Whitelist (kamuya açık politik figürler vs. — opinion §X kararı)

3. OUTPUT katmanı:
   - Redacted text → LLM provider
   - Sentinel string ile yer tutucu (ör. [REDACTED_EMAIL])
   - Başarısız → çağrı block + INSUFFICIENT_DATA döner

4. AUDIT:
   - PII detect edilen alanların metadata'sı (count, type) provider_call_logs
   - Tekrar edenler alarm (kaynak içerik PII içeriyorsa publisher uyarısı)
```

Detay implementasyon: [docs/engineering/prompt-contracts.md §1.5](../../docs/engineering/prompt-contracts.md) (prompt-level), pipeline kodu `apps/api/app/core/pii_redaction.py`.

## Alternatifler ve neden reddedildi

| Alternatif | Artı | Eksi | Karar |
|---|---|---|---|
| PII redaction yok | Daha basit pipeline | KVKK ihlali risk, R-LGL-01 + R-LGL-11 yüksek | Reddedildi |
| Sadece user input redact | Kısmi koruma | Kazınan içerikteki PII yine provider'a gider | Reddedildi |
| LLM provider'a "do not log PII" yaz | Provider-side savunma | Hukuki garanti yok, provider DPA değişebilir | Reddedildi (yetersiz, ama opt-in flag eklenebilir) |
| Post-LLM redaction (output) | Output safety | Provider zaten input'u almış, KVKK ihlali olmuş | Reddedildi |
| Local LLM (vLLM) | Yurt dışı transfer yok | MVP-1'de kapsamı dışı, performans sınırlı | Reddedildi (MVP-1 için, future opt-in) |

## Sonuçlar

- **Etkilenen kavramlar:** [[risk-kvkk-violation]] (bu mitigation oraya bağlı), provider abstraction (her provider call redact_pii çağrısından sonra olmalı).
- **Etkilenen varlıklar:** [[deepseek-v3]], [[claude-haiku-4-5]], [[nim-bge-m3]] (embedding'de de uygulanır mı? — açık soru), [[celery-worker]] (`worker_rag` ve `worker_embedding` redact pipeline'ı kullanır).
- **Etkilenen kararlar:** [[mvp-1-scope-lock]] (PII redaction MVP-1'den itibaren aktif şart).
- **Etkilenen kod:** `apps/api/app/core/pii_redaction.py`, `apps/api/app/services/llm_router.py` (her çağrı öncesi pipeline çağrısı).
- **Etkilenen dokümanlar:**
  - [docs/legal/opinion-integration.md](../../docs/legal/opinion-integration.md) — avukat eklemesi
  - [docs/legal/ropa.md](../../docs/legal/ropa.md) — veri envanteri (PII processing aktivitesi)
  - [docs/engineering/prompt-contracts.md §1.5](../../docs/engineering/prompt-contracts.md) — prompt-level rules
  - [INDEX.md §4](../../INDEX.md) — locked decision listesi

## Geri alma maliyeti

Bu kararı kaldırmak: **mümkün değil**. KVKK uyumu için zorunlu. Sadece pipeline güncellenebilir (yeni regex pattern, NER model, vb.).

## Açık sorular / TODO

- **Embedding'de de redact?** Embedding model'i NIM'e gider (yurt dışı). Article chunk → embedding pipeline'ı PII redaction'dan geçiyor mu? `apps/api/app/workers/embedding.py` içinde redact_pii() çağrısı var mı doğrulanmalı.
- **NER model:** Hangi model kullanılıyor (spaCy TR? local? NIM provider mı?). Performance ↔ accuracy trade-off dokümante edilmeli.
- **Whitelist kararı:** Politik figürler "kamuya açık veri" olarak whitelist'te mi (örn. cumhurbaşkanı adı redact edilmemeli, sıradan vatandaş adı edilmeli)? Opinion-integration §X kararı varsa kontrol.
- **Audit dashboard:** PII detect rates publisher uyarısına dönüşüyor mu? Operasyonel runbook eksik.
- **VERBİS gönüllü kayıt:** 1K+ user sonrası VERBİS kayıt yapılır (R-LGL-01 mitigation'da geçiyor). PII processing aktivitesi VERBİS bildirilmeli (DPO ile koordineli).

## İlişkiler

- **Bağlı varlıklar:** [[risk-kvkk-violation]] (motivasyon)
- **Bağlı kavramlar:** [[risk-scoring]]
- **Bağlı kararlar:** [[mvp-1-scope-lock]]
- **Bağlı topics:** [[risk-catalog]]

## Kaynaklar

- [docs/strategy/risk-register.md §3.3 (R-LGL-01 detay)](../../docs/strategy/risk-register.md)
- [docs/strategy/risk-register.md §2.1](../../docs/strategy/risk-register.md) — risk skoru
- [docs/legal/opinion-integration.md](../../docs/legal/opinion-integration.md) — avukat ön-görüş eklemesi
- [docs/legal/compliance-brief.md §2 (KVKK)](../../docs/legal/compliance-brief.md) — full mitigation
- [docs/legal/ropa.md](../../docs/legal/ropa.md) — veri envanteri
- [docs/engineering/prompt-contracts.md §1.5](../../docs/engineering/prompt-contracts.md) — prompt-level rules
- [INDEX.md §4](../../INDEX.md) — Çekirdek kararlar
