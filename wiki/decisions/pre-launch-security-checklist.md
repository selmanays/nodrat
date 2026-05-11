---
type: decision
title: "Pre-launch security checklist — MVP-1 production go/no-go"
slug: "pre-launch-security-checklist"
category: "security"
status: "locked"
created: "2026-05-11"
updated: "2026-05-11"
sources:
  - "docs/engineering/threat-model.md §7 Pre-Launch Security Checklist"
tags: ["security", "checklist", "production", "go-no-go", "mvp-1"]
---

# Pre-launch Security Checklist

> **TL;DR:** Nodrat'ın production'a açılması için **zorunlu 15 madde** checklist. Threat-model.md §7'de detaylı, INDEX.md §4 locked decision. Tüm maddeler ✅ olmadan launch yok.

## Locked Karar — 15 Madde

```text
✅ 1. TLS hard-enforce (HTTP → HTTPS redirect)
✅ 2. Cloudflare proxied (Origin CA + Full strict)
✅ 3. JWT 15dk + refresh 30g rotation
✅ 4. Argon2id password hash (bcrypt değil)
✅ 5. KVKK Aydınlatma + Privacy Policy yayınlanmış
✅ 6. ROPA güncel + DPO atanmış
✅ 7. Backup günlük şifreli (Contabo Object Storage S3-comp encrypted, AES-256)
✅ 8. Restore drill aylık (Risk Register R-OPS-03)
✅ 9. Rate limit per IP + per user + per endpoint
✅ 10. PII redaction zorunlu (LLM çağrısı öncesi) ([[pii-redaction-mandatory]])
✅ 11. admin_audit_log INSERT-only trigger
✅ 12. Robots.txt sıfır tolerans + User-Agent etiketi
✅ 13. Paywall hard ban + 25 kelime cap (FSEK)
✅ 14. 18+ yaş gate ([[age-gate-18-plus]])
✅ 15. Output liability disclaimer ToS §6+§10 ([[output-liability-disclaimer]])
```

## Audit Trail

Her madde için **tarih damgalı kabul kaydı** (admin_audit_log):

- Maddenin sorumlu kişisi (DPO, Security Officer, Tech Lead)
- Doğrulama tarihi + sonuç (PASS/FAIL/MITIGATED)
- Risk register linki

## Re-evaluation

Yıllık DPO review + her major release (MVP-1 → MVP-2 → vs.) tekrar audit.

## Production Status

✅ **MVP-1 launched** — tüm 15 madde PASS (2026-Q1 audit).

## İlişkiler

- [[threat-model-md]] §7
- [[stride-threat-analysis]]
- [[ai-specific-threats]]
- [[incident-response-md]]
- [[risk-kvkk-violation]]
- [[pii-redaction-mandatory]]
- [[age-gate-18-plus]]
- [[output-liability-disclaimer]]

## Kaynaklar

- [docs/engineering/threat-model.md](../../docs/engineering/threat-model.md) §7
- INDEX.md §4 (locked decisions)
