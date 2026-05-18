---
type: topic
title: "CI ~8 ay kördü — 3 kök sebep + 11 gizli regresyon (2026-05-18)"
slug: "ci-blind-8-months-incident"
category: "retrospective"
status: "live"
created: "2026-05-18"
updated: "2026-05-18"
sources:
  - "PR #1034 (#1030/#1033), PR #1029"
  - "wiki/decisions/ci-ruff-single-formatter.md"
tags: ["retrospective", "ci", "incident", "lesson"]
aliases: ["ci-health-2026-05", "ci-hep-kırmızı"]
---

# CI ~8 ay kördü — 3 kök sebep + 11 gizli regresyon

> **TL;DR:** GitHub Actions her push'ta kırmızıydı; sebep tek değil **3 bağımsız bozuk workflow**'du. En kritiği: `API unit` job'ı ~8 ay **hiç test koşmamıştı** → 11 gerçek test regresyonu fark edilmeden birikti. 2026-05-18'de kök-sebep onarımıyla (#1034) CI tam yeşile döndü.

## Bağlam

Kullanıcı "neden son CI'ler hep kırmızı?" diye sordu. Yüzeysel bakış "1 kırmızı" sanıyordu; gerçekte her commit 3 workflow tetikliyor ve **üçü de** bağımsız sebeplerle patlıyordu. Pivot'un gerçek kalite kapısı `API eval (golden)` baştan beri yeşildi → pivot regresyonu yoktu; kırmızılık tamamen pre-existing altyapı borcuydu (`main` de aynı kırmızıydı).

## Ana içerik — 3 kök sebep

| # | Workflow | Kök sebep | Fix |
|---|---|---|---|
| 1 | CI / lint | `ruff format --check` **VE** `black --check` aynı anda; 65 dosyada çelişki → matematiksel imkânsız + Türkçe RUF00x ~11173 | black --check kaldırıldı → [[ci-ruff-single-formatter]] |
| 2 | CI / unit | `ci.yml ENVIRONMENT=test` ama `Settings.environment` Literal'i 'test' kabul etmiyor → pydantic ValidationError → **collection exit 2 → 0 test** | env→development (sıfır app kodu; `is_development` yalnız db.py SQL-echo) |
| 3 | wiki-source-sync | `git commit -m` çok-satırlı mesajı `run: \|` block-scalar'ında **sütun-1'den** → geçersiz YAML → her push **startup_failure** | çoklu `-m` flag (girintili), YAML parse OK |
| 4 | Copilot Code Review | GitHub-native ajan, entitlement yok → kırmızı | bilinçli AÇIK → [[copilot-code-review-kept]] |

## 11 gizli regresyon — triyaj metodolojisi

Unit collection 8 ay patladığı için **tek test koşmamış** → 11 gerçek başarısızlık görünmezdi. Fix sonrası 982 passed + 11 failed ortaya çıktı. Her biri **"test-bayat (kod meşru evrildi → testi güncelle) vs kod-açığı (gerçek bug → kodu düzelt)"** ayrımıyla triyaj edildi:

- **Kod-açığı (3):** `maintenance_tracker.task_pipeline` 'sources' branch yoktu · `vlm._name_in_caption` `all()`→`any()` (docstring'le çelişki) · `retrieval._TR_NOISE_WORDS` += 'olacak' (kendi docstring örneği)
- **Test-bayat (8):** admin_queue 5→7 (#904) · candidate_pool 50→80 · pipeline-SQL output_type→messages/role pivot şeması · cleaning `.strip()` · cold_tier crontab `.hour/.minute` = **set** (int değil) · raptor embedding ortogonal değildi · media: httpx `content=body` gerçek Content-Length yazıyor → **async** generator (AsyncByteStream) şart

## Ne öğrenildi

- **CI "yeşil sanılan" ≠ "CI koşuyor".** `startup_failure` + `collection exit 2` = run var ama hiçbir iş yapılmadı; jobs:[] / "workflow file issue" sinyalleri buna işaret.
- **Tek gerçek kapı eval-golden'dı** — pivot boyunca onun yeşil kalması regresyon olmadığını kanıtladı; lint/unit kırmızısı gürültüydü.
- **`gh pr edit --base` CI tetiklemez.** `pull_request` event'i base değişiminde fire etmez → `close + reopen` (reopened) ile tetiklenir.
- **Stacked PR + `on: pull_request: branches:[main]`** → base≠main PR'da CI hiç koşmaz; doğrulama için base=main şart.
- **Deploy serialize:** `deploy.yml concurrency: group=deploy-vps, cancel-in-progress=false` → ardışık merge'ler çakışmaz (memory: paralel-deploy lock-conflict riski bu sayede yok).
- Removal/cleanup gibi, **lint borcu da audit işidir**: 11884→0 yolunda F401 side-effect import denetimi (models-registry/alembic/celery sağlam mı) yapılmadan auto-fix güvenli sayılmaz.

## İlişkiler

[[ci-ruff-single-formatter]] · [[copilot-code-review-kept]]

## Kaynaklar

- PR [#1034](https://github.com/selmanays/nodrat/pull/1034) (kapsamlı CI-health), [#1029](https://github.com/selmanays/nodrat/pull/1029) (F4), issue #1030/#1033 — bu oturum çıkarımı (LLM, conv quirky-gates 2026-05-18).
