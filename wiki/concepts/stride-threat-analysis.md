---
type: concept
title: "STRIDE tehdit analizi (Nodrat komponent bazlı)"
slug: "stride-threat-analysis"
category: "security"
status: "live"
created: "2026-05-11"
updated: "2026-05-11"
sources:
  - "docs/engineering/threat-model.md §2 STRIDE Komponent Bazlı"
  - "docs/engineering/threat-model.md §1 Asset Envanteri"
tags: ["security", "stride", "threat-model", "engineering"]
---

# STRIDE Tehdit Analizi

> **TL;DR:** STRIDE = Spoofing / Tampering / Repudiation / Information disclosure / Denial of Service / Elevation of Privilege. Nodrat komponentleri için her komponente STRIDE haritalanmış. Asset envanteri threat-model.md §1; mitigation §2.

## STRIDE Açılım

| Harf | Tehdit | Anti-saldırı |
|---|---|---|
| **S**poofing | Kimlik sahteciliği | Auth (JWT + Argon2id), MFA, 2FA Faz 6 |
| **T**ampering | Veri/kod değişikliği | TLS, signature, audit log |
| **R**epudiation | İnkar | admin_audit_log, log immutability |
| **I**nformation disclosure | Veri sızıntısı | TLS, encryption-at-rest, RLS, KVKK |
| **D**enial of Service | Hizmet engeli | Rate limit, quota, Cloudflare, autoscale |
| **E**levation of Privilege | Yetki yükseltme | Role check, principle of least privilege |

## Nodrat Komponentleri (asset envanteri özet)

| Komponent | Risk yüksek STRIDE | Mitigation |
|---|---|---|
| **API (FastAPI)** | I, D, E | Bearer auth, rate limit, role check (require_admin) |
| **Web (Next.js)** | S, I | CSP, secure cookies, CSRF token |
| **DB (Postgres + pgvector)** | T, I | TLS, encryption-at-rest, RLS, daily backup |
| **Redis** | T, D | AUTH password, internal-only network |
| **MinIO** | I, T | Presigned URL TTL, bucket policy private default |
| **Workers (Celery)** | T, R | Idempotency, retry + dead letter, audit log |
| **Provider (DeepSeek)** | I (output sızıntı) | PII redaction zorunlu öncesi (#pii-redaction-mandatory) |
| **Caddy reverse proxy** | D, I | TLS termination, IP allowlist admin, rate limit |

## Detaylı Mitigation (threat-model.md §2)

Tablo çok geniş (15+ row, her komponent için STRIDE matrisi). Anahtar pattern'ler:

1. **Auth zinciri:** JWT 15dk + refresh 30g + Argon2id (S+E mitigation)
2. **PII redaction zorunlu:** LLM provider'a kullanıcı kişisel verisi gitmez (I mitigation) — [[pii-redaction-mandatory]]
3. **Rate limit + quota:** D mitigation; user_id × endpoint × pencere
4. **Audit log immutable:** admin_audit_log row INSERT-only (R mitigation)
5. **Backup encrypted:** Contabo Object Storage S3-comp, AES-256 (I, T mitigation)

## Production Status

- ✅ Tüm 6 STRIDE kategori için en az bir mitigation production'da
- ✅ Pre-launch security checklist ([[pre-launch-security-checklist]])
- ⏳ Faz 6: 2FA TOTP eklemesi (S mitigation güçlendirme)

## İlişkiler

- [[threat-model-md]] §2
- [[ai-specific-threats]] — STRIDE'a ek AI tehditleri
- [[pii-redaction-mandatory]]
- [[pre-launch-security-checklist]]
- [[risk-kvkk-violation]]

## Kaynaklar

- [docs/engineering/threat-model.md](../../docs/engineering/threat-model.md) §2
