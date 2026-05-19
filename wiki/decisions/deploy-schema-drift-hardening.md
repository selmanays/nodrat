---
type: decision
title: "Deploy schema-drift hardening — current==head assert + api force-recreate"
slug: "deploy-schema-drift-hardening"
status: "locked"
decided_on: "2026-05-19"
decided_by: "tech"
created: "2026-05-19"
updated: "2026-05-19"
sources:
  - "PR #1047 (v1 — current==head assert), #1054 (v2 — force-recreate kör-nokta)"
  - ".github/workflows/deploy.yml (Alembic migrate + verify at head)"
tags: ["locked-decision", "deploy", "ci-cd", "incident", "infrastructure"]
aliases: ["schema-drift", "deploy-hardening", "alembic-assert", "force-recreate"]
---

# Deploy schema-drift hardening — current==head assert + api force-recreate

> **Karar:** `deploy.yml` migration adımı, `alembic upgrade head` sonrası **`alembic current == alembic heads`** assert eder (eşit değilse `exit 1` → deploy LOUD fail). Ek olarak alembic ÖNCESİ **api container'ı `--force-recreate --no-deps`** ile zorla yenilenir (assert'in anlamlı olması için).
> **Durum:** locked
> **Tarih:** 2026-05-19

## Bağlam (incident)

Prod chat 500 verdi: `column messages.effective_query does not exist`. Kök: `deploy.yml` `alembic upgrade head` adımı şemayı UYGULAMADAN "başarılı" geçti → prod `20260518_0200`'de kaldı. `/health` 200 olduğu için smoke yakalamadı. Manuel `alembic upgrade head` ile kurtarıldı. Kullanıcı: "sistem nasıl bozuldu düzgünce araştır, kalıcı çöz."

## v1 — current==head assert (#1047)

`upgrade head` sonrası `alembic current` ile `alembic heads` ilk-token karşılaştırılır; eşit değil/boşsa `exit 1`. Genel (tek-kolon hardcode YOK), tüm gelecek migration'ları kapsar. `set -euo pipefail` + explicit exit.

## v2 — force-recreate (#1054), KANITLI kör-nokta

Faz 7 ([[faz7-chat-research-rename]]) deploy'unda v1 **tekrar sessizce geçti**: `docker compose up -d` bazen api'yi **eski container'da korur** (image-digest/timing). `docker compose exec api alembic` ESKİ migration dosyalarına bakar → `heads`=ESKİ → `current(ESKİ)==heads(ESKİ)` → assert sessizce geçer; yeni container sonra gelir ama alembic re-run edilmez. Prod `20260519_0100` uygulanmadı; manuel kurtarıldı.

**Fix:** alembic ÖNCESİ `docker compose up -d --force-recreate --no-deps api` → exec daima YENİ kod/migration dosyalarına vurur → `current==heads` assert'i ANLAMLI (heads = gerçek yeni). `--no-deps` postgres/redis korur (veri güvenliği).

## Alternatifler ve neden reddedildi

| Alternatif | Neden reddedildi |
|---|---|
| Yalnız smoke `/health` | İncident kanıtı: schema bozuk + /health 200 (effective_query'ye dokunmaz) |
| Tek kolon existence check | Rotlar; gelecek migration'ları kapsamaz — assert genel olmalı |
| v1 tek başına (force-recreate'siz) | Kör-nokta KANITLI: stale container → assert false-pass (Faz 7'de tekrar etti) |
| Authed-smoke | CI'da servis-credential yönetimi; alembic-head assert daha sağlam + credential-suz |

## Sonuç

- Sessiz schema-drift artık **yapısal olarak imkânsız**: stale container olsa bile force-recreate → yeni dosyalar → assert gerçek head'i görür → uyumsuzsa LOUD fail + failure-notification.
- Faz 7 deploy'u (manuel kurtarmadan SONRA) bu dersle kalıcılaştı; v2-merge deploy'u force-recreate yolunu canlı doğrular (prod zaten head → no-op, geçer).

> 🔧 **2026-05-19 ops gözlem — GitHub Actions kredisi geri gelmiş (auto-deploy işlevsel):** `actions_credits_exhausted` varsayımı (2026-05-09'dan beri "her deploy manuel SSH") **bu seansta çürütüldü**: #1058 ve #1059 merge'lerinde hem **CI** hem **Deploy to VPS** workflow'u otomatik koştu ve **success** verdi (v2-hardened: rsync → build → `up -d --force-recreate --no-deps api` → `alembic upgrade head` → `current==heads` assert → `/health` 200 smoke). Bağımsız SSH doğrulaması: `alembic current==head=20260519_0100`, kod-marker'lar mevcut, `/health` 200. Sonuç: auto-deploy artık güvenilir; manuel SSH yalnız acil-kurtarma fallback'i (runner allocation fail durumunda). Bu sayfanın hardening'i auto-deploy yolunda canlı çalışır.

## İlişkiler

- [[faz7-chat-research-rename]] — kör-noktayı tetikleyen migration
- [[pivot-editorial-research-engine]] — pivot deploy güvenilirliği

## Geri alma maliyeti

> Düşük: yalnız `deploy.yml` (tek `git revert`). Geri-alma deploy güvenilirliğini DÜŞÜRÜR — önerilmez. Assert mantığı v1↔v2 korunur.

## Kaynaklar

- [.github/workflows/deploy.yml](.github/workflows/deploy.yml) — "Alembic migrate + verify at head"
- PR #1047 (v1 assert), #1054 (v2 force-recreate)
