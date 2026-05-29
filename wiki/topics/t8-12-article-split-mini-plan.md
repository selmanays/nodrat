---
type: topic
title: "T8-12 Article Split Mini-Plan"
slug: "t8-12-article-split-mini-plan"
status: planned
created: "2026-05-28"
updated: "2026-05-28"
github_issue: "https://github.com/selmanays/nodrat/issues/1087"
sources:
  - "wiki/topics/t8-model-relocation-mini-plan.md"
  - "wiki/topics/refactor-pr-checklist.md"
  - "wiki/plans/modular-monolith-transition-master-plan.md§13"
tags: ["t8", "article", "model-relocation", "sub-pr-split", "modular-monolith"]
aliases: ["T8-12 article split", "article model relocation"]
---

## TL;DR

**T8-12 = `Article` + `ArticleImage` ORM `app/models/article.py` → `app/modules/articles/models.py`.** T8 unlocked-harvest sonrası (15/22) kalan en bağımsız HIGH track. **Üç engel:** (1) **12 caller > 8** (kullanıcı hard kuralı → sub-PR split); (2) **`sources → articles` contract ihlali** (sources/tasks Article import ediyor; sources strict-forbidden — v82/T8-11 paterni, article-hedefli varyant); (3) **Vector(1024) summary_embedding + relationship()** (Article↔ArticleImage). Çözüm: **2 sub-PR** — A: sources→articles decouple (raw SQL, davranış-koruyan) + B: model relocation (atomik). Behavior-preserving; veri/migration/index DEĞİŞMEZ.

## 1. Problem

`Article` (haber içeriği) + `ArticleImage` (görseller) modülerleşmenin merkezinde — articles domain'inin kalbi. T8 boyunca ertelendi (v78 "13 caller sub-PR"; v82 "article sub-PR split mini-plan gerek"). T8 unlocked harvest (T8-15/17/16/11/10) tamamlandıktan sonra kalan en yüksek değerli bağımsız iş.

**Audit (2026-05-28, main `ae654d2`):**
- **Model:** `Article` (Vector(1024) `summary_embedding` Phase 8.2-12 hardened; FK `sources.id` RESTRICT) + `ArticleImage` (FK `articles.id` CASCADE + `sources.id`). **relationship() internal:** `Article.images` ↔ `ArticleImage.article` (cascade all,delete-orphan). 2 class birlikte taşınır → mapper-safe (T8-11/T8-10 kanıtlı).
- **Hedef:** `modules/articles/models.py` (articles modülü A-grubu; `*.models` purge muafiyeti v93 mevcut).

## 2. Caller analizi (12 + facade + test)

| Caller | import | eager/lazy | Domain contract | Durum |
|---|---|---|---|---|
| `api/admin_queue.py:46` | Article, ArticleImage | eager | api (serbest) | DIRECT flip |
| `modules/articles/admin/routes.py:31` | Article, ArticleImage | eager | same-module | DIRECT flip |
| `modules/articles/tasks/articles.py:52` | Article, ArticleImage | eager | same-module | DIRECT flip |
| `modules/clusters/tasks/clustering.py:25` | Article | eager | clusters → rag/generations forbidden; **articles OK** | DIRECT flip |
| `modules/embedding/tasks/embedding.py:85` | Article | **lazy** | embedding → rag/generations forbidden; **articles OK** | DIRECT flip |
| `modules/media/admin/routes.py:29` | Article, ArticleImage | eager | media → rag/generations forbidden; **articles OK** | DIRECT flip |
| `modules/media/media_suggest.py:29` | Article, ArticleImage | eager | media (OK) | DIRECT flip |
| `modules/media/tasks/image_vlm.py:28` | Article, ArticleImage | eager | media (OK) | DIRECT flip |
| `modules/media/tasks/media.py:20` | ArticleImage | eager | media (OK) | DIRECT flip |
| `modules/ops/tasks/maintenance.py:33` | Article | eager | ops (source-contract yok) | DIRECT flip |
| `modules/sources/tasks/sources.py:194` | Article | **lazy** | **sources → ANY domain YASAK** ⚠️ | **DECOUPLE (raw SQL)** |
| `tests/integration/test_record_failure_539.py:14` | Article | eager | test | DIRECT flip |

**Tek contract blocker = sources** (pyproject `sources/ must not import any other domain` forbidden listesinde `app.modules.articles` var). Diğer 11 caller LEGAL (articles **kernel alt-katman**; clusters/embedding/media yalnız rag/generations'a forbidden).

## 3. Contract çözümü — sources→articles decouple (davranış-koruyan)

`sources/tasks/sources.py:194` (`recompute_extract_health` task) Article'ı yalnız **count query** için kullanıyor (`select(func.count(Article.id)).where(Article.source_id == sid).where(Article.status == ...)`). ORM bağımlılığı gereksiz — raw SQL ile decouple edilebilir:

```python
# ÖNCE (sources → articles import):
from app.models.article import Article
cleaned = (await db.execute(
    select(func.count(Article.id)).where(Article.source_id == sid).where(Article.status == "cleaned").where(Article.cleaned_at >= cutoff)
)).scalar_one()

# SONRA (raw SQL — tablo adı sabit; import YOK; davranış AYNEN):
import sqlalchemy as sa
cleaned = (await db.execute(
    sa.text("SELECT count(*) FROM articles WHERE source_id = :sid AND status = 'cleaned' AND cleaned_at >= :cutoff"),
    {"sid": sid, "cutoff": cutoff},
)).scalar_one()
```

`articles` tablo adı sabit (T8 model taşınsa da değişmez); count davranışı birebir. sources→articles import edge kalkar → contract temiz. **Bu, T8-8 "raw SQL caller'lar tablo adı sabit, etkilenmez" prensibinin tersi uygulaması** (ORM caller → raw SQL'e indirgeme).

## 4. Sub-PR sıralaması

| Sub-PR | Scope | Caller/dosya | Risk |
|---|---|---|---|
| **T8-12a** ✅ **DONE v97** | sources/tasks Article ORM query → raw SQL; sources→articles edge KALDIR | 1 dosya (sources/tasks/sources.py) | **TAMAMLANDI** PR [#1352](https://github.com/selmanays/nodrat/pull/1352) `004a824`; 2 count query `sa.text`'e (davranış birebir); Article import kaldırıldı; import-linter 16/16; scheduler 5/5; TAM 1186; FULL deploy GREEN + SSH 13/13. T8-12b relocation artık contract-temiz. |
| **T8-12b** (relocation) | `article.py` → `modules/articles/models.py` + facade + **11 caller DIRECT flip** | 12-13 dosya (model + facade + 11 caller + README) | MED — **atomik** (facade poisoned: clusters/embedding/media → app.models → rag/generations transitive YASAK → facade-path kullanılamaz; stub yasak → model relocation tek PR). 11 mekanik tek-satır flip; T8-11 (8) + T8-16 (5) kanıtlı kalıp |

> **Caller>8 atomik gerekçesi (T8-12b):** Model relocation atomiktir — eski `app/models/article.py` silinince (stub yasak) tüm caller AYNI PR'da kırılır. Facade-path bölme **çalışmaz** çünkü `app/models/__init__.py` rag/generations re-export ediyor (v78 POISONED) ve clusters/embedding/media bunlara forbidden → facade-path transitive ihlal. Dolayısıyla 11 caller DIRECT flip atomik zorunlu. Risk azaltma: (a) T8-12a ön-PR sources'ı çıkarır (12→11); (b) her flip tek-satır mekanik; (c) pre-flight matrisi (facade identity + mapper + module_init + TAM 1186) tam koruma; (d) A-grubu `*.models` purge muafiyeti (v93) articles için aktif.

## 5. Vector + relationship + veri güvenliği guard

- **Vector(1024) `summary_embedding`:** ORM declaration konum değişir; **tablo `articles` / kolon / ivfflat index / migration `20260511_0100` DEĞİŞMEZ**. Raw SQL `UPDATE articles SET summary_embedding` + `<=> ::vector` query'leri tablo adına bağlı → etkilenmez. **Embedding/RAG/index VERİSİNE dokunulmaz** (hard-stop #2/#13 invariant korunur; reembed/rechunk/reindex YOK).
- **relationship():** Article↔ArticleImage internal back_populates; 2 class birlikte taşınır → mapper resolution korunur (T8-10/T8-11 kanıtlı; mapper_resolution 3/3 ön-şart).
- **Behavior-preserving:** pure ORM declaration move + raw-SQL decouple (davranış birebir); no migration write, no DB schema change, no manual trigger.

## 6. Pre-flight matrisi (her sub-PR)

ruff + format / 5-form stale grep (`app.models.article`) / **lint-imports 16/16** (T8-12b: sources→articles YOK doğrula) / mapper_resolution 3/3 / module_init_lazy 9/9 (articles A-grubu + `*.models` muafiyeti) / admin_rag collect / **facade identity** (Article+ArticleImage `is`) / **TAM `pytest tests/unit/` 1186** / branch-CI-gated merge → FULL deploy watcher → SSH 13/13 smoke → vNN closure.

## 7. Hard-stop kuralları (T8-12 boyunca)

- import-linter 16/16 bozulursa DUR (özellikle sources→articles T8-12a sonrası temiz olmalı).
- Vector/embedding/RAG/index VERİSİNE dokunma ihtimali → DUR (yalnız ORM declaration move; veri/migration YOK).
- relationship/mapper resolution bozulursa DUR.
- ignore_imports YASAK (contract çözümü davranış-koruyan decouple ile).
- Caller flip sonrası lint-imports TEKRAR çalıştır (T8-11 dersi).

## İlişkiler

- [[t8-model-relocation-mini-plan]] — ana T8 planı (T8-12 satırı)
- [[refactor-pr-checklist]] — pre-flight + A-grubu×forbidden dersi (T8-11)
- [[modular-monolith-transition-master-plan]] §13 — milestone

## Kaynaklar

- `apps/api/app/models/article.py` (Article + ArticleImage; Vector + relationship)
- `apps/api/pyproject.toml` `[[tool.importlinter.contracts]]` (sources forbidden)
- docs/engineering/data-model.md §6 (article schema)

## Açık sorular / TODO

- T8-12b sonrası **T8-19** (article.summary_embedding vector hardening "re-verify") — Phase 8.2-12'de zaten hardened; relocation sonrası mapper + Vector ORM declaration re-verify (pratik NOP, pre-flight kapsar).
- ArticleImage `sources.id` FK (ikinci FK) — sources tablosu T8-11'de taşındı ama FK **table-name** ("sources.id") → etkilenmez.
