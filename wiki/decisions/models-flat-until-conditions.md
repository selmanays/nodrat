---
type: decision
title: SQLAlchemy Models Stay Flat Until 5 Preconditions
slug: models-flat-until-conditions
status: locked
decided_on: 2026-05-20
decided_by: founder
created: 2026-05-20
updated: 2026-05-20
sources:
  - wiki/decisions/modular-monolith-boundary.md
  - wiki/plans/modular-monolith-transition-master-plan.md§4
tags:
  - architecture
  - modular-monolith
  - sqlalchemy
  - alembic
  - locked-decision
aliases:
  - models-flat
  - model-relocation-preconditions
---

# SQLAlchemy Models Stay Flat Until 5 Preconditions

> **Karar:** Modüler monolit ana geçişinde (Faz 0-8) SQLAlchemy modelleri `apps/api/app/models/` altında **flat** kalır. Modül taşıma sadece ayrı **Faz N+1**'de, 5 ön-şart hep birlikte sağlandığında yapılır.
>
> **Durum:** locked
> **Tarih:** 2026-05-20

## Bağlam

Mevcut durum (API kod analizi 2026-05-20):
- `models/__init__.py` 20 model explicit import + `__all__` tuple (autogenerate güvenli).
- `alembic/env.py`: `from app.models import *` + `target_metadata = Base.metadata`.
- 14 `relationship()` çağrısı, **%100 back_populates**, **%93 class-form** (`relationship(Article)` doğrudan class-ref) + %7 string-form.

Modeller modüllere taşınırsa:
- **Class-ref relationship** → import cycle (User↔Conversation↔Message↔Article kompleksinde mapper init order'da hata).
- **Alembic autogenerate** → model import path'i değişince `target_metadata` hidrate olmazsa tablo "drop" diye algılanır (sessiz schema migration).
- **Test setupı** → her test fixture'ı eski path'leri import ediyor; toptan değişim büyük PR.

## Alternatifler ve neden reddedildi

| Alternatif | Artı | Eksi | Karar |
|---|---|---|---|
| Modelleri ilk fazda dik kes | "Modül = tam dikey" mantıklı | Class-ref relationship'lar circular import yapar; autogenerate kırılır; refactor PR'ları büyür | **Reddedildi** |
| Modelleri hiçbir zaman taşıma | Riski sıfır | Modül yapısı eksik kalır; "Article modeli kim sahibi?" sorusu kod düzeyinde silik | **Reddedildi** (uzun vade) |
| **Modelleri flat tut, repository/service modülde; Faz N+1'de şartlı taşı** | Refactor riskini izole eder; iş mantığı yine modülde; circular import beklenmez | İki katmanlı geçiş (ana + N+1) | **Seçildi** |

## 5 ön-şart (hepsinin **birlikte** sağlanması zorunlu)

| # | Ön-şart | Doğrulama |
|---|---|---|
| 1 | **Tüm `relationship()` çağrıları string-ref formunda** — `relationship("Article", back_populates="source")`. | Script: `grep -rE 'relationship\(\w+[\s,]' apps/api/app/models/` → boş çıkmalı (class-form yok). |
| 2 | **Alembic check CI'da** — `alembic check` no-diff + `alembic current == alembic heads` jobs. | `.github/workflows/ci.yml` içinde dedicated job; her PR'da yeşil. |
| 3 | **Boş DB → upgrade head testi** — yeni Postgres + tüm migration uygulanır + tüm modeller import-resolve. | `tests/migration/test_fresh_upgrade.py` (yeni, Faz 8'de eklenecek). |
| 4 | **Mapper resolution testi** — SQLAlchemy `configure_mappers()` hata vermez; relationship'lar tam çözülür. | `tests/migration/test_mapper_resolution.py` (yeni). |
| 5 | **Autogenerate diff sıfır** — `alembic revision --autogenerate` çıktısı boş; schema = code state. | Manuel kontrol + CI alembic-check job'unun bir parçası. |

## Repository/service pattern (Faz 0-8 boyunca)

Her modül kendi service + repository'sini içerir; modele flat path ile erişir:

```
modules/articles/repository.py:
    from app.models.article import Article   # FLAT
    
    class ArticleRepository:
        async def get_by_id(self, session, article_id) -> Article: ...
        async def list_by_source(self, session, source_id) -> list[Article]: ...
```

Faz N+1 sonrası import değişir:

```
modules/articles/repository.py:
    from modules.articles.models import Article   # TAŞINMA SONRASI
```

İş mantığı, route, service **değişmez** → izolasyon model taşımayı düşük riskli yapar.

## Faz N+1 sırası (5 ön-şart sağlandıktan sonra)

Sıra: kernel önce → orta → üst.
1. `sources/`
2. `articles/`
3. orta katman modüller (crawler/rag iç modelleri varsa, clusters, entities, media, style_profiles, sft)
4. paralel modüller (accounts, billing, legal, prompts_admin, settings_admin)
5. üst katman (generations)

Her PR:
- `app/models/<entity>.py` → `modules/<mod>/models.py`
- `app/models/__init__.py`'de re-export 1 release deprecation period
- Sonraki PR: re-export silinir, `app/models/<entity>.py` dosyası boş veya silinir
- Alembic autogenerate diff = 0 doğrulanır

## Sonuçlar

- Faz 0-8 boyunca **modeller dokunulmaz**.
- Modül taşıma PR'larında sadece service/repository/routes/tasks taşınır.
- 5 ön-şart Faz 8'de aktif hazırlanır; sağlandığında bu sayfa `status: ready-for-migration` olur ve Faz N+1 milestone'u (`Nodrat Modular Monolith v1.1`) açılır.

## Geri alma maliyeti

Bu karar gevşetilip modeller erken taşınırsa: class-ref relationship'larda circular import; autogenerate sessiz schema kayması; ROLLBACK için tüm taşınan modeller geri alınır + alembic state temizlenir. **Yüksek maliyet** (production schema riski).

## İlişkiler

- **Bağlı kararlar:** [[modular-monolith-boundary]]
- **Bağlı tracker:** GitHub T8 — Model relocation prerequisites
- **Bağlı kanonik doc:** `docs/engineering/data-model.md` §1 Migration Stratejisi (ileride Faz N+1 hazırlık bölümü eklenir)

## Kaynaklar

- [wiki/plans/modular-monolith-transition-master-plan.md §4](../plans/modular-monolith-transition-master-plan.md)
- [docs/engineering/data-model.md](../../docs/engineering/data-model.md) §1
