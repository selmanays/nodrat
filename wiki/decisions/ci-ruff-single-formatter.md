---
type: decision
title: "CI tek formatter = ruff (black --check kaldırıldı)"
slug: "ci-ruff-single-formatter"
status: "locked"
decided_on: "2026-05-18"
decided_by: "tech"
created: "2026-05-18"
updated: "2026-05-18"
sources:
  - "PR #1034 (#1030/#1033)"
  - ".github/workflows/ci.yml"
  - "apps/api/pyproject.toml"
tags: ["locked-decision", "ci", "tooling"]
aliases: ["ruff-only", "black-check-kaldırıldı"]
---

# CI tek formatter = ruff (black --check kaldırıldı)

> **Karar:** API lint job'ında tek formatter ruff'tır; `black --check` adımı + `[tool.black]` + `black` dev-dep kaldırıldı. Türkçe/yapısal gerekçeli ruff ignore politikası eklendi.
> **Durum:** locked
> **Tarih:** 2026-05-18

## Bağlam

CI `API lint` job'ı **aynı anda** `ruff format --check` VE `black --check` koşuyordu. Bu iki formatter **65 dosyada** birbiriyle çelişiyor (biri istediği gibi formatlarsa diğeri patlıyor) → hiçbir kaynak hali ikisini birden geçemez → **lint job matematiksel olarak asla yeşil olamazdı**. Ek olarak ruff'ın `RUF001/002/003` (ambiguous-unicode) kuralı, bilerek Türkçe olan kod tabanında (`ı/ş/ç/ğ/ö/ü`) her docstring'de patlıyordu (~11173 ihlal). Bu, "[[ci-blind-8-months-incident|CI ~8 ay kırmızı]]" durumunun **en derin kök sebebiydi**.

## Alternatifler ve neden reddedildi

| Alternatif | Artı | Eksi | Karar |
|---|---|---|---|
| ruff tek formatter, black --check kaldır | Tek hızlı araç; ruff zaten ana toolchain | black alışkanlığı | **seçildi** |
| black tut, ruff format --check kaldır | — | ruff = ana linter, formatter de ruff olmalı; black yavaş | reddedildi |
| İkisini uyumlu konfigle | "iki kontrol" | 65-dosya çelişki sürekli kırılgan; bakım yükü | reddedildi |
| RUF00x'i dosya-dosya `# noqa` | granüler | ~11173 nokta = absürt churn | reddedildi (config-ignore) |

## Sonuçlar

- **Etkilenen:** `ci.yml` (black --check adımı silindi), `pyproject.toml` (`[tool.black]` + black dev-dep silindi; `ignore += E501,RUF001/002/003`; per-file-ignore `scripts→E402`, `retrieval.py→S608`, `tests→stil`), kod tabanı ilk kez `ruff format` uyumlu (~207 dosya).
- İlke: E501 = formatter'ın işi (uzun TR string bölünemez); S608 = kod-kontrollü SQL+bound-param FP sınıfı; bunlar "borç gizleme" değil **ilkesel** (gerçek-bug F-kuralları aktif kaldı).
- İlişki: [[ci-blind-8-months-incident]] · [[copilot-code-review-kept]]

## Geri alma maliyeti

> `ci.yml`'e `black --check` geri eklenirse 65-dosya ruff↔black çelişkisi geri döner, lint job tekrar kalıcı kırmızı olur. RUF00x ignore kaldırılırsa Türkçe kod tabanı yine ~11173 hata verir. Bu karar pratikte geri alınamaz (geri-alma = bilinen bozuk duruma dönüş).
