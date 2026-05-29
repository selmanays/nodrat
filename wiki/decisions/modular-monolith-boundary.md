---
type: decision
title: Modular Monolith Boundary (Domain-Based Layering)
slug: modular-monolith-boundary
status: locked
decided_on: 2026-05-20
decided_by: founder
created: 2026-05-20
updated: 2026-05-30
sources:
  - wiki/plans/modular-monolith-transition-master-plan.md§1
  - docs/engineering/modular-monolith-architecture.md
tags:
  - architecture
  - modular-monolith
  - locked-decision
aliases:
  - mm-boundary
---

# Modular Monolith Boundary (Domain-Based Layering)

> **Karar:** Nodrat domain-bazlı modüler monolite dönüşür. Microservice'e gidilmez. `apps/api/app/modules/<domain>/` + `apps/api/app/shared/<infra>/` ağacı; 4 mantıksal katman (kernel → orta → üst, paralel + cross-cutting).
>
> **Durum:** locked
> **Tarih:** 2026-05-20

## Bağlam

Mevcut `apps/api/app/` yatay kesim (api/core/models/workers/providers) — domain sınırı yok. `core/` 47 dosya tek düz klasör; `app.api.*` route'ları iş mantığı + LLM tool çağrılarını içeriyor. God-file'lar (retrieval.py 2174, app_research_stream.py 1440, extractor.py 1189) sessiz regresyon riski yaratıyor. Sources/articles/generations/rag/crawler gibi domain'ler net sınır olmadan birbirini import ediyor.

Hedef: tek repo + tek deploy, ama **domain-bazlı dikey kesim**.

## Alternatifler ve neden reddedildi

| Alternatif | Artı | Eksi | Karar |
|---|---|---|---|
| Microservice'e geç | Sınır en sıkı | Tek dev + LLM workflow için aşırı maliyet; deploy karmaşası; FK ilişkileri RPC'ye dönüşür | **Reddedildi** |
| Mevcut layer-bazlı yapıda kal | Refactor sıfır | `core/` çöplüğü büyür; god-file'lar sessiz regresyon yaratmaya devam eder; boundary yok | **Reddedildi** |
| Sources/articles'ı crawler altına koy | "Yazan modül sahibi" mantıklı | Article çok yerden okunur (rag, generations, clusters, sft) — hepsi crawler'ı import etmek zorunda kalır → boundary saçma | **Reddedildi** |
| Toptan refactor (12 gün donmuş trunk) | Tek atomik geçiş | MVP-1.8 RAG + RC3-B akışını engeller; sessiz regresyon riski; geçmiş CI körlüğü dersi | **Reddedildi** |
| **Domain-based modular monolith, boundary-first evrimsel** | Tek deploy korunur; sınır net; refactor MVP temposunu engellemez; god-file disiplini facade ile | Refactor 2-3 ay'a yayılır | **Seçildi** |

## Katman seviyeleri

```
Seviye 4 (üst):      generations
Seviye 3 (orta):     crawler, rag, clusters, entities, media, style_profiles, sft
Seviye 2 (kernel):   sources, articles                     ← domain kernel (DDD shared kernel)
Seviye 1 (paralel):  accounts, billing, legal, prompts_admin, settings_admin
Seviye 0 (alt):      shared/* (db, providers, prompts, util, http, storage,
                                email, observability, runtime_config, workers)
Cross-cutting:       ops    — modüllerin public API'larını okur (TEK İSTİSNA)
Cross-cutting:       public — yalnız rag.facade + health
```

## Modüller (18 + shared)

Tam liste + sorumluluk: `wiki/plans/modular-monolith-transition-master-plan.md §2.2`.

Özel sahiplikler (kullanıcı kararı 2026-05-20):
- `takedown` — legal sahip; model `app/models/takedown.py` flat.
- `cost_tracker` — `shared/observability/`; billing read-only.
- `conversation_context` — `modules/generations/conversation/context.py`; shared değil.
- `settings_store`, `prompts_store` — `shared/runtime_config/`; admin modülleri yalnız CRUD yüzeyi.
- `event.py`, `job.py`, `provider_log.py` — şimdilik flat; sahipleri: ileride observability/ops adayları.

## Karar notu (2026-05-23): Extraction primitives → `shared/extraction/`

**Bağlam:** P4 PR-D'nin sürmesi için PR #1146 closure'da bekleyen *"extractor `modules/crawler/` mi yoksa başka bir yere mi?"* sorusu. PR #1146'da denenen `app.modules.crawler.extractor` facade'ına 3 kernel caller (sources×2 + articles×1) flip edilince **contract 2** (sources/ → modules.crawler forbidden) ve **contract 3** (articles/ → modules.crawler forbidden) **BROKEN** oldu (kanıt: PR #1146 lint-imports çıktısı). Mevcut çatışma: master plan §2.2 line 89'da *"crawler: HTML çekme + extraction cascade + ..."* tanımı extraction'ı crawler altına yerleştiriyor — ama kernel/middle ayrımı (kontrat-enforced) kernel modüllerin extraction'a *direkt* erişimini bloke ediyor.

**Karar (locked, 2026-05-23):**
- **Extraction primitives** (`extract_article` / `extract_with_trafilatura` / `extract_with_selectors` / `extract_fallback` / `extract_listing_cards` / `extract_structured_tier` / `extract_body_images` + `ExtractedArticle`/`ListingCard`/`BodyImage` dataclass'ları + `_extractor_filters` + `structured_data`) **pure HTML/content parsing kütüphanesi** olarak `app/shared/extraction/` altında yaşar (Seviye 0 — leaf; I/O yok, durum yok, deterministik).
- **Crawler** (`modules/crawler/`) seviye 3 (orta) konumunda kalır; fetch / orchestration / site_profile / crawling flow ve "extraction cascade *orchestration*" sorumluluğundadır — gerekirse `shared.extraction` primitive'lerini çağırır.
- **Kernel modülleri (articles, sources) `modules/crawler`'a İMPORT ETMEZ** — contract 2/3 korunur. Kernel'in extraction ihtiyacı `app.shared.extraction` üzerinden karşılanır (kernel→shared izinli).
- `shared/__init__.py` *"Shared infrastructure"* tanımı **"infrastructure + pure parsing primitive libraries"** olarak okunur (precedent: `shared/providers/wikipedia.py` ≈600 LoC HTTP+HTML logic).

**Reddedilen alternatifler:**
- **A) Extractor `modules/crawler/` altında full migration + caller flip** → contracts 2/3 BROKEN (PR #1146'da fiilen denendi, geri alındı).
- **C) Yeni `modules/extraction/` (kernel-level shared service)** → yeni katman tanımı + contracts update + master plan §2.2 yeni satır gerekir; design overhead yüksek; "implicit allow" emsali zayıf.
- **D) Contract 2/3 gevşetme (`app.modules.crawler.extractor` exception)** → kernel/middle boundary'nin özünü zayıflatır; her benzer ihtiyaç için emsal yaratır.
- **E) Status quo — `core/extractor.py` kalıcı home** → "core/ boşalır" modular monolith hedefi extractor için iptal; PR #1146 facade scaffold ölü kod kalır.

**Yapılış sırası (2-PR split, kullanıcı 2026-05-23 onayı):**
- **PR-D1 (bu, docs-only):** Boundary kararı + master plan §2.2/§2.3/§3 doc revizyonu. Kod taşımaz; contracts değişmez.
- **PR-D2 (ayrı onay sonrası):** `core/{extractor, _extractor_filters, structured_data}.py` → `shared/extraction/{...}` `git mv`; 4 caller import update (`core/cleaning.py` + `modules/sources/admin/routes.py` + `modules/sources/tasks/sources.py` + `modules/articles/tasks/articles.py`); `modules/crawler/extractor/` facade kararı (0-caller olduğu için sil tercihi); `tests/unit/test_extractor.py` import path güncel; `shared/__init__.py` docstring güncel; behavior-eş (mevcut characterization safety-net); `lint-imports` 13 kept / 0 broken korunur.

**Süperseder/etkilenir:** PR #1146 closure'daki *"extractor layer decision deferred"* maddesi → **resolved**. T6 #1085'in "extractor boundary kararı" alt-kalemi **DONE for boundary** (code move PR-D2'de).

## Karar notu (2026-05-29): T7-7 R2 — `sources → accounts` auth cross-cutting istisnası

**Bağlam:** T7-7 (deps split) `app/core/deps.py` (FastAPI auth/role kernel: `get_current_user`/`require_admin`/`require_foreign_transfer_consent`/`get_client_ip`) → `app/modules/accounts/deps.py` taşındı (`core/* must not import modules/*` ihlalini kaldırıp T8-21 User+Session relocation'ı unblock etmek için). 24 caller'ın 23'ü sorunsuz flip edildi; **tek engel `sources/admin/routes.py`** — `require_admin` (User-bağlı auth gate, 5 route) + `get_client_ip` (4 yer) kullanıyor ama `sources/ must not import any other domain module` strict-forbidden contract'ı `app.modules.accounts`'ı listeliyordu. `require_admin` → `get_current_user` → `select(User)` zinciri raw-SQL'lenemez (T8-12a'daki count-query'nin aksine; FastAPI `Depends()` + dönüş tipi `User`).

**Karar (R2):** `app.modules.accounts` **sources strict-forbidden listesinden çıkarıldı** (pyproject `[[tool.importlinter.contracts]]`; business domain'ler — articles/rag/generations/clusters/media/... — yasak KALDI).

**Gerekçe — neden bu (2026-05-23 extraction-case'deki reddedilen "contract gevşetme"den FARKLI):**
- Extraction-case (option D, yukarıda): kernel (sources/articles) → **MIDDLE** (crawler) = **upward layer ihlali** (kernel'in üst katmana bağımlılığı) → reddedildi, `shared/extraction` ile çözüldü.
- R2: kernel (sources) → **PARALLEL** (accounts, "Seviye 1 paralel" — bkz. §katman seviyeleri). accounts **auth/identity cross-cutting altyapı**; `require_admin` HER admin router'ın (kernel sources/admin dahil) ihtiyaç duyduğu evrensel gate — `app.core`/`app.shared` gibi her katmandan import edilebilir bir yatay servis. Dolayısıyla `sources → accounts.deps` **upward layer ihlali DEĞİL**; auth'un cross-cutting doğasının kabulü. sources strict-forbidden contract'ının asıl amacı (sources'ı **business** domain'lerden izole tutmak) korunur.
- **Auth ENFORCEMENT birebir değişmez** (`require_admin` super_admin gate + 401/403 + KVKK m.9 `require_foreign_transfer_consent` AYNEN); R2 yalnız import-boundary tanımının refinement'i (per-line `ignore_imports` suppress DEĞİL → "ignore_imports yasak" kuralına uygun). **Reversible** (gerekirse listeye geri eklenir + R1 decouple ile alternatif çözüm).
- **Alternatifler:** R1 (require_admin'i concrete User'dan decouple — HIGH; get_current_user ORM döner + 24 caller `Annotated[User, ...]`); R3 (`sources/admin/routes.py` → `app/api/`'ye taşı — sources'ı özel-vaka yapar, diğer 7 modül admin'i in-module tutuyor; [[admin-route-domain-ownership]] ihlali). R2 master-plan-aligned (accounts = auth evi) + en düşük blast-radius + tutarlı (tüm modüller admin route'unu in-module tutar).

**Uygulandı:** T7-7e (v104, PR [#1365](https://github.com/selmanays/nodrat/pull/1365) `bc2e357`); `lint-imports` 16 kept / 0 broken (R2 sonrası `sources/ must not import any other domain module` hâlâ KEPT — sadece accounts çıktı; `core/* must not import modules/*` KEPT — User edge kalktı). Detay: [[t7-7-deps-split-mini-plan]] §4.

## Karar notu (2026-05-30): T8-7b — `FailedJob` + `AdminAuditLog` cross-cutting observability istisnası (flat kalır)

**Bağlam:** T8 model relocation'ın son adımında (T8-7) `app/models/` altında kalan 3 cross-cutting observability modeli (`ProviderCallLog`, `FailedJob`, `AdminAuditLog`) ele alındı. Hedef `modules/ops/models.py`'di (master plan: ops = observability evi). Ancak `domain modules must not import ops/` import-linter contract'ı (niyet: **ops bir cross-cutting SINK; modüller veriyi yukarı-doğru ops'a emit eder, ops kodunu import ETMEZ**) çatışma yarattı:
- **`ProviderCallLog`:** domain importer YOK (cost_tracker T7-6'da raw `INSERT`'e geçti; tek importer facade'di; okuyan tek katman api/ admin_system → `api → ops` LEGAL). → **T8-7a'da `modules/ops/models.py`'ye taşındı** (ops'un ilk modeli; temiz).
- **`FailedJob`:** 2 domain modül yazıyor (`articles/tasks/articles.py`, `sources/tasks/sources.py`). **`AdminAuditLog`:** 6 domain admin modül yazıyor (articles/admin, prompts_admin, sources/admin, sft/admin, legal, settings_admin). Bunları `modules/ops/models.py`'ye taşımak → domain modüller `app.modules.ops`'u import eder → **`domain modules must not import ops/` ihlali**.

**🔑 İçgörü:** Bu 2 modeli `app/models/job.py`'de TUTMAK contract-clean'dir. Domain modüller `from app.models.job import FailedJob` yazar → `app.models.job` ≠ `app.modules.ops`; **hiçbir contract `modules → app.models`'i yasaklamaz**. ops'a taşımak ihlal yaratırken flat tutmak sıfır ihlal.

**Karar (Option 1 — kullanıcı onaylı 2026-05-30, nihai):** `FailedJob` + `AdminAuditLog` `app/models/job.py`'de **KALIR** — **documented cross-cutting observability exception**. `ProviderCallLog` ops'a taşınır (domain importer yok).

**Gerekçe:**
- Bu modeller tek bir domain'e ait DEĞİL — her domain'in yazdığı cross-cutting observability (error ledger + admin audit). ops contract'ının asıl amacı (ops'u modüllerin import etmediği bir sink yapmak) bu **write-target** modeller için ops'u yanlış ev kılar.
- `shared/`'a da konamaz (`shared/* must not import legacy core/api/models` + model `Base`'e muhtaç → `shared → core.db` yasak). Yani write-target observability modelinin contract-clean tek evi `app/models/` (flat).
- **Reddedilen alternatifler:** (A) ops-contract refine — `domain → ops` observability modelleri için gevşet → ops-izolasyon niyetini (contract'ın *asıl amacı*) zayıflatır; R2'den daha yıkıcı (R2'de accounts paralel auth'tu, burada ops açıkça "import edilmeyen sink"). (B) raw-SQL decouple — 8 domain write-site'ı raw `INSERT`'e çevir; uygulanabilir ama invasive + asimetrik (api read'ler ORM kalır) + gereksiz scope. (C/Option 1) flat tut — contract-clean, sıfır kod değişikliği, sıfır risk, behavior-preserving. **Option 1 seçildi.**
- **Reversible:** İleride event-driven observability (modüller event emit → ops consume) kurulursa bu modeller ops'a taşınabilir.

**Sonuç:** T8 model relocation **fonksiyonel TAM** — taşınabilir tüm modeller modüllerine taşındı; `FailedJob`/`AdminAuditLog` bilinçli + gerekçeli istisna. Bu, "tüm flat modeller taşınmalı" hedefinin %100'üne ulaşmama değil; ops-izolasyon mimarisinin doğal sonucu (write-target cross-cutting modeller flat kalır). **Uygulandı:** T8-7a (v113, PR [#1382](https://github.com/selmanays/nodrat/pull/1382) `8b31157`); `lint-imports` 16/16 KEPT (`domain modules must not import ops/` dahil); prod facade identity doğrulandı.

## Sonuçlar

- Etkilenen kavramlar: [[import-direction-rules]], [[models-flat-until-conditions]], [[god-file-facade-first]], [[admin-route-domain-ownership]].
- 8 fazlı geçiş planı: `wiki/plans/modular-monolith-transition-master-plan.md §9`.
- Karar değişimi: yeni decision sayfası + bu sayfa `superseded by` ile bağlanır.

## Geri alma maliyeti

Bu karar değiştirilirse: master plan tamamen yeniden yazılır, 8 fazlı geçiş hattı tekrar planlanır, açılmış GitHub issue'ları kapatılır/yeniden organize edilir, `wiki/decisions/*` ilgili 5 sayfa superseded işaretlenir. **Yüksek maliyet.** Bu yüzden locked.

## İlişkiler

- **Bağlı kararlar:** [[import-direction-rules]], [[models-flat-until-conditions]], [[god-file-facade-first]], [[admin-route-domain-ownership]], [[no-internal-backcompat-aliases]]
- **Bağlı playbook:** [[refactor-anti-patterns-do-not-do]], [[refactor-pr-checklist]], [[new-feature-module-checklist]]
- **Master plan:** `wiki/plans/modular-monolith-transition-master-plan.md`

## Kaynaklar

- [docs/engineering/modular-monolith-architecture.md](../../docs/engineering/modular-monolith-architecture.md)
- [docs/engineering/refactor-playbook.md](../../docs/engineering/refactor-playbook.md)
- [wiki/plans/modular-monolith-transition-master-plan.md](../plans/modular-monolith-transition-master-plan.md)
