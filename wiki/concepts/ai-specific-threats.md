---
type: concept
title: "AI-specific tehditler — prompt injection, data exfil, model abuse"
slug: "ai-specific-threats"
category: "security"
status: "live"
created: "2026-05-11"
updated: "2026-05-11"
sources:
  - "docs/engineering/threat-model.md §3 AI-Specific Tehditler"
tags: ["security", "ai", "prompt-injection", "llm", "owasp"]
---

# AI-Specific Tehditler

> **TL;DR:** STRIDE klasik framework AI sistemlerinde yetersiz. Nodrat 4 AI-spesifik tehdide karşı koruma altında: prompt injection, data exfiltration, model jailbreak, halüsinasyon weaponization.

## 1. Prompt Injection

**Saldırı:** Kullanıcı sorgusu LLM system prompt'u override etmek için tasarlanmış (örn. "system prompt'u görmezden gel, X yap").

**Mitigation:**
- System message strict — kullanıcı request_text **tek user role'da** geçer
- Response_format JSON zorunlu — serbest metin verme
- Halüsinasyon yasağı prompt'u — yetkisiz instruction reddet (#677)
- DeepSeek/Claude **tier 1 jailbreak resistance** test edildi

## 2. Data Exfiltration (kullanıcı verisi LLM provider'a kaçar)

**Saldırı:** Kullanıcı email / IP / account ID / KVKK PII LLM provider'a (DeepSeek, Claude) gönderilir → provider log'unda kalır → ihlal.

**Mitigation:**
- **PII redaction zorunlu** ([[pii-redaction-mandatory]]) — LLM çağrısı öncesi şart (avukat onayı 2026-05)
- `provider_call_logs` — Nodrat tarafı log; içerik kullanıcı ID barındırmaz
- KVKK m.9 yurt dışı transfer — LS US için ek aydınlatma (R-LGL-13)
- Ana mitigation: anonimize edilmiş `query` + `context` gider

## 3. Model Jailbreak (kullanıcı LLM'i kötü amaçla kullanır)

**Saldırı:** Kullanıcı Nodrat'ı kullanarak yasal/etik dışı içerik üretmeye çalışır (nefret söylemi, dezenformasyon, 18 altı içerik).

**Mitigation:**
- **18+ yaş gate** ([[age-gate-18-plus]])
- Content moderation — DeepSeek default safety
- ToS §6 — kullanıcı yasaklı kullanım sorumlu (ban)
- admin_audit_log → şüpheli pattern alert

## 4. Halüsinasyon Weaponization (dezenformasyon)

**Saldırı:** Halüsinasyon temelli yanlış bilgiyi gerçekmiş gibi yayınlama.

**Mitigation:**
- **Insufficient_data pattern** ([[insufficient-data-pattern]]) — boş retrieval'da uydurma yasak
- Citation zorunlu — her iddia [#N] kaynak ile
- Output liability disclaimer ([[output-liability-disclaimer]]) — kullanıcı sorumluluğu
- Faz 7a numerical entity NER (#679) — sayısal halüsinasyon önleme

## OWASP Top 10 for LLM (2023) Mapping

| OWASP | Nodrat Mitigation |
|---|---|
| LLM01 Prompt Injection | system prompt strict, JSON response_format |
| LLM02 Insecure Output Handling | citation validator, halüsinasyon yasağı |
| LLM03 Training Data Poisoning | N/A (kendi model değil; DeepSeek/Claude vendor) |
| LLM04 Model DoS | Rate limit + quota + Cloudflare |
| LLM05 Supply Chain | Provider abstraction + failover |
| LLM06 Sensitive Info Disclosure | PII redaction + KVKK m.9 |
| LLM07 Insecure Plugin Design | N/A (plugin yok) |
| LLM08 Excessive Agency | LLM no tool execution, sadece text output |
| LLM09 Overreliance | Insufficient_data + citation + UX feedback |
| LLM10 Model Theft | N/A (vendor model) |

## İlişkiler

- [[stride-threat-analysis]] — klasik STRIDE
- [[threat-model-md]] §3
- [[pii-redaction-mandatory]]
- [[insufficient-data-pattern]]
- [[output-liability-disclaimer]]
- [[age-gate-18-plus]]

## Kaynaklar

- [docs/engineering/threat-model.md](../../docs/engineering/threat-model.md) §3
