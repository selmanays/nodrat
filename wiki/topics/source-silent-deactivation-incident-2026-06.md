---
type: topic
title: "Kaynakların sessiz auto-deactivation incident'ı (2026-06)"
slug: "source-silent-deactivation-incident-2026-06"
category: "retrospective"
status: "live"
created: "2026-06-15"
updated: "2026-06-15"
sources:
  - "docs/legal/scraping-policy.md"
  - "docs/engineering/architecture.md"
tags: ["incident", "crawler", "robots", "deploy", "ci", "retrospective"]
aliases: ["source silent deactivation", "23 haber incident"]
---

# Kaynakların sessiz auto-deactivation incident'ı (2026-06)

> **TL;DR:** "Sabahtan beri sadece 23 haber" şikâyeti gerçekti — ama crawler arızası değil: 27 kaynaktan 24'ü **sessizce** pasife düşmüştü (yalnız 2-3 musluk açık). Kök neden bir yazılım hatasıydı: robots.txt'in **geçici** çekilememesi kalıcı engelle eşitlenip canlı kaynağı kapatıyordu (audit yok); sonraki healthcheck robots bayrağını healleyip **kanıtı siliyordu**. Fix (#1498), alakasız CI-engeli (#1502) ve deploy-keepalive (#1510) ile çözüldü; 23 kaynak güvenle reaktive edildi → 20 dk'da 23 kaynaktan 829 haber aktı.

## Bağlam
2026-06-15: kullanıcı "bir sürü kaynağımız var ama sabahtan beri 23 haber geldi, sorun mu var?" diye sordu. Tanı: infra sağlıklı (13 container up, pipeline temiz — 14044 cleaned, 0 takılı article). Gerçek sorun **aktif kaynak sayısının çökmesi** (3/27 aktif). Trend: 1-9 Haz ~113-174/gün (4-5 kaynak) → 10 Haz'dan ~20-50/gün (2-3 kaynak); düşüş Hürriyet'in (3403 makale, en büyük kaynaklardan) 9 Haz'da pasife düşmesiyle çakışıyor.

## Ana içerik (zincir)
| Aşama | Bulgu / aksiyon |
|---|---|
| Tanı | "23" doğru; sebep crawler/işleme değil — 24 kaynak `is_active=false` |
| Kök neden | robots geçici fetch hatası → kalıcı engel sanılıp auto-deactivate; audit yok; sonraki healthcheck bayrağı healleyip izi siliyor → [[robots-transient-vs-genuine-deactivation]] |
| Fix (#1498/#1499) | transient ≠ disallow; gerçek auto-deactivation `FailedJob` izi bırakır; +11 test |
| CI engeli (#1501/#1502) | alakasız: CI `pip install` gitignored uv.lock'u yok sayıyor → starlette 1.1+ `_IncludedRouter` 14 router testini kırdı → fastapi/starlette üst-sınır pin |
| Deploy engeli (#1509/#1510) | uzun web build'de runner→VPS SSH idle-kopması (exit 255) → deploy.yml'e SSH keepalive |
| Kurtarma | `reactivate_dormant_sources` (admin-tetikli, robots re-check'li, idempotent); dry-run → 23/23 uygun → gerçek run → **26/26 RSS aktif** |
| Doğrulama | 20 dk'da 23 kaynaktan **829 haber** (ilk crawl backlog dalgası; dedup ile normale oturur) |

## Çıkarımlar (dersler)
- **Fail-closed bağlama duyarlı olmalı:** kaynak *eklerken* doğru, canlı kaynağı transient hatada öldürmek yanlış.
- **Sessiz state-değişimi tehlikeli:** auto-deactivation iz/audit bırakmadığı + healthcheck bayrağı "healledi" için aylarca fark edilmedi. Artık `FailedJob` izi var; "kaynak X gündür haber getirmiyor" proaktif alarmı hâlâ yok (future).
- **CI determinizmi:** `pip install -e .` gitignored uv.lock'u yok sayar → sınırsız dep'ler upstream release'le sessizce CI'ı kırar ([[ci-blind-8-months-incident]] komşusu).
- **Deploy kırılganlığı:** uzun (~10 dk) web build SSH oturumunu koparabiliyor (exit 255); keepalive gerekti.
- **`admin_audit_log.actor_id` NOT NULL** → sistem-aktörlü olaylar `FailedJob`'a yazılır ([[queue-management]]).

## İlişkiler
- [[robots-transient-vs-genuine-deactivation]] — locked karar (bu incident'in fix kuralı)
- [[extraction-confidence-telemetry]] · [[generic-extractor-cascade]] · [[queue-management]] — kaynak sağlık + DLQ
- [[deploy-schema-drift-hardening]] — deploy.yml hardening komşusu (keepalive aynı dosya)
- [[ci-ruff-single-formatter]] · [[ci-blind-8-months-incident]] — CI kırılganlık komşuları

## Açık sorular / TODO
- "Kaynak X gündür sessiz / otomatik kapandı" proaktif alarm (henüz yok).
- CI/deploy'u uv.lock'tan kurmak (kalıcı determinizm) — ayrı iş.

## Kaynaklar
- GitHub: [#1498](https://github.com/selmanays/nodrat/issues/1498)/[#1499](https://github.com/selmanays/nodrat/pull/1499) · [#1501](https://github.com/selmanays/nodrat/issues/1501)/[#1502](https://github.com/selmanays/nodrat/pull/1502) · [#1509](https://github.com/selmanays/nodrat/issues/1509)/[#1510](https://github.com/selmanays/nodrat/pull/1510)
- [docs/legal/scraping-policy.md](../../docs/legal/scraping-policy.md) · [docs/engineering/architecture.md](../../docs/engineering/architecture.md)
