---
type: topic
title: "New Feature in Module Format — Checklist"
slug: "new-feature-module-checklist"
category: playbook
status: live
created: 2026-05-20
updated: 2026-05-20
sources:
  - "wiki/decisions/modular-monolith-boundary.md"
  - "wiki/decisions/import-direction-rules.md"
tags: ["new-feature", "checklist", "modular-monolith", "playbook"]
aliases: ["new-feature-checklist", "feature-module-format"]
---

# New Feature in Module Format — Checklist

> **TL;DR:** Modüler monolit dönüşümü başladıktan sonra yazılan **her yeni feature** modül-formatında olur — eski `core/` veya `api/` çöplüğüne dosya **eklenmez**. Bu checklist yeni feature başlangıcında "hangi modüle düşer, sınır ihlali var mı, hangi testler şart" sorularına cevap verir.

## Bağlam

Refactor evrimsel — yeni feature'lar refactor PR'ları arasında akmaya devam eder. Eğer yeni feature eski yapıya yazılırsa, refactor borç biriktirmeye devam eder (anti-pattern #6: "`core/` içine yeni domain logic ekleme"). Bu checklist disipline binmenin pratik aracıdır.

## Ana içerik — Checklist

### 1. Modül kararı

- [ ] Bu feature hangi mevcut modüle düşer? ([[modular-monolith-boundary]] §2.2 modül listesinden seç)
- [ ] Mevcut modüle düşmüyorsa yeni modül mü gerek? **Çok nadir** — önce mevcut modülü genişletmeyi düşün.
- [ ] Yeni modül gerekiyorsa: master plan'a karar ekle ([[modular-monolith-boundary]] revise edilir).

### 2. Katman + import yönü kontrolü

- [ ] Bu feature hangi katmanda (kernel / orta / üst / paralel)?
- [ ] Hangi diğer modülleri okuyacak? Hepsi [[import-direction-rules]] §3.1 "Allowed imports" tablosunda mı?
- [ ] Forbidden ok'a takılan import var mı? Varsa tasarım yanlış — feature'ı yeniden düşün.

### 3. Modül dosya yapısı

- [ ] `modules/<mod>/__init__.py` — public facade expose
- [ ] `modules/<mod>/service.py` — iş mantığı
- [ ] `modules/<mod>/repository.py` — DB erişimi (model flat path'ten import: `from app.models.X import X`)
- [ ] `modules/<mod>/schemas.py` — Pydantic DTO
- [ ] `modules/<mod>/deps.py` — FastAPI dependency'ler
- [ ] `modules/<mod>/routes.py` — app-level FastAPI router
- [ ] (varsa) `modules/<mod>/admin/routes.py` — admin yüzeyi
- [ ] (varsa) `modules/<mod>/tasks/<task>.py` — Celery task'lar
- [ ] (varsa) `modules/<mod>/internal/*` — modül-içi yardımcı (dışarıdan import edilmez)

### 4. Model + schema

- [ ] Yeni DB tablosu varsa `apps/api/app/models/<entity>.py` (flat); `app/models/__init__.py` + `__all__` güncel.
- [ ] Alembic migration ayrı bir migration script — refactor PR'ından bağımsız.
- [ ] Repository bu modeli `from app.models.<entity> import X` ile import eder.

### 5. Route + URL

- [ ] URL prefix master plan'a uygun (`/app/<sub>`, `/admin/<sub>`, `/public/<sub>`).
- [ ] `main.py` router include eklendi.
- [ ] OpenAPI/API contracts (`docs/engineering/api-contracts.md`) güncellendi.

### 6. Worker / Celery

- [ ] Task `modules/<mod>/tasks/<task>.py` içinde.
- [ ] Task name pattern: `tasks.<mod>.<task_name>` (string-bound; değişirse Beat kırılır).
- [ ] `shared/workers/celery_app.py` `include` listesine eklendi.
- [ ] Queue routing (`task_routes`) güncel — uygun queue'ya bağlı.
- [ ] Beat schedule gerekirse: ayrı PR'da eklenir (refactor scope dışı).

### 7. Frontend (varsa)

- [ ] `src/modules/<mod>/` (backend mirror) altında bileşen + api client.
- [ ] `src/app/<route>/page.tsx` — Next.js route shell minimal; modül bileşenini import eder.
- [ ] API client `src/modules/<mod>/api/<mod>-api.ts` — `src/lib/api.ts`'in base infra'sını kullanır.

### 8. Testler

- [ ] Unit test `apps/api/tests/unit/test_<mod>_<feature>.py`
- [ ] Integration test gerekirse `apps/api/tests/integration/`
- [ ] RAG / SSE / extraction'a dokunuyorsa characterization snapshot extend edildi mi?
- [ ] Frontend touch ediyorsa Playwright smoke

### 9. Docs / wiki sync (aynı PR'da)

- [ ] `wiki/log.md` entry
- [ ] `docs/engineering/api-contracts.md` yeni endpoint
- [ ] `docs/engineering/data-model.md` yeni tablo
- [ ] (gerekiyorsa) yeni decision sayfası `wiki/decisions/<slug>.md`

### 10. Anti-pattern kontrolü

- [ ] `core/` veya `api/` klasörüne yeni dosya **eklenmedi**.
- [ ] God-file'a satır eklenmedi (zaten 800+ satırsa: separate facade ile yeni iş).
- [ ] Davranış değiştiren bir refactor karıştırılmadı (feature PR'ı sadece feature).
- [ ] Davranış değişikliği "ayrı feature" gerektiriyorsa: ayrı issue + ayrı PR.

## Çıkarımlar

1. Yeni feature **modüler yapıyı zayıflatmaz, güçlendirir**. Her feature doğru modüle yazılırsa refactor süresi 2-3 ay'dan kısalır.
2. "Geçici olarak `core/`'a koyayım sonra taşırım" yasak — alias-debt anti-pattern'ine yol açar.
3. Yeni modül oluşturma neredeyse her zaman yanlış — önce mevcut modülü genişlet.

## İlişkiler

- **Bağlı kararlar:** [[modular-monolith-boundary]], [[import-direction-rules]], [[admin-route-domain-ownership]]
- **İlgili playbook:** [[refactor-pr-checklist]], [[refactor-anti-patterns-do-not-do]]

## Açık sorular / TODO

- Bu checklist Faz 1 sonrası (iskelet kurulduktan sonra) gerçekten kullanılabilir hale gelir. PR template'ine `?template=new-feature.md` URL variant'ı eklemek değerlendirilebilir (Faz 2-3'te).

## Kaynaklar

- [wiki/plans/modular-monolith-transition-master-plan.md](../plans/modular-monolith-transition-master-plan.md)
- [docs/engineering/modular-monolith-architecture.md](../../docs/engineering/modular-monolith-architecture.md)
