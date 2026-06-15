---
type: decision
title: "Robots geçici fetch hatası canlı kaynağı deaktive etmez"
slug: "robots-transient-vs-genuine-deactivation"
status: "locked"
decided_on: "2026-06-15"
decided_by: "tech"
created: "2026-06-15"
updated: "2026-06-15"
sources:
  - "docs/legal/scraping-policy.md§3.3"
  - "docs/engineering/architecture.md§3.3"
tags: ["locked-decision", "crawler", "robots", "source-health"]
aliases: ["robots transient vs genuine"]
---

# Robots geçici fetch hatası canlı kaynağı deaktive etmez

> **TL;DR:** Aktif bir haber kaynağı, robots.txt'in o an **çekilememesi** (network/timeout/5xx/4xx-forbidden → `report.fetched=False`) durumunda artık **otomatik kapatılmaz**. Yalnız robots başarıyla çekilip **gerçek bir Disallow** alındığında (`fetched=True` ama `base_url_allowed=False`) kaynak deaktive edilir. Geçici hatada `is_active` + `robots_txt_compliant` korunur, sağlık `yellow` işaretlenir. Locked 2026-06-15 (#1498). Zero-tolerance robots politikası **kaynak EKLEME** için aynen geçerli (fail-closed); bu karar yalnız **canlı kaynak** için transient/genuine ayrımıdır.

## Bağlam
2026-06-15'te "sabahtan beri 23 haber" şikâyeti incelendi. Kök neden: `_healthcheck_source_async` (6 saatlik beat) ve crawl task'ları, robots.txt geçici çekilemediğinde bunu kalıcı engelle eşitleyip aktif kaynağı **sessizce** kapatıyordu (audit yok, yalnız `logger.warning`); sonraki healthcheck robots bayrağını yeşile çevirip kanıtı siliyordu. Sonuç: 27 kaynaktan 24'ü pasife düşmüş, günlük hacim ~150→~25. Detay: [[source-silent-deactivation-incident-2026-06]].

`fetch_robots` zaten geçici (`fetched=False`) ile gerçek-disallow'u ayırt ediyordu (`RobotsFetchError` tipi mevcuttu ama healthcheck karar noktasında kullanılmıyordu). Fail-closed mantığı **yeni kaynak doğrulamak** için doğru, ama daha önce vetlenmiş **canlı** kaynağı anlık ağ takılmasında öldürmek yanlıştı.

## Alternatifler ve neden reddedildi
| Alternatif | Neden reddedildi |
|---|---|
| Mevcut davranış (transient = disallow) | Anlık ağ hatası kalıcı veri kaybı (kaynak sessiz ölür) yaratıyor — incident'in kök nedeni |
| N ardışık transient sonrası kapat | Gereksiz karmaşıklık; transient asla "engel" değil, retry'da kendini çözer |
| Hiç auto-deactivate etme | Gerçek robots disallow'a uyum (legal zero-tolerance) bırakılamaz |

## Sonuçlar
- Healthcheck + crawl yalnız `fetched=True ∧ ¬base_url_allowed` → deaktive.
- Geçici hatada `is_active`/`robots_txt_compliant` dokunulmaz; health `yellow`.
- Gerçek auto-deactivation artık görünür iz bırakır: `FailedJob(job_type='source.auto_deactivated', severity='warning')`. `admin_audit_log.actor_id` NOT NULL olduğundan sistem-aktör oraya yazamaz → FailedJob (DLQ) kullanıldı. Bkz. [[queue-management]].
- Kurtarma: `reactivate_dormant_sources` (admin-tetikli, robots re-check'li, idempotent) task'ı eklendi.

## Geri alma maliyeti
Düşük — saf kod davranışı (schema/migration yok). Ama geri almak incident'i geri getirir; yapılmamalı.

## İlişkiler
- [[source-silent-deactivation-incident-2026-06]] — incident retrospektifi
- [[generic-extractor-cascade]] — quarantine/discarded status modeli (komşu kaynak-sağlık kararı)
- [[extraction-confidence-telemetry]] — kaynak sağlık telemetrisi
- [[queue-management]] — FailedJob/DLQ severity (auto-deactivation izi buraya yazılır)

## Kaynaklar
- [docs/legal/scraping-policy.md](../../docs/legal/scraping-policy.md) §3.3 (robots uyumu)
- [docs/engineering/architecture.md](../../docs/engineering/architecture.md) §3.3 (source health / crawl)
- GitHub: [#1498](https://github.com/selmanays/nodrat/issues/1498) / [PR #1499](https://github.com/selmanays/nodrat/pull/1499)
- Kod: `apps/api/app/modules/sources/tasks/sources.py` + `apps/api/app/shared/crawl/robots.py`
