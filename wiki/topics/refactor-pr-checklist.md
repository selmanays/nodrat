---
type: topic
title: Refactor PR Checklist (Behavior-Preserving Discipline)
slug: refactor-pr-checklist
category: playbook
status: live
created: 2026-05-20
updated: 2026-05-20
sources:
  - .github/PULL_REQUEST_TEMPLATE/refactor.md
  - wiki/decisions/no-internal-backcompat-aliases.md
  - wiki/decisions/god-file-facade-first.md
tags:
  - refactor
  - checklist
  - modular-monolith
  - playbook
aliases:
  - refactor-pr
  - behavior-preserving-checklist
---

# Refactor PR Checklist (Behavior-Preserving Discipline)

> **TL;DR:** Her modüler monolit refactor PR'ı bu checklist'i geçer. **Refactor = davranış değişmez.** Davranış değişikliği gerekiyorsa ayrı issue + ayrı PR. Bu sayfa PR template'inin (`.github/PULL_REQUEST_TEMPLATE/refactor.md`) gerekçesini ve detayını verir.

## Bağlam

Refactor PR'ları "küçük + geri alınabilir + davranış-koruyan" olmadığında: sessiz regresyon riski (god-file dersleri), alias-debt birikimi (backward-compat tuzağı), docs/wiki sync atlanması (paralel worktree karmaşası). Bu checklist üç tuzağı önler.

## Ana içerik — Checklist

### 1. Linked issue

- [ ] PR description'da `Closes #<issue>` veya `Part of #<issue>` var.
- [ ] Issue master plan'a (`wiki/plans/modular-monolith-transition-master-plan.md`) link veriyor.
- [ ] Issue ilgili phase (P0-P8) altında.

### 2. Scope = Refactor

- [ ] PR template'inde "Refactor (behavior-preserving)" işaretli.
- [ ] Feature, fix veya davranış değişikliği **YOK**. Varsa ayrı PR.
- [ ] Tek modülü dokunuyor (5+ modül = big-bang anti-pattern #1).

### 3. Behavior-preserving guarantee

- [ ] Application davranışı değişmedi.
- [ ] URL sözleşmeleri (prefix + endpoint isimleri) değişmedi.
- [ ] Celery task name'leri değişmedi (string-bound; #17 anti-pattern).
- [ ] DB schema değişmedi (Alembic migration refactor PR'ında **yok**).
- [ ] LLM prompt content değişmedi (RC3-B v2 marker-detect dahil).
- [ ] Runtime config key'leri + Redis pub/sub channel adları değişmedi.

### 4. Test gates

- [ ] Unit test green (`pytest tests/unit`).
- [ ] Integration test green (`pytest tests/integration`).
- [ ] Characterization snapshot (retrieval / SSE / extraction touch ediyorsa) — **delta = 0**.
- [ ] Eval baseline diff (RAG touch ediyorsa) — recall@5/10 delta < 0.5%.
- [ ] Frontend tsc + Playwright smoke (frontend touch ediyorsa).

### 5. Boundary enforcement (import-linter)

- [ ] Yeni `modules/<mod>` veya `shared/<sub>` strict kapsamda (Faz 1'den itibaren).
- [ ] Legacy `app.core.*` veya `app.api.*` taşındıysa strict kapsama promote edildi.
- [ ] Yasaklı ok yok (CI yeşil).
- [ ] Cross-module import'lar yalnız `service.py` / `repository.py` / `schemas.py` üzerinden — `internal/*` import edilmiyor.

### 6. No internal alias-debt

- [ ] Eski path silindi (`app/core/<old>.py` veya `app/api/<old>.py` dosyası yok).
- [ ] **Broader grep pattern** (Phase 2 PR 2 dersi — dot-form ve modül-level her ikisi):
  ```bash
  grep -rE 'from app\.(api|core|workers\.tasks)(\.[a-z_]+)? import' apps/api --include="*.py"
  grep -rE 'import app\.(api|core|workers\.tasks)' apps/api --include="*.py"
  ```
  Test dahil tüm `apps/api/` üstünde **kod/test eski path kalmamalı**.
- [ ] Sonuçları körlemesine değiştirme:
  - Gerçek eski path referanslarını düzelt.
  - Tarihsel `wiki/log.md` veya migration history docstring referansları (README, alembic versions) açıklama amaçlı kalabilir.
  - Kod / test import path'lerinde eski modül yolu kalmamalı.
- [ ] Re-export köprü yok (one-PR atomic).

### 7. Docs / wiki sync (aynı PR'da)

- [ ] `wiki/log.md` entry eklendi (yapılan iş özeti).
- [ ] `wiki/plans/modular-monolith-transition-master-plan.md` "Current Status" güncel.
- [ ] Yeni decision sayfası varsa `wiki/decisions/<slug>.md` oluşturuldu + index güncel.
- [ ] Mimari/yapı değişimi varsa `docs/engineering/*` ilgili bölüm güncel.
- [ ] Bidirectional backlink kontrol (yeni sayfa A→B varsa B→A da).

### 8. God-file disiplini (touch ediyorsa)

- [ ] Facade önce kuruldu mu?
- [ ] Characterization snapshot test paketi yeşil mi?
- [ ] İç parçalama "pure functions" → "stateless logic" → "orchestrator" sırasıyla mı?
- [ ] Snapshot diff = 0?

### 9. Runtime-sensitive değişiklik (touch ediyorsa)

- [ ] settings_store / prompts_store / cost_tracker / Celery Beat Schedule etkileniyor mu?
- [ ] Staging cluster'da Redis pub/sub davranışı doğrulandı mı?
- [ ] Worker process'in eski-yeni path'i import etmediği log'la doğrulandı mı?

### 10. Rollback plan

- [ ] PR revert edilirse ne olur dokümante edildi.
- [ ] Worker restart / cache invalidate / DB rollback gibi özel adım gerek mi?
- [ ] Spike değilse: production deploy edildiyse clean-main restore mecburiyetinde mi?

## Review tarafının kontrolleri

Reviewer:
- [ ] Tüm checkbox'lar dolu mu?
- [ ] CI yeşil mi (lint + import-linter + tests + alembic check)?
- [ ] PR description "What changed" + "What did NOT change" iki bölümü de doldurulmuş mu?
- [ ] Risk seviyesi gerçekçi mi (Low/Medium/High)?
- [ ] Staging doğrulama screenshot/log var mı (uygulanabilirse)?

## Çıkarımlar

1. Bu checklist disiplin değil, **production güvenliği** aracı. Atlanan her madde geçmişte production regresyonuna yol açmıştır.
2. Refactor PR ≠ feature PR. Tek scope. Karıştırma.
3. Docs sync **aynı PR'da** — kullanıcı açık talebi (2026-05-20): "Tam otonom ilerleyeceğin için dokümantasyonu ayrı bir yük gibi görmüyorum."

## İlişkiler

- **Bağlı kararlar:** [[no-internal-backcompat-aliases]], [[god-file-facade-first]], [[import-direction-rules]]
- **İlgili playbook:** [[refactor-anti-patterns-do-not-do]], [[new-feature-module-checklist]]
- **PR template:** [.github/PULL_REQUEST_TEMPLATE/refactor.md](../../.github/PULL_REQUEST_TEMPLATE/refactor.md)

## Açık sorular / TODO

- Checklist GitHub PR template'inde otomatik render olur; her PR'da gözden geçirilir. Yeni öğrenmeler bu sayfaya + template'e eşzamanlı eklenir.

## Kaynaklar

- [.github/PULL_REQUEST_TEMPLATE/refactor.md](../../.github/PULL_REQUEST_TEMPLATE/refactor.md)
- [wiki/plans/modular-monolith-transition-master-plan.md](../plans/modular-monolith-transition-master-plan.md)
