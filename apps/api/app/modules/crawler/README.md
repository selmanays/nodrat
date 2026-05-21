# `modules/crawler/`

**Layer:** middle — see [`wiki/plans/modular-monolith-transition-master-plan.md`](../../../../wiki/plans/modular-monolith-transition-master-plan.md) §2.

**Status:** Phase 4 mini-cycle başladı (extractor facade re-export aktive). Tam Phase 4 migration (fetcher + cleaning + structured_data + site_profiles + content_quality + extractor internal split) ileride.

## Yapı

```
modules/crawler/
├── __init__.py             Module facade (middle-layer docstring)
├── extractor/
│   └── __init__.py         Pure re-export facade → app.core.extractor
└── README.md               Bu dosya
```

## Public API (mevcut)

`modules.crawler.extractor` re-exports (Phase 4 PR-B):

| Symbol | Type | Source |
|---|---|---|
| `extract_article` | function | `app.core.extractor` (main cascade entry) |
| `extract_body_images` | function | `app.core.extractor` |
| `extract_with_selectors` | function | `app.core.extractor` |
| `extract_with_trafilatura` | function | `app.core.extractor` |
| `extract_fallback` | function | `app.core.extractor` |
| `extract_listing_cards` | function | `app.core.extractor` |
| `extract_structured_tier` | function | `app.core.extractor` |
| `BodyImage` | dataclass | `app.core.extractor` |
| `ExtractedArticle` | dataclass | `app.core.extractor` |
| `ListingCard` | dataclass | `app.core.extractor` |
| `MIN_TEXT_LENGTH` | int | `app.core.extractor` |

## Source-of-truth

`core/extractor.py` (1189 LoC) **DOKUNULMADI**. Facade pure re-export pattern; behavior aynen `app.core.extractor`.

## Strateji (T6 #1085 god-file facade-first)

1. **PR-A** ([#1144](https://github.com/selmanays/nodrat/pull/1144)) — characterization tests: `extract_body_images` için 15 yeni unit test (URL resolution, dedup, figure, missing-attrs, position, realistic fixture). Safety-net.
2. **PR-B SCAFFOLD STEP** (bu PR) — `modules/crawler/extractor/__init__.py` re-export facade **modülü** eklenir. Production caller flip **YAPILMAZ** — mevcut master plan §3.1/§3.2'ye göre kernel modülleri (`articles`, `sources`) `crawler` middle layer'ı import edemez. 3 caller hâlâ `app.core.extractor`'dan import eder. Boundary kararı ([açık soru](#açık-sorular--blocked-questions)) çözülene kadar caller migration **ertelendi**.
3. **PR-C** (caller flip — boundary kararına bağlı) — extractor layer kararına göre üç olası yol: (a) master plan §3.1 revize edip kernel→crawler allowed yapmak; (b) extractor'ı `shared/extraction/` veya başka layer'a taşımak; (c) Phase 4 full migration'da extractor'la birlikte kernel/middle boundary revize.
4. **PR-D — internal split** — küçük adım; characterization PASS safety-net üzerinde image extraction / structured tier ayrı dosya.
5. **Full Phase 4** — fetcher + cleaning + structured_data + site_profiles + content_quality migration.

## Açık sorular / Blocked questions

**Boundary kararı (bu PR'da kapatılmadı):**

- Extractor gerçekten `modules/crawler/` mı kalmalı, yoksa `shared/extraction/` veya başka bir boundary'de mi daha doğru?
- Kernel modülleri (`articles`, `sources`) `crawler` extraction surface'ini ileride nasıl tüketecek?
- 3 caller (`articles/tasks/articles.py:51`, `sources/admin/routes.py:37`, `sources/tasks/sources.py:22`) hangi extractor path'inden import edecek (Phase 4 sonu)?

Bu sorular **Phase 4 full migration** öncesi karara bağlanmalı. Bu PR sadece scaffold; kullanıcı kuralı: master plan boundary'sini sessizce değiştirme + new `ignore_imports` ekleme.

## Veri güvenliği invariant (kullanıcı kuralı)

- Application behavior **DEĞİŞMEZ** (pure re-export)
- DB/Redis/state-change YOK
- Production article ya da source üzerinde state-changing smoke yok
- Pre-existing extractor cascade behavior preserved

## Smoke acceptance (post-merge, BLOCKING passive — scaffold-only)

1. New path `app.modules.crawler.extractor` import OK + 11 symbol attr (extract_article, extract_body_images, ..., MIN_TEXT_LENGTH)
2. Old path `app.core.extractor` **HÂLÂ** importable (source-of-truth; bu PR yalnız re-export facade ekler)
3. `extract_article` ve `extract_listing_cards` re-export identity: `app.modules.crawler.extractor.extract_article is app.core.extractor.extract_article` True
4. 3 caller (`articles/tasks/articles.py:51`, `sources/admin/routes.py:37`, `sources/tasks/sources.py:22`) **hâlâ** `app.core.extractor`'dan import eder (caller flip bu PR'da YOK)
5. Mevcut `test_extractor.py` 1496 LoC + 15 characterization tests PASS
6. 7 container × 6 pattern × ≥5 dk log scan: 0 hits (yeni modül import edilebilir ama production path hâlâ legacy)

**Manuel trigger YASAK** (production article fetch state-change yapmaz; smoke read-only).

## References

- [`wiki/decisions/modular-monolith-boundary.md`](../../../../wiki/decisions/modular-monolith-boundary.md)
- [`wiki/decisions/import-direction-rules.md`](../../../../wiki/decisions/import-direction-rules.md)
- [`wiki/plans/modular-monolith-transition-master-plan.md`](../../../../wiki/plans/modular-monolith-transition-master-plan.md) §6 (God-file Strategy)
- T6 [#1085](https://github.com/selmanays/nodrat/issues/1085) — God-file facade strategy
- PR [#1144](https://github.com/selmanays/nodrat/pull/1144) — extract_body_images characterization tests (safety-net)
