---
title: Wiki Log — Kronolojik Kayıt
type: hub
updated: 2026-05-08
---
<!-- En son giriş yukarıda (Epic #448 Avukat + Vergi Danışmanı görüşü integrated — §3.9 N-09 RESOLVED + §3.10 N-10 INTEGRATED, 3 yeni canonical legal doc) -->



# Wiki Log

## [2026-05-08 akşam] review-integration | Epic #448 Avukat + Vergi Danışmanı görüşü integrated

- **Kaynak/Tetikleyici:** Kullanıcı Epic #448 review için avukat + vergi danışmanı görüşlerini iletti. Sonuç: ✅ avukat şartlı uygun (7 ön-launch maddesi) + ✅ vergi danışmanı onaylı (şahıs ticari kazanç + threshold matrisi).
- **Etkilenen sayfalar:**
  - **Update:** [[lemon-squeezy-payment-provider]] (review_status frontmatter eklendi: `avukat-sartli-onayli + vergi-danismani-integrated`; 6 yeni source ref: opinion-integration §3.9/§3.10, refund-policy, mesafeli-satis, payment-fallback-plan; trade-off section TIA + mali müşavir yükü eklendi; "Açık sorular / TODO" → "Resolved sorular" yeniden organize edildi; "Açık implementation TODO" 4 yeni issue listesi; Kaynaklar listesi tamamen güncellendi)
  - **Hub:** wiki/index.md (Payment/billing decision satırı: "✅ avukat şartlı + vergi danışmanı onaylı"; istatistik açık doküman senkronizasyonu **1 → 0** ✅)
- **Yeni:** 0
- **Güncellendi:** 2 (decision page + index)
- **Avukat 6 sorunun cevapları integrated (§3.9 N-09 RESOLVED):**
  1. LS MoR yapısı KVKK + TR e-ticaret hukuku → ŞARTLI UYGUN (LS açıkça listele, açık rıza, DPA/SCC)
  2. Nodrat e-Arşiv yükümlülüğü → büyük ölçüde EVET muaf (mali müşavir teyit şart)
  3. DPA + SCC yeterli mi → TEK BAŞINA DEĞİL (5 maddelik TIA gerek)
  4. m.9 server-side enforcement → EVET zorunluya yakın (5 akış backend gate)
  5. LS hosted refund + 14 gün → ŞARTLI UYGUN (5 maddelik kullanıcı bilgilendirme)
  6. R-FIN-04 fallback → KESİNLİKLE GEREKLİ (6-senaryo + Paddle ön başvuru)
- **Vergi danışmanı 7 madde integrated (§3.10 N-10 INTEGRATED):**
  1. e-Arşiv → TR müşteriye yok (LS MoR keser); LS payout için mali müşavir 4 yazılı teyit
  2. Sınıflandırma → ŞAHIS TİCARİ KAZANÇ (basit usul/serbest meslek/değer artış DEĞİL)
  3. Limited threshold → $3K review / $5K plan / $10K convert
  4. KDV → TR B2C yok; LS payout için ihracat istisnası mali müşavirle
  5. Stopaj → TR'de yok (ödeyen ABD'de LS)
  6. FX → ticari faaliyet kapsamında kur farkı geliri/gideri
  7. Threshold operasyonel trigger'lar → B2B/ekip/yatırım MRR'den bağımsız Limited
- **3 yeni canonical doc (Epic #448 docs PR):**
  - `docs/legal/refund-policy.md` (LS hosted refund + 14 gün cayma + 8 bölüm)
  - `docs/legal/mesafeli-satis-sozlesmesi.md` (TR Mesafeli Sözleşmeler Yönetmeliği uyumu)
  - `docs/legal/payment-fallback-plan.md` (R-FIN-04 6-senaryo + Paddle ön başvuru + 30-gün tampon)
- **4 yeni implementation issue (Epic #448 review output):**
  - [#470](https://github.com/selmanays/nodrat/issues/470) Server-side foreign_transfer_consent enforcement (5 akış 403 gate)
  - [#471](https://github.com/selmanays/nodrat/issues/471) Paddle fallback PaymentProvider abstraction (R-FIN-04)
  - [#472](https://github.com/selmanays/nodrat/issues/472) refund-policy + mesafeli-satis frontend yayın
  - [#473](https://github.com/selmanays/nodrat/issues/473) Şahıs ticari kazanç mükellefiyeti aç + mali müşavir 4 yazılı teyit
- **Branch:** `wiki/lemon-squeezy-review-integration`
- **Açık doküman senkronizasyonu:** 1 → **0** ✅ (docs PR #477 ile wiki/docs hizalı)
- **Ders:** Strateji pivot review akışı = locked decision wiki'de önce, danışman cevapları integrated → wiki frontmatter'a `review_status` eklenmesi → docs catch-up sub-issue PR ile senkron. CLAUDE.md §1.3 wiki write disiplini korundu (dedicated wiki/* branch).



Sadece-ekleme (append-only) kronolojik kayıt. LLM her `ingest`, `query` (arşivlenen) ve `lint` operasyonu sonrası buraya bir kayıt ekler.

## [2026-05-08] decision+pivot | Iyzico → Lemon Squeezy MoR (USD primary) — Epic #448

- **Kaynak/Tetikleyici:** Kullanıcı stratejik kararı — "Iyzico kullanımını değiştirmek istiyorum Lemon Squeezy ile çünkü biz ilk başta şirket olmadan ödeme alabileceğimiz bir yapıyla ilerleyeceğiz". Solo founder + bootstrap context'te launch hızı önceliklendirildi: Limited Şti. (~6-8 hafta) + e-Arşiv altyapısı (~$50-100/ay sabit) gereksinimleri kaldırıldı.
- **5 stratejik karar (kullanıcı onayladı):**
  1. **Para birimi:** USD primary (TL display locale ile)
  2. **Şirket kuruluşu (#46):** kapatıldı (LS MoR olduğu için ilk aşamada gereksiz; >$3K MRR sonrası yeniden değerlendir)
  3. **e-Arşiv:** kaldırıldı (LS MoR müşteriye fatura keser)
  4. **Trial:** card-required aynı kalsın (LS native destek)
  5. **Multi-seat:** LS variant + custom seat counter
- **Etkilenen sayfalar:**
  - **Yeni:** [[lemon-squeezy-payment-provider]] (locked decision — Faz 6 LS MoR USD primary, alternatifler tablosu, KVKK m.9 cross-border, R-FIN/R-LGL impact)
  - **Update:** [[provider-abstraction]] (Faz 6+ tablosu: Iyzico/Stripe → LemonSqueezyPaymentProvider), [[mvp-cut-list-method]] (Faz 6 row LS), [[mvp-1-scope]] (Faz 6 LATER liste LS), [[mvp-roadmap]] (MVP-3 + MVP-4+ LS notları), [[risk-catalog]] (R-LGL-10 ~~8~~ → 2 ✅ LS MoR e-Arşiv handles, R-LGL-11 LS m.9 ek checkbox notu, R-LGL-12 LS hosted refund), [[risk-register-md]] (MVP-3 fonksiyonel kapsam: Iyzico+e-Arşiv → LS MoR)
  - **Hub:** wiki/index.md (yeni "Payment / billing" decisions section, istatistik 31 → 32 sayfa, locked decisions 8 → 9, açık doküman senkronizasyonu 1 🟡)
- **Yeni:** 1 decision sayfası
- **Güncellendi:** 7 (provider-abstraction, mvp-cut-list-method, mvp-1-scope, mvp-roadmap, risk-catalog, risk-register-md, index)
- **Trade-off muhasebesi:**
  - **Kazanılan:** Launch hızı (Limited Şti. süreci yok), sabit maliyet sıfıra yakın (e-Arşiv altyapı yok), tax compliance global (LS yönetir), refund/chargeback hosted, customer portal LS hosted, TR dışı pazara açılma kolay.
  - **Kaybedilen:** Komisyon ~%2.5 daha yüksek (Pro $24 net ~$22.30, ~%93 retain), TR müşteri USD görür (FX algısı), LS account/payout dependency riski (yeni R-FIN-XX), KVKK m.9 yurt dışı transfer açık rıza zorunlu (yeni R-LGL).
- **GitHub issue ops:**
  - **Epic [#448](https://github.com/selmanays/nodrat/issues/448):** master tracking
  - **Update:** [#53](https://github.com/selmanays/nodrat/issues/53) rename "Iyzico TL + e-Arşiv" → "Lemon Squeezy MoR + USD primary" + body USD/LS, [#76](https://github.com/selmanays/nodrat/issues/76) body LS hosted checkout/portal, [#49](https://github.com/selmanays/nodrat/issues/49) DPA listesinden Stripe/Iyzico kaldırıldı + LS eklendi
  - **Close:** [#46](https://github.com/selmanays/nodrat/issues/46) Limited Şti. defer (LS MoR sayesinde ilk aşamada gereksiz; >$3K MRR threshold)
  - **Yeni sub-issue:** [#450](https://github.com/selmanays/nodrat/issues/450) LS Customer Portal + webhook handler (signature verify, 7 event), [#451](https://github.com/selmanays/nodrat/issues/451) Multi-seat agency LS variant + seat counter, [#453](https://github.com/selmanays/nodrat/issues/453) KVKK m.9 yurt dışı transfer açık rıza akışı
- **Açık doküman senkronizasyonu (Epic #448 docs PR sırada):** 15 docs dosyası USD/LS update bekliyor — `pricing-strategy.md` (USD recalc + LS provider), `unit-economics.md` (~%5+50¢ LS fee margin recalc), `risk-register.md` (yeni R-FIN-XX MoR dependency + R-FIN-XX FX exposure + R-LGL-XX KVKK m.9), `success-metrics.md` (USD KPI), `prd.md` §6 (Faz 6 rewrite), `ux-wireframes.md` (LS checkout/portal), `architecture.md` (payment provider section), `data-model.md` (subscriptions ls_* sütunlar), `api-contracts.md` (LS webhook spec), `threat-model.md` (US PII transfer), `legal/*` (8 dosya — compliance, tos, privacy, kvkk, ropa, cookies, dpo, incident, opinion), `INDEX.md` (locked decisions §4 + milestone §5b note). Wiki kararı **önce locked**; docs catch-up Epic #448 docs PR ile.
- **Branch:** `wiki/lemon-squeezy-pivot` (CLAUDE.md §1.3 — wiki write only on dedicated wiki/* branch).
- **Ders:** Strateji pivotunda **wiki kararı önce locked, docs catch-up sonra** akışı uygun. Çünkü kullanıcı kararı verdi → karar zaten "locked" — docs hâlâ eski Iyzico planını anlatıyor olsa bile wiki "şu anki gerçeği" yansıtmalı. Doküman senkronizasyonu ayrı PR ile sıralı yapılır (`Açık doküman senkronizasyonu` istatistiğinde takip).



## Format

```
## [YYYY-MM-DD] ingest|query|lint | başlık

- **Kaynak/Tetikleyici:** ...
- **Etkilenen sayfalar:** [[slug-1]], [[slug-2]], ...
- **Yeni:** N
- **Güncellendi:** N
- **Notlar:** opsiyonel kısa not (sürpriz bulgu, açık soru, çelişki)
```

> Avantaj: `grep "^## \[" log.md | tail -20` son 20 işlemi listeler. `grep "ingest" log.md` sadece ingest'leri gösterir.

---

## [2026-05-08] update | Epic #443 follow-up #475 — admin queue overview 4.3s → 11-684ms

- **Kaynak/Tetikleyici:** Kullanıcı admin özet + kuyruk sayfasının her yenilemede birkaç saniye sürdüğünü bildirdi.
- **Etkilenen sayfalar:** [[queue-management]] — performans bölümü güncellendi (yeni mimari + ölçümler)
- **Yeni:** 0 wiki page
- **Güncellendi:** Kod tabanı ([PR #475](https://github.com/selmanays/nodrat/pull/475) + 1 hotfix commit):
  - `core/celery_introspect.py` — `_INSPECT_TIMEOUT_S = 0.5` (eskiden 2.0); yeni `get_broker_snapshot()` tek inspect call ile worker_count + active_counts + Redis pipeline ile 4 LLEN tek round-trip + 5s Redis snapshot cache (`nodrat:broker:overview`)
  - `api/admin_queue.py` — queue_overview endpoint snapshot kullanır, broker arka planda async başlar; DB sıralı (AsyncSession concurrent destekleme bug'ı var, gather kullanılmaz)
  - `apps/web/.../admin/queue/page.tsx` — bakım görevleri ayrı 30s interval (beat schedule en kısa 5 dk; 30s yeterli), ana 10s refresh sadece overview + failed_jobs

- **Profile (production canlı ölçüm):**
  - **Önce:** `inspect.active` 2123ms + `inspect.ping` 2014ms + DB sıralı 110ms = **~4300ms**
  - **Sonra cache miss:** ~510-684ms (timeout 0.5s + tek inspect)
  - **Sonra cache hit:** ~11-50ms (Redis GET)
  - Auto-refresh 10s + cache TTL 5s → her 2 yenilemenin 1'i cache hit
  - **Hızlanma: cache miss 6-8x, cache hit 86-390x**

- **Etkilenen sayfalar (UI):**
  - `/admin` (özet) — `getQueueOverview` çağırır, otomatik hızlanır → 152ms HTTPS round-trip
  - `/admin/queue` — aynı endpoint + paralel `listFailedJobs` → 276ms HTTPS round-trip
- **Notlar:**
  - Geriye dönük uyumlu: `get_active_counts_by_queue` + `get_worker_count` fn'leri korundu (testler + olası dış kullanım)
  - 21/21 unit test yeşil, TS clean
  - SQLAlchemy `AsyncSession concurrent operations not permitted` bug'ı (ilk commit'te yakalandı, hotfix ile DB sıralıya alındı — broker async başladığı için yine paralel ilerler)
  - Maintenance task'ları ana refresh'i bloklamaz: 30s interval bağımsız

## [2026-05-08] update | Epic #443 follow-up #468 — bakım görevleri (backfill/retry) admin panelde

- **Kaynak/Tetikleyici:** Kullanıcı admin queue sayfasında 5 backfill/retry maintenance task'ı (görsel + haber işleme boru hatları) görmek + manuel tetiklemek istedi.
- **Etkilenen sayfalar:** [[queue-management]] — yeni "Bakım görevleri" bölümü (5 task listesi + tracking mimarisi + endpoint'ler)
- **Yeni:** 0 wiki page
- **Güncellendi:** Backend + frontend + 1 PR ([#469](https://github.com/selmanays/nodrat/pull/469)):
  - `core/maintenance_tracker.py` (yeni) — Redis-backed Celery signal hook tracker
  - `workers/celery_app.py` — task_prerun + task_postrun signal handlers (sadece TRACKED_TASKS)
  - `api/admin_queue.py` — `GET /admin/queue/maintenance` + `POST .../{task_name}/run-now`
  - `apps/web/src/app/admin/queue/page.tsx` — alt bölümde "Bakım görevleri" kartı
- **Production etki (deployed 2026-05-08 22:00 UTC):**
  - 5 task admin panelde görünür: stuck haber yakalama, başarısız haber tekrar dene, bekleyen görsel VLM kuyruğa al, başarısız görsel tekrar dene, eksik chunk yakalama
  - Manuel test: `tasks.articles.backfill_missing_chunks` admin tetiklendi → status=succeeded, dispatched=0 (chunks zaten var)
  - 21/21 unit test yeşil
- **Notlar:**
  - `triggered_by` ayrımı (admin vs beat) signal handler'da kapsam dışı — gelecekte Celery task headers ile yapılabilir
  - Tracker key TTL 24h — task hiç çalışmazsa "Henüz çalıştırılmadı" gösterilir

## [2026-05-08] update | Epic #443 follow-up — alarm 396 → 30 unresolved (%92), bulk actions, AA SPA tanısı

- **Kaynak/Tetikleyici:** Epic #443 sonrası "sonraki iterasyonlar" — 4 yeni alt-issue açıldı (#460 AA extract, #461 drill-down, #462 bulk actions, #463 discovered_timeout backfill); 3'ü teslim edildi, #461 sonraki oturuma kaldı.
- **Etkilenen sayfalar:** [[queue-management]] (baseline tablosu güncellenmedi — bu log entry'de delta tutuldu, page page'de "production etki" tablosu Epic close-out anındaki snapshot'ı temsil eder)
- **Yeni:** 0 wiki page
- **Güncellendi:** Aşağıdaki kod tabanı:
  - PR [#464](https://github.com/selmanays/nodrat/pull/464) (#463) — `discovered_timeout` 88 legacy satır auto-resolve migration
  - PR [#465](https://github.com/selmanays/nodrat/pull/465) (#460) — AA SPA migration tanısı + 187 extract failure warning auto-resolve migration
  - PR [#466](https://github.com/selmanays/nodrat/pull/466) (#462) — bulk retry/resolve endpoints + UI multi-select toolbar (3 yeni unit test, 18/18 yeşil)
- **Production etki kümülatif (Epic #443 + follow-up, 2026-05-08 21:30 UTC):**
  - failed_jobs unresolved: **396 → 30** (−366, **%92 azalma**)
  - Geriye kalan: 28 article.fetch_detail (gerçek HTTP fail) + 2 article.extract (evrensel)
  - severity dağılımı: 30 error + 187 warning (AA SPA) + 91 permanent_info (duplicate_content + discovered_timeout)
  - Bulk endpoints canlı: `/admin/queue/failed/bulk-retry`, `/admin/queue/failed/bulk-resolve` (max 200 id)
- **AA SPA tanısı (önemli karar girdisi):**
  - aa.com.tr Tailwind + JS-rendered SPA mimarisine geçmiş
  - Statik HTML body skeleton placeholder'lar, JSON-LD `articleBody` sadece 83 char özet
  - Mevcut site_profiles selector'ları (`article, .detay, .haber-detay`) artık boş wrapper'lara denk geliyor
  - Kullanıcı seçenekleri (#460 issue comment'inde): (1) `sources.is_active=false` geçici disable, (2) Playwright JS-render (#71 LATER cut-list), (3) AA-specific JSON-LD özet kabul (önerilmez, kalite düşer)
- **Notlar:**
  - PR-C (drill-down panel #461) bir sonraki oturuma bırakıldı — alarm seviyesi 30'a düştüğü için aciliyet düştü
  - `crawler_jobs` tablosu hala ölü (artık hiç write yok) — kaldırma vs audit ledger kararı açık (öneri için ayrı issue)
  - `tasks.maintenance.detect_stale_discovered` task gerek yok — orphan article zaten 0 (sistem düzgün)
  - CI manuel: kullanıcı GitHub Actions kredisi bittiği için tüm merge'ler `--admin`, deploy ssh+rsync ile manuel yapıldı

## [2026-05-08] ingest | Epic #443 — Admin queue sayfası overhaul (4 PR + 1 yeni concept)

- **Kaynak/Tetikleyici:** Kullanıcı `/admin/queue` sayfasını incelerken iki yapısal hata fark etti: (1) "41 sırada" + "0/0 24h" kartları yanlış veri gösteriyordu çünkü hiçbir Celery task `crawler_jobs` tablosuna yazmıyordu; (2) "364 unresolved" alarmı gerçek hata değil, %20'si RSS re-emit info kaydıydı.
- **Etkilenen sayfalar:**
  - `concepts/`: **YENİ** [[queue-management]] — Celery broker introspection + DLQ severity 3-tier + admin retry akışı + production baseline before/after tablo
  - `topics/`: [[data-pipelines]] (kuyruk haritası → 4 ana queue celery task_routes ile birebir, [[queue-management]] backlink)
- **Yeni:** 1 concept page ([[queue-management]])
- **Güncellendi:** Epic + 4 PR ile aşağıdaki kod tabanı:
  - PR [#447](https://github.com/selmanays/nodrat/pull/447) — Celery broker depth + retry Celery `apply_async` dispatch
  - PR [#449](https://github.com/selmanays/nodrat/pull/449) — `ArticleImage.processed_at` smoke hotfix
  - PR [#454](https://github.com/selmanays/nodrat/pull/454) — `failed_jobs.severity` migration + duplicate_content auto-resolve backfill
  - PR [#456](https://github.com/selmanays/nodrat/pull/456) — Frontend pagination + severity badge + label fix + 10s auto-refresh
- **Production etki (deployed 2026-05-08 19:30 UTC):**
  - `failed_jobs` unresolved: **396 → 305** (−91, %23 azalma — 74 duplicate_content auto-resolve + 17 yeni RSS re-emit otomatik permanent_info)
  - 4 kuyruk kartından 13/16 hücre artık gerçek broker veri (önce yapısal olarak yanlış)
  - Crawl 24h success: 311 / fail: 246 (önce 0/0)
  - Event 24h success: 275 (yeni agenda card)
  - Image VLM 24h success: 377 (yeni VLM processed)
  - Worker count: 5 (broker bağlantı sağlığı yeni metrik)
  - UI: 305 kaydın tamamına pagination ile erişim (önce sadece ilk 50)
  - Retry butonu Celery worker'a gerçek `apply_async` (önce sadece DB ledger)
- **Notlar:**
  - `crawler_jobs` tablosu artık tamamen boş yazma — gelecekte ya kaldırılır ya admin retry audit'e dönüştürülür (karar verilmeli, ayrı issue önerisi)
  - 175 `article.extract` failure ve 88 `article.discovered_timeout` ASIL kalan sorun — kazıma kalitesi tarafında ayrı incelemenin konusu
  - PR-3 sınırlı tutuldu (sadece pagination + severity + auto-refresh) — drill-down panel + bulk actions sonraki iterasyona kaldı
  - CI manuel: kullanıcının GitHub Actions kredisi bittiği için tüm merge'ler `--admin` ile, deploy ssh + rsync ile manuel yapıldı

## [2026-05-08] update | MVP-2.1 epic close-out — endpoint refactor + UI sekmesi + 2 yeni locked decision

- **Kaynak/Tetikleyici:** GitHub PR [#441](https://github.com/selmanays/nodrat/pull/441) (closes [#440](https://github.com/selmanays/nodrat/issues/440)) — `mvp-2-1-delta` endpoint kötü adlandırılmış (milestone-bound) → jenerik refactor + browser UI eklendi. Önceki preparation: PR [#431](https://github.com/selmanays/nodrat/pull/431) (closes #429, #432).
- **Etkilenen sayfalar:**
  - `decisions/`: **YENİ** [[endpoint-naming-policy]] (production endpoint adlandırma kuralı), **YENİ** [[pipeline-observability-location]] (`/admin/rag` LLM, `/admin/observability` infra)
  - `topics/`: [[pipeline-performance-baseline]] (PR #418/#431/#441 satırları + telemetry hooks 3 madde tikle + 2026-05-15 production ölçüm placeholder)
- **Yeni:** 2 locked decision sayfası
- **Güncellendi:** 1 topic sayfası (pipeline-performance-baseline)
- **Notlar:**
  - Eski `GET /admin/dashboard/mvp-2-1-delta` SİLİNDİ → yeni `GET /admin/rag/pipeline-comparison` (jenerik tarih aralığı parametreleri).
  - UI: `/admin/rag` sayfasına "Performans" sekmesi (7. sekme). Browser üzerinden admin login ile kullanılabilir — JWT manuel kopyalama gerekmez.
  - **MVP-2.1 epic [#391](https://github.com/selmanays/nodrat/issues/391) kod kapsamı tamamlandı** (7/7 sub-issue + 5 PR: #411, #416, #418, #431, #441). Production data ile final acceptance ölçümü 2026-05-15 sonrası yapılacak (post window 7-gün dolduğunda).
  - **Production verisi alındı (2026-05-08T15:55Z):** 2026-05-01..05-08 dönemi için 10,972 LLM chat çağrısı, %81 cache hit ratio, %1.7 halü oranı (hedef <%2 ✓). Ama bu pencere PR #418 deploy'unu kapsıyor — temiz pre/post karşılaştırması için 2026-05-15 sonrası gerek.
  - Karar 1: **Endpoint adı milestone-bound olamaz** ([[endpoint-naming-policy]]). Bu kural retroaktif değil — proaktif. Yeni PR'larda enforce edilir.
  - Karar 2: **Yeni LLM/pipeline gözlem aracı `/admin/rag`'a sekme** ([[pipeline-observability-location]]). `/admin/observability` infrastructure-only kalır.

## [2026-05-08] correction | data-pipelines.md §1 Kural A4 — gerçek mekanizma (slug varyasyonları, UTM değil)

- **Kaynak/Tetikleyici:** Kullanıcı "38 duplicate_content nedir, nasıl tespit ediyoruz, neye göre, wiki güncel mi?" sorusu. Production örnekleri incelenince Kural A4'te yanlış bir iddia tespit edildi.
- **Etkilenen sayfalar:** [[data-pipelines]] §1 Kural A4
- **Yeni:** 0
- **Güncellendi:** 1 sayfa (Kural A4 yeniden yazıldı)
- **Düzeltilen iddia:** Eski metin "canonicalize_url'in tracking parametrelerini farklı canonical hesaplaması nedeniyle" diyordu — YANLIŞ. `canonicalize_url` ([cleaning.py:94-119](../apps/api/app/core/cleaning.py:94)) UTM/fbclid/gclid vb. tüm tracking parametrelerini düzgün strip ediyor.
- **Gerçek kök neden:** Yayıncı RSS feed'inin aynı haberi **path/slug varyasyonlarıyla** emit etmesi. canonicalize_url path'i değiştirmiyor, sadece query'yi temizliyor. Production örneği: Evrensel `chpyi` (yapışık) vs `chp-yi` (tireli) slug — aynı haber, iki ayrı canonical_url, ikisi de DB'ye giriyor, fetch_detail ikincisi `(source_id, real_content_hash)` UNIQUE'e çarpıyor.
- **Eklenen detay:**
  - Hash mekanizması: `compute_content_hash() = SHA-256(re.sub(r"\s+", " ", text.lower().strip()))` (whitespace + lowercase normalize, sonra SHA-256)
  - UNIQUE constraint kayıt: `uq_articles_source_content_hash` UNIQUE `(source_id, content_hash)`
  - İki aşamalı hash: discover'da provisional (summary/title), fetch_detail'de real (cleaned.clean_text)
  - Production örneği tablosu (chpyi vs chp-yi case)
  - Diğer nadiren oluşan A4 nedenleri: crawler race condition (paralel poll). Republish ise (canonical aynı kalır) discover'da yakalanır, A4'e düşmez.
- **Branch:** `wiki/fix-kural-a4-real-mechanism`
- **Ders:** Wiki yazarken kod davranışını VARSAYMAK yetmez — production örneklerine bakarak doğrulamak gerekiyor. UTM tracking iddiası mantıklı görünüyordu ama gerçek mekanizma tamamen farklıydı (slug variation). DLQ'daki 38 duplicate_content entry'sinin URL'lerine bakmak yarım dakika sürdü ve doğru tabloyu çıkardı.

## [2026-05-08] update | data-pipelines.md §1 article kuyruk discipline + Kural A1-A5 (#433/#436 dersi)

- **Kaynak/Tetikleyici:** Kullanıcı admin panel'de [/admin/articles](https://nodrat.com/admin/articles) "Keşfedildi: 126" + "Başarısız: 60" gördü; image pipeline'a yaptığımız self-healing iyileştirmesinin article için aynı kalıbını istedi. Plan onaylandı (4 fazlı: B + C + E + opsiyonel D).
- **Etkilenen sayfalar:** [[data-pipelines]] (Pipeline 1 §Hata akışı genişletildi + yeni §Kuyruk discipline + freshness kuralları, 5 alt madde A1-A5)
- **Yeni:** 0
- **Güncellendi:** 1 sayfa (~140 satır eklendi)
- **Eklenen 5 kural (image §4 ile paralel yapı):**
  - **A1) Backfill discovered** (5 dk beat, batch=100, 72h freshness): RSS poll sonrası dispatch edilen fetch_detail Redis broker'da kaybolursa (worker crash, OOM) backfill yakalar. Idempotent.
  - **A2) Retry-failed** (saatlik :25 beat, batch=50, 72h cutoff): failed → discovered UPDATE + dispatch. Image retry (:20) ile çakışmaz.
  - **A3) Transient vs permanent classification:** `_TRANSIENT_EXCEPTIONS` listesi (`httpx.TimeoutException`, `OperationalError`, `ConnectionError`). IntegrityError DEĞİL — explicit handler. Eski `autoretry_for=Exception` "Bug sentinel" pattern'iyle 124 article stuck kalıyordu.
  - **A4) Duplicate content (RSS re-emit pattern):** UTM tracking parametre farklılığı → canonicalize_url farklı çıkıyor → discover'da iki ayrı article row → ikinci fetch_detail commit `IntegrityError: uq_articles_source_content_hash`. Çözüm: same-session rollback + `_record_failure(job_type='article.duplicate_content')`. Kod örneği eklendi (#434, #435 MissingGreenlet hotfix dersi).
  - **A5) Drenaj sağlığı izleme:** 3 SQL query (status dağılım, stale ratio, DLQ recent), worker log grep, alarm tetikleyicileri.
- **Production verify (deploy sonrası):**
  - Faz B (#434/#435) deploy → 2 manuel dispatch ile IntegrityError handler doğrulandı (article 'failed', DLQ 'duplicate_content' entry, MissingGreenlet kaybolmuş).
  - Faz C (#437) deploy + manuel backfill + manuel retry_failed:
    - cleaned: 2550 → 2580 (+30, başarıyla işlenenler)
    - discovered: 124 → 88 (kalan 88'in tamamı stale >72h, doğru bypass)
    - failed: 62 → 78 (+16 duplicate_content olarak işaretlendi)
    - DLQ son 15 dk: 38× duplicate_content, 17× extract conf<0.6, 1× fetch_detail
- **Branch:** `wiki/article-pipeline-rules`
- **Cross-link:** [#433](https://github.com/selmanays/nodrat/issues/433) [#434](https://github.com/selmanays/nodrat/pull/434) [#435](https://github.com/selmanays/nodrat/pull/435) [#436](https://github.com/selmanays/nodrat/issues/436) [#437](https://github.com/selmanays/nodrat/pull/437)
- **Ders:** Image pipeline'da öğrendiğimiz pattern'leri (transient classification, IntegrityError handler, 5dk backfill + saatlik retry-failed, 72h freshness window) article için aynısını uygulamak fizibıl. Sentinel pattern'inin generic olduğunu gördük — herhangi bir worker pipeline (embedding, clustering, RAPTOR) için de aynı yapı gerekir gerekirse. Open follow-up: Pipeline 2/3/5 için aynı discipline kuralları yazılacak mı? (scope dışı — bu kullanıcının ihtiyaç görmesine bağlı).

## [2026-05-07] init | wiki iskeleti kuruldu

- **Kaynak/Tetikleyici:** Kullanıcı isteği — LLM Wiki örüntüsünü Nodrat'a uygulamak.
- **Etkilenen sayfalar:** —
- **Yeni:** wiki/{README,index,log,SETUP}.md, wiki/_templates/{entity,concept,topic,decision,source}.md, kök CLAUDE.md, .mcp.json, .obsidian/{app,core-plugins}.json.
- **Güncellendi:** .gitignore (Obsidian section), .env.example (OBSIDIAN_API_KEY).
- **Notlar:** Obsidian MCP server: `mcp-obsidian` (Markus Pfundstein, PyPI üzerinden `uvx mcp-obsidian`). Kullanıcı manuel Obsidian + Local REST API plugin kuracak — bkz. [SETUP.md](SETUP.md).

## [2026-05-07] ingest | architecture.md (pilot)

- **Kaynak/Tetikleyici:** Pilot ingest — şablonları stres-test etmek için en zengin doküman seçildi (`docs/engineering/architecture.md` v0.1).
- **Etkilenen sayfalar:**
  - `sources/`: [[architecture-md]]
  - `entities/`: [[deepseek]], [[claude-haiku-4-5]], [[nim-bge-m3]], [[contabo-vps]], [[celery-worker]]
  - `concepts/`: [[provider-abstraction]], [[hot-cold-tier]], [[binary-quantization]]
  - `decisions/`: [[deepseek-default-llm]], [[claude-haiku-premium-llm]], [[contabo-vps-hosting]]
  - `topics/`: [[llm-provider-strategy]]
- **Yeni:** 13 (1 source + 5 entity + 3 concept + 3 decision + 1 topic)
- **Güncellendi:** wiki/index.md (sayfa kataloğu + istatistik), wiki/log.md (bu kayıt)
- **Notlar — 3 ÇELİŞKİ tespit edildi:**
  1. **Hosting:** architecture.md §0 "Hetzner CCX23" yazıyor; INDEX §4 "Contabo VPS 40" diyor. INDEX güncel (v1.4, 2026-05-07). Kaynak doküman v0.2 sürüm güncellemesi gerekiyor → `nodrat-dev` ile issue/PR akışı.
  2. **Backup:** architecture.md §9.1 "B2 (encrypted)" diyor, §5.4 ve INDEX "Contabo Object Storage" diyor (MVP-1.5'te geçiş). §9 güncellenmeli.
  3. **Embedding model:** Adapter adı `nim_bge_m3` ama gerçekte `nvidia/nv-embedqa-e5-v5` serve ediliyor (cosine ≈ 0, orthogonal vs. local BAAI/bge-m3). #345 migration ile çözülecek.
- **Açık sorular:** Yer yer "TODO" bölümleri sayfalarda (NIM rate limit detayı, eval gate test set, HNSW memory footprint, free-tier abuse alarm, comparison_generation task_type net mapping, vb.).

## [2026-05-08] ingest | risk-register.md

- **Kaynak/Tetikleyici:** Kullanıcı "devam" — pilot sonrası önerdiğim sıralı ingest planının #1 dokümanı.
- **Etkilenen sayfalar:**
  - `sources/`: [[risk-register-md]]
  - `entities/` (risk objeleri): [[risk-fsek-telif]], [[risk-kvkk-violation]], [[risk-source-fragility]], [[risk-cost-runaway]]
  - `concepts/`: [[risk-scoring]], [[mvp-cut-list-method]], [[kill-switch]]
  - `decisions/`: [[twenty-five-word-quote-cap]], [[mvp-1-scope-lock]], [[pii-redaction-mandatory]]
  - `topics/`: [[risk-catalog]], [[mvp-1-scope]], [[mvp-roadmap]]
- **Yeni:** 14 (1 source + 4 risk-entity + 3 concept + 3 decision + 3 topic)
- **Güncellendi:** wiki/index.md (27 sayfa toplam, kategori bazlı gruplanma + 6 locked decision), wiki/log.md (bu kayıt)
- **Notlar — 3 skor anomalisi tespit edildi (kaynak doküman güncellemesi gerekli):**
  1. **R-FIN-02 (DeepSeek API instability) skor 9** ama §2.2 sarı tablosunda. → 🔴 olmalı.
  2. **R-MKT-02 ("ChatGPT yeter") skor 9** ama §2.2 sarı tablosunda. → 🔴 olmalı.
  3. **R-MKT-03 (Düşük WTP) skor 9** ama §2.2 sarı tablosunda. → 🔴 olmalı.
  Aksiyon: `nodrat-dev` ile risk-register.md sürüm bump (v0.2 → §2.1/§2.2 yeniden organize).
- **Çapraz cross-link kapsamı:** Bu ingest sayesinde 27 sayfanın tamamı en az 2 backlink alıyor. [[risk-catalog]] hub-of-hubs (top mitigation kapsama matrisi).
- **Açık locked decisions çağrısı:** Risk-register §3 detayında 4 yeni locked decision sayfası açılması gerekti — bu, INDEX §4'teki tüm "✅ locked" listesinin de wiki'ye taşınmasının zaman alacağının göstergesi (henüz 6/22).
- **Sürpriz bulgu:** MVP-2 -19 hafta erken delivered (2026-09-29 hedef → 2026-05-07). Resmi gerekçe doküman yok. Discovery güçlü çıkması + AI agent verimliliği + MVP-1.x'lerin MVP-2 feature'larını "kapması" hipotezleri [[mvp-roadmap]] ve [[mvp-1-scope]]'da dokümante edildi.
- **Sıradaki ingest önerileri:**
  - [docs/product/prd.md](../docs/product/prd.md) — kanonik kök, ~12 entity/concept tahmini
  - [docs/strategy/discovery-validation.md](../docs/strategy/discovery-validation.md) + [validation/research-findings.md](../docs/validation/research-findings.md) — persona-p1a, persona-p1b entity'leri
  - [docs/engineering/prompt-contracts.md](../docs/engineering/prompt-contracts.md) — R-PRD-01 (halü) detay + citation %100 / halü <%2 thresholds
  - [docs/engineering/data-model.md](../docs/engineering/data-model.md) — 12 tablonun her biri için entity

---

## [2026-05-08] lint+update | deepseek-default-llm.md eskimiş iddia düzeltildi

- **Kaynak/Tetikleyici:** Kullanıcı bildirimi — sayfa `deepseek-v3.1-terminus / NIM endpoint` diyor ama kod tabanı artık `deepseek-v4-flash / native DeepSeek API` kullanıyor.
- **Etkilenen sayfalar:** [[deepseek-default-llm]]
- **Yeni:** 0
- **Güncellendi:** 1
- **Doğrulama:** [apps/api/app/providers/deepseek.py:61](../apps/api/app/providers/deepseek.py) → `DEEPSEEK_CHAT_DEFAULT_MODEL = "deepseek-v4-flash"`. Class `DeepSeekProvider` (DeepSeek native API). Registry routing name `deepseek_v3` korunmuş (backward-compat).
- **Migration commit zinciri:** #163 (native API provider) → #361 (model adı v4-flash) → #378 (smoke fixes) → #379 (thinking-disabled, 2026-05-07).
- **Düzeltilen iddialar:** model adı (v3.1-terminus → v4-flash), provider (NIM → native), API key (NIM_API_KEY → DEEPSEEK_API_KEY), adapter dosya yolu (packages/model-providers/nim_chat.py → apps/api/app/providers/deepseek.py), "Native DeepSeek API reddedildi" → kabul edildi (#163), §Ek not'taki yanlış varyant tablosu (v4-flash "timeout sorunları" iddiası tam tersine — production default).
- **⚠️ Çelişki bloğu eklendi:** docs/engineering/architecture.md §4.2/§4.3 hâlâ NIM/v3.1-terminus diyor — wiki güncel, kaynak eskimiş. CLAUDE.md §1.1 gereği docs/ LLM tarafından yazılmaz → ayrı `nodrat-dev` görevi açılmalı.
- **Branch disiplini:** Bu güncelleme `wiki/deepseek-v4-flash-update` dedicated branch'inde (CLAUDE.md §1.3). Feature worktree dışında.
- **Açık çelişki sayısı:** 6 → 7 (yeni: deepseek-default-llm vs architecture.md).

---

## [2026-05-08] lint+update | DeepSeek migration ailesi tam temizlendi

- **Kaynak/Tetikleyici:** İlk turdan sonra kullanıcı "hata kalmasın wiki'de" istedi. DeepSeek migration (NIM/v3.1-terminus → native API/v4-flash) wiki ailesinde 5 ek dosyada faktüel referans bulundu.
- **Etkilenen sayfalar:** [[deepseek]] (entity, neredeyse tam yeniden yazıldı), [[provider-abstraction]] (concept, adapter listesi + routing pseudocode), [[architecture-md]] (source, 2 ana çıkarım + yeni ⚠️ Çelişki bloğu + sürüm takibi), [[nim-bge-m3]] (entity, "ortak API key" iddiası düzeltildi), [[llm-provider-strategy]] (topic, TL;DR + cost tablosu + risk tablosu yeniden yazıldı), [[mvp-1-scope-lock]] (decision quote), [[claude-haiku-premium-llm]] (routing pseudocode model adı), wiki/index.md (entity + decision listing açıklamaları).
- **Yeni:** 0
- **Güncellendi:** 8 (deepseek-v3 + provider-abstraction + architecture-md + nim-bge-m3 + llm-provider-strategy + mvp-1-scope-lock + claude-haiku-premium-llm + index.md)
- **Anahtar düzeltmeler:**
  - `deepseek-ai/deepseek-v3.1-terminus` → `deepseek-v4-flash` (8 yer)
  - "NIM endpoint default" → "NIM endpoint fallback" (5 yer)
  - "Tek API key (NIM_API_KEY)" → "DeepSeek chat: DEEPSEEK_API_KEY ayrı, embedding: NIM_API_KEY" (3 yer)
  - "DeepSeek V3 (NIM free) cost $0" → "DeepSeek native $0.27/$1.10 + %75 kampanya 2026-05-31'e kadar" (cost tablosu)
  - Routing pseudocode `DeepSeekProvider(model="deepseek-v3")` → `model="deepseek-v4-flash"` (3 yer)
  - Adapter listesi: NimChatProvider primary → fallback; DeepSeekProvider eklendi
- **Korunan:** Slug `deepseek-v3` ve registry name `deepseek_v3` backward-compat için bilinçli olarak korundu (`generation_log.provider_name` migration boyunca aynı).
- **⚠️ Çelişki sayısı korundu:** 7 — wiki içi tutarlılık sağlandı; tek açık çelişki `wiki ↔ docs/engineering/architecture.md` (kaynak v0.1 hâlâ NIM/v3.1-terminus diyor). Bu `nodrat-dev` görevi olarak chip ile spawn edildi.

---

## [2026-05-08] re-sync+lint | architecture.md v0.2 + ⚠️ DeepSeek çelişki cleanup

- **Kaynak/Tetikleyici:** [PR #405](https://github.com/selmanays/nodrat/pull/405) (`docs(architecture): DeepSeek migration sync — §0/§4.2/§4.3`) main'e merge edildi → `architecture.md` v0.1 → v0.2. PR #403 ile eklenen ⚠️ DeepSeek migration çelişki bloğu artık resolved.
- **Etkilenen sayfalar:** [[deepseek-default-llm]] (⚠️ blok kaldırıldı + Kaynaklar listesi güncellendi), [[deepseek]] (Kaynaklar listesi "(eskimiş)" notları temizlendi), [[architecture-md]] (frontmatter v0.1 → v0.2, ana çıkarımlar #3 yeniden yazıldı, ⚠️ DeepSeek bloğu kaldırıldı, sürüm değişikliği takibi v0.2 satırı eklendi, "üretilen wiki sayfaları" listesi temizlendi), wiki/index.md (istatistik: çelişki 7 → 6, son re-sync eklendi).
- **Yeni:** 0
- **Güncellendi:** 4
- **Çelişki muhasebesi:**
  - **Resolved (1):** `wiki ↔ docs/engineering/architecture.md §0/§4.2/§4.3` DeepSeek migration → kaynak v0.2 ile hizalandı (#405).
  - **Hâlâ açık (3 architecture):** Hosting (§0 Hetzner CCX23 vs INDEX Contabo VPS 40), Backup (§9.1 B2 vs §5.4 Contabo OS), Embedding model (§4.2 nim_bge_m3 ↔ baai/bge-m3 orthogonal).
  - **Hâlâ açık (3 risk-register):** R-FIN-02, R-MKT-02, R-MKT-03 skor anomalileri (skor 9 ama §2.2 sarı tablosunda).
  - **Toplam:** 7 → 6.
- **Branch disiplini:** Bu temizlik `wiki/contradiction-cleanup` dedicated branch'te (CLAUDE.md §1.3). Feature worktree dışında, ayrı kısa-ömürlü worktree.

---

## [2026-05-08] lint+update | Hetzner/B2 wiki temizliği — production hep Contabo netliği

- **Kaynak/Tetikleyici:** Kullanıcı net bildirim: "Hetzner ile hiç alakamız yok, B2 de kullanmıyoruz". Wiki sayfaları Hetzner CCX23 → Contabo migration'ını historical fact olarak gösteriyordu — ama production hiç Hetzner üzerinde çalışmadı; sadece architecture.md draft dilinde Hetzner geçiyordu.
- **Doğrulama (kod tabanı):** `infra/deploy.sh:22` + `.github/workflows/deploy.yml` Contabo IP'sini (164.68.107.205) kullanıyor; `apps/api/app/config.py` + `infra/backup.sh` Contabo Object Storage endpoint'i (`eu2.contabostorage.com`) kullanıyor. Hetzner stringi kod tabanında yok. B2 referansları sadece `infra/restore.sh:44-46` legacy stub + `docs/operations/deployment-manual-steps.md` doc-debt.
- **Memory dosyası onayı:** `~/.claude/projects/-Users-selmanay-Desktop-nodrat/memory/manual_deploy.md` "Eski VPS (decommission edilecek): 173.212.238.104 (VPS 10, 4 vCPU/8GB)" diyor — eski production Contabo VPS 10'du, Hetzner değil.
- **Etkilenen sayfalar:**
  - [[contabo-vps]] entity — TL;DR + Rolü/faz ilişkisi yeniden yazıldı (Contabo VPS 10 → VPS 40 yükseltme; Hetzner sadece "draft mention, hiç deploy edilmedi" notu olarak)
  - [[contabo-vps-hosting]] decision — Karar quote + Bağlam + Alternatifler tablosu güncellendi; ⚠️ Çelişki bloğu çok daha keskin gerekçelerle yeniden yazıldı (architecture.md §0/§2.1/§5.1/§9.1/§13 stale referans listesi; chip-spawn aksiyonu)
  - [[architecture-md]] source — ⚠️ Hosting/Backup blokları yeniden yazıldı (production hep Contabo netliği + #330/`714d5b2` migration kanıtı); §12.1 darboğaz açık karar nüansı; sürüm değişikliği takibi yeni satır
  - [[mvp-roadmap]] topic — MVP-1.5 changelog "Hetzner CCX23 → Contabo VPS 40" → "Contabo VPS 10 → Cloud VPS 40 yükseltme"
  - [[risk-register-md]] source — Ana çıkarımlar #4 aynı düzeltme
  - wiki/index.md — decision listing açıklaması + istatistik açık çelişki notları güncellendi (Hosting çelişkisi rephrased)
- **Yeni:** 0
- **Güncellendi:** 6
- **Korunan:** B2 historical mention'ları korundu (INDEX "öncesinde Backblaze B2" diyor, MEMORY "eski .env/B2" diyor — gerçek MVP-1 era backup'tı, MVP-1.5'te migrate edildi).
- **Açık çelişki muhasebesi:** 6 → 6 (rephrased; sayı değişmedi). architecture.md hâlâ §0/§2.1/§5.1/§9.1/§13'te Hetzner/B2 — ayrı `nodrat-dev` chip ile temizlenecek.
- **Branch:** `wiki/hetzner-b2-cleanup` (CLAUDE.md §1.3).

---

## [2026-05-08] re-sync+lint | architecture.md v0.3 + Hetzner/B2 ⚠️ blokları kaldırıldı

- **Kaynak/Tetikleyici:** [PR #410](https://github.com/selmanays/nodrat/pull/410) main'e merge edildi (commit `0b57986`, closes [#409](https://github.com/selmanays/nodrat/issues/409)). architecture.md v0.2 → v0.3 — §0/§1/§2.1/§5.1/§7/§8/§9/§12.1/§13 stale Hetzner/B2 referansları kod tabanına hizalandı.
- **Etkilenen sayfalar:**
  - [[architecture-md]] source — frontmatter v0.2 → v0.3, doküman bilgisi re-sync history, "Ne içerir" özeti güncel forma, ana çıkarımlar #10 backup hedefi düzeltildi, "üretilen wiki sayfaları" listesinde [[contabo-vps-hosting]] " — ⚠️ kaynakla çelişkili" notu kaldırıldı, ⚠️ Hosting + ⚠️ Backup blokları silindi (resolved), §12.1 darboğaz açık karar nüansı v0.3 ile uyumlu, sürüm takibi v0.3 satırı eklendi
  - [[contabo-vps-hosting]] decision — ⚠️ Çelişki bloğu silindi (resolved); karar tarih notu v0.3 referansı ekledi; "Bağlam" notu draft Hetzner'ın v0.3 ile temizlendiğini belirtir; alternatifler tablosu satır güncellendi; Kaynaklar listesi
  - wiki/index.md — Sources listesinde architecture-md "1 çelişki" (hosting+backup resolved); istatistik açık çelişki **6 → 4**, son re-sync 2026-05-08 v0.3 (#410)
- **Yeni:** 0
- **Güncellendi:** 4
- **Çelişki muhasebesi:**
  - **Resolved (2):** wiki ↔ architecture.md §0/§2.1 Hosting (Hetzner production hiç kullanmadı netliği), §0/§5.1/§9.1/§13 Backup (B2 → Contabo OS migration). Her ikisi de #410 ile kaynak doküman hizalandı, wiki ⚠️ blokları kaldırıldı.
  - **Hâlâ açık (1 architecture):** §4.2 Embedding model (nim_bge_m3 ↔ baai/bge-m3 orthogonal) — #345 migration ile çözülecek.
  - **Hâlâ açık (3 risk-register):** R-FIN-02, R-MKT-02, R-MKT-03 skor anomalileri.
  - **Toplam:** 6 → 4.
- **Branch:** `wiki/post-409-cleanup` (CLAUDE.md §1.3 — docs PR sonrası ayrı küçük wiki PR'ı).

---

## [2026-05-08] re-sync+lint | risk-register v0.2 + embedding "çelişki" → "açık migration" reclassification

- **Kaynak/Tetikleyici:**
  - [PR #414](https://github.com/selmanays/nodrat/pull/414) main'e merge edildi (commit `5e052ca`, closes [#413](https://github.com/selmanays/nodrat/issues/413)). risk-register.md v0.1 → v0.2 — R-FIN-02, R-MKT-02, R-MKT-03 (skor 9) §2.2 sarı'dan §2.1 kırmızıya taşındı (methodology §1.1 gereği).
  - Embedding "çelişki" durumu yeniden değerlendirildi: kod tabanı investigation `apps/api/app/config.py:128-146 use_local_embedding=False default`, `.env.example:100 DEFAULT_EMBEDDING_PROVIDER=nim_bge_m3`, #345/#346 scaffold merged ama re-embed task production'da koşturulmadı. Wiki ↔ docs **çelişki yok** (her ikisi tutarlı şekilde "nim_bge_m3 actually serves nv-embedqa-e5-v5, scaffold ready, re-embed pending" diyor) — bu bir wiki **etiketleme hatası**ydı. Reclassify "⚠️ Çelişki" → "🟡 Açık operasyonel migration".
- **Etkilenen sayfalar:**
  - [[risk-register-md]] source — frontmatter v0.1 → v0.2, doküman bilgisi re-sync history, ana çıkarımlar #1 v0.2 forma çevrildi (10 risk §2.1'de listendi), §Açık sorular bölümünden 3 anomali notu kaldırıldı (resolved), sürüm takibi v0.2 satırı eklendi
  - [[architecture-md]] source — ⚠️ Embedding bloğu 🟡 açık operasyonel migration formuna çevrildi (kod tabanı durumu detayıyla); sürüm takibi yeni satır
  - [[nim-bge-m3]] entity — "⚠️ Çelişki / kritik bilgi" başlığı "🟡 Açık operasyonel migration & kritik bilgi" olarak değişti; #345/#346 merged scaffold durumu + production durumu (`USE_LOCAL_EMBEDDING=false`) + gerçek kapanış kriteri eklendi; `last_op_status_check` frontmatter alanı
  - wiki/index.md — Sources listesinde [[architecture-md]] "0 çelişki" + "1 açık migration"; [[risk-register-md]] v0.2 (#414); istatistik **açık çelişki sayısı: 0** ✅ + "açık operasyonel migration: 1"
- **Yeni:** 0
- **Güncellendi:** 4
- **Çelişki muhasebesi (final):**
  - **Resolved (4):** wiki ↔ architecture.md DeepSeek migration (#403/#405/#407), Hosting (#408/#410/#412), Backup (#408/#410/#412), risk-register skor anomalileri R-FIN-02 + R-MKT-02 + R-MKT-03 (#414).
  - **Reclassified (1 → 0):** Embedding nim_bge_m3 — wiki ↔ docs çelişkisi değil, dokümante edilmiş açık operasyonel migration. Gerçek kapanış DB chunks + agenda_cards re-embed task çalıştırıldığında.
  - **Toplam açık çelişki:** 4 → **0** ✅
  - **Açık operasyonel migration:** 1 (embedding re-embed task)
- **Branch:** `wiki/post-414-cleanup` (CLAUDE.md §1.3 — docs PR sonrası ayrı küçük wiki PR'ı).

---

## [2026-05-08] correction | Embedding migration aslında #350 ile tamamlanmış (kullanıcı admin panel telemetry'siyle düzeltti)

- **Kaynak/Tetikleyici:** Kullanıcı admin panel ekranını gösterdi (RAG İzlencesi → Özellik Anahtarları): `llm.use_local_embedding` toggle **AÇIK**, son 24 saat metric `bge-m3 (local) 340 / bge-m3 (NIM yedek) 0`. Wiki'nin "açık operasyonel migration" iddiası yanlıştı — production tarafında migration 2026-05-06'da tamamlanmış.
- **Önceki investigation hatası:** Spawn edilen Explore agent sadece `apps/api/app/config.py:128 use_local_embedding=False` (env-var fallback default) ve `.env.example:100 DEFAULT_EMBEDDING_PROVIDER=nim_bge_m3` 'a baktı. Şunları kaçırdı:
  - **PR [#350](https://github.com/selmanays/nodrat/pull/350)** (`3366ab3`, 2026-05-06) — `feat(rag): NIM → local embedding migration + rerank eval (closes #345)`. `_reembed_chunks_async` + `_reembed_agenda_cards_async` task'ları `apps/api/app/workers/tasks/maintenance.py:522-697`'de
  - **Runtime config mekanizması (MVP-1.2 #262/#264):** `app_settings` Postgres tablosu + `SettingsStore` singleton (`apps/api/app/core/settings_store.py`) admin panel'den değer override ediyor; `config.py` default'u sadece DB row yoksa fallback
  - **`apps/api/app/api/admin_settings.py:257`** — `llm.use_local_embedding` runtime tunable
  - **Production telemetry** — kullanıcının ekranında NIM yedek 0 çağrı görünür kanıt
- **Etkilenen sayfalar:**
  - [[nim-bge-m3]] entity — neredeyse tam yeniden yazıldı: "legacy embedding provider, fallback only" başlığı, production telemetry tablosu, migration timeline (#350 dahil), runtime config mekanizması, kalan opsiyonel TODO (rename consideration, local rerank flip)
  - [[architecture-md]] source — 🟡 "Açık migration" bloğu ✅ "Embedding migration tamamlandı" formuna çevrildi; #350 + admin panel telemetry kanıtı; sürüm takibi correction satırı
  - wiki/index.md — Sources line'ı "tüm çelişkiler resolved"; istatistik açık operasyonel migration **1 → 0** ✅; opsiyonel "devam eden ops todo" notu (local rerank, çelişki değil)
- **Yeni:** 0
- **Güncellendi:** 3
- **Çelişki muhasebesi (gerçek final):**
  - Açık çelişki: **0** ✅
  - Açık operasyonel migration: **0** ✅ (embedding tamamlandı 2026-05-06 #350)
  - Opsiyonel ops todo: 1 (local rerank flip — çelişki değil, plan)
- **Ders alınan:** İleride benzer "çelişki / migration" sorularında investigation **hem kod default'una hem de runtime config'e (app_settings + admin panel telemetry) bakmalı**. Memory dosyasına not eklenecek.
- **Branch:** `wiki/embedding-migration-complete` (CLAUDE.md §1.3).

---

## [2026-05-08] sync+rename | parallel session merge + nim/local split + deepseek rename

- **Kaynak/Tetikleyici:** Kullanıcı 3 sorun bildirdi: (1) Obsidian'da nim-bge-m3.md eski görünüyor, (2) dosya adı `local-bge-m3.md` olmalı mı / ayrı sayfa mı, (3) `deepseek-v3.md` adı yanıltıcı (v3 hiç kullanılmadı), v3 aliases içinde olmalı.
- **Tespit:** Lokal main 9 commit geride + working tree'de 11 dosyada uncommitted MVP-2.1 reality sync + 1 yeni page (`pipeline-performance-baseline.md`) işi vardı. Paralel oturumdan kalmış değerli iş — kayıp önlemi alındı.
- **Akış (A planı — yerel iş + sync):**
  1. Lokal mod'lar `/tmp/nodrat-local-mods-2026-05-08.patch` + `/tmp/nodrat-new-page-pipeline-baseline.md` snapshot'a alındı
  2. `git stash --include-untracked` ile lokal main temizlendi (stash@{0}: wiki-mvp-2.1-local-work-2026-05-08)
  3. `git pull --ff-only` — local main `4ad9ac1`'e geldi (origin/main, MVP-2.1 PR #418 dahil)
  4. Yeni worktree `wiki/sync-and-rename` `origin/main`'den açıldı
  5. Lokal iyileştirmeler her dosya için origin/main + local diff manuel merge
  6. Renames + split yapıldı
- **Etkilenen sayfalar (9):**
  - **Yeni:** [[local-bge-m3]] (production primary embedding, BAAI/bge-m3 local, #350 sonrası); [[pipeline-performance-baseline]] (MVP-2.1 baseline + tracking — paralel oturumdan kalan 202-satırlık sayfa)
  - **Rename:** `wiki/entities/deepseek-v3.md` → `wiki/entities/deepseek.md` (slug `deepseek-v3` → `deepseek`; eski slug aliases içinde — Obsidian search çalışmaya devam eder)
  - **Sadeleştirildi:** [[nim-bge-m3]] — fallback only rolüne çekildi (primary content [[local-bge-m3]]'e taşındı)
  - **Cross-link güncellendi (sed ile):** 14 dosyada `[[deepseek-v3]]` → `[[deepseek]]`
  - **MVP-2.1 reality sync (paralel oturum işi):** [[provider-abstraction]] (adapter listesi production state ile yeniden yazıldı), [[llm-provider-strategy]] (fallback chain production reality + risk tablosu güncel), [[mvp-roadmap]] (MVP-2.1 milestone block delivered eklendi + MVP-1.5 changelog'a embedding migration eklendi), [[deepseek-default-llm]] (runtime tunable correction), [[deepseek]] (registry path + routing düzeltildi), [[risk-cost-runaway]] (M7 satırı + PR #411/#416/#418 referansları)
  - **Hub:** wiki/index.md (Provider listing nim/local-bge-m3 split, Topics 4 → 5, Sources line, istatistik 27 → 29 sayfa)
- **Yeni:** 2 (local-bge-m3, pipeline-performance-baseline)
- **Güncellendi:** 9 (+ rename: deepseek-v3 → deepseek)
- **Korunan paralel session iyileştirmeleri:** Cache claim ⚠️ doğrulama notu (local-bge-m3 sayfasında), services/llm_router.py kaldırma notu, registry.py:80 fallback açıklaması, runtime config mekanizması netliği, MVP-2.1 PR #411/#416/#418 commit zinciri tracking.
- **Branch:** `wiki/sync-and-rename` (CLAUDE.md §1.3 — tek branch tüm değişiklikler).
- **İstatistik:** Toplam sayfa **27 → 29**, açık çelişki **0** ✅, açık migration **0** ✅.
- **Kullanıcı talimatı (PR merge sonrası):** `cd /Users/selmanay/Desktop/nodrat && git checkout main && git pull --ff-only` — Obsidian otomatik yansıtır.

---

> Sıradaki adım: kullanıcı onayı — local rerank flip planlama (`llm.use_local_rerank=false` → true, NIM rerank kalkar), yoksa sıradaki ingest (prd.md / discovery / prompt-contracts)?

## [2026-05-08] merge+deploy | MVP-2.1 PR #418 production'da — EPIC KAPANIŞ 🎯

- **Kaynak/Tetikleyici:** Kullanıcı kararı — α planı (PR #3: #392+#393 quality-critical batch). MVP-2.1 epic'in son sub-issue çifti.
- **Etkilenen sayfalar:** [[pipeline-performance-baseline]] (PR #418 tracking row + epic closure row + footnote).
- **Yeni:** 0
- **Güncellendi:** 1
- **Akış:**
  1. Branch `perf/mvp-2.1-batch-3-quality-critical` origin/main'den açıldı (PR #416 squash sonrası temiz)
  2. #392 implement: 4 SYSTEM_PROMPT_* tamamen STATIC, max_posts/tone user payload'undaki output_constraints'tan; PROMPT_VERSION 1.0.0 → 1.1.0; tone dynamic append kaldırıldı
  3. #393 implement: `retrieval.content_top_k` setting (default 5), `hybrid_search_agenda_cards(top_k=10)` → `top_k=content_top_k`, supplementary 8→4
  4. 3 yeni unit test (test_format_system_prompt_static_prefix_392, _routes_by_output_type, _unknown_output_type_falls_back)
  5. Lokal pytest: 17/17 PASS prompt + 29/30 PASS citation
  6. Lokal ruff: yeni hata yok (4 auto-fix uygulandı)
  7. Commit `8a89a4f` + push, PR [#418](https://github.com/selmanays/nodrat/pull/418) açıldı (MERGEABLE/UNSTABLE — CI runner outage devam)
  8. Admin override squash merge → commit `4ad9ac11`
  9. Manuel rsync + docker compose build/up VPS (skill protocol §Manuel deploy)
  10. Smoke test PASS: container healthy 6 sn'de, `/api/health` 200, startup logs temiz, prompt loading error yok.
- **MVP-2.1 epic kapanış özeti:**
  - 7/7 sub-issue closed (#392-#398), 3 PR (#411 + #416 + #418), epic [#391](https://github.com/selmanays/nodrat/issues/391)
  - Plan 2026-05-28 → gerçekleşen 2026-05-08 — **20 gün önde**
  - Tahmini etki: input token -%36, citation NIM call 6→1, settings DB call 9→2, latency P50 -300-500ms, \$/req -%25-35
- **⚠️ Eval-gated kuyruk:** PR #418 prompt v1.1.0 prod'da. Halü oranı + citation accuracy izleme 30-60 dk. Alarm fire ederse `4ad9ac11` revert.
- **Sonraki:** 24-48 saat production observation, `provider_call_logs` 7-günlük rolling avg query (TODO), MVP-3 cut-over kuyrukta.

## [2026-05-08] new-page | data-pipelines.md (8 boru hattı overview)

- **Kaynak/Tetikleyici:** Kullanıcı isteği — "şu an beklerken tüm boru hatlarımızı wikiye ekler misin? kaynak kazımadan, embedlemeye, reranklamaya, görsel işleme akışından, haber depolamaya, object storage kullanımına, x içeriği üretimine ve ücretsiz haber arama servisine kadar her şeyi". MVP-2.1 PR #418 production observation döneminde dokümantasyon işi.
- **Etkilenen sayfalar:**
  - `topics/`: [[data-pipelines]] (yeni, kapsamlı 8-pipeline overview)
  - `wiki/index.md`: Topics listesi 5 → 6; istatistik 29 → 30 sayfa
- **Yeni:** 1
- **Güncellendi:** 1 (index)
- **İçerik (8 pipeline + altyapı katmanı):**
  1. **Source Crawl** — RSS poll → discover → fetch detail → trafilatura clean → DB
  2. **Embedding** — chunk → NIM bge-m3 (nv-embedqa-e5-v5) → article_chunks.embedding 1024-dim
  3. **Clustering + Agenda Card** — pgvector cosine → event_clusters → DeepSeek synthesis → agenda_cards
  4. **Image VLM (process & discard)** — img URL → NIM Llama 4 Maverick → caption+OCR+depicts → article_images metadata only (5 TB/yıl → 90 GB/yıl, %98 azalma)
  5. **RAPTOR-Lite weekly** — daily cards → cluster → weekly summary cards (parent_card_ids zinciri)
  6. **/app/generate** — 6-adım RAG pipeline (planner → embed → search → rerank → content gen → citation). MVP-2.1 ile optimize edildi (3 PR: #411, #416, #418). Detay [[pipeline-performance-baseline]].
  7. **/ara public search** — anonim TOFU funnel, 10 req/min/IP rate limit, embed + RRF, register wall ile /app/generate'e yönlendirir
  8. **Object Storage + Cold Tier + Backup** — MinIO (hot, deprecated process & discard sonrası) + Contabo Object Storage (cold tier 30+gün + restic backup) + cron daily 04:00
- **Provider envanteri özeti:** DeepSeek v4-flash (3 pipeline: agenda + raptor + content gen), NIM bge-m3 (4 pipeline: chunk embed + cluster + citation + search), NIM rerank (1 pipeline), NIM Llama 4 Maverick VLM (1 pipeline), Anthropic Haiku 4.5 (Pro+ aktivasyon, Faz 2).
- **Cross-link:** Her pipeline için ilgili wiki entity/concept/decision/topic'ler işaretlendi.
- **Açık TODO:** Pipeline-level latency dashboard, cold tier restore drill, image VLM eval, public search Phase C, local provider flip eval gate'leri, RAPTOR monthly trigger.

## [2026-05-08] correction | data-pipelines.md + pipeline-performance-baseline.md embedding provider düzeltildi (production: LOCAL)

- **Kaynak/Tetikleyici:** Kullanıcı tespiti — "Embedding için neden NIM bge-m3 (nv-embedqa-e5-v5) yazdın biz local model kullanıyoruz vps te"
- **Etkilenen sayfalar:** [[data-pipelines]] (Pipeline #2 + provider envanteri + status tablosu), [[pipeline-performance-baseline]] (ADIM 2 + ADIM 6 diagramları + per-request metrik tablosu + latency tablosu), [[llm-provider-strategy]] (TL;DR + tier mapping satırı)
- **Yeni:** 0
- **Güncellendi:** 3
- **Hatanın özü:** Yeni yazdığım data-pipelines.md'de Pipeline #2'yi `.env.example` default'a (`USE_LOCAL_EMBEDDING=false`) bakarak "NIM aktif" şeklinde belgeledim. **Production VPS `.env` farklı:** `USE_LOCAL_EMBEDDING=true`. SSH ile doğrulandı.
- **Production telemetry (provider_call_logs son 7 gün, doğrulama):**
  - `local_bge_m3` 422 çağrı, son: **2026-05-07 23:15** (TODAY) ✅ aktif
  - `nim_bge_m3` 4,646 çağrı, son: 2026-05-06 18:46 (1.5 gün önce, migration öncesi)
  - Migration tamamlandı: PR #350 (2026-05-06)
- **Düzeltilenler:**
  - [[data-pipelines]] §1️⃣ Pipeline 2 (Embedding) → "NIM bge-m3" → "Local BAAI/bge-m3 (VPS CPU)"
  - [[data-pipelines]] kuş bakışı diyagram → "NIM bge-m3" → "LOCAL bge-m3 (VPS CPU)"
  - [[data-pipelines]] provider envanteri tablosu → Local AKTİF, NIM FALLBACK ayrımı eklendi
  - [[data-pipelines]] pipeline durumu tablosu → "Embedding ✅ Production (LOCAL post-#345 migration)"
  - [[pipeline-performance-baseline]] ADIM 2 + ADIM 6 diyagramları → local primary olarak işaretlendi
  - [[pipeline-performance-baseline]] baseline metric tablosu → "NIM embedding call/req" → "Embedding call/req (local-primary)"
  - [[pipeline-performance-baseline]] latency tablosu → embedding 0.05-0.1s local CPU
  - [[llm-provider-strategy]] TL;DR → embedding "[[nim-bge-m3]]" → "local BAAI/bge-m3 ([[local-bge-m3]])"
  - [[llm-provider-strategy]] tier mapping satırı → "Embedding tüm tier'larda [[local-bge-m3]]" + NIM fallback notu
- **Zaten doğru olanlar (kontrol edildi, dokunulmadı):**
  - [[provider-abstraction]] adapter listesi → `LocalBgeM3Provider ✅ AKTİF (production primary)` zaten doğru, #350 referanslı
  - [[nim-bge-m3]] entity → "legacy embedding provider, fallback only" zaten doğru, [[local-bge-m3]] cross-link var
- **Kök neden:** Yeni sayfalar (data-pipelines, pipeline-performance-baseline) yazılırken `.env.example` default'una göre belgelendim — production `.env`'i SSH ile doğrulamadım. Önceki düzeltme turlarında provider-abstraction + nim-bge-m3 + local-bge-m3 doğru güncellendiği için tutarsızlık yeni sayfalarda kaldı.
- **Ders:** Pipeline veya provider durumu yazarken her zaman SSH ile production `.env` + `provider_call_logs` query'siyle doğrula. `.env.example` sadece example — gerçeği yansıtmaz.

## [2026-05-08] update | data-pipelines.md §4 Kural 8 — permanent fail edge case'leri (#427 dersi)

- **Kaynak/Tetikleyici:** Kullanıcı isteği — admin panel'de [/admin/media](https://nodrat.com/admin/media) "Başarısız: 7" gördü; "görsel işlemeyle ilgili kuralları boru hattı wikisine yazar mısın" dedi. [#424](https://github.com/selmanays/nodrat/issues/424) sonrası kalan 7 failed image teşhisi → [#427](https://github.com/selmanays/nodrat/issues/427) + [#428](https://github.com/selmanays/nodrat/pull/428) fix → wiki güncellemesi.
- **Etkilenen sayfalar:** [[data-pipelines]] (Pipeline 4 §Kural 3 güncellendi + yeni §Kural 8 eklendi)
- **Yeni:** 0
- **Güncellendi:** 1 sayfa (60+ satır eklendi)
- **Kural 3 değişikliği:**
  - Önceki tablo: "ImageDownloadError 4xx/5xx → transient"
  - Yeni tablo: "5xx + diğer 4xx (404/410 hariç) → transient", "404/410 (Gone) → permanent". Permanent satıra magic bytes sniff fail eklendi.
- **Yeni Kural 8 — Permanent fail edge case'leri (3 alt madde):**
  - **A) HTTP 404/410 → permanent:** Yayıncı silmiş URL'ler. Eski 4× retry × 6 dispatch × 72h = 864 wasted req → yeni 1 HEAD req × 72h = 72 req per ölü URL. 12× verimlilik kazancı.
  - **B) Boş Content-Type → magic bytes fallback:** WhatsApp/Manifold/yanlış konfigüre S3 vakaları. `_sniff_image_mime()` ilk 16 byte'tan JPEG/PNG/GIF/WebP/AVIF detect (whitelist'e göre). RIFF→WEBP brand check WAV/AVI'yi dışlıyor.
  - **C) Duplicate dispatch (design notu, bug değil):** #424 26h kırık backfill ~93k task biriktirmişti. Drenaj sırasında aynı image_id 4-6× dispatch normal. `status='failed'` için idempotency yok ama HEAD 404 fix'i ile maliyet düşük (0.13s/dispatch). Açık follow-up: retry_count veya 'gone' status (data-model değişikliği, MVP-1.x dışı).
- **Production verify (deploy sonrası 13:51 UTC):** [#428](https://github.com/selmanays/nodrat/pull/428) merged, manuel deploy + `celery call retry_failed`. Sonuç:
  - WhatsApp image 57ca9e40 → processed (caption: "BBC News logosu", magic bytes JPEG detect, NIM VLM 22.4s)
  - 6 haberturk → 'rejected, HTTP 404 (gone) at HEAD' her biri 0.13-0.58s (autoretry yok, GET'e gitmiyor)
  - DB final: 1945 processed / 6 failed / 1951 total (admin panel 7 → 6 başarısız)
- **Branch:** `wiki/427-image-permanent-fail-patterns`
- **Cross-link:** [#424](https://github.com/selmanays/nodrat/issues/424) [#425](https://github.com/selmanays/nodrat/pull/425) [#427](https://github.com/selmanays/nodrat/issues/427) [#428](https://github.com/selmanays/nodrat/pull/428)
- **Ders:** 7 failed image'ın 6'sı production sorun değil — yayıncı haber silmiş, fail beklenen. 1'i (WhatsApp) gerçek bug — Content-Type missing CDN fallback eksikti. Admin panel'deki "Başarısız" sayısının her zaman 0'a düşmesini beklemek yanlış; freshness window dolu (≤72h) sürece kaynak ölü URL'ler stage'inde failed olabilir.

## [2026-05-08] update | data-pipelines.md §4 image VLM kuyruk discipline + freshness kuralları (#424 ders)

- **Kaynak/Tetikleyici:** Kullanıcı isteği — "görsel işlemeyle ilgili kuralları boru hattı wikisine yazar mısın". [#424](https://github.com/selmanays/nodrat/issues/424) regression sonrası kuyruk davranışını dokümante etmek.
- **Etkilenen sayfalar:** [[data-pipelines]] (Pipeline 4 genişletildi)
- **Yeni:** 0 (mevcut sayfaya bölüm eklendi)
- **Güncellendi:** 1
- **Eklenen 7 kural:**
  1. **Backfill** (5 dk beat, batch=300, idempotent — sadece status='pending')
  2. **Retry-failed** (saatlik beat, batch=100, max_age_hours=72 freshness window)
  3. **Transient vs permanent** sınıflandırma tablosu — `_TRANSIENT_EXCEPTIONS` listesi + bug sentinel pattern (autoretry tetiklemeyen `TypeError/AttributeError/KeyError` → stuck pending)
  4. **Cost tracker contract** — `tracker.record()` valid kwargs (input_tokens, output_tokens, cached_tokens, model, cost_usd); yanlış kwarg → kural 3 sentinel (#424 örneği)
  5. **Runtime kill-switch** — 4 admin setting tablosu (media.processing_enabled / vlm_model / max_image_bytes / download_timeout)
  6. **Worker concurrency=2** (NIM 40 RPM güvenli pay, ~4-5 image/dk pratik throughput)
  7. **Drenaj sağlığı izleme** — 3 SQL query + worker log grep + alarm tetikleyicisi
- **Branch:** `wiki/image-vlm-pipeline-rules`
- **Bağlam:** [#424](https://github.com/selmanays/nodrat/issues/424) ile öğrendiğimiz: TypeError gibi unexpected exception'lar autoretry listesinde olmadığı için DB status değişmiyor → backfill her 5 dk yeniden dispatch ediyor → kuyruk donar. Bu pattern'i wiki'de "Bug sentinel" olarak adlandırdık. Production semptom: pending count düşmüyor, worker log'da TypeError pattern'i.
- **Cross-link:** Pipeline 4 → R-OPS-05 (storage runaway, çözüldü) + R-FIN-01 (cost runaway, kural 5+6 ile mitigate) + #425 (regression örneği).
- **Ders:** Provider abstraction ve runtime config dokümante etmek yetmez; davranış sözleşmeleri (idempotency, retry classification, kill-switch) ayrı bir bölüm hak ediyor — yoksa "kuyruk neden donmuş?" sorusuna kod okuyarak cevap aramak gerek.

## [2026-05-08] removal | NIM bge-m3 historical iz temizliği — DB rows + integration test + comment'ler (#422)

- **Kaynak/Tetikleyici:** Kullanıcı isteği — "yani şu an nim'deki bge-m3 modeli tamamen sistemden çıkartıldı değil mi? o zaman özet sayfasındaki grafikte de bu model görünmesin geçmiş istatistik verilerini de silmen lazım hiçbir şeyde izi olmasın". PR #421 follow-up.
- **Yeni:** 0
- **Güncellendi:** 8 wiki + 9 kod dosyası
- **Silinen:** `apps/api/tests/integration/test_nim_embedding.py` (88 satır — PR #421'de kaçırılmıştı, NimEmbeddingProvider import ediyordu)
- **Akış:**
  - **Kod cleanup (9 dosya):** test_nim_embedding.py SİL; test_cost_tracker.py + test_provider_timeout #420 referansları sade; cost_tracker docstring + local_embedding + registry + provider_log + embedding + maintenance comment sadeleştirildi
  - **DB cleanup:** `provider_call_logs` 4,646 satır SİLİNDİ (`WHERE provider='nim_bge_m3'`). Total cost: $0 (NIM free tier'dı), tarih: 2026-05-01 → 2026-05-06. Admin dashboard graph'larından otomatik kaybolur (provider-bazlı GROUP BY).
  - **Redis:** SCAN `*nim_bge*` + `*nv-embedqa*` → 0 key (zaten temiz)
  - **Wiki (8 active sayfa):** provider-abstraction, local-bge-m3, llm-provider-strategy, pipeline-performance-baseline, data-pipelines, mvp-roadmap, architecture-md, index — hepsinden NIM nv-embedqa-e5-v5 / NIM yedek / nim_bge_m3 referansları temizlendi
- **Audit sonucu:** `grep -r "nim_bge_m3|nv-embedqa-e5-v5|NimEmbeddingProvider"` aktif wiki + kod = **0 sonuç**.
- **Branch:** `chore/422-nim-historical-trace-cleanup`
- **Sebep:** Kullanıcı admin dashboard'da NIM bge-m3 graphını gördü; aktif kod kaldırıldı ama DB'deki historical telemetry hâlâ graph'ı çiziyordu. PR #421'de kalan integration test dosyası da kaçırılmıştı — CI'da import error verecekti.
- **Ders:** Removal işi sadece kod silmek değil; audit/logs/cache/historical data'yı da silmek demek. Source-of-truth tek olmalı, historical artifacts production verilerini bozmamalı.
